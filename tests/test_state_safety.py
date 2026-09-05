#!/usr/bin/env python3
"""State-safety regressions (wave W4): the DATA-01 defects.

DATA-01-F2   reset kept the approval (written under stp_review, deleted under
             stp) and never touched pipeline_state.yaml, so the regenerated
             document inherited the old sign-off and the pipeline still read
             "completed" with zero artifacts            [D01-11, D01-12]
DATA-01-F1   _write_yaml was Path.write_text — truncate-in-place, 11 callers
             including approvals.yaml and pr_info.yaml   [D01-03, D01-04, D01-08]
DATA-01-F3   /api/pipelines/matrix never applied the approval-gate overlay the
             list and detail routes apply                [D01-10]
DATA-01-F4   routing.yaml was read-modify-write with no lock and no tmp+rename;
             project.yaml had two writers with different locking [D01-05, D01-06]
DATA-01-F5   coverage history.yaml read-modify-write raced between the upload
             route and the collection worker             [D01-07]
F6/F7 + F12  the outputs upload had no expanded-size or member cap (tar bomb),
             no rollback on a mid-copy OSError, and validated only the path
             prefix, so an upload for ticket X wrote artifacts for ticket Y
                                                         [D01-31..D01-34]

Same conventions as tests/test_metrics_endpoints.py and tests/test_reliability.py:
QF_DEV/QF_OUTPUTS_DIR set before `import ui`, ui is a module-level singleton so
globals are monkeypatched per test, and the module-level TestClient is NOT
entered as a context manager (that would run the lifespan against real outputs/).

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_state_safety.py -q
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import types
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

KEY = "w4testkey"
HDR = {"X-API-Key": KEY}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh tmp outputs/ + config/ per test, with every module global that was
    derived from them at import time re-pointed."""
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
    return out


def _seed_ticket(out: Path, jira_id: str, phases: dict) -> Path:
    """A ticket with real artifacts and a real pipeline_state.yaml."""
    (out / jira_id / "stp").mkdir(parents=True)
    (out / jira_id / "stp" / f"{jira_id}_test_plan.md").write_text("# plan\n")
    (out / jira_id / "std").mkdir(parents=True)
    (out / jira_id / "std" / f"{jira_id}_test_description.yaml").write_text("scenarios: []\n")
    state = out / jira_id / "state" / "pipeline_state.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(yaml.safe_dump({"ticket_id": jira_id, "project_id": "example",
                                     "phases": phases}, sort_keys=False))
    return state


# ---------------------------------------------------------------------------
# D01-11 / D01-12 — reset clears the approval AND the phase status
# ---------------------------------------------------------------------------

def test_reset_clears_approval_and_phase_status(env):
    jid = "RST-1"
    state_file = _seed_ticket(env, jid, {
        "stp": {"status": "completed", "output": "stp/x.md", "verdict": "APPROVED"},
        "std": {"status": "completed", "output": "std/y.yaml"},
        "codegen": {"status": "completed"},
    })

    r = client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR, json={"action": "approve"})
    assert r.status_code == 200, r.text
    approvals_file = env / jid / "state" / "approvals.yaml"
    assert "stp_review" in yaml.safe_load(approvals_file.read_text())

    r = client.post(f"/api/pipelines/{jid}/reset/stp", headers=HDR)
    assert r.status_code == 200, r.text

    # D01-11: neither the canonical gate key nor the legacy phase key survives.
    approvals = yaml.safe_load(approvals_file.read_text()) or {}
    assert "stp_review" not in approvals
    assert "stp" not in approvals

    # D01-12: pipeline_state.yaml no longer claims the reset phases completed,
    # and the stale output/verdict keys are gone with them.
    phases = yaml.safe_load(state_file.read_text())["phases"]
    assert [phases[p]["status"] for p in ("stp", "std", "codegen")] == ["pending"] * 3
    assert "output" not in phases["stp"] and "verdict" not in phases["stp"]

    detail = client.get(f"/api/pipelines/{jid}").json()
    assert detail["phases"]["stp"]["status"] != "completed"


def test_reset_does_not_create_a_state_file(env):
    """Reset of a ticket with no state file must not invent one — the inferred
    path is what the dashboard reads for those."""
    jid = "RST-2"
    (env / jid / "stp").mkdir(parents=True)
    (env / jid / "stp" / f"{jid}_test_plan.md").write_text("# plan\n")
    r = client.post(f"/api/pipelines/{jid}/reset/stp", headers=HDR)
    assert r.status_code == 200, r.text
    assert not (env / jid / "state" / "pipeline_state.yaml").exists()


