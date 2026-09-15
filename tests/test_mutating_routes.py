#!/usr/bin/env python3
"""TEST-01-F06: mutating routes nothing exercised end-to-end.

Before this file the whole suite's only POST was /api/beacon. Everything that
writes — the phase state machine, the approval gate, the toggles PUT, startup
reconciliation, the git-sync copy — was reachable only through the running
dashboard, so any of them could break with a green suite. The tar-upload caps
and the reset path are already covered in tests/test_state_safety.py (W4) and
the unauthenticated-write matrix in tests/test_authz_matrix.py (W1); this file
deliberately does not repeat either.

`pipeline_runner.run_phase` shells out to the `claude` CLI and _git_sync talks
to a real remote — both are monkeypatched in every test here. ui.py auto-loads
the repo .env at import, so an un-patched call would spend a real token.

Same conventions as tests/test_state_safety.py: QF_DEV/QF_OUTPUTS_DIR set before
`import ui`, ui is a module-level singleton so globals are monkeypatched per
test, and the module-level TestClient is NOT entered as a context manager.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_mutating_routes.py -q
"""
import asyncio
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

client = TestClient(ui.app)

KEY = "w8testkey"
HDR = {"X-API-Key": KEY}
# An auth-on server refuses a run without the member's own Jira + GitHub identity.
MEMBER = {"jira_username": "member@example.com", "jira_token": "member-jira-tok",
          "github_token": "member-gh-tok"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh tmp outputs/ + config/ per test. Mirrors test_state_safety.py::env,
    plus the two globals the run route reads (_running_tasks, _claude_available)."""
    out = tmp_path / "outputs"
    out.mkdir()
    cfg = tmp_path / "config"
    (cfg / "projects").mkdir(parents=True)
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "CONFIG", cfg)
    monkeypatch.setattr(ui, "COVERAGE_DIR", out / "coverage")
    monkeypatch.setattr(ui, "_TEST_COVERAGE_DIR", out / "coverage" / "_tests")
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_routing_cache", (0.0, {}))
    monkeypatch.setattr(ui, "_USAGE_LOG", out / "_usage" / "dashboard_usage.jsonl")
    monkeypatch.setattr(ui, "_API_KEY", KEY)
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    monkeypatch.setattr(ui, "_slack_pipeline_event", lambda *a, **k: None)
    monkeypatch.setattr(ui, "_get_approval_gates", lambda _pid: ["stp", "std"])
    monkeypatch.setattr(ui, "_infer_project", lambda _jid: "example")
    monkeypatch.setattr(ui, "_running_tasks", {})
    monkeypatch.setattr(ui, "_claude_available", lambda: True)
    return out


def _seed_ticket(out: Path, jira_id: str, phases: dict) -> Path:
    """A ticket with real artifacts and a real pipeline_state.yaml.
    Same shape as tests/test_state_safety.py::_seed_ticket."""
    (out / jira_id / "stp").mkdir(parents=True, exist_ok=True)
    (out / jira_id / "stp" / f"{jira_id}_test_plan.md").write_text("# plan\n")
    (out / jira_id / "std").mkdir(parents=True, exist_ok=True)
    (out / jira_id / "std" / f"{jira_id}_test_description.yaml").write_text("scenarios: []\n")
    state = out / jira_id / "state" / "pipeline_state.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(yaml.safe_dump({"ticket_id": jira_id, "project_id": "example",
                                     "phases": phases}, sort_keys=False))
    return state


def _phase(state_file: Path, phase: str) -> dict:
    return yaml.safe_load(state_file.read_text())["phases"][phase]


def _failures_total(phase: str) -> int:
    r = client.get("/metrics")
    assert r.status_code == 200
    prefix = f'qf_pipeline_run_failures_total{{phase="{phase}"}} '
    for line in r.text.splitlines():
        if line.startswith(prefix):
            return int(line[len(prefix):])
    return 0


@pytest.fixture
def fake_runner(monkeypatch):
    """Stand in for pipeline_runner.run_phase (which shells out to `claude`/
    `agent`). `calls` records every invocation; set `.result` / `.raises` per
    test. Signature matches frozen decision 7:
    run_phase(model, jira_id, phase, creds=None, runtime="claude", isolate=False)."""
    import pipeline_runner

    class _Runner:
        calls: list[tuple] = []
        result: dict = {"output": "done", "verdict": "APPROVED"}
        raises: Exception | None = None
        last_creds: dict | None = None
        last_runtime: str | None = None
        last_isolate: bool | None = None

        def __call__(self, model, jira_id, phase, creds=None, runtime="claude", isolate=False):
            self.calls.append((model, jira_id, phase, runtime))
            self.last_creds = creds
            self.last_runtime = runtime
            self.last_isolate = isolate
            if self.raises:
                raise self.raises
            return self.result

    runner = _Runner()
    runner.calls = []
    monkeypatch.setattr(pipeline_runner, "run_phase", runner)
    return runner


# ---------------------------------------------------------------------------
# A — POST /api/pipelines/{jira_id}/run/{phase}: the phase state machine
# ---------------------------------------------------------------------------

def test_run_route_marks_in_progress_and_schedules_the_worker(env, monkeypatch):
    """pending -> in_progress happens in the request, before the worker runs:
    the button must not look idle while a `claude` subprocess is spawning."""
    jid = "RUN-1"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    scheduled: list[tuple] = []
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: scheduled.append(a))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=MEMBER)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "started", "phase": "stp", "jira_id": jid}
    assert _phase(state_file, "stp")["status"] == "in_progress"
    assert "started_ts" in _phase(state_file, "stp")
    assert ui._running_tasks[f"{jid}/stp"]["status"] == "running"
    for _ in range(200):  # the worker runs on a daemon thread
        if scheduled:
            break
        threading.Event().wait(0.01)
    assert scheduled == [(jid, "stp", "")]


def test_worker_completes_the_phase_when_the_deliverable_exists(env, fake_runner):
    """in_progress -> completed, with the runner's verdict persisted."""
    jid = "RUN-2"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})

    ui._run_phase_background(jid, "stp")

    assert fake_runner.calls == [(ui._RUNNER_MODEL_DEFAULT, jid, "stp", "claude")]
    ph = _phase(state_file, "stp")
    assert ph["status"] == "completed"
    assert ph["verdict"] == "APPROVED"
    assert ui._running_tasks[f"{jid}/stp"]["status"] == "completed"


