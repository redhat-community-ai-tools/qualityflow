""""Request changes": a dashboard *_refine run with optional reviewer notes.

An APPROVED_WITH_FINDINGS review never triggers the builders' auto-refine
(critical findings only), so the dashboard can run /refine-stp|std
--address-findings itself. Covers the runner argv, the run route's
preconditions and feedback file, and the completion path that refreshes the
parent verdict and drops the now-stale gate decision.

Reuses test_mutating_routes.py's fixtures (env, fake_runner) — same
conventions: no real CLI, globals monkeypatched per test.
"""
import json
import subprocess

import pytest
import yaml

import pipeline_runner
from test_mutating_routes import (HDR, MEMBER, _phase, _seed_ticket,  # noqa: F401 — fixtures
                                  _write_project, client, env, fake_runner, ui)


# --- runner argv -----------------------------------------------------------

@pytest.fixture
def capture_run(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","result":"ok"}\n', stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    return calls


@pytest.mark.parametrize("runtime", ["claude", "cursor"])
@pytest.mark.parametrize("phase,prompt", [
    ("stp_refine", "/refine-stp PROJ-1 --address-findings"),
    ("std_refine", "/refine-std PROJ-1 --address-findings"),
    ("stp", "/stp-builder PROJ-1"),
    ("stp_review", "/review-stp PROJ-1"),
])
def test_refine_phases_ask_the_command_to_address_findings(capture_run, runtime, phase, prompt):
    pipeline_runner.run_phase("", "PROJ-1", phase, runtime=runtime)
    argv = capture_run[0]
    assert argv[argv.index("-p") + 1] == prompt


# --- run route preconditions -----------------------------------------------

def _review(out, jid, doc, verdict):
    p = out / jid / "reviews" / f"{jid}_{doc}_review.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Review\n\nVerdict: {verdict}\n")
    return p


def _stp_only(out, jid):
    """STP produced, STD not yet — the only state stp_refine accepts."""
    state = _seed_ticket(out, jid, {"stp": {"status": "completed"}})
    (out / jid / "std" / f"{jid}_test_description.yaml").unlink()
    return state


def _notes(out, jid, doc="stp"):
    return out / jid / "reviews" / f"{jid}_{doc}_feedback.md"


@pytest.fixture
def no_worker(monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)


def test_unknown_phase_lists_the_refine_phases(env, no_worker):
    r = client.post("/api/pipelines/RC-1/run/nonsense", headers=HDR, json=MEMBER)
    assert r.status_code == 400
    assert "stp_refine" in r.json()["detail"] and "std_refine" in r.json()["detail"]


def test_review_toggle_off_refuses_the_refine(env, no_worker):
    _stp_only(env, "RC-2")
    _write_project(ui.CONFIG, "example", {"stp_review": False})
    r = client.post("/api/pipelines/RC-2/run/stp_refine", headers=HDR, json=MEMBER)
    assert r.status_code == 400
    assert "stp_review" in r.json()["detail"]


def test_refine_without_the_document_is_409(env, no_worker):
    r = client.post("/api/pipelines/RC-3/run/stp_refine", headers=HDR, json=MEMBER)
    assert r.status_code == 409
    assert r.json()["detail"] == "Run STP first"


def test_stp_refine_after_std_was_generated_is_409(env, no_worker):
    _seed_ticket(env, "RC-4", {"stp": {"status": "completed"}})  # STD artifact on disk
    r = client.post("/api/pipelines/RC-4/run/stp_refine", headers=HDR, json={**MEMBER, "feedback": "x"})
    assert r.status_code == 409
    assert "reset from STD" in r.json()["detail"]
    assert not _notes(env, "RC-4").exists()


def test_stp_refine_while_std_is_in_progress_in_state_is_409(env, no_worker):
    state = _stp_only(env, "RC-5")
    data = yaml.safe_load(state.read_text())
    data["phases"]["std"] = {"status": "in_progress"}
    state.write_text(yaml.safe_dump(data))
    assert client.post("/api/pipelines/RC-5/run/stp_refine", headers=HDR, json=MEMBER).status_code == 409


def test_std_refine_after_tests_were_generated_is_409(env, no_worker):
    _seed_ticket(env, "RC-6", {"std": {"status": "completed"}})
    (env / "RC-6" / "go-tests").mkdir()
    (env / "RC-6" / "go-tests" / "qf_feature_test.go").write_text("package x\n")
    r = client.post("/api/pipelines/RC-6/run/std_refine", headers=HDR, json=MEMBER)
    assert r.status_code == 409
    assert "reset from Test Generation" in r.json()["detail"]


