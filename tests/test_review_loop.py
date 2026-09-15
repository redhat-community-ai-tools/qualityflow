"""The rest of the human review loop on the dashboard: Edit, Re-run review,
What changed — plus git sync not reverting any of it.

Same fixtures/conventions as test_request_changes.py (env, fake_runner from
test_mutating_routes.py; fake_git from test_state_safety.py).
"""
import json
import os
import threading
import time

import pytest
import yaml

from test_mutating_routes import (HDR, MEMBER, _phase, _seed_ticket,  # noqa: F401 — fixtures
                                  _write_project, client, env, fake_runner, ui)
from test_request_changes import capture_run  # noqa: F401 — fixture
from test_state_safety import fake_git  # noqa: F401 — fixture


def _stp_only(out, jid, phases=None):
    state = _seed_ticket(out, jid, phases or {"stp": {"status": "completed"}})
    (out / jid / "std" / f"{jid}_test_description.yaml").unlink()
    return state


def _stp(out, jid):
    return out / jid / "stp" / f"{jid}_test_plan.md"


def _review(out, jid, doc, verdict):
    p = out / jid / "reviews" / f"{jid}_{doc}_review.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Review\n\nVerdict: {verdict}\n")
    return p


def _sha(jid, kind):
    r = client.get(f"/api/artifacts/{jid}/{kind}")
    assert r.status_code == 200, r.text
    return r.json()["sha"]


def _put(jid, kind, content, base_sha):
    return client.put(f"/api/artifacts/{jid}/{kind}", headers=HDR,
                      json={"content": content, "base_sha": base_sha})


def _audit_rows(out):
    return [json.loads(l) for l in (out / ".audit" / "audit.jsonl").read_text().splitlines()]


# --- GET artifact ------------------------------------------------------------

def test_get_artifact_carries_sha_and_has_previous(env):
    _stp_only(env, "RL-1")
    body = client.get("/api/artifacts/RL-1/stp").json()
    assert len(body["sha"]) == 16 and body["has_previous"] is False
    assert body["raw"] == "# plan\n"  # existing fields unchanged
    ui._snapshot_to_previous(_stp(env, "RL-1"), "20260101000000")
    assert client.get("/api/artifacts/RL-1/stp").json()["has_previous"] is True


# --- PUT edit ----------------------------------------------------------------

def test_edit_saves_snapshots_marks_stale_and_drops_the_approval(env):
    jid = "RL-2"
    state = _stp_only(env, jid, {"stp": {"status": "completed", "verdict": "APPROVED",
                                         "findings": {"critical": 0, "major": 2, "minor": 0}}})
    ui._write_approvals(jid, {"stp_review": {"status": "approved"}, "std_review": {"status": "approved"}})

    r = _put(jid, "stp", "# plan\n\nA new scenario.\n", _sha(jid, "stp"))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"status": "saved", "sha": _sha(jid, "stp"), "has_previous": True, "review_stale": True}
    assert _stp(env, jid).read_text() == "# plan\n\nA new scenario.\n"
    diff = client.get(f"/api/artifacts/{jid}/stp/diff").json()
    assert diff["has_diff"] and "+A new scenario." in diff["diff"]
    stp = _phase(state, "stp")
    assert stp["status"] == "completed" and stp["verdict"] == "APPROVED"
    assert stp["review_stale"] is True and "findings" not in stp
    assert stp["edited_by"] == "api-key" and stp["edited_ts"]
    assert stp["edit_history"] == [{"ts": stp["edited_ts"], "by": "api-key"}]
    assert ui._read_approvals(jid) == {"std_review": {"status": "approved"}}
    row = _audit_rows(env)[-1]
    assert row["action"] == "edit_artifact" and row["kind"] == "stp" and row["bytes"] == len("# plan\n\nA new scenario.\n")
    assert "new scenario" not in json.dumps(row)
    detail = client.get(f"/api/pipelines/{jid}").json()["phases"]["stp"]
    assert detail["review_stale"] is True and detail["edit_history"]


def test_edit_history_is_capped(env):
    jid = "RL-3"
    state = _stp_only(env, jid)
    for i in range(12):
        assert _put(jid, "stp", f"# plan v{i}\n", _sha(jid, "stp")).status_code == 200
    assert len(_phase(state, "stp")["edit_history"]) == 10
    assert len(list(_stp(env, jid).parent.glob(".previous-*"))) <= ui._PREVIOUS_ROTATIONS_KEPT


def test_edit_keeps_the_dashboard_name_as_a_display_only_claim(env):
    jid = "RL-31"
    state = _stp_only(env, jid)
    r = client.put(f"/api/artifacts/{jid}/stp", headers=HDR,
                   json={"content": "# plan\n", "base_sha": _sha(jid, "stp"), "display_name": "Ema"})
    assert r.status_code == 200
    stp = _phase(state, "stp")
    assert stp["edited_by"] == "api-key"  # identity stays server-resolved
    assert stp["edited_name"] == "Ema"
    assert stp["edit_history"][-1] == {"ts": stp["edited_ts"], "by": "api-key", "claimed_name": "Ema"}