def test_exit_zero_without_a_deliverable_is_blocked_not_completed(env, fake_runner):
    """The gate/toggle/prereq path: the CLI declines and still exits 0, so the
    phase must not go green. This is what an unapproved gate looks like from
    here — the run route itself does not consult approvals (see notes)."""
    jid = "RUN-3"
    # No std artifact on disk — the deliverable check fails.
    state_file = _seed_ticket(env, jid, {"std": {"status": "in_progress"}})
    (env / jid / "std" / f"{jid}_test_description.yaml").unlink()

    ui._run_phase_background(jid, "std")

    assert _phase(state_file, "std")["status"] == "blocked"
    assert ui._running_tasks[f"{jid}/std"]["status"] == "blocked"


def test_runner_failure_marks_failed_and_increments_the_counter(env, fake_runner):
    jid = "RUN-4"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    fake_runner.raises = RuntimeError("claude exited 1")
    before = _failures_total("stp")

    ui._run_phase_background(jid, "stp")

    ph = _phase(state_file, "stp")
    assert ph["status"] == "failed"
    assert "claude exited 1" in ph["error"]
    assert ui._running_tasks[f"{jid}/stp"]["status"] == "failed"
    assert _failures_total("stp") == before + 1


def test_second_run_while_one_is_in_flight_does_not_spawn_a_second_worker(env, monkeypatch):
    """Pinned as-is: the route answers 200 {"status": "already_running"}, not a
    409. What matters is that no second `claude` subprocess is started."""
    jid = "RUN-5"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    scheduled: list[tuple] = []
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: scheduled.append(a))
    ui._running_tasks[f"{jid}/stp"] = {"status": "running"}

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=MEMBER)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "already_running"
    assert scheduled == []


def test_another_phase_of_a_running_ticket_is_409_naming_the_running_phase(env, monkeypatch):
    """Every phase of a ticket writes one outputs/{id}/ tree and one
    pipeline_state.yaml — a second member's std must not start mid-stp."""
    jid = "ISO-1"
    _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: pytest.fail("worker must not run"))
    ui._running_tasks[f"{jid}/stp"] = {"status": "running"}
    ui._running_tasks[f"{jid}0/std"] = {"status": "running"}  # ISO-10 is not ISO-1

    r = client.post(f"/api/pipelines/{jid}/run/std", headers=HDR, json=MEMBER)
    assert r.status_code == 409, r.text
    assert "stp run in progress" in r.json()["detail"]


@pytest.mark.parametrize("method,path", [
    ("post", "/api/pipelines/ISO-2/reset/std"),
    ("delete", "/api/pipelines/ISO-2"),
    ("delete", "/api/outputs/ISO-2"),
    ("post", "/api/outputs/ISO-2"),
])
def test_reset_delete_and_upload_are_409_while_the_ticket_runs(env, method, path):
    _seed_ticket(env, "ISO-2", {"stp": {"status": "in_progress"}})
    ui._running_tasks["ISO-2/stp"] = {"status": "running"}

    r = getattr(client, method)(path, headers={**HDR, "Content-Type": "application/json"},
                                **({"content": b'{"path": "stp/ISO-2/x.md", "content": "x"}'} if method == "post" else {}))
    assert r.status_code == 409, r.text
    assert (env / "ISO-2" / "stp" / "ISO-2_test_plan.md").exists()  # nothing archived


def test_run_cap_returns_429_once_the_dashboard_is_full(env, monkeypatch):
    jid = "ISO-3"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: pytest.fail("worker must not run"))
    monkeypatch.setattr(ui, "_MAX_CONCURRENT_RUNS", 2)
    ui._running_tasks.update({"OTHER-1/stp": {"status": "running"}, "OTHER-2/std": {"status": "running"},
                              "OTHER-3/stp": {"status": "completed", "_finished": 0}})

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=MEMBER)
    assert r.status_code == 429, r.text
    assert "2 runs already in progress" in r.json()["detail"]
    assert f"{jid}/stp" not in ui._running_tasks


@pytest.mark.parametrize("blank,field", [
    ({"jira_username": ""}, "Jira"), ({"jira_token": " "}, "Jira"), ({"github_token": ""}, "GitHub")])
def test_blank_member_jira_or_github_is_400_on_a_multi_user_server(env, monkeypatch, blank, field):
    jid = "ISO-4"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: pytest.fail("worker must not run"))

    r = client.post(f"/api/pipelines/{jid}/run/std", headers=HDR, json={**MEMBER, **blank})
    assert r.status_code == 400, r.text
    assert f"Paste your {field}" in r.json()["detail"] and "in Settings" in r.json()["detail"]


def test_sso_only_server_is_isolated_too(env, monkeypatch, fake_runner):
    """P1-3: the helm chart supports OIDC with no API key. That server is just as
    shared, so the 400s and the runner's strip must key off SSO as well."""
    jid = "ISO-6"
    _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    monkeypatch.setattr(ui, "_API_KEY", "")
    monkeypatch.setattr(ui, "_OIDC_ENABLED", True)
    real_worker = ui._run_phase_background
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: pytest.fail("worker must not run"))

    r = client.post(f"/api/pipelines/{jid}/run/std", json={})
    assert r.status_code == 400 and "Paste your Jira" in r.json()["detail"], r.text

    real_worker(jid, "stp", creds=MEMBER)
    assert fake_runner.last_isolate is True


