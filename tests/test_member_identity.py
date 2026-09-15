#!/usr/bin/env python3
"""Per-member identity and metrics (PR 2).

Attribution comes from the member's own Jira token, verified server-side via
GET /rest/api/2/myself — never from a name the browser claims. The HTTP call is
mocked at urllib.request.urlopen; no test reaches a real Jira (conftest stubs
_jira_identity for every other test; this file restores the real one).

Same conventions as tests/test_mutating_routes.py: QF_DEV/QF_OUTPUTS_DIR set
before `import ui`, globals monkeypatched per test, TestClient not entered.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_member_identity.py -q
"""
import io
import json
import logging
import os
import socket
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

REAL_JIRA_IDENTITY = ui._jira_identity  # captured before conftest's per-test stub
client = TestClient(ui.app)
KEY = "memberkey"
HDR = {"X-API-Key": KEY}
BASE = "https://jira.example.com"
TOKEN = "FAKE-jira-token-not-real-0000"
ALICE = {"accountId": "acc-alice", "emailAddress": "Alice@Example.com", "displayName": "Alice A"}


class _FakeJira:
    """urlopen stand-in: answers /myself per token, counts calls."""

    def __init__(self):
        self.calls = 0
        self.by_token = {TOKEN: ALICE}
        self.raise_exc = None

    def __call__(self, req, context=None, timeout=None):
        self.calls += 1
        assert req.full_url == f"{BASE}/rest/api/2/myself"
        if self.raise_exc:
            raise self.raise_exc
        import base64
        user, _, tok = base64.b64decode(req.headers["Authorization"].split()[1]).decode().partition(":")
        if tok not in self.by_token:
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))
        return io.BytesIO(json.dumps(self.by_token[tok]).encode())


@pytest.fixture
def jira(monkeypatch):
    fake = _FakeJira()
    monkeypatch.setattr(ui, "_jira_identity", REAL_JIRA_IDENTITY)
    monkeypatch.setattr(ui, "_jira_identity_cache", {})
    monkeypatch.setattr(ui.urllib.request, "urlopen", fake)
    monkeypatch.setenv("JIRA_URL", BASE)
    return fake


@pytest.fixture
def env(tmp_path, monkeypatch, jira):
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "CONFIG", tmp_path / "config")
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_USAGE_LOG", out / "_usage" / "dashboard_usage.jsonl")
    monkeypatch.setattr(ui, "_API_KEY", KEY)
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    monkeypatch.setattr(ui, "_slack_pipeline_event", lambda *a, **k: None)
    monkeypatch.setattr(ui, "_get_approval_gates", lambda _pid: ["stp", "std"])
    monkeypatch.setattr(ui, "_infer_project", lambda _jid: "example")
    monkeypatch.setattr(ui, "_running_tasks", {})
    monkeypatch.setattr(ui, "_claude_available", lambda: True)
    monkeypatch.setattr(ui, "_VERTEX_PROJECT", "")
    return out


def _state(out: Path, jid: str, phases: dict) -> Path:
    path = out / jid / "state" / "pipeline_state.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"ticket_id": jid, "phases": phases}, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# _jira_identity
# ---------------------------------------------------------------------------

def test_myself_200_returns_identity_and_is_cached(jira):
    ident, err = ui._jira_identity("alice@example.com", TOKEN, BASE)
    assert err is None
    assert ident == {"account_id": "acc-alice", "email": "alice@example.com", "display_name": "Alice A"}
    assert ui._jira_identity("alice@example.com", TOKEN, BASE) == (ident, None)
    assert jira.calls == 1  # second lookup served from cache
    ui._jira_identity("alice@example.com", "other-token", BASE)
    assert jira.calls == 2  # cache is keyed by the credential, not the username


def test_myself_401_is_invalid_credentials_and_cached(jira):
    assert ui._jira_identity("alice@example.com", "wrong", BASE) == (None, "invalid Jira credentials")
    ui._jira_identity("alice@example.com", "wrong", BASE)
    assert jira.calls == 1