# ---------------------------------------------------------------------------
# D01-03 / D01-04 / D01-08 — _write_yaml is atomic
# ---------------------------------------------------------------------------

def test_write_yaml_does_not_truncate_when_replace_fails(env, monkeypatch):
    target = env / "approvals.yaml"
    original = yaml.safe_dump({"stp_review": {"status": "approved"}}, sort_keys=False)
    target.write_text(original)

    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("ENOSPC")))
    with pytest.raises(OSError):
        ui._write_yaml(target, {"stp_review": {"status": "rejected"}})

    assert target.read_text() == original  # D01-04: no truncation, no silent loss
    assert list(env.glob("*.tmp")) == []


def test_write_yaml_and_atomic_update_leave_no_tmp(env):
    target = env / "pr_info.yaml"  # D01-08: same writer as approvals.yaml
    ui._write_yaml(target, {"url": "https://example.com/pull/1"})
    assert yaml.safe_load(target.read_text())["url"].endswith("/pull/1")

    ui._atomic_yaml_update(target, lambda d: {**d, "state": "open"})
    assert yaml.safe_load(target.read_text())["state"] == "open"
    assert list(env.glob("*.tmp")) == []
    # The sibling temp name must not collide with another file's real name.
    assert not (env / "pr_info.tmp").exists()


# ---------------------------------------------------------------------------
# D01-10 — matrix and detail agree on a gated phase
# ---------------------------------------------------------------------------

def test_matrix_applies_approval_gates(env):
    jid = "MTX-1"
    _seed_ticket(env, jid, {
        "stp": {"status": "completed"},
        "std": {"status": "completed"},
        "codegen": {"status": "pending"},
    })
    detail = client.get(f"/api/pipelines/{jid}").json()
    row = next(r for r in client.get("/api/pipelines/matrix").json() if r["jira_id"] == jid)
    assert detail["phases"]["std"]["status"] == "awaiting_approval"
    assert row["std"]["status"] == detail["phases"]["std"]["status"]


# ---------------------------------------------------------------------------
# D01-05 / D01-06 — routing.yaml and project.yaml writes
# ---------------------------------------------------------------------------

_ROUTING = 'routes:\n  - project: "example"\n    jira_prefixes:\n      - "EXA"\n\ndefault_project: example\n'

_NEW_PROJECT = {"project_id": "w4proj", "display_name": "W4", "jira_prefixes": ["W4X"],
                "jira_url": "https://jira.example.com", "feature_toggles": {}}


def test_create_project_writes_routing_atomically(env):
    routing = ui.CONFIG / "routing.yaml"
    routing.write_text(_ROUTING)

    r = client.post("/api/projects", headers=HDR, json=_NEW_PROJECT)
    assert r.status_code == 200, r.text

    content = routing.read_text()
    assert 'project: "w4proj"' in content and '- "W4X"' in content
    assert 'project: "example"' in content  # comments//existing routes preserved
    assert list(ui.CONFIG.glob("*.tmp")) == []
    assert list((ui.CONFIG / "projects" / "w4proj").glob("*.tmp")) == []
    # D01-06: project.yaml went through the same locked writer as update_toggles
    assert (ui.CONFIG / "projects" / "w4proj" / "project.yaml").exists()
    r = client.put("/api/projects/w4proj/toggles", headers=HDR,
                   json={"feature_toggles": {"stp_generation": False}})
    assert r.status_code == 200, r.text
    assert yaml.safe_load((ui.CONFIG / "projects" / "w4proj" / "project.yaml").read_text()
                          )["feature_toggles"]["stp_generation"] is False