def test_laptop_dashboard_run_is_not_isolated(env, monkeypatch, fake_runner):
    jid = "ISO-7"
    _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    monkeypatch.setattr(ui, "_API_KEY", "")
    monkeypatch.setattr(ui, "_OIDC_ENABLED", False)
    ui._run_phase_background(jid, "stp", creds={})
    assert fake_runner.last_isolate is False


def test_a_run_cannot_start_while_a_reset_holds_the_ticket(env, monkeypatch):
    """TOCTOU: the reset's 409 check and its claim share one lock acquisition,
    and the claim lasts until the reset finishes."""
    jid = "ISO-8"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: pytest.fail("worker must not run"))
    seen = {}
    real_archive = ui._archive_to_previous

    def archive_while_someone_clicks_run(target, ts):
        seen["run"] = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=MEMBER)
        return real_archive(target, ts)

    monkeypatch.setattr(ui, "_archive_to_previous", archive_while_someone_clicks_run)
    r = client.post(f"/api/pipelines/{jid}/reset/stp", headers=HDR)
    assert r.status_code == 200, r.text
    assert seen["run"].status_code == 409, seen["run"].text
    assert jid not in ui._tickets_in_maintenance  # released afterwards
    assert f"{jid}/stp" not in ui._running_tasks


def test_max_concurrent_runs_env_is_parsed_defensively():
    import subprocess
    for raw, want in (("abc", "2"), ("0", "1"), ("-3", "1"), ("4", "4")):
        out = subprocess.run(
            [sys.executable, "-c", "import ui; print(ui._MAX_CONCURRENT_RUNS)"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            env={**os.environ, "QF_DEV": "1", "QF_MAX_CONCURRENT_RUNS": raw})
        assert out.returncode == 0, out.stderr[-500:]
        assert out.stdout.strip().splitlines()[-1] == want, (raw, out.stdout)


def test_a_finished_result_survives_more_than_one_status_read(env):
    """A second tab / another member polling the same run must see it finish."""
    jid = "ISO-5"
    ui._running_tasks[f"{jid}/stp"] = {"status": "completed", "_finished": ui.time.time(),
                                       "result": {"phase": "stp", "jira_id": jid, "verdict": "APPROVED"}}
    for _ in range(2):
        body = client.get(f"/api/pipelines/{jid}/run/stp/status").json()
        assert body["status"] == "completed" and body["verdict"] == "APPROVED"


def test_run_route_threads_the_callers_own_jira_github_identity_to_the_worker(env, monkeypatch):
    """A shared dashboard has no identity of its own for MCP calls — each run
    must carry the clicking user's own Jira/GitHub credentials (browser-stored,
    same trust boundary as push-PR's github_token) into the background worker's
    kwargs, not just accept and drop them."""
    jid = "RUN-8"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.update(kwargs=k))
    body = {"jira_username": "alice@example.com", "jira_token": "secret-jira-tok",
            "github_token": "ghp_secrettok"}

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=body)
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["creds"] == dict(body, cursor_api_key="", codex_api_key="", gcp_adc="",
                                               gcp_project="", gcp_region="")


def test_run_route_with_no_creds_body_sends_blank_creds_not_none(env, monkeypatch):
    """No body fields -> a dict of empty strings, never a KeyError or a bare
    None reaching the worker — _env_for treats blanks as no-op, so a purely
    local/dev run (no browser involved) still passes creds={} shaped data.
    Auth off: a multi-user server refuses blank creds (see the 400 tests)."""
    jid = "RUN-9"
    monkeypatch.setattr(ui, "_API_KEY", "")
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.update(kwargs=k))
    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["creds"] == {"jira_username": "", "jira_token": "", "github_token": "",
                                           "cursor_api_key": "", "codex_api_key": "", "gcp_adc": "",
                                           "gcp_project": "", "gcp_region": ""}
    assert captured["kwargs"]["runtime"] == "claude"


def test_worker_forwards_creds_to_the_runner_without_persisting_them(env, fake_runner):
    """_run_phase_background -> pipeline_runner.run_phase: creds reach the
    runner call, and pipeline_state.yaml (output/verdict/usage/model only)
    never carries the raw token."""
    jid = "RUN-10"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    creds = {"jira_username": "alice@example.com", "jira_token": "secret-jira-tok",
            "github_token": "ghp_secrettok"}

    ui._run_phase_background(jid, "stp", creds=creds)

    assert fake_runner.last_creds == creds
    assert _phase(state_file, "stp")["status"] == "completed"
    assert "secret-jira-tok" not in state_file.read_text()
    assert "ghp_secrettok" not in state_file.read_text()


# ---------------------------------------------------------------------------
# A2 — dual runtime (RUN-2026-09-08-dual-runtime, lane C): runtime selector
# and the Cursor per-user API key follow the exact same trust boundary as
# jira_token/github_token above.
# ---------------------------------------------------------------------------

def test_run_route_threads_runtime_cursor_to_the_worker(env, monkeypatch):
    """frozen decision 7: body key "runtime", value "cursor" reaches the
    background worker's kwargs unchanged."""
    jid = "RUN-11"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={**MEMBER, "runtime": "cursor", "cursor_api_key": "crsr_FAKENOTAREALKEY0000000000"})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["runtime"] == "cursor"