def test_std_edit_on_a_ticket_without_state_creates_the_entry(env):
    jid = "RL-4"
    (env / jid / "std").mkdir(parents=True)
    (env / jid / "std" / f"{jid}_test_description.yaml").write_text("scenarios: []\n")
    r = _put(jid, "std", "scenarios:\n  - id: S1\n", _sha(jid, "std"))
    assert r.status_code == 200, r.text
    std = _phase(env / jid / "state" / "pipeline_state.yaml", "std")
    assert std["status"] == "completed" and std["review_stale"] is True


def test_edit_with_a_stale_base_sha_is_409(env):
    _stp_only(env, "RL-5")
    r = _put("RL-5", "stp", "# mine\n", "0" * 16)
    assert r.status_code == 409
    assert "changed since you opened it" in r.json()["detail"]
    assert _stp(env, "RL-5").read_text() == "# plan\n"


def test_edit_after_downstream_was_generated_is_409(env):
    _seed_ticket(env, "RL-6", {"stp": {"status": "completed"}})  # STD on disk
    r = _put("RL-6", "stp", "# mine\n", _sha("RL-6", "stp"))
    assert r.status_code == 409 and "reset from STD" in r.json()["detail"]
    assert not list(_stp(env, "RL-6").parent.glob(".previous-*"))


def test_edit_while_a_run_holds_the_ticket_is_409(env, monkeypatch):
    _stp_only(env, "RL-7")
    monkeypatch.setitem(ui._running_tasks, "RL-7/stp_review", {"status": "running"})
    r = _put("RL-7", "stp", "# mine\n", _sha("RL-7", "stp"))
    assert r.status_code == 409 and "run in progress" in r.json()["detail"]
    assert _stp(env, "RL-7").read_text() == "# plan\n"


@pytest.mark.parametrize("kind,content,base_sha,needle", [
    ("stp", "   \n", "x", "non-empty"),
    ("stp", 42, "x", "non-empty"),
    ("stp", "x" * (512 * 1024 + 1), "x", "too large"),
    ("stp", "# ok\n", "", "base_sha"),
    ("std", "scenarios: [\n", "x", "STD YAML does not parse"),
    ("std", "- a list\n", "x", "STD YAML does not parse"),
    ("stp_review", "# ok\n", "x", "Only the STP and STD"),
])
def test_edit_validation_is_400(env, kind, content, base_sha, needle):
    _seed_ticket(env, "RL-8", {})
    r = client.put(f"/api/artifacts/RL-8/{kind}", headers=HDR, json={"content": content, "base_sha": base_sha})
    assert r.status_code == 400, r.text
    assert needle in r.json()["detail"]


def test_edit_of_a_missing_document_is_404(env):
    assert _put("RL-9", "stp", "# x\n", "x").status_code == 404


def test_edit_needs_the_api_key(env):
    _stp_only(env, "RL-10")
    r = client.put("/api/artifacts/RL-10/stp", json={"content": "# x\n", "base_sha": _sha("RL-10", "stp")})
    assert r.status_code == 403


# --- refine snapshot -----------------------------------------------------------

def test_accepted_refine_snapshots_the_document(env, monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)
    _stp_only(env, "RL-11")
    r = client.post("/api/pipelines/RL-11/run/stp_refine", headers=HDR, json=MEMBER)
    assert r.status_code == 200, r.text
    snaps = list(_stp(env, "RL-11").parent.glob(".previous-*/RL-11_test_plan.md"))
    assert len(snaps) == 1 and snaps[0].read_text() == "# plan\n"


@pytest.mark.parametrize("stale,flag", [(True, True), (False, False), (None, False)])
def test_refine_of_an_edited_document_asks_for_a_rereview(env, monkeypatch, stale, flag):
    seen, started = {}, threading.Event()
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: (seen.update(k), started.set()))
    stp = {"status": "completed"} if stale is None else {"status": "completed", "review_stale": stale}
    _stp_only(env, "RL-19", {"stp": stp})
    assert client.post("/api/pipelines/RL-19/run/stp_refine", headers=HDR, json=MEMBER).status_code == 200
    assert started.wait(5) and seen["rereview"] is flag


@pytest.mark.parametrize("runtime", ["claude", "cursor"])
@pytest.mark.parametrize("phase,rereview,prompt", [
    ("std_refine", True, "/refine-std PROJ-1 --address-findings --rereview"),
    ("stp_refine", False, "/refine-stp PROJ-1 --address-findings"),
    ("stp_review", True, "/review-stp PROJ-1"),  # only a refine takes the flag
])
def test_runner_prompt_carries_rereview(capture_run, runtime, phase, rereview, prompt):
    import pipeline_runner
    pipeline_runner.run_phase("", "PROJ-1", phase, runtime=runtime, rereview=rereview)
    argv = capture_run[0]
    assert isinstance(argv, list) and argv[argv.index("-p") + 1] == prompt


