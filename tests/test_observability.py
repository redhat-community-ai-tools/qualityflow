#!/usr/bin/env python3
"""Observability regressions (wave W9a): OBS-01-F2, OBS-01-F3 (remainder), DATA-01-F15.

OBS-01-F2   _setup_logging() configured only the app's own logger, so under the
            default QF_LOG_FORMAT=json 221 of 223 captured lines were plain text
            (every uvicorn access/error line). Access lines also carried the raw
            path+query. And _run_phase_background ran in a detached thread
            outside RequestIDMiddleware's contextvar scope, so a failed run's
            ERROR line had no request_id to correlate it back to the click.
OBS-01-F3   /metrics had no counter for background-worker failures, peer-rollup
            fan-out failures or coverage-upload failures (the run/git-sync/disk
            families landed in W7, see tests/test_ops_metrics.py).
DATA-01-F15 mtime-derived phase durations were dropped only when non-positive —
            no upper clamp — so a shifted mtime put stp_avg_hours: 5130 (7
            months) on the manager dashboard.

Same conventions as tests/test_state_safety.py: QF_DEV/QF_OUTPUTS_DIR set
before `import ui`, ui is a module-level singleton so globals are monkeypatched
per test, and the module-level TestClient is NOT entered as a context manager.
The `env` / `_seed_ticket` helpers are reused from tests/test_state_safety.py.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_observability.py -q
"""
import json
import logging
import os
import sys
import threading
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))  # replaced per-test by the fixture
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import
from fastapi.testclient import TestClient  # noqa: E402

from test_state_safety import HDR, env, _seed_ticket  # noqa: E402,F401 — `env` is a fixture

client = TestClient(ui.app)
# Separate client for the paths that let a non-HTTP exception escape the route:
# the default TestClient re-raises it instead of returning the 500 a real server would.
lenient = TestClient(ui.app, raise_server_exceptions=False)


def _boom(*_a, **_k):
    raise RuntimeError("exploded")


def _metrics_text() -> str:
    r = client.get("/metrics")
    assert r.status_code == 200
    return r.text


@pytest.fixture
def log_format(capsys):
    """Re-run _setup_logging() in the requested format and restore the previous
    handlers afterwards — it mutates process-wide logging state."""
    saved = {name: (lg.handlers[:], lg.filters[:], lg.level, lg.propagate)
             for name in ui._MANAGED_LOGGERS if (lg := logging.getLogger(name))}

    def _apply(fmt: str):
        os.environ["QF_LOG_FORMAT"] = fmt
        ui._setup_logging()
        capsys.readouterr()  # drop anything emitted during setup

    yield _apply

    os.environ["QF_LOG_FORMAT"] = "json"
    for name, (handlers, filters, level, propagate) in saved.items():
        lg = logging.getLogger(name)
        lg.handlers[:] = handlers
        lg.filters[:] = filters
        lg.setLevel(level)
        lg.propagate = propagate


def _access(path: str, status: int = 200):
    """Emit one line in uvicorn's real access-log record shape."""
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "192.0.2.10", "GET", path, "1.1", status)


def _json_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().err.splitlines()
            if line.startswith("{")]


# ---------------------------------------------------------------------------
# A — OBS-01-F2: every logger emits the configured format, not just ours
# ---------------------------------------------------------------------------

def test_uvicorn_access_and_error_logs_are_json(log_format, capsys):
    log_format("json")
    # A real 404 through the app — the request path that produces an access line.
    assert client.get("/definitely-not-a-route").status_code == 404
    _access("/definitely-not-a-route", 404)
    logging.getLogger("uvicorn.error").warning("uvicorn said something")

    lines = _json_lines(capsys)
    assert {l["logger"] for l in lines} == {"uvicorn.access", "uvicorn.error"}
    assert all(l["level"] and l["timestamp"] and l["message"] for l in lines)


def test_app_logger_is_still_json(log_format, capsys):
    log_format("json")
    ui.logger.info("app line")
    assert [l["logger"] for l in _json_lines(capsys)] == ["qualityflow.dashboard"]