def test_run_route_unknown_or_absent_runtime_defaults_to_claude_never_errors(env, monkeypatch):
    """frozen decision 7: absent/empty/unknown -> "claude", never a 400."""
    jid = "RUN-12"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = []
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.append(k.get("runtime")))

    for body in ({}, {"runtime": ""}, {"runtime": "bogus"}, {"runtime": "CURSOR"}):
        ui._running_tasks.pop(f"{jid}/stp", None)  # each POST must actually re-dispatch
        r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={**MEMBER, **body})
        assert r.status_code == 200, r.text
    # "CURSOR" is not the exact spelling "cursor" (frozen decision 7 is a value
    # match, not free text) -> also falls back to claude.
    assert captured == ["claude", "claude", "claude", "claude"]


def test_cursor_api_key_threads_through_creds_and_never_lands_in_state(env, fake_runner):
    """P0: cursor_api_key is a per-request credential exactly like the Jira/
    GitHub tokens — it must reach the runner's creds and never be written to
    pipeline_state.yaml, mirroring test_worker_forwards_creds_to_the_runner_
    without_persisting_them above."""
    jid = "RUN-13"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "in_progress"}})
    creds = {"jira_username": "", "jira_token": "", "github_token": "",
            "cursor_api_key": "cursor-test-secret-tok"}

    ui._run_phase_background(jid, "stp", creds=creds, runtime="cursor")

    assert fake_runner.last_creds == creds
    assert fake_runner.last_runtime == "cursor"
    assert _phase(state_file, "stp")["status"] == "completed"
    assert "cursor-test-secret-tok" not in state_file.read_text()


def test_run_route_threads_cursor_api_key_from_the_request_body(env, monkeypatch):
    jid = "RUN-14"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={**MEMBER, "runtime": "cursor", "cursor_api_key": "key_abc123"})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["creds"]["cursor_api_key"] == "key_abc123"
    # And the run route response itself never echoes it back.
    assert "key_abc123" not in r.text


def test_run_route_threads_codex_api_key_from_the_request_body(env, monkeypatch):
    jid = "CODEX-14"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={**MEMBER, "runtime": "codex", "codex_api_key": "sk-test-codex-key"})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["runtime"] == "codex"
    assert captured["kwargs"]["creds"]["codex_api_key"] == "sk-test-codex-key"
    assert "sk-test-codex-key" not in r.text


def test_run_route_requires_codex_key_for_isolated_members(env, monkeypatch):
    jid = "CODEX-15"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: pytest.fail("worker must not start"))
    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={**MEMBER, "runtime": "codex", "codex_api_key": " "})
    assert r.status_code == 400
    assert "OpenAI API key" in r.text


# ---------------------------------------------------------------------------
# A3 — per-user Vertex identity: on a Vertex-backed server a Claude run
# carries the clicking user's own ADC or it does not run. No fallback to the
# pod's shared GOOGLE_APPLICATION_CREDENTIALS ("nobody uses my key").
# ---------------------------------------------------------------------------

FAKE_ADC = '{"type": "authorized_user", "refresh_token": "1//0FAKEFAKEFAKEFAKEFAKEFAKE"}'


def test_cursor_run_without_a_key_is_refused_on_a_multi_user_server(env, monkeypatch):
    """Symmetry with the Vertex rule: an auth-enabled server never lets a blank
    Cursor key fall back to the process's own CURSOR_API_KEY."""
    jid = "RUN-17"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={"runtime": "cursor", "cursor_api_key": "  "})
    assert r.status_code == 400, r.text
    assert "Cursor API key" in r.text
    assert captured == {}


def test_claude_run_without_a_vertex_credential_is_refused_with_the_settings_message(env, monkeypatch):
    jid = "RUN-15"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_VERTEX_PROJECT", "itpc-ca-cec5aed01a")
    scheduled: list = []
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: scheduled.append(k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={})
    assert r.status_code == 400, r.text
    assert "Paste your Vertex credential in Settings" in r.json()["detail"]
    assert scheduled == []


def test_cursor_run_needs_no_vertex_credential(env, monkeypatch):
    jid = "RUN-16"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_VERTEX_PROJECT", "itpc-ca-cec5aed01a")
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={**MEMBER, "runtime": "cursor", "cursor_api_key": "crsr_FAKENOTAREALKEY0000000000"})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["creds"]["gcp_adc"] == ""


def test_gcp_adc_threads_through_creds_and_never_lands_in_state_or_the_response(env, monkeypatch, fake_runner):
    jid = "RUN-17"
    state_file = _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    monkeypatch.setattr(ui, "_VERTEX_PROJECT", "itpc-ca-cec5aed01a")
    captured = {}
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: captured.update(kwargs=k))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={**MEMBER, "gcp_adc": FAKE_ADC, "gcp_project": "test-project"})
    assert r.status_code == 200, r.text
    assert captured["kwargs"]["creds"]["gcp_adc"] == FAKE_ADC
    assert FAKE_ADC not in r.text and "1//0FAKE" not in r.text

    # ...and the worker never writes it to the state file on the PVC.
    ui._run_phase_background(jid, "stp", creds=captured["kwargs"]["creds"])
    assert "1//0FAKE" not in state_file.read_text()


def test_claude_status_reports_the_per_user_credential_requirement(monkeypatch):
    monkeypatch.setattr(ui, "_VERTEX_PROJECT", "owner-personal-project")
    r = client.get("/api/claude/status")
    body = r.json()
    assert body["per_user_credential"] is True
    assert "available" in body  # still means "server configured", not "run can start"
    assert "owner-personal-project" not in r.text  # the owner's project id is nobody else's business