def test_myself_timeout_is_none_and_not_cached(jira):
    jira.raise_exc = socket.timeout("timed out")
    ident, err = ui._jira_identity("alice@example.com", TOKEN, BASE)
    assert ident is None and err == "could not reach Jira"
    ui._jira_identity("alice@example.com", TOKEN, BASE)
    assert jira.calls == 2  # a transient failure must not stick for an hour


def test_no_creds_or_unconfigured_jira_makes_no_call(jira):
    assert ui._jira_identity("", TOKEN, BASE) == (None, None)
    assert ui._jira_identity("alice@example.com", TOKEN, ui._JIRA_URL_PLACEHOLDER) == \
        (None, "Jira URL not configured on this dashboard")
    assert jira.calls == 0


def test_myself_403_is_an_error_but_not_cached(jira):
    """403 is Jira's CAPTCHA/lockout answer, not proof the token is wrong."""
    jira.raise_exc = urllib.error.HTTPError(BASE, 403, "Forbidden", {}, io.BytesIO(b""))
    ident, err = ui._jira_identity("alice@example.com", TOKEN, BASE)
    assert ident is None and "403" in err
    jira.raise_exc = None
    assert ui._jira_identity("alice@example.com", TOKEN, BASE)[0]["email"] == "alice@example.com"
    assert jira.calls == 2


def test_cache_is_bounded(jira, monkeypatch):
    monkeypatch.setattr(ui, "_JIRA_IDENTITY_MAX", 3)
    for i in range(5):
        jira.by_token[f"t{i}"] = ALICE
        ui._jira_identity("alice@example.com", f"t{i}", BASE)
    assert len(ui._jira_identity_cache) == 3


def test_token_never_reaches_logs(jira, caplog):
    caplog.set_level(logging.DEBUG)
    ui._jira_identity("alice@example.com", TOKEN, BASE)
    ui._jira_identity("alice@example.com", TOKEN + "x", BASE)  # 401
    jira.raise_exc = urllib.error.HTTPError(BASE, 500, "boom", {}, io.BytesIO(b""))
    ui._jira_identity("bob@example.com", TOKEN + "y", BASE)
    jira.raise_exc = socket.timeout("timed out")
    ui._jira_identity("carol@example.com", TOKEN + "z", BASE)
    assert TOKEN not in caplog.text


# ---------------------------------------------------------------------------
# /api/whoami
# ---------------------------------------------------------------------------