def test_text_format_is_honoured_for_uvicorn_loggers_too(log_format, capsys):
    log_format("text")
    _access("/api/pipelines", 200)
    line = capsys.readouterr().err.strip()
    assert line and not line.startswith("{")
    assert "uvicorn.access" in line and "/api/pipelines" in line


def test_access_log_strips_the_query_string(log_format, capsys):
    log_format("json")
    _access("/api/pipelines?token=abc&next=/x", 200)
    raw = capsys.readouterr().err
    assert "token=abc" not in raw
    assert "/api/pipelines" in json.loads(raw.strip())["message"]


def test_query_stripping_survives_a_reattached_handler(log_format, capsys):
    """The filter lives on the logger, not a handler, so a handler added later
    (uvicorn's own, a test harness's) still gets the scrubbed record."""
    log_format("json")
    seen: list[str] = []
    probe = logging.Handler()
    probe.emit = lambda record: seen.append(record.getMessage())  # type: ignore[method-assign]
    access = logging.getLogger("uvicorn.access")
    access.addHandler(probe)
    try:
        _access("/api/coverage/upload?token=supersecret", 200)
    finally:
        access.removeHandler(probe)
    capsys.readouterr()
    assert seen and "supersecret" not in seen[0] and "/api/coverage/upload" in seen[0]


def test_non_path_arguments_are_left_alone(log_format, capsys):
    log_format("json")
    logging.getLogger("uvicorn.access").info("query=%s", "a?b")
    assert json.loads(capsys.readouterr().err.strip())["message"] == "query=a?b"


# ---------------------------------------------------------------------------
# B — OBS-01-F2: the background thread carries the triggering request's id
# ---------------------------------------------------------------------------

def test_background_failure_log_carries_the_request_id(env, log_format, monkeypatch, capsys):
    import pipeline_runner

    log_format("json")
    monkeypatch.setattr(pipeline_runner, "run_phase", _boom)
    monkeypatch.setattr(ui, "_running_tasks", {})

    # A real thread: contextvars start empty there, which is exactly the bug.
    t = threading.Thread(target=ui._run_phase_background, args=("OBS-1", "stp", "", "reqid-abc123"))
    t.start()
    t.join(10)
    assert not t.is_alive()

    errors = [l for l in _json_lines(capsys) if l["level"] == "ERROR"]
    assert errors, "expected an ERROR line from the failed run"
    assert all(l.get("request_id") == "reqid-abc123" for l in errors)


def test_run_route_hands_its_request_id_to_the_thread(env, monkeypatch):
    """Pins the spawn site: without this the propagation above is never reached."""
    _seed_ticket(env, "OBS-2", {"stp": {"status": "completed", "output": "stp/x.md"}})
    captured: list[dict] = []
    done = threading.Event()

    def _record(*_args, **kwargs):
        captured.append(kwargs)
        done.set()

    monkeypatch.setattr(ui, "_run_phase_background", _record)
    monkeypatch.setattr(ui, "_running_tasks", {})
    monkeypatch.setattr(ui, "_claude_available", lambda: True)

    r = client.post("/api/pipelines/OBS-2/run/std", headers={**HDR, "X-Request-ID": "click-42"})
    assert r.status_code == 200, r.text
    assert done.wait(10)
    assert captured[0]["request_id"] == "click-42"


# ---------------------------------------------------------------------------
# C — OBS-01-F3: the three remaining failure-mode counters
# ---------------------------------------------------------------------------

def test_peer_rollup_failure_increments_the_counter(monkeypatch):
    ui._peer_rollup_failures.clear()
    monkeypatch.setattr(ui, "_local_rollup", lambda: {"cluster": "local", "projects": []})
    monkeypatch.setattr(ui, "_get_peers", lambda: [{"label": "peer-a", "url": "http://peer.invalid"}])
    monkeypatch.setattr(ui, "_fetch_peer_rollup", _boom)

    body = client.get("/api/rollup").json()
    assert any(c.get("error") for c in body["clusters"]), "peer error should stay isolated"
    assert 'qf_peer_rollup_failures_total{peer="peer-a"} 1' in _metrics_text()