def test_get_models_is_runtime_aware_with_grok_default_for_cursor(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(ui, "_RUNNER_MODEL_DEFAULT", "claude-sonnet-4@20250514")
    monkeypatch.setattr(ui, "_RUNNER_MODELS", ["claude-sonnet-4@20250514", "claude-opus-4@20250514"])
    monkeypatch.setattr(ui, "_RUNNER_CURSOR_MODEL_DEFAULT", "cursor-grok-4.6-high")
    monkeypatch.setattr(ui, "_RUNNER_CURSOR_MODELS", ["cursor-grok-4.6-high"])
    monkeypatch.setattr(ui, "_CURSOR_MODEL_LABELS", {"cursor-grok-4.6-high": "Cursor Grok 4.6"})

    body = client.get("/api/models").json()
    assert body["claude"]["default"] == "claude-sonnet-4@20250514"
    assert body["claude"]["models"] == ["claude-sonnet-4@20250514", "claude-opus-4@20250514"]
    assert body["claude"]["labels"] == {}
    assert body["cursor"]["default"] == "cursor-grok-4.6-high"
    assert body["cursor"]["models"] == ["cursor-grok-4.6-high"]
    assert body["cursor"]["labels"]["cursor-grok-4.6-high"] == "Cursor Grok 4.6"
    assert body["cursor"]["env_key"] is False
    assert body["codex"]["default"] == "gpt-6-astra"
    assert body["codex"]["models"][:6] == [
        "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra",
        "gpt-5.6-luna", "gpt-5.5", "gpt-5.2",
    ]
    assert body["codex"]["labels"]["gpt-6-astra"] == "GPT-6 Astra (default)"
    assert body["codex"]["env_key"] is False


def test_get_models_degrades_gracefully_when_claude_list_is_empty(monkeypatch):
    """R-6b: on cnv2 today QF_RUNNER_MODEL/QF_RUNNER_MODELS are absent, so the
    Claude bucket is genuinely empty. The Cursor bucket must still be usable —
    its default is hardcoded, not env-dependent — and the route must not error."""
    monkeypatch.setattr(ui, "_RUNNER_MODEL_DEFAULT", "")
    monkeypatch.setattr(ui, "_RUNNER_MODELS", [])

    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert body["claude"]["default"] == ""
    assert body["claude"]["models"] == []
    assert body["claude"]["labels"] == {}
    assert body["cursor"]["default"] == "cursor-grok-4.6-high"
    assert "cursor-grok-4.6-high" in body["cursor"]["models"]
    assert "composer-2.5" in body["cursor"]["models"]
    assert "claude-4.6-opus-high" in body["cursor"]["models"]
    assert body["cursor"]["labels"]["cursor-grok-4.6-high"] == "Cursor Grok 4.6"


def test_pipeline_list_hides_cost_for_a_completed_cursor_phase(env):
    """X-1 (cross-lane, RUN-2026-09-08-dual-runtime): Cursor's result event
    carries no cost field, so pipeline_runner.run_phase persists
    usage={"cost_usd": None, ...} for every Cursor-run phase. The list
    summary (_summarize_phases, what /api/pipelines and the dashboard cards
    read) must drop the usage block entirely rather than forward a None
    cost — the UI has no business rendering "$NaN" or, worse, "$0.00"
    (which would falsely claim a free run) for a runtime that never reports
    cost at all."""
    jid = "RUN-15"
    _seed_ticket(env, jid, {"stp": {"status": "completed", "model": "grok-4.6",
                                    "usage": {"cost_usd": None, "duration_ms": 4000}}})

    rows = [r for r in client.get("/api/pipelines").json() if r["jira_id"] == jid]
    assert rows
    assert "usage" not in rows[0]["phases"]["stp"]
    # ponytail: no production change alongside this test — ui.py:2178's
    # `usage.get("cost_usd") is not None` guard (list route) and index.html's
    # `typeof costUsd === 'number'` guard (detail route) already predate this
    # campaign and already degrade a None cost to "not captured"/"—", never
    # "$NaN" or "$0.00". This test only pins that behavior so a future edit
    # to either guard trips a red test instead of silently regressing for
    # every Cursor run.


def test_unknown_phase_and_malformed_ticket_are_rejected(env, monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: pytest.fail("worker must not run"))
    assert client.post("/api/pipelines/RUN-6/run/nonsense", headers=HDR, json={}).status_code == 400
    assert client.post("/api/pipelines/not-a-ticket/run/stp", headers=HDR, json={}).status_code == 400


def test_disabled_toggle_blocks_the_run_without_calling_the_runner(env, monkeypatch):
    jid = "RUN-7"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    _write_project(ui.CONFIG, "example", {"stp_generation": False})
    monkeypatch.setattr(ui, "_run_phase_background",
                        lambda *a, **k: pytest.fail("worker must not run"))

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json=MEMBER)
    assert r.status_code == 400
    assert "stp_generation" in r.json()["detail"]


# ---------------------------------------------------------------------------
# B — POST /api/pipelines/{jira_id}/approve/{phase}
# ---------------------------------------------------------------------------

def test_approve_writes_under_the_gate_key_the_cli_reads(env):
    """W4's fix: the decision must land under stp_review, the key the pipeline
    gate reads. Written as "stp" it was invisible and the CLI stayed blocked."""
    jid = "APR-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})

    r = client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR,
                    json={"action": "approve", "reviewer": "qe@example.com"})
    assert r.status_code == 200, r.text

    approvals = yaml.safe_load((env / jid / "state" / "approvals.yaml").read_text())
    assert approvals[ui._GATE_APPROVAL_KEY["stp"]]["status"] == "approved"
    # W9b/OBS-01-F6: `reviewer` is now the server-resolved identity; the name the
    # client sent is kept beside it as a claim, never as the identity.
    assert approvals[ui._GATE_APPROVAL_KEY["stp"]]["reviewer"] == "api-key"
    assert approvals[ui._GATE_APPROVAL_KEY["stp"]]["claimed_name"] == "qe@example.com"
    assert "stp" not in approvals
    # The gate overlay stops holding the phase at awaiting_approval.
    row = client.get(f"/api/pipelines/{jid}").json()
    assert row["phases"]["stp"]["status"] == "completed"