def test_background_passes_rereview_to_the_runner(env, monkeypatch):
    import pipeline_runner
    got = {}
    monkeypatch.setattr(pipeline_runner, "run_phase", lambda *a, **k: got.update(k) or {"output": ""})
    _stp_only(env, "RL-20")
    ui._run_phase_background("RL-20", "stp_refine", rereview=True)
    assert got["rereview"] is True


# --- re-run review -------------------------------------------------------------

def test_review_without_the_document_is_409(env, monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)
    r = client.post("/api/pipelines/RL-12/run/std_review", headers=HDR, json=MEMBER)
    assert r.status_code == 409 and r.json()["detail"] == "Run STD first"


def test_review_toggle_off_is_400(env, monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)
    _stp_only(env, "RL-13")
    _write_project(ui.CONFIG, "example", {"stp_review": False})
    r = client.post("/api/pipelines/RL-13/run/stp_review", headers=HDR, json=MEMBER)
    assert r.status_code == 400 and "stp_review" in r.json()["detail"]


def test_review_is_allowed_after_downstream_was_generated(env, monkeypatch):
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)
    _seed_ticket(env, "RL-14", {"stp": {"status": "completed"}})  # STD on disk
    assert client.post("/api/pipelines/RL-14/run/stp_review", headers=HDR, json=MEMBER).status_code == 200


def test_completed_review_refreshes_the_verdict_and_keeps_the_approval(env, monkeypatch):
    import pipeline_runner
    jid = "RL-15"
    state = _stp_only(env, jid, {"stp": {"status": "completed", "verdict": "NEEDS_REVISION",
                                         "review_stale": True,
                                         "findings": {"critical": 1, "major": 0, "minor": 0}}})
    ui._write_approvals(jid, {"stp_review": {"status": "approved"}})
    review = _review(env, jid, "stp", "NEEDS_REVISION")
    old = time.time() - 3600
    os.utime(review, (old, old))

    def rereview(*a, **k):  # the re-review overwrites the existing report
        review.write_text("# Review\n\nVerdict: APPROVED\n")
        return {"output": "done"}
    monkeypatch.setattr(pipeline_runner, "run_phase", rereview)

    ui._run_phase_background(jid, "stp_review")

    assert _phase(state, "stp_review")["status"] == "completed"
    stp = _phase(state, "stp")
    assert stp["verdict"] == "APPROVED" and stp["review_stale"] is False
    assert stp["reviewed_ts"] == _phase(state, "stp_review")["finished_ts"]
    assert "findings" not in stp and "refined_ts" not in stp
    assert ui._read_approvals(jid) == {"stp_review": {"status": "approved"}}


def test_review_that_wrote_nothing_is_blocked_not_completed(env, fake_runner):
    jid = "RL-16"
    state = _stp_only(env, jid, {"stp": {"status": "completed", "verdict": "APPROVED", "review_stale": True}})
    review = _review(env, jid, "stp", "NEEDS_REVISION")
    old = time.time() - 3600
    os.utime(review, (old, old))  # the previous review, untouched by this run

    ui._run_phase_background(jid, "stp_review")

    assert _phase(state, "stp_review")["status"] == "blocked"
    stp = _phase(state, "stp")
    assert stp["verdict"] == "APPROVED" and stp["review_stale"] is True


def test_completed_refine_marks_the_review_fresh(env, fake_runner):
    jid = "RL-17"
    state = _stp_only(env, jid, {"stp": {"status": "completed", "review_stale": True}})
    _review(env, jid, "stp", "APPROVED")
    ui._run_phase_background(jid, "stp_refine", actor="alice@example.com")
    stp = _phase(state, "stp")
    assert stp["review_stale"] is False and stp["reviewed_ts"] == stp["refined_ts"]


# --- git sync --------------------------------------------------------------------

def test_git_sync_keeps_a_locally_edited_output_across_syncs(env, fake_git):
    remote_out = fake_git.parent / "outputs" / "SY-1" / "stp"
    remote_out.mkdir(parents=True)
    (remote_out / "SY-1_test_plan.md").write_text("git-v1\n")
    (remote_out / "untouched.md").write_text("git-v1\n")
    assert ui._git_sync()["status"] == "ok"
    local = ui.OUTPUTS / "SY-1" / "stp"
    assert (local / "SY-1_test_plan.md").read_text() == "git-v1\n"

    (local / "SY-1_test_plan.md").write_text("dashboard-edit\n")
    (remote_out / "untouched.md").write_text("git-v2\n")
    assert ui._git_sync()["status"] == "ok"
    assert ui._git_sync()["status"] == "ok"  # a second pass: the floor has moved past the edit

    assert (local / "SY-1_test_plan.md").read_text() == "dashboard-edit\n"
    assert (local / "untouched.md").read_text() == "git-v2\n"


# --- snapshots stay local ----------------------------------------------------------

def test_snapshots_are_not_pushed_as_docs(env):
    jid = "RL-18"
    _stp_only(env, jid)
    ui._snapshot_to_previous(_stp(env, jid), "20260101000000")
    docs = [d["path"] for d in ui._collect_pr_files(jid)["docs"]]
    assert docs == [f"docs/qualityflow/{jid}/stp/{jid}_test_plan.md"]