def test_coverage_collection_worker_crash_increments_the_counter(monkeypatch):
    ui._background_task_failures.clear()
    monkeypatch.setitem(ui._collection_tasks, "t-crash", {"task_id": "t-crash", "status": "pending"})
    monkeypatch.setattr(ui, "_collection_worker", _boom)

    ui._collection_worker_thread("t-crash", "acme", "widget", {})

    assert ui._collection_tasks["t-crash"]["status"] == "failed"
    assert "qf_background_task_failures_total 1" in _metrics_text()


def test_collection_worker_failing_without_raising_still_counts(monkeypatch):
    """The worker swallows most of its own errors and only marks the task
    failed — counting escaped exceptions alone would miss nearly every one."""
    ui._background_task_failures.clear()
    monkeypatch.setitem(ui._collection_tasks, "t-soft", {"task_id": "t-soft", "status": "pending"})
    monkeypatch.setattr(ui, "_collection_worker",
                        lambda tid, *_a: ui._collection_tasks[tid].update(status="failed"))

    ui._collection_worker_thread("t-soft", "acme", "widget", {})

    assert "qf_background_task_failures_total 1" in _metrics_text()


def test_successful_collection_does_not_count(monkeypatch):
    ui._background_task_failures.clear()
    monkeypatch.setitem(ui._collection_tasks, "t-ok", {"task_id": "t-ok", "status": "pending"})
    monkeypatch.setattr(ui, "_collection_worker",
                        lambda tid, *_a: ui._collection_tasks[tid].update(status="completed"))

    ui._collection_worker_thread("t-ok", "acme", "widget", {})

    assert "qf_background_task_failures_total 0" in _metrics_text()


def test_rejected_coverage_upload_increments_the_counter(env):
    ui._coverage_upload_failures.clear()
    r = client.post("/api/coverage/upload?org=acme&repo=widget&commit=not-a-sha",
                    headers=HDR, content="mode: set\n")
    assert r.status_code == 400
    assert 'qf_coverage_upload_failures_total{project="acme/widget"} 1' in _metrics_text()


def test_coverage_upload_write_failure_increments_the_counter(env, monkeypatch):
    ui._coverage_upload_failures.clear()
    monkeypatch.setattr(ui, "_store_coverage", _boom)
    r = lenient.post("/api/coverage/upload?org=acme&repo=widget&commit=abc1234",
                     headers=HDR, content="mode: set\ngithub.com/a/b/c.go:1.1,2.2 1 1\n")
    assert r.status_code == 500
    assert 'qf_coverage_upload_failures_total{project="acme/widget"} 1' in _metrics_text()


def test_all_three_families_are_declared_even_at_zero():
    body = _metrics_text()
    for name in ("qf_background_task_failures_total",
                 "qf_peer_rollup_failures_total",
                 "qf_coverage_upload_failures_total"):
        assert f"# TYPE {name} counter" in body


# ---------------------------------------------------------------------------
# D — DATA-01-F15: mtime-derived durations are bounded above, not just below
# ---------------------------------------------------------------------------

def _seed_with_created(out: Path, jira_id: str, created: str) -> None:
    _seed_ticket(out, jira_id, {"stp": {"status": "completed", "output": "stp/x.md"}})
    state = out / jira_id / "state" / "pipeline_state.yaml"
    data = yaml.safe_load(state.read_text())
    data["created"] = created  # mtimes are "now", so this sets the inferred duration
    state.write_text(yaml.safe_dump(data, sort_keys=False))


def test_absurd_inferred_duration_is_dropped(env):
    """The measured defect: created predates the artifact mtime by years."""
    _seed_with_created(env, "DUR-1", "2020-01-01T00:00:00+00:00")
    durations = client.get("/api/metrics/example").json()["value"]["phase_durations"]
    assert durations["stp_avg_hours"] is None