def test_whoami_verified_via_jira(env):
    r = client.post("/api/whoami", headers=HDR, json={"jira_username": "alice@example.com", "jira_token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json() == {"verified": True, "email": "alice@example.com", "actor": "alice@example.com",
                        "display_name": "Alice A", "source": "jira"}
    assert TOKEN not in r.text


def test_whoami_invalid_creds_reports_the_error(env):
    r = client.post("/api/whoami", headers=HDR, json={"jira_username": "alice@example.com", "jira_token": "bad"})
    body = r.json()
    assert body["verified"] is False and body["source"] == "none"
    assert body["error"] == "invalid Jira credentials"


def test_whoami_without_creds_is_unverified(env):
    body = client.post("/api/whoami", headers=HDR, json={}).json()
    assert body == {"verified": False, "email": "", "actor": "api-key", "display_name": "", "source": "none"}


def test_whoami_checks_the_selected_projects_jira(env, monkeypatch):
    """Runs of a project use its jira.yaml when JIRA_URL is unset — whoami must
    verify against that same Jira, and say so plainly when there is none."""
    monkeypatch.delenv("JIRA_URL")
    creds = {"jira_username": "alice@example.com", "jira_token": TOKEN}
    body = client.post("/api/whoami", headers=HDR, json=creds).json()
    assert body["verified"] is False and body["error"] == "Jira URL not configured on this dashboard"

    (ui.CONFIG / "projects" / "proj1").mkdir(parents=True)
    (ui.CONFIG / "projects" / "proj1" / "jira.yaml").write_text(f"instance:\n  url: {BASE}\n")
    body = client.post("/api/whoami", headers=HDR, json=dict(creds, project="proj1")).json()
    assert body["verified"] is True and body["email"] == "alice@example.com"
    # A project id is a config path segment — anything else is ignored, not followed.
    body = client.post("/api/whoami", headers=HDR, json=dict(creds, project="../proj1")).json()
    assert body["verified"] is False


def test_whoami_requires_the_api_key(env):
    assert client.post("/api/whoami", json={}).status_code == 403


# ---------------------------------------------------------------------------
# actor on the run record
# ---------------------------------------------------------------------------

def test_run_records_verified_actor_and_completion_preserves_it(env, monkeypatch):
    import pipeline_runner
    jid = "MEM-1"
    state_file = _state(env, jid, {"stp": {"status": "completed", "model": "old", "finished_ts": "t0"}})
    (env / jid / "stp").mkdir(parents=True)
    (env / jid / "stp" / f"{jid}_test_plan.md").write_text("# plan\n")
    real_worker = ui._run_phase_background
    monkeypatch.setattr(ui, "_run_phase_background", lambda *a, **k: None)

    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={"jira_username": "alice@example.com", "jira_token": TOKEN, "github_token": "FAKE-gh"})
    assert r.status_code == 200, r.text
    ph = yaml.safe_load(state_file.read_text())["phases"]["stp"]
    assert ph["status"] == "in_progress"
    assert (ph["actor"], ph["actor_name"]) == ("alice@example.com", "Alice A")
    assert ph["history"] == [{"status": "completed", "model": "old", "finished_ts": "t0"}]  # historic: no actor
    assert ui._running_tasks[f"{jid}/stp"]["actor"] == "alice@example.com"
    rows = [json.loads(line) for line in (env / ".audit" / "audit.jsonl").read_text().splitlines()]
    assert {"action": "run_phase", "actor": "alice@example.com", "phase": "stp", "source": "jira"}.items() \
        <= rows[-1].items()
    assert TOKEN not in state_file.read_text() + (env / ".audit" / "audit.jsonl").read_text()

    monkeypatch.setattr(pipeline_runner, "run_phase", lambda *a, **k: {"output": "ok", "verdict": "APPROVED"})
    real_worker(jid, "stp")
    ph = yaml.safe_load(state_file.read_text())["phases"]["stp"]
    assert ph["status"] == "completed"
    assert (ph["actor"], ph["actor_name"]) == ("alice@example.com", "Alice A")

    # Next run's Jira lookup fails (401): attribution falls back, the run is NOT
    # blocked, and the finished attempt keeps its actor in history.
    r = client.post(f"/api/pipelines/{jid}/run/stp", headers=HDR,
                    json={"jira_username": "alice@example.com", "jira_token": "bad", "github_token": "FAKE-gh"})
    assert r.status_code == 200 and r.json()["status"] == "started", r.text
    ph = yaml.safe_load(state_file.read_text())["phases"]["stp"]
    assert ph["actor"] == "api-key"
    assert ph["history"][-1]["actor"] == "alice@example.com"