def test_routing_survives_a_failed_replace(env, monkeypatch):
    routing = ui.CONFIG / "routing.yaml"
    routing.write_text(_ROUTING)

    real_replace = os.replace

    def fail_on_routing(src, dst, *a, **k):
        if str(dst).endswith("routing.yaml"):
            raise OSError("ENOSPC")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", fail_on_routing)
    with pytest.raises(OSError):  # TestClient re-raises server-side exceptions
        client.post("/api/projects", headers=HDR, json=_NEW_PROJECT)

    assert routing.read_text() == _ROUTING  # D01-05: original text intact
    assert list(ui.CONFIG.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# D01-07 — concurrent coverage history writes
# ---------------------------------------------------------------------------

def test_store_coverage_history_is_atomic_under_concurrency(env, monkeypatch):
    """/api/coverage/upload and the _collection_worker thread both call this.
    Widening the read-modify-write window makes the lost update deterministic
    instead of relying on the scheduler: unlocked, both threads read the same
    history and the loser's entry vanishes."""
    repo_dir = ui.COVERAGE_DIR / "acme" / "widget"
    repo_dir.mkdir(parents=True)
    (repo_dir / "history.yaml").write_text(yaml.safe_dump([{"commit": "seed0000"}]))

    real_read_text = Path.read_text

    def slow_read(self, *a, **k):
        out = real_read_text(self, *a, **k)
        if self.name == "history.yaml":
            time.sleep(0.05)  # hold the window open across the other thread's read
        return out

    monkeypatch.setattr(Path, "read_text", slow_read)

    payload = {"totals": {"coverage": 50.0}, "files": []}
    barrier = threading.Barrier(2)

    def store(commit):
        barrier.wait()
        ui._store_coverage("acme", "widget", commit, "main", payload)

    threads = [threading.Thread(target=store, args=(c,)) for c in ("aaaaaaa", "bbbbbbb")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    history = yaml.safe_load(real_read_text(repo_dir / "history.yaml"))
    assert sorted(h["commit"] for h in history) == ["aaaaaaa", "bbbbbbb", "seed0000"]
    assert list(repo_dir.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# D01-31..D01-34 — outputs upload: tar bomb, member cap, ticket scope, rollback
# ---------------------------------------------------------------------------

class _Zeros(io.RawIOBase):
    """Lazy zero stream — a 300 MB member without a 300 MB buffer."""

    def __init__(self, n):
        self.n = n

    def readable(self):
        return True

    def readinto(self, b):
        k = min(len(b), self.n)
        b[:k] = bytes(k)
        self.n -= k
        return k


def _targz(members) -> bytes:
    """members: list of (name, size_or_bytes)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            if isinstance(payload, int):
                info.size = payload
                tar.addfile(info, _Zeros(payload))
            else:
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _upload(jira_id: str, body: bytes):
    return client.post(f"/api/outputs/{jira_id}", headers={**HDR, "Content-Type": "application/gzip"},
                       content=body)


def test_upload_rejects_expanded_size_bomb(env):
    body = _targz([("stp/PART-1/big.md", 300 * 1024 * 1024)])
    assert len(body) < 50 * 1024 * 1024  # the compressed cap would not have caught it
    r = _upload("PART-1", body)
    assert r.status_code == 413, r.text
    assert not (env / "PART-1").exists()


def test_upload_rejects_too_many_members(env):
    body = _targz([(f"stp/PART-1/f{i}.md", b"x") for i in range(5001)])
    r = _upload("PART-1", body)
    assert r.status_code == 413, r.text
    assert not (env / "PART-1").exists()


def test_upload_rejects_member_for_another_ticket(env):
    body = _targz([("stp/PART-1/ok.md", b"ok"), ("stp/OTHER-9/evil.md", b"evil")])
    r = _upload("PART-1", body)
    assert r.status_code == 400, r.text
    assert not (env / "OTHER-9").exists()


def test_upload_rolls_back_a_failed_copy(env, monkeypatch):
    dest_a = env / "PART-1" / "stp" / "a.md"
    dest_a.parent.mkdir(parents=True)
    dest_a.write_text("OLD")

    real_copy2 = shutil.copy2
    calls = []

    def flaky(src, dst, *a, **k):
        calls.append(dst)
        if len(calls) == 3:
            raise OSError("ENOSPC")
        return real_copy2(src, dst, *a, **k)

    monkeypatch.setattr(shutil, "copy2", flaky)
    body = _targz([(f"stp/PART-1/{n}.md", b"NEW") for n in ("a", "b", "c")])
    r = _upload("PART-1", body)

    assert r.status_code >= 500, r.text
    assert dest_a.read_text() == "OLD"  # archived copy restored (or never clobbered)
    assert not (dest_a.parent / "b.md").exists()
    assert not (dest_a.parent / "c.md").exists()
    assert not (dest_a.parent / ".previous" / "a.md").exists()


# ---------------------------------------------------------------------------
# W9b / OBS-01-F6 — the audit trail is durable, and the actor is not forgeable
# ---------------------------------------------------------------------------

def _audit_rows(out: Path) -> list[dict]:
    """Every audit event on disk. The file is the deliverable — no read API."""
    log = out / ".audit" / "audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def test_approve_records_the_resolved_actor_not_the_name_the_client_claimed(env):
    """Live-demonstrated in OBS-01: a caller holding only the shared API key
    could put any name in body.reviewer and it was stored and echoed back as the
    approving actor. The audit identity is now always resolved server-side."""
    jid = "AUD-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})

    r = client.post(f"/api/pipelines/{jid}/approve/stp", headers=HDR,
                    json={"action": "approve", "reviewer": "ceo@example.com"})
    assert r.status_code == 200, r.text

    rows = [a for a in _audit_rows(env) if a["action"] == "approve_phase"]
    assert len(rows) == 1
    assert rows[0]["actor"] == "api-key"          # resolved from the credential
    assert rows[0]["jira_id"] == jid and rows[0]["phase"] == "stp"
    assert rows[0]["claimed_name"] == "ceo@example.com"  # kept, clearly as a claim
    # …and the stored decision agrees with the audit line.
    approvals = yaml.safe_load((env / jid / "state" / "approvals.yaml").read_text())
    assert approvals["stp_review"]["reviewer"] == "api-key"


def test_toggles_and_create_project_leave_a_durable_audit_record(env):
    """Both used to leave no audit trace anywhere — live-confirmed by OBS-01."""
    (ui.CONFIG / "routing.yaml").write_text(_ROUTING)
    assert client.post("/api/projects", headers=HDR, json=_NEW_PROJECT).status_code == 200
    assert client.put("/api/projects/w4proj/toggles", headers=HDR,
                      json={"feature_toggles": {"stp_generation": False}}).status_code == 200

    by_action = {a["action"]: a for a in _audit_rows(env)}
    assert by_action["create_project"]["project_id"] == "w4proj"
    assert by_action["create_project"]["actor"] == "api-key"
    assert by_action["update_toggles"]["project_id"] == "w4proj"
    assert json.loads(by_action["update_toggles"]["toggles"]) == {"stp_generation": False}


def test_reset_push_pr_and_close_pr_records_survive_on_disk(env, monkeypatch):
    """These three resolved the real actor already, but only to process stdout —
    no durable record and nothing to read it back from."""
    jid = "AUD-2"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    ui._write_pr_info(jid, {"url": "https://github.com/o/r/pull/1", "number": 1,
                            "target_repo": "o/r", "state": "open", "platform": "github"})
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setattr(ui, "_github_api", lambda *a, **k: {})

    # close first: a reset from stp clears pr_info.yaml, and the close route 404s
    # without it.
    assert client.post(f"/api/pipelines/{jid}/close-pr", headers=HDR,
                       json={"action": "close"}).status_code == 200
    assert client.post(f"/api/pipelines/{jid}/reset/stp", headers=HDR).status_code == 200

    actions = {a["action"]: a for a in _audit_rows(env)}
    assert actions["reset_phase"]["actor"] == "api-key"
    assert actions["reset_phase"]["archived_to"].startswith(".previous-")
    assert actions["close_pr"]["jira_id"] == jid


# ---------------------------------------------------------------------------
# W9b / DATA-01-F11 — destructive routes tombstone first and record who did it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", ["/api/pipelines/{jid}", "/api/outputs/{jid}"])
def test_delete_archives_before_removing_and_writes_an_audit_record(env, route):
    """Both used to rmtree the whole ticket — approvals, pr_info.yaml, run
    history — with no archive and, for /api/outputs, no record of who did it."""
    jid = "DEL-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    (env / jid / "state" / "approvals.yaml").write_text(
        yaml.safe_dump({"stp_review": {"status": "approved", "reviewer": "qe"}}))

    r = client.request("DELETE", route.format(jid=jid), headers=HDR)
    assert r.status_code == 200, r.text
    assert not (env / jid).exists()

    archives = sorted(env.glob(".previous-*/" + jid))
    assert len(archives) == 1, f"no tombstone: {list(env.iterdir())}"
    saved = yaml.safe_load((archives[0] / "state" / "approvals.yaml").read_text())
    assert saved["stp_review"]["reviewer"] == "qe"  # the non-regenerable part survived

    row = next(a for a in _audit_rows(env) if a["action"].startswith("delete_"))
    assert row["jira_id"] == jid and row["actor"] == "api-key"
    assert row["archived_to"] == archives[0].parent.name


def test_reset_test_coverage_writes_an_audit_record(env):
    proj = ui._test_cov_project_dir("example")
    (proj / "uploads").mkdir(parents=True)
    (proj / "uploads" / "a.yaml").write_text("coverage_pct: 1\n")

    r = client.delete("/api/coverage/test/example/reset", headers=HDR)
    assert r.status_code == 200, r.text
    row = next(a for a in _audit_rows(env) if a["action"] == "reset_test_coverage")
    assert row["project_id"] == "example" and row["actor"] == "api-key"


# ---------------------------------------------------------------------------
# W9b / REL-F07 — coverage history dedupes on (commit, branch)
# ---------------------------------------------------------------------------

def test_duplicate_coverage_uploads_do_not_evict_the_history(env):
    """A retried job, or a CI matrix uploading one shard per package, wrote N
    entries for one commit and pushed the real trend past the 50-entry cap."""
    payload = {"totals": {"coverage_pct": 70.0, "covered": 7, "total": 10}, "files": {}}
    for _ in range(3):
        ui._store_coverage("acme", "widget", "cafe1234", "main", payload)
    ui._store_coverage("acme", "widget", "cafe1234", "release", payload)  # other branch: kept
    ui._store_coverage("acme", "widget", "beef5678", "main", payload)

    history = ui._load_coverage_history("acme", "widget")
    assert [(h["commit"], h["branch"]) for h in history] == [
        ("beef5678", "main"), ("cafe1234", "release"), ("cafe1234", "main")]


# ---------------------------------------------------------------------------
# W9b / DATA-01-F9 — the std-nested test layout is visible to every consumer
# ---------------------------------------------------------------------------

def test_std_nested_tests_are_found_by_push_pr_the_rollup_and_the_viewer(env):
    """_find_test_files knew three layouts; _collect_pr_files, _ticket_test_count
    and the artifact viewer knew two, so a ticket counted as codegen-complete in
    the rollup while push-PR shipped the docs and silently omitted the tests."""
    jid = "LAY-1"
    _seed_ticket(env, jid, {"codegen": {"status": "completed"}})
    for lang, name, body in (("go", "qf_nad_test.go", "func TestNad(t *testing.T) {}\n"),
                             ("python", "qf_nad.py", "def test_nad():\n    pass\n")):
        d = env / "std" / jid / f"{lang}-tests"
        d.mkdir(parents=True)
        (d / name).write_text(body)

    assert len(ui._find_test_files(jid, "go")) == 1  # already true — the reference
    groups = ui._collect_pr_files(jid)
    assert [f["path"].rsplit("/", 1)[-1] for f in groups["primary"]] == ["qf_nad_test.go"]
    assert [f["path"].rsplit("/", 1)[-1] for f in groups["tier2"]] == ["qf_nad.py"]
    assert ui._ticket_test_count(jid) == 2

    for kind, name in (("go_test", "qf_nad_test.go"), ("python_test", "qf_nad.py")):
        r = client.get(f"/api/artifacts/{jid}/{kind}:{name}")
        assert r.status_code == 200, f"{kind} 404'd in the viewer: {r.text}"
        assert r.json()["path"].endswith(name)


# ---------------------------------------------------------------------------
# DATA-01-F10 — the metrics partition prefers the state file's own project_id
# ---------------------------------------------------------------------------

def test_metrics_partition_prefers_the_state_files_project_id(env, monkeypatch):
    """The partition re-derived the project from the Jira prefix, so a ticket
    whose state file says project_id: example landed under a phantom project
    "can" once routing lost the CAN route — /api/metrics/example then read zero
    for every value metric while /api/pipelines still listed the ticket."""
    jid = "CAN-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"},
                            "std": {"status": "completed"},
                            "codegen": {"status": "completed"}})
    # Real _infer_project behaviour with the CAN route missing: prefix.lower().
    monkeypatch.setattr(ui, "_infer_project", lambda j: j.split("-")[0].lower())

    assert client.get(f"/api/pipelines/{jid}").json()["project_id"] == "example"

    totals = client.get("/api/metrics/example").json()["totals"]
    assert totals["pipelines"] == 1, f"real project read zero: {totals}"
    assert totals["completed"] == 1

    projects = {p["project_id"] for p in client.get("/api/metrics/_all").json()["projects"]}
    assert "can" not in projects, f"phantom project from the prefix: {projects}"
    assert "example" in projects


# ---------------------------------------------------------------------------
# D01-08 (wave W10) — GET /api/pipelines/{id} refreshed PR state from GitHub and
# wrote pr_info.yaml inline: a read route blocking on a third-party API and
# mutating state. The lookup + write now run in a daemon thread.
# ---------------------------------------------------------------------------

PR_INFO = {"url": "https://github.com/o/r/pull/1", "number": 1,
           "target_repo": "o/r", "state": "open", "platform": "github"}


def test_get_pipeline_does_not_write_pr_info_itself(env, monkeypatch):
    jid = "PRBG-1"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    ui._write_pr_info(jid, PR_INFO)
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setattr(ui, "_pr_state_cache", {})
    # Anything the GET does on its own thread now blows up; only the worker may.
    monkeypatch.setattr(ui, "_write_pr_info",
                        lambda *a, **k: pytest.fail("GET wrote pr_info.yaml (D01-08)"))
    monkeypatch.setattr(ui, "_github_api",
                        lambda *a, **k: pytest.fail("GET called GitHub inline (D01-08)"))
    spawned: list[tuple] = []
    monkeypatch.setattr(ui, "_pr_state_refresh_worker",
                        lambda *a, **k: spawned.append(a))

    resp = client.get(f"/api/pipelines/{jid}")

    assert resp.status_code == 200
    assert resp.json()["pr"]["state"] == "open"  # last-known, straight off disk
    deadline = time.time() + 5
    while not spawned and time.time() < deadline:
        time.sleep(0.01)
    assert spawned, "no background PR refresh was started"
    assert spawned[0][0] == jid


def test_background_worker_persists_the_new_pr_state(env, monkeypatch):
    """The feature still works — the write just happens off the request path."""
    jid = "PRBG-2"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    ui._write_pr_info(jid, PR_INFO)
    monkeypatch.setattr(ui, "_pr_state_cache", {})
    monkeypatch.setattr(ui, "_github_api", lambda *a, **k: {"merged": True, "state": "closed"})

    ui._pr_state_refresh_worker(jid, dict(PR_INFO), "ghp_fake")

    assert ui._read_pr_info(jid)["state"] == "merged"


def test_one_refresh_thread_per_pr_per_ttl(env, monkeypatch):
    """The GET is polled; the cache slot is reserved before the thread starts."""
    jid = "PRBG-3"
    _seed_ticket(env, jid, {"stp": {"status": "completed"}})
    ui._write_pr_info(jid, PR_INFO)
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setattr(ui, "_pr_state_cache", {})
    started: list[int] = []
    monkeypatch.setattr(ui, "_pr_state_refresh_worker", lambda *a, **k: started.append(1))

    for _ in range(5):
        assert client.get(f"/api/pipelines/{jid}").status_code == 200
    time.sleep(0.2)

    assert len(started) == 1, f"spawned {len(started)} refresh threads for one PR"


# ---------------------------------------------------------------------------
# W11a — the last DATA-01 residuals
#
# D01-09  onboarding.yaml had two unlocked writers (a full overwrite in
#         _save_onboarding_state, a read-modify-write in list_onboarding)
# D01-23  the config-PVC initContainer used `cp -Rn`, so a *changed* shipped
#         default was never applied on upgrade                [deployment.yaml]
# D01-24  git sync's config tree copy reverted every dashboard/API edit
# D01-25  git sync never pruned a file deleted upstream
# D01-26  an unreachable remote at boot left the pod serving stale config mutely
# D01-29  reset_test_coverage deleted with no tombstone
# D01-35  the JSON coverage uploads checked the size after parsing the body
# D01-41  _atomic_write_text renamed without fsync
# ---------------------------------------------------------------------------

def test_onboarding_writers_share_the_yaml_lock(env, monkeypatch):
    """D01-09: both writers go through _atomic_yaml_update, and the refresh
    applies its update to the doc as it is on disk *now* — an onboarding POST
    that lands between the read and the write is not reverted."""
    ui._save_onboarding_state("acme", "widget", {
        "org": "acme", "repo": "widget", "status": "pr_created",
        "pr": {"url": "https://example.com/pr/1", "number": 1, "state": "open"},
    })
    state_file = ui.COVERAGE_DIR / "acme" / "widget" / "onboarding.yaml"
    assert state_file.with_suffix(".yaml.lock").exists(), "full-overwrite writer took no lock"

    def _concurrent_write(*_a, **_k):
        # A POST /api/coverage/onboard landing mid-refresh.
        ui._save_onboarding_state("acme", "widget", {
            **yaml.safe_load(state_file.read_text()), "landed_mid_refresh": True})
        return {"merged": True, "state": "closed"}

    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_fake")
    monkeypatch.setattr(ui, "_github_api", _concurrent_write)

    assert client.get("/api/coverage/onboarding").status_code == 200

    on_disk = yaml.safe_load(state_file.read_text())
    assert on_disk["pr"]["state"] == "merged"          # the refresh still applied
    assert on_disk["status"] == "merged"
    assert on_disk["landed_mid_refresh"] is True       # ...without reverting the writer it raced


def test_seed_config_applies_changed_defaults_but_keeps_operator_edits(tmp_path):
    """D01-23: the initContainer's seed script, run for real over three
    "upgrades". `cp -Rn` never got past the first block."""
    tpl = (ROOT / "deploy/helm/qualityflow-dashboard/templates/deployment.yaml").read_text()
    body = tpl.split("python3 - <<'PY'", 1)[1].split("\n              PY")[0]
    script = "\n".join(line[14:] for line in body.split("\n")[1:])
    assert "cp -Rn" not in script, "still the exists-skip seed"

    src, dst = tmp_path / "app", tmp_path / "data"
    (src / "sub").mkdir(parents=True)
    dst.mkdir()
    seed = tmp_path / "seed.py"
    seed.write_text(script.replace("/app/config", str(src)).replace("/data/config", str(dst)))

    def run():
        subprocess.run([sys.executable, str(seed)], check=True, capture_output=True)

    (src / "_defaults.yaml").write_text("v1\n")
    (src / "sub" / "project.yaml").write_text("v1\n")
    run()
    assert (dst / "_defaults.yaml").read_text() == "v1\n"    # seeded an empty PVC

    (src / "_defaults.yaml").write_text("v2\n")              # new image ships a new default
    (dst / "sub" / "project.yaml").write_text("operator\n")  # operator edits the other file
    run()
    assert (dst / "_defaults.yaml").read_text() == "v2\n"    # D01-23: the upgrade lands
    assert (dst / "sub" / "project.yaml").read_text() == "operator\n"

    (src / "sub" / "project.yaml").write_text("v2\n")        # and keeps landing...
    run()
    assert (dst / "sub" / "project.yaml").read_text() == "operator\n", \
        "an operator edit was clobbered by a later shipped default"


@pytest.fixture
def fake_git(tmp_path, monkeypatch):
    """A git remote that is really just a directory: _git_sync "clones" by
    finding the scratch tree already populated."""
    scratch = tmp_path / "scratch"
    (scratch / "config" / "projects").mkdir(parents=True)
    monkeypatch.setattr(ui, "_GIT_SCRATCH", scratch)
    monkeypatch.setattr(ui, "_last_sync", None)
    monkeypatch.setattr(ui, "_last_sync_ts", 0.0)
    monkeypatch.setenv("GIT_REPO_URL", "https://git.example.com/qf.git")
    fake = types.ModuleType("git")
    fake.Repo = type("Repo", (), {"clone_from": staticmethod(lambda *a, **k: None)})
    monkeypatch.setitem(sys.modules, "git", fake)
    return scratch / "config"


def test_git_sync_keeps_dashboard_edits_and_prunes_upstream_deletes(env, fake_git):
    """D01-24 + D01-25: git wins on the first sync and on files nobody touched;
    an edit made since the last sync survives; a file deleted upstream goes."""
    (fake_git / "projects" / "kept.yaml").write_text("git-v1\n")
    (fake_git / "projects" / "dropped.yaml").write_text("git-v1\n")
    (fake_git / "routing.yaml").write_text("git-v1\n")

    assert ui._git_sync()["status"] == "ok"
    assert (ui.CONFIG / "projects" / "kept.yaml").read_text() == "git-v1\n"

    # A dashboard edit, and a project the dashboard created that git has never
    # heard of. Then git moves on and deletes one of its own files.
    (ui.CONFIG / "projects" / "kept.yaml").write_text("dashboard-edit\n")
    (ui.CONFIG / "projects" / "ui-made.yaml").write_text("dashboard\n")
    (fake_git / "projects" / "kept.yaml").write_text("git-v2\n")
    (fake_git / "projects" / "dropped.yaml").unlink()
    (fake_git / "routing.yaml").write_text("git-v2\n")

    assert ui._git_sync()["status"] == "ok"

    # D01-24: the edit made since the last sync is not reverted...
    assert (ui.CONFIG / "projects" / "kept.yaml").read_text() == "dashboard-edit\n"
    # ...but a file the dashboard never touched still tracks git.
    assert (ui.CONFIG / "routing.yaml").read_text() == "git-v2\n"
    # D01-25: gone upstream, gone locally — but only for files git delivered.
    assert not (ui.CONFIG / "projects" / "dropped.yaml").exists()
    assert (ui.CONFIG / "projects" / "ui-made.yaml").read_text() == "dashboard\n"


def test_never_synced_remote_logs_a_stale_config_warning(env, monkeypatch):
    """D01-26: /readyz deliberately stays ready on a sync failure, so the loop
    has to say out loud that the config it is serving may be stale."""
    warnings: list[str] = []
    monkeypatch.setattr(ui, "_last_sync", None)
    monkeypatch.setattr(ui, "_git_sync", lambda: {"status": "error", "error": "unreachable"})
    monkeypatch.setattr(ui.logger, "warning", lambda msg, *a: warnings.append(msg % a))
    monkeypatch.setenv("GIT_REPO_URL", "https://git.example.com/qf.git")
    monkeypatch.setenv("GIT_SYNC_INTERVAL", "60")
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())

    ui._start_git_sync_loop()
    deadline = time.time() + 5
    while not warnings and time.time() < deadline:
        time.sleep(0.01)
    ui._shutdown_event.set()

    assert warnings, "an unreachable remote at boot produced no warning"
    assert "git.example.com" in warnings[0] and "STALE" in warnings[0]


def test_reset_test_coverage_archives_before_deleting(env):
    """D01-29: the last destructive route without a tombstone."""
    proj = ui._test_cov_project_dir("example")
    (proj / "prs").mkdir(parents=True)
    (proj / "prs" / "42.yaml").write_text("pr: 42\n")
    (proj / "uploads").mkdir()
    (proj / "uploads" / "u1.yaml").write_text("cov: 1\n")
    (proj / "history.yaml").write_text("- coverage: 71.5\n")
    (proj / "latest.yaml").write_text("coverage: 71.5\n")

    r = client.delete("/api/coverage/test/example/reset", headers=HDR)
    assert r.status_code == 200, r.text
    assert r.json()["removed"] == {"uploads": 1, "prs": 1, "history": True}
    assert not (proj / "history.yaml").exists()

    archives = list(proj.glob(".previous-*"))
    assert len(archives) == 1, f"no tombstone: {archives}"
    assert (archives[0] / "history.yaml").read_text() == "- coverage: 71.5\n"
    assert (archives[0] / "prs" / "42.yaml").exists()
    assert (archives[0] / "uploads" / "u1.yaml").exists()


@pytest.mark.parametrize("path", ["/api/coverage/test/upload", "/api/coverage/product/upload"])
def test_json_coverage_uploads_reject_oversize_before_parsing(env, monkeypatch, path):
    """D01-35: the 413 has to come off Content-Length, not off len(str(data))
    once the whole body is already a parsed dict in memory."""
    parsed: list[int] = []
    monkeypatch.setattr(ui, "_detect_and_parse_coverage", lambda *a, **k: parsed.append(1))

    r = client.post(path, headers={**HDR, "Content-Length": str(64 * 1024 * 1024)},
                    content=b'{"project": "example"}')

    assert r.status_code == 413, r.text
    assert not parsed


def test_atomic_write_fsyncs_before_rename(env, monkeypatch):
    """D01-41: .flush() does not reach disk; only the rename was ever durable."""
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])

    ui._atomic_write_text(env / "durable.yaml", "x: 1\n")

    assert order == ["fsync", "replace"]
    assert (env / "durable.yaml").read_text() == "x: 1\n"


# ---------------------------------------------------------------------------
# FW01-12 (wave W11b) — /api/resolve read project.yaml's own feature_toggles
# block and never merged config/_defaults.yaml, so every toggle a project
# inherits (the pattern config/README.md recommends) was simply absent from the
# API response. resolve.py and _load_project_toggles both do the merge.
# ---------------------------------------------------------------------------

def test_resolve_returns_defaults_merged_toggles(env):
    (ui.CONFIG / "routing.yaml").write_text(_ROUTING)
    (ui.CONFIG / "_defaults.yaml").write_text(yaml.safe_dump(
        {"feature_toggles": {"stp_generation": True, "std_generation": True,
                             "lsp_analysis": True, "polarion": False}}))
    proj = ui.CONFIG / "projects" / "example"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "project.yaml").write_text(yaml.safe_dump(
        {"display_name": "Example", "feature_toggles": {"polarion": True}}))

    toggles = client.get("/api/resolve/EXA-1").json()["feature_toggles"]

    assert toggles == ui._load_project_toggles("example"), "must match the canonical merge"
    assert toggles["lsp_analysis"] is True, "an inherited default was dropped"
    assert toggles["polarion"] is True, "the project override must still win"