def test_plausible_inferred_duration_is_kept(env):
    from datetime import datetime, timedelta, timezone

    created = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    _seed_with_created(env, "DUR-2", created)
    stp_avg = client.get("/api/metrics/example").json()["value"]["phase_durations"]["stp_avg_hours"]
    assert stp_avg is not None and 5.0 < stp_avg < 7.0


def test_absurd_ticket_does_not_poison_the_average(env):
    from datetime import datetime, timedelta, timezone

    _seed_with_created(env, "DUR-3", (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat())
    _seed_with_created(env, "DUR-4", "2019-06-01T00:00:00+00:00")
    stp_avg = client.get("/api/metrics/example").json()["value"]["phase_durations"]["stp_avg_hours"]
    assert stp_avg is not None and stp_avg < ui._INFERRED_DURATION_CEILING_HOURS
    assert 3.0 < stp_avg < 5.0  # the sane ticket alone, not an average with 60000h


# ---------------------------------------------------------------------------
# OBS-01.5 (wave W10) — /readyz probed only OUTPUTS, so a failed/delayed config
# PVC mount left the pod Ready while /api/projects silently returned [].
# ---------------------------------------------------------------------------

def test_readyz_reports_both_mounts(env):
    assert client.get("/readyz").json() == {
        "status": "ready", "outputs_accessible": True,
        "outputs_writable": True, "config_accessible": True,
    }


def test_readyz_fails_when_config_is_missing(env, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "CONFIG", tmp_path / "NO_SUCH_CONFIG_DIR")
    resp = client.get("/readyz")
    assert resp.status_code == 503, resp.text
    # ...while the pod is still alive — /healthz is a liveness probe.
    assert client.get("/healthz").status_code == 200


def test_readyz_fails_when_config_is_a_file(env, monkeypatch, tmp_path):
    """is_dir() alone: a broken mount can leave a file (or a dangling link)."""
    bad = tmp_path / "config-not-a-dir"
    bad.write_text("")
    monkeypatch.setattr(ui, "CONFIG", bad)
    assert client.get("/readyz").status_code == 503


# ---------------------------------------------------------------------------
# OBS-01.9 (wave W11b) — the boot banner carried commit/pipelines/outputs/claude
# only, so `oc logs` right after a deploy could not confirm auth, runner, peers
# or which config dir the pod actually mounted.
# ---------------------------------------------------------------------------

def test_startup_banner_reports_the_effective_config(env, monkeypatch):
    monkeypatch.setattr(ui, "_start_git_sync_loop", lambda: None)
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())
    monkeypatch.setattr(ui, "_OIDC_ENABLED", True)
    monkeypatch.setattr(ui, "_get_peers", lambda: [
        {"label": "a", "url": "https://svc:s3cr3t@a.example"},
        {"label": "b", "url": "https://b.example"},
    ])

    recorded: list[str] = []
    monkeypatch.setattr(ui.logger, "info",
                        lambda msg, *a, **_k: recorded.append(msg % a if a else msg))

    with TestClient(ui.app):
        pass

    banner = [line for line in recorded if line.startswith("QualityFlow Dashboard ready")]
    assert len(banner) == 1, recorded
    for field in ("auth=oidc", "runner=yes", "peers=2", f"config={ui.CONFIG}"):
        assert field in banner[0], banner[0]
    assert "s3cr3t" not in banner[0], "peer credentials must never reach the log"


def test_startup_banner_says_auth_none_without_oidc(env, monkeypatch):
    monkeypatch.setattr(ui, "_start_git_sync_loop", lambda: None)
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())
    monkeypatch.setattr(ui, "_OIDC_ENABLED", False)
    monkeypatch.setattr(ui, "_get_peers", list)

    recorded: list[str] = []
    monkeypatch.setattr(ui.logger, "info",
                        lambda msg, *a, **_k: recorded.append(msg % a if a else msg))

    with TestClient(ui.app):
        pass

    banner = next(line for line in recorded if line.startswith("QualityFlow Dashboard ready"))
    assert "auth=none" in banner and "peers=0" in banner