def test_reject_is_recorded_and_leaves_the_phase_gated(env):
    jid = "APR-2"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})

    r = client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR,
                    json={"action": "reject", "comment": "missing negative cases"})
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["status"] == "rejected"

    approvals = yaml.safe_load((env / jid / "state" / "approvals.yaml").read_text())
    assert approvals["stp_review"]["comment"] == "missing negative cases"
    # W9b fixes what W8 pinned as-is: a rejection used to release the phase back
    # to "completed", so it dropped out of Needs You, counted as done in the
    # rollup and opened the downstream gate while the CLI stayed blocked. A
    # rejected gate is still waiting on a human; the decision rides along on
    # phase["approval"] so the UI can say "rejected" rather than "untouched".
    stp = client.get(f"/api/pipelines/{jid}").json()["phases"]["stp"]
    assert stp["status"] == "awaiting_approval"
    assert stp["approval"]["status"] == "rejected"


def test_approve_rejects_an_ungated_phase_and_a_bogus_action(env):
    jid = "APR-3"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    assert client.post(f"/api/pipelines/{jid}/approve/codegen", headers=HDR,
                       json={"action": "approve"}).status_code == 400
    assert client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR,
                       json={"action": "maybe"}).status_code == 400
    assert not (env / jid / "state" / "approvals.yaml").exists()


def test_approve_without_the_api_key_is_refused(env):
    """One assertion only — tests/test_authz_matrix.py covers the whole matrix."""
    jid = "APR-4"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    assert client.post(f"/api/pipelines/{jid}/approve/stp",
                       json={"action": "approve"}).status_code == 403
    assert not (env / jid / "state" / "approvals.yaml").exists()


# ---------------------------------------------------------------------------
# C — PUT /api/projects/{project_id}/toggles
# ---------------------------------------------------------------------------

def _write_project(cfg: Path, project_id: str, toggles: dict) -> Path:
    # The toggles PUT reads its name allowlist out of _defaults.yaml (W9b), so a
    # config tree without one is the degraded, name-permissive case, not the
    # normal one. Seed the real names here.
    (cfg / "_defaults.yaml").write_text(yaml.safe_dump(
        {"feature_toggles": {"stp_generation": True, "std_generation": True,
                             "lsp_analysis": True, "pii_sanitization": True,
                             "test_strategy": "auto"}}, sort_keys=False))
    d = cfg / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "project.yaml"
    p.write_text(yaml.safe_dump({"project_id": project_id, "display_name": project_id.upper(),
                                 "feature_toggles": toggles}, sort_keys=False))
    return p


def test_toggles_put_persists_and_is_visible_on_the_next_read(env):
    jid = "TOG-1"
    _seed_ticket(env, jid, {"stp": {"status": "pending"}})
    proj_yaml = _write_project(ui.CONFIG, "example", {"stp_generation": True,
                                                      "lsp_analysis": True})
    assert client.get(f"/api/pipelines/{jid}").json()["feature_toggles"]["stp_generation"] is True

    r = client.put("/api/projects/example/toggles", headers=HDR,
                   json={"feature_toggles": {"stp_generation": False}})
    assert r.status_code == 200, r.text
    assert r.json()["feature_toggles"]["stp_generation"] is False

    # On disk, merged rather than replaced…
    on_disk = yaml.safe_load(proj_yaml.read_text())["feature_toggles"]
    assert on_disk == {"stp_generation": False, "lsp_analysis": True}
    # …and the caches do not serve the pre-write answer.
    assert client.get(f"/api/pipelines/{jid}").json()["feature_toggles"]["stp_generation"] is False


def test_toggles_put_on_an_unknown_project_is_404(env):
    assert client.put("/api/projects/nosuch/toggles", headers=HDR,
                      json={"feature_toggles": {"stp_generation": False}}).status_code == 404


def test_toggles_put_rejects_unknown_names_and_non_bool_values(env):
    """W8 found this and pinned it xfail(strict); W9b fixed it, so the marker and
    its companion `test_toggles_put_currently_accepts_anything` are gone. A typo'd
    name and a string value both used to persist verbatim into project.yaml —
    `toggles.get(k, True)` reads the string "false" as truthy, so the user
    believed a phase was disabled and it stayed on."""
    proj_yaml = _write_project(ui.CONFIG, "example", {"stp_generation": True})
    bad = client.put("/api/projects/example/toggles", headers=HDR,
                     json={"feature_toggles": {"stp_generashun": False}})
    worse = client.put("/api/projects/example/toggles", headers=HDR,
                       json={"feature_toggles": {"stp_generation": "false"}})
    assert bad.status_code == 400 and worse.status_code == 400
    assert "stp_generashun" in bad.json()["detail"]
    # Neither rejected write reached the file.
    assert yaml.safe_load(proj_yaml.read_text())["feature_toggles"] == {"stp_generation": True}


def test_toggles_put_accepts_the_one_non_bool_toggle_and_survives_a_reread(env):
    """test_strategy is legitimately a string enum, so a blanket isinstance(bool)
    check would have rejected the one valid non-bool toggle in _defaults.yaml."""
    proj_yaml = _write_project(ui.CONFIG, "example", {"stp_generation": True})
    assert client.put("/api/projects/example/toggles", headers=HDR,
                      json={"feature_toggles": {"test_strategy": "tier",
                                                "lsp_analysis": False}}).status_code == 200
    assert client.put("/api/projects/example/toggles", headers=HDR,
                      json={"feature_toggles": {"test_strategy": "sideways"}}).status_code == 400
    on_disk = yaml.safe_load(proj_yaml.read_text())["feature_toggles"]
    assert on_disk == {"stp_generation": True, "test_strategy": "tier", "lsp_analysis": False}


