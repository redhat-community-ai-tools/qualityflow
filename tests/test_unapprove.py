"""Un-approve: take back a gate decision so the document can be worked on again.

The document goes back to awaiting approval. What was already built from it
(the STD from an STP, tests from an STD) would no longer match, so it is
archived like Reset Phase, but only when the caller confirms (cascade).
Reuses test_mutating_routes.py's fixtures.
"""
import yaml

from test_mutating_routes import HDR, _seed_ticket, client, env, ui  # noqa: F401 — fixtures


def _approve(jid, doc="stp"):
    r = client.post(f"/api/pipelines/{jid}/approve/{doc}", headers=HDR, json={"action": "approve"})
    assert r.status_code == 200, r.text


def _unapprove(jid, doc="stp", **extra):
    return client.post(f"/api/pipelines/{jid}/approve/{doc}", headers=HDR,
                       json={"action": "unapprove", **extra})


def test_unapprove_with_nothing_built_reopens_the_stp(env):
    jid = "UNA-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    (env / jid / "std" / f"{jid}_test_description.yaml").unlink()  # no STD yet
    _approve(jid)

    r = _unapprove(jid, comment="more changes after review")
    assert r.status_code == 200, r.text
    assert r.json()["reset"] == []
    assert "stp_review" not in ui._read_approvals(jid)
    assert (env / jid / "stp" / f"{jid}_test_plan.md").exists()  # the plan stays
    assert client.get(f"/api/pipelines/{jid}").json()["phases"]["stp"]["status"] == "awaiting_approval"


def test_unapprove_refuses_when_an_std_exists_unless_confirmed(env):
    jid = "UNA-2"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}, "std": {"status": "completed"}})
    _approve(jid)

    r = _unapprove(jid)
    assert r.status_code == 409
    assert "Confirm" in r.json()["detail"]
    assert ui._read_approvals(jid)["stp_review"]["status"] == "approved"  # nothing changed
    assert (env / jid / "std" / f"{jid}_test_description.yaml").exists()


def test_confirmed_unapprove_archives_the_std_and_reopens_the_stp(env):
    jid = "UNA-3"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}, "std": {"status": "awaiting_approval"}})
    _approve(jid)
    _approve(jid, "std")

    r = _unapprove(jid, cascade=True)
    assert r.status_code == 200, r.text
    assert "std" in r.json()["reset"]
    assert not (env / jid / "std" / f"{jid}_test_description.yaml").exists()
    assert list((env / jid).rglob(".previous-*")), "the STD is archived, not deleted"
    assert ui._read_approvals(jid) == {}  # both decisions are gone
    phases = yaml.safe_load((env / jid / "state" / "pipeline_state.yaml").read_text())["phases"]
    assert phases["std"] == {"status": "pending"}
    assert (env / jid / "stp" / f"{jid}_test_plan.md").exists()


def test_unapprove_without_a_decision_is_409(env):
    jid = "UNA-4"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    r = _unapprove(jid, cascade=True)
    assert r.status_code == 409
    assert "no decision" in r.json()["detail"]
    assert (env / jid / "std" / f"{jid}_test_description.yaml").exists()