def test_cli_completing_the_phase_in_place_keeps_actor_and_does_not_double_count():
    """`state.py complete-phase` (std-builder, review-*, generate-tests) flips
    status to completed in the file BEFORE the background thread records the
    result. That entry is this run, not a previous one."""
    phases = {"std": {"status": "in_progress", "started_ts": "s1", "actor": "alice@example.com",
                      "actor_name": "Alice A",
                      "history": [{"status": "completed", "finished_ts": "f0", "actor": "bob@example.com"}]}}
    phases["std"].update(status="completed", completed="c1")  # the CLI's in-run write
    ui._record_phase_result(phases, "std", {"status": "completed", "finished_ts": "f1", "model": "m"})
    ph = phases["std"]
    assert (ph["actor"], ph["actor_name"], ph["started_ts"]) == ("alice@example.com", "Alice A", "s1")
    assert ph["history"] == [{"status": "completed", "finished_ts": "f0", "actor": "bob@example.com"}]

    # The next run archives it exactly once, with its actor.
    ui._record_phase_result(phases, "std", {"status": "in_progress", "started_ts": "s2", "actor": "carol@example.com"})
    assert [h.get("actor") for h in phases["std"]["history"]] == ["bob@example.com", "alice@example.com"]
    assert phases["std"]["started_ts"] == "s2" and phases["std"]["actor"] == "carol@example.com"

    # A pure-CLI result (no dashboard started_ts/finished_ts) is still archived as before.
    cli = {"stp": {"status": "completed", "started": "x", "completed": "y", "model": "old"}}
    ui._record_phase_result(cli, "stp", {"status": "in_progress", "started_ts": "s3", "actor": "dan@example.com"})
    assert cli["stp"]["history"] == [{"status": "completed", "model": "old"}]


def test_uploaded_state_cannot_forge_attribution(env):
    """POST /api/outputs holds only the shared key: uploaded actor fields are
    replaced by what this server recorded for the same attempt, or dropped."""
    import tarfile
    jid = "MEM-5"
    _state(env, jid, {"stp": {"status": "completed", "started_ts": "s1", "finished_ts": "f1",
                              "actor": "alice@example.com", "actor_name": "Alice A"}})
    forged = {"ticket_id": jid, "phases": {
        "stp": {"status": "completed", "started_ts": "s1", "finished_ts": "f1",
                "actor": "mallory@example.com", "actor_name": "Mallory"},
        "std": {"status": "completed", "finished_ts": "f2", "actor": "mallory@example.com",
                "history": [{"status": "failed", "finished_ts": "f0", "actor": "mallory@example.com"}]},
    }}

    r = client.post(f"/api/outputs/{jid}", headers=HDR,
                    json={"path": f"state/{jid}/pipeline_state.yaml", "content": yaml.safe_dump(forged)})
    assert r.status_code == 200, r.text
    stored = yaml.safe_load((env / "state" / jid / "pipeline_state.yaml").read_text())["phases"]
    assert (stored["stp"]["actor"], stored["stp"]["actor_name"]) == ("alice@example.com", "Alice A")
    assert "actor" not in stored["std"] and "actor" not in stored["std"]["history"][0]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = yaml.safe_dump(forged).encode()
        info = tarfile.TarInfo(f"state/{jid}/pipeline_state.yaml")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    r = client.post(f"/api/outputs/{jid}", headers={**HDR, "Content-Type": "application/gzip"},
                    content=buf.getvalue())
    assert r.status_code == 200, r.text
    text = (env / "state" / jid / "pipeline_state.yaml").read_text()
    assert "mallory" not in text and "alice@example.com" in text


def test_approve_uses_verified_jira_identity_as_reviewer(env):
    jid = "MEM-2"
    _state(env, jid, {"stp": {"status": "awaiting_approval"}})
    r = client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR,
                    json={"action": "approve", "reviewer": "Someone Else",
                          "jira_username": "alice@example.com", "jira_token": TOKEN})
    assert r.status_code == 200, r.text
    approval = r.json()["approval"]
    assert approval["reviewer"] == "alice@example.com"
    assert approval["claimed_name"] == "Someone Else"


def test_edit_uses_verified_jira_identity_as_editor(env):
    jid = "MEM-3"
    state = _state(env, jid, {"stp": {"status": "completed"}})
    stp = env / jid / "stp" / f"{jid}_test_plan.md"
    stp.parent.mkdir(parents=True)
    stp.write_text("# plan\n")
    sha = client.get(f"/api/artifacts/{jid}/stp").json()["sha"]
    r = client.put(f"/api/artifacts/{jid}/stp", headers=HDR,
                   json={"content": "# plan v2\n", "base_sha": sha, "display_name": "Someone Else",
                         "jira_username": "alice@example.com", "jira_token": TOKEN})
    assert r.status_code == 200, r.text
    doc = yaml.safe_load(state.read_text())["phases"]["stp"]
    assert doc["edited_by"] == "alice@example.com"
    assert doc["edited_name"] and doc["edited_name"] != "Someone Else"  # verified name beats the claim