def test_create_project_rejects_an_unknown_toggle(env):
    """Same allowlist on the other route that writes feature_toggles — validating
    only the PUT would have left the create path wide open."""
    (ui.CONFIG / "_defaults.yaml").write_text(yaml.safe_dump(
        {"feature_toggles": {"stp_generation": True}}, sort_keys=False))
    r = client.post("/api/projects", headers=HDR,
                    json={"project_id": "w9bproj", "display_name": "W9B",
                          "feature_toggles": {"stp_generashun": True}})
    assert r.status_code == 400
    assert not (ui.CONFIG / "projects" / "w9bproj").exists()


# ---------------------------------------------------------------------------
# D — startup reconciliation (the lifespan's first act, before any network)
# ---------------------------------------------------------------------------

def _run_startup(monkeypatch):
    """Drive ui._lifespan's startup half with the git-sync loop stubbed out."""
    monkeypatch.setattr(ui, "_start_git_sync_loop", lambda: None)
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())

    async def _drive():
        async with ui._lifespan(None):
            pass

    asyncio.run(_drive())


def test_startup_fails_phases_left_in_progress_by_a_dead_process(env, monkeypatch):
    """A phase can only be in_progress while a thread owns it, and a restart
    wipes that dict — so a surviving in_progress is stuck forever unless boot
    flips it. Both layouts are swept (_iter_state_files)."""
    canonical = _seed_ticket(env, "REC-1", {
        "stp": {"status": "completed", "verdict": "APPROVED"},
        "std": {"status": "in_progress", "started_ts": "2026-01-01T00:00:00Z"},
    })
    legacy = env / "state" / "REC-2" / "pipeline_state.yaml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(yaml.safe_dump({"ticket_id": "REC-2", "project_id": "example",
                                      "phases": {"stp": {"status": "in_progress"}}}))

    _run_startup(monkeypatch)

    assert _phase(canonical, "std")["status"] == "failed"
    assert _phase(canonical, "std")["error"] == "Interrupted by dashboard restart"
    assert _phase(legacy, "stp")["status"] == "failed"
    # Terminal phases are left exactly as they were.
    assert _phase(canonical, "stp") == {"status": "completed", "verdict": "APPROVED"}


def test_startup_survives_a_corrupt_state_file(env, monkeypatch):
    good = _seed_ticket(env, "REC-3", {"stp": {"status": "in_progress"}})
    bad = env / "REC-4" / "state" / "pipeline_state.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("phases: [this is a list, not a mapping]\n")

    _run_startup(monkeypatch)

    assert _phase(good, "stp")["status"] == "failed"


# ---------------------------------------------------------------------------
# E — _git_sync copies into the mounted data dirs, not the image layer
# ---------------------------------------------------------------------------

def test_git_sync_copies_into_the_mounted_dirs(env, tmp_path, monkeypatch):
    """In-cluster OUTPUTS/CONFIG are PVCs while ROOT is the read-mostly image
    layer, so a sync that wrote ROOT/outputs "succeeded" and was then never
    read by anything."""
    repo_path = tmp_path / "clone"
    (repo_path / ".git").mkdir(parents=True)
    (repo_path / "outputs" / "SYN-1" / "stp").mkdir(parents=True)
    (repo_path / "outputs" / "SYN-1" / "stp" / "SYN-1_test_plan.md").write_text("# synced\n")
    (repo_path / "config" / "projects" / "synced").mkdir(parents=True)
    (repo_path / "config" / "projects" / "synced" / "project.yaml").write_text("project_id: synced\n")

    class _FakeGit:
        class Repo:
            def __init__(self, _path):
                self.git = type("g", (), {"update_environment": lambda *a, **k: None})()
                origin = type("o", (), {"url": "https://example.invalid/qf.git",
                                        "set_url": lambda *a, **k: None,
                                        "fetch": lambda *a, **k: None,
                                        "pull": lambda *a, **k: None})()
                self.remotes = type("r", (), {"origin": origin})()

            @staticmethod
            def clone_from(*_a, **_k):
                raise AssertionError("should have pulled the existing clone")

    monkeypatch.setitem(sys.modules, "git", _FakeGit)
    monkeypatch.setenv("GIT_REPO_URL", "https://example.invalid/qf.git")
    # W11a made the clone dir a module global, so the ui.Path redirect this
    # test used to need (to keep off a developer's live /tmp scratch clone) is
    # gone.
    monkeypatch.setattr(ui, "_GIT_SCRATCH", repo_path)

    assert ui._git_sync()["status"] == "ok"

    assert (ui.OUTPUTS / "SYN-1" / "stp" / "SYN-1_test_plan.md").read_text() == "# synced\n"
    assert (ui.CONFIG / "projects" / "synced" / "project.yaml").exists()
    assert not (ROOT / "outputs" / "SYN-1").exists(), "synced into the image layer"


