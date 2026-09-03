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
import os
import shutil
import sys
import tarfile
import threading
import time
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