# ---------------------------------------------------------------------------
# ?member= filters and /api/members
# ---------------------------------------------------------------------------

def _seed_team(out: Path):
    done = {"status": "completed", "started_ts": "2026-09-01T00:00:00+00:00",
            "finished_ts": "2026-09-01T00:10:00+00:00"}
    # MEM-11: alice ran stp (m1); bob's std attempt only survives in history (m2).
    _state(out, "MEM-11", {
        "stp": dict(done, actor="alice@example.com", actor_name="Alice A", model="m1",
                    verdict="APPROVED", usage={"cost_usd": 1.0}),
        "std": dict(done, model="m3", verdict="APPROVED",
                    history=[{"status": "failed", "model": "m2", "actor": "bob@example.com", "actor_name": "Bob"}]),
        "codegen": dict(done),
    })
    # MEM-12: historic, nobody attributed.
    _state(out, "MEM-12", {
        "stp": dict(done, model="m1", verdict="APPROVED", usage={"cost_usd": 2.0}),
        "std": dict(done, model="m1", verdict="APPROVED"),
        "codegen": dict(done),
    })


def test_models_member_filter_is_attempt_level(env):
    _seed_team(env)
    team = client.get("/api/metrics/models?project=all").json()["models"]
    assert team["m1"]["n"] == 3 and team["m2"]["n"] == 1 and team["m3"]["n"] == 1
    alice = client.get("/api/metrics/models?project=all&member=ALICE@example.com").json()["models"]
    assert set(alice) == {"m1"} and alice["m1"]["n"] == 1  # MEM-11's m3 and MEM-12 excluded
    bob = client.get("/api/metrics/models?project=all&member=bob@example.com").json()["models"]
    assert set(bob) == {"m2"}


def test_roi_member_filter_is_ticket_level(env):
    _seed_team(env)
    team = {t["jira_id"] for t in client.get("/api/metrics/roi?project=all").json()["per_ticket"]}
    assert team == {"MEM-11", "MEM-12"}
    alice = {t["jira_id"] for t in client.get("/api/metrics/roi?project=all&member=alice@example.com").json()["per_ticket"]}
    assert alice == {"MEM-11"}
    bob = client.get("/api/metrics/roi?project=all&member=bob@example.com").json()["per_ticket"]
    assert [t["jira_id"] for t in bob] == ["MEM-11"]  # a history-only attempt still counts


def test_engineering_member_filter(env):
    _seed_team(env)
    assert client.get("/api/metrics/engineering?project=all").json()["n_completed_runs"] == 2
    assert client.get("/api/metrics/engineering?project=all&member=alice@example.com").json()["n_completed_runs"] == 1
    assert client.get("/api/metrics/engineering?project=all&member=nobody@example.com").json()["n_completed_runs"] == 0


def test_quality_trend_member_filter(env):
    _seed_team(env)
    team = {r["jira_id"] for r in client.get("/api/metrics/quality-trend?project=all").json()["runs"]}
    assert team == {"MEM-11", "MEM-12"}
    alice = client.get("/api/metrics/quality-trend?project=all&member=alice@example.com").json()
    assert [r["jira_id"] for r in alice["runs"]] == ["MEM-11"]


def test_members_lists_distinct_actors_without_unattributed(env):
    _seed_team(env)
    _state(env, "MEM-13", {"stp": {"status": "completed", "actor": "api-key"},
                           "std": {"status": "completed", "actor": "anonymous"}})
    body = client.get("/api/members?project=all").json()
    assert body["members"] == [
        {"email": "alice@example.com", "name": "Alice A", "runs": 1},
        {"email": "bob@example.com", "name": "Bob", "runs": 1},
    ]