def test_git_sync_reclones_when_the_scratch_clone_points_at_another_repo(env, tmp_path, monkeypatch):
    """W3-noted: _git_sync rewrites origin to the configured URL on every sync,
    so a scratch clone left behind by a different GIT_REPO_URL was fetched and
    pulled into. Unrelated history makes the ff-only pull fail rather than merge
    foreign content, but the stale tree must go, not be reused."""
    repo_path = tmp_path / "clone"
    (repo_path / ".git").mkdir(parents=True)
    (repo_path / "stale.txt").write_text("from the wrong repo\n")

    cloned: list = []

    class _FakeGit:
        class Repo:
            def __init__(self, _path):
                self.git = type("g", (), {"update_environment": lambda *a, **k: None})()
                # Same host, different path — and carrying a token, to prove the
                # comparison is on host+path and not on the raw string.
                origin = type("o", (), {"url": "https://x-access-token:ghp_x@example.invalid/other.git",
                                        "set_url": lambda *a, **k: None,
                                        "fetch": lambda *a, **k: (_ for _ in ()).throw(
                                            AssertionError("fetched a foreign clone")),
                                        "pull": lambda *a, **k: None})()
                self.remotes = type("r", (), {"origin": origin})()

            @staticmethod
            def clone_from(url, dest, **_k):
                cloned.append((url, dest))
                (Path(dest) / "outputs" / "SYN-2" / "stp").mkdir(parents=True)
                (Path(dest) / "outputs" / "SYN-2" / "stp" / "SYN-2_test_plan.md").write_text("# fresh\n")

    monkeypatch.setitem(sys.modules, "git", _FakeGit)
    monkeypatch.setenv("GIT_REPO_URL", "https://example.invalid/qf.git")
    monkeypatch.setattr(ui, "_GIT_SCRATCH", repo_path)

    assert ui._git_sync()["status"] == "ok"

    assert cloned and str(cloned[0][1]) == str(repo_path), "did not fall through to a fresh clone"
    assert not (repo_path / "stale.txt").exists(), "stale clone was reused, not removed"
    assert (ui.OUTPUTS / "SYN-2" / "stp" / "SYN-2_test_plan.md").read_text() == "# fresh\n"


def test_git_sync_keeps_the_clone_when_only_the_token_differs(env, tmp_path, monkeypatch):
    """A rotated GIT_TOKEN changes the stored origin URL but not the repo, so it
    must not trigger a re-clone on every sync."""
    repo_path = tmp_path / "clone"
    (repo_path / ".git").mkdir(parents=True)
    pulled: list = []

    class _FakeGit:
        class Repo:
            def __init__(self, _path):
                self.git = type("g", (), {"update_environment": lambda *a, **k: None})()
                origin = type("o", (), {"url": "https://x-access-token:OLDTOKEN@EXAMPLE.invalid/qf.git/",
                                        "set_url": lambda *a, **k: None,
                                        "fetch": lambda *a, **k: None,
                                        "pull": lambda *a, **k: pulled.append(a)})()
                self.remotes = type("r", (), {"origin": origin})()

            @staticmethod
            def clone_from(*_a, **_k):
                raise AssertionError("re-cloned on a token rotation")

    monkeypatch.setitem(sys.modules, "git", _FakeGit)
    monkeypatch.setenv("GIT_REPO_URL", "https://example.invalid/qf.git")
    monkeypatch.setattr(ui, "_GIT_SCRATCH", repo_path)

    assert ui._git_sync()["status"] == "ok"
    assert pulled, "existing clone was not pulled"


def test_git_sync_never_writes_git_token_into_the_clone(env, tmp_path, monkeypatch):
    """P1-2: a token in the remote URL lands in the scratch clone's .git/config,
    readable by every pipeline run (same UID). Pull and clone both get it as a
    per-command env header instead, and origin is reset token-free."""
    repo_path = tmp_path / "clone"
    (repo_path / ".git").mkdir(parents=True)
    seen: dict = {"urls": [], "env": {}}

    class _FakeGit:
        class Repo:
            def __init__(self, _path):
                self.git = type("g", (), {"update_environment": lambda _s, **k: seen["env"].update(k)})()
                origin = type("o", (), {"url": "https://x-access-token:FAKEOLDTOKEN@example.invalid/qf.git",
                                        "set_url": lambda _s, u: seen["urls"].append(u),
                                        "fetch": lambda *a, **k: None,
                                        "pull": lambda *a, **k: None})()
                self.remotes = type("r", (), {"origin": origin})()

            @staticmethod
            def clone_from(url, dest, **k):
                seen["clone"] = (url, k["env"])

    monkeypatch.setitem(sys.modules, "git", _FakeGit)
    monkeypatch.setenv("GIT_REPO_URL", "https://example.invalid/qf.git")
    monkeypatch.setenv("GIT_TOKEN", "FAKEGITTOKEN")
    monkeypatch.setattr(ui, "_GIT_SCRATCH", repo_path)

    assert ui._git_sync()["status"] == "ok"  # existing clone: fetch + pull
    assert seen["urls"] == ["https://example.invalid/qf.git"]  # scrubs the old stored token
    assert seen["env"]["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert "FAKEGITTOKEN" in __import__("base64").b64decode(
        seen["env"]["GIT_CONFIG_VALUE_0"].rsplit(" ", 1)[1]).decode()

    import shutil
    shutil.rmtree(repo_path)  # no .git: fresh clone path
    assert ui._git_sync()["status"] == "ok"
    url, clone_env = seen["clone"]
    assert "FAKEGITTOKEN" not in url and clone_env["GIT_CONFIG_KEY_0"] == "http.extraHeader"


def test_git_honours_the_env_passed_header_without_touching_config(tmp_path, monkeypatch):
    """The mechanism _git_auth_env relies on (git >= 2.31), checked against the
    real git binary — a read-only `git config --get`, no repo, no network."""
    import shutil
    import subprocess
    if not shutil.which("git"):
        pytest.skip("git not installed")
    monkeypatch.setenv("GIT_TOKEN", "FAKEGITTOKEN")
    header_env = ui._git_auth_env("https://example.invalid/qf.git")
    assert ui._git_auth_env("ssh://git@example.invalid/qf.git") == {}  # http(s) only
    out = subprocess.run(["git", "config", "--get", "http.extraHeader"], cwd=str(tmp_path),
                         capture_output=True, text=True,
                         env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path), **header_env})
    assert out.stdout.strip() == header_env["GIT_CONFIG_VALUE_0"], out.stderr
    assert not list(tmp_path.iterdir())  # nothing written