@pytest.mark.parametrize("feedback", ["x" * 8001, 42])
def test_bad_feedback_is_400_and_writes_nothing(env, no_worker, feedback):
    _stp_only(env, "RC-7")
    r = client.post("/api/pipelines/RC-7/run/stp_refine", headers=HDR, json={**MEMBER, "feedback": feedback})
    assert r.status_code == 400
    assert not _notes(env, "RC-7").exists()
    assert "RC-7/stp_refine" not in ui._running_tasks


def test_accepted_refine_writes_the_stripped_notes(env, no_worker):
    _stp_only(env, "RC-8")
    r = client.post("/api/pipelines/RC-8/run/stp_refine", headers=HDR,
                    json={**MEMBER, "feedback": "  Cover the upgrade path.  "})
    assert r.status_code == 200, r.text
    text = _notes(env, "RC-8").read_text()
    assert text.startswith("<!-- Reviewer notes from the dashboard, api-key ")
    assert text.endswith("\nCover the upgrade path.\n")
    assert "member-jira-tok" not in text and "member-gh-tok" not in text


def test_blank_feedback_removes_stale_notes(env, no_worker):
    _stp_only(env, "RC-9")
    _notes(env, "RC-9").parent.mkdir(parents=True, exist_ok=True)
    _notes(env, "RC-9").write_text("old notes\n")
    r = client.post("/api/pipelines/RC-9/run/stp_refine", headers=HDR, json={**MEMBER, "feedback": "   "})
    assert r.status_code == 200, r.text
    assert not _notes(env, "RC-9").exists()


def test_notes_write_failure_releases_the_reservation(env, no_worker, monkeypatch):
    _stp_only(env, "RC-10")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ui, "_atomic_write_text", boom)
    r = client.post("/api/pipelines/RC-10/run/stp_refine", headers=HDR, json={**MEMBER, "feedback": "x"})
    assert r.status_code == 500
    assert "RC-10/stp_refine" not in ui._running_tasks


# --- completion ------------------------------------------------------------

def test_completed_refine_refreshes_the_verdict_and_drops_the_approval(env, fake_runner):
    jid = "RC-11"
    state = _seed_ticket(env, jid, {"stp": {"status": "completed",
                                            "findings": {"critical": 0, "major": 5, "minor": 5}}})
    (env / jid / "std" / f"{jid}_test_description.yaml").unlink()
    _review(env, jid, "stp", "APPROVED")  # what the refine's re-review wrote
    ui._write_approvals(jid, {"stp_review": {"status": "approved", "reviewer": "a"},
                              "stp": {"status": "approved"}, "std_review": {"status": "approved"}})

    ui._run_phase_background(jid, "stp_refine", actor="alice@example.com")

    assert _phase(state, "stp_refine")["status"] == "completed"
    stp = _phase(state, "stp")
    assert stp["status"] == "completed"
    assert stp["verdict"] == "APPROVED"
    assert "findings" not in stp  # pre-refine counts would contradict the new verdict
    assert stp["refined_ts"] == _phase(state, "stp_refine")["finished_ts"]
    assert ui._read_approvals(jid) == {"std_review": {"status": "approved"}}
    rows = [json.loads(l) for l in (env / ".audit" / "audit.jsonl").read_text().splitlines()]
    assert rows[-1]["action"] == "request_changes"
    assert rows[-1]["actor"] == "alice@example.com" and rows[-1]["phase"] == "stp_refine"
    # the detail route surfaces it, and the refined STP is back on the Approve card
    detail = client.get(f"/api/pipelines/{jid}").json()["phases"]["stp"]
    assert detail["refined_ts"] and detail["status"] == "awaiting_approval"


def test_failed_refine_keeps_the_prior_decision(env, fake_runner):
    jid = "RC-12"
    state = _stp_only(env, jid)
    ui._write_approvals(jid, {"stp_review": {"status": "approved"}})
    fake_runner.raises = RuntimeError("refine exited 1")

    ui._run_phase_background(jid, "stp_refine")

    assert _phase(state, "stp_refine")["status"] == "failed"
    assert "refined_ts" not in _phase(state, "stp")
    assert ui._read_approvals(jid) == {"stp_review": {"status": "approved"}}


def test_refinement_log_and_notes_are_listed_artifacts(env):
    jid = "RC-13"
    _stp_only(env, jid)
    (env / jid / "reviews").mkdir()
    (env / jid / "reviews" / f"{jid}_stp_refinement_log.md").write_text("# log\n")
    (env / jid / "reviews" / f"{jid}_stp_feedback.md").write_text("notes\n")
    labels = {a["type"]: a["label"] for a in client.get(f"/api/artifacts/{jid}").json()}
    assert labels["stp_refinement_log"] == "STP Refinement Log"
    assert labels["stp_feedback"] == "STP Reviewer Notes"
    assert "std_refinement_log" not in labels
    assert client.get(f"/api/artifacts/{jid}/stp_feedback").json()["raw"] == "notes\n"
