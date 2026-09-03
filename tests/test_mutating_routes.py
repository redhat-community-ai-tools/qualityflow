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
    """Stand in for pipeline_runner.run_phase (which shells out to `claude`).
    `calls` records every invocation; set `.result` / `.raises` per test."""
    import pipeline_runner

    class _Runner:
        calls: list[tuple] = []
        result: dict = {"output": "done", "verdict": "APPROVED"}
        raises: Exception | None = None

        def __call__(self, model, jira_id, phase):
            self.calls.append((model, jira_id, phase))
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

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={})
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

    assert fake_runner.calls == [(ui._RUNNER_MODEL_DEFAULT, jid, "stp")]
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

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "already_running"
    assert scheduled == []


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

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR, json={})
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
    assert approvals[ui._GATE_APPROVAL_KEY["stp"]]["reviewer"] == "qe@example.com"
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
    # Pinned as-is: a rejection is a *recorded decision*, so the gate overlay
    # stops holding the phase at awaiting_approval and hangs the decision off
    # it instead. The downstream CLI gate reads approvals.yaml, where the
    # status is "rejected", so the pipeline stays blocked either way.
    stp = client.get(f"/api/pipelines/{jid}").json()["phases"]["stp"]
    assert stp["status"] == "completed"
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


@pytest.mark.xfail(strict=True, reason=(
    "TEST-01-F06 bug found by W8: update_toggles does cfg['feature_toggles'].update(body) "
    "with no key allowlist and no type check, so a typo'd name or a string value is "
    "persisted verbatim into project.yaml. Harmless to the runtime (unknown keys are "
    "ignored, and `toggles.get(k, True)` treats 'false' as truthy) but it silently "
    "accepts a toggle the user believes they set. Product fix belongs in a ui.py wave."))
def test_toggles_put_rejects_unknown_names_and_non_bool_values(env):
    _write_project(ui.CONFIG, "example", {"stp_generation": True})
    bad = client.put("/api/projects/example/toggles", headers=HDR,
                     json={"feature_toggles": {"stp_generashun": False}})
    worse = client.put("/api/projects/example/toggles", headers=HDR,
                       json={"feature_toggles": {"stp_generation": "false"}})
    assert bad.status_code == 400 and worse.status_code == 400


def test_toggles_put_currently_accepts_anything(env):
    """Companion to the xfail above: pins what actually happens today, so the
    behaviour change is visible in the diff when the validation lands."""
    proj_yaml = _write_project(ui.CONFIG, "example", {"stp_generation": True})
    r = client.put("/api/projects/example/toggles", headers=HDR,
                   json={"feature_toggles": {"stp_generashun": False,
                                             "stp_generation": "false"}})
    assert r.status_code == 200
    on_disk = yaml.safe_load(proj_yaml.read_text())["feature_toggles"]
    assert on_disk == {"stp_generashun": False, "stp_generation": "false"}


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
                origin = type("o", (), {"set_url": lambda *a, **k: None,
                                        "fetch": lambda *a, **k: None,
                                        "pull": lambda *a, **k: None})()
                self.remotes = type("r", (), {"origin": origin})()

            @staticmethod
            def clone_from(*_a, **_k):
                raise AssertionError("should have pulled the existing clone")

    monkeypatch.setitem(sys.modules, "git", _FakeGit)
    monkeypatch.setenv("GIT_REPO_URL", "https://example.invalid/qf.git")
    # ponytail: the clone dir is hardcoded to /tmp/qualityflow-repo inside
    # _git_sync, and this test must not touch a developer's live scratch clone.
    # Redirecting that one literal through ui.Path is the smallest seam; make
    # the path configurable in product code and this hook goes away.
    monkeypatch.setattr(ui, "Path",
                        lambda p: repo_path if str(p) == "/tmp/qualityflow-repo" else Path(p))

    assert ui._git_sync()["status"] == "ok"

    assert (ui.OUTPUTS / "SYN-1" / "stp" / "SYN-1_test_plan.md").read_text() == "# synced\n"
    assert (ui.CONFIG / "projects" / "synced" / "project.yaml").exists()
    assert not (ROOT / "outputs" / "SYN-1").exists(), "synced into the image layer"
