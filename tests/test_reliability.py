#!/usr/bin/env python3
"""Reliability regressions (wave W3): the four REL-01 defects.

REL-F01/F02  git sync blocked startup and /api/sync was an anonymous,
             unbounded, queueing GET on the anyio threadpool
REL-F03      a failure inside _run_phase_background's own error handler left
             the task "running" forever
REL-F06      a wrong-shaped pipeline_state.yaml 500'd the whole pipeline list
REL-F04      an unhandled error in the product-coverage worker wedged the
             per-project dedupe guard

Same conventions as tests/test_metrics_endpoints.py: QF_DEV/QF_OUTPUTS_DIR set
before `import ui`, ui is a module-level singleton so globals are monkeypatched
per test, and the module-level TestClient is NOT entered as a context manager
(that would run the lifespan against the real outputs/). test_lifespan_* is the
one exception — it is specifically about the lifespan.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_reliability.py -q
"""
import os
import sys
import threading
import time
import types
import urllib.error
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


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_USAGE_LOG", out / "_usage" / "dashboard_usage.jsonl")
    return out


def _write_state(outputs: Path, jira_id: str, doc) -> None:
    p = outputs / jira_id / "state" / "pipeline_state.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, sort_keys=False))


# ---------------------------------------------------------------------------
# A1 — REL-01.STARTUP-LIFESPAN: a hung git sync must not delay serving
# ---------------------------------------------------------------------------

def test_lifespan_serves_while_git_sync_is_stuck(outputs, monkeypatch):
    """/healthz answers, and startup reconciliation has already run, while the
    very first git sync is still blocked on an unreachable remote."""
    monkeypatch.setenv("GIT_REPO_URL", "http://127.0.0.1:1/x.git")
    _write_state(outputs, "REL-1", {"jira_id": "REL-1",
                                    "phases": {"stp": {"status": "in_progress"}}})

    released = threading.Event()
    calls: list[float] = []

    def _blocking_sync():
        calls.append(time.time())
        released.wait(30)
        return {"status": "ok"}

    monkeypatch.setattr(ui, "_git_sync", _blocking_sync)
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())

    try:
        t0 = time.time()
        with TestClient(ui.app) as c:
            elapsed = time.time() - t0
            assert c.get("/healthz").status_code == 200
            assert elapsed < 2, f"startup took {elapsed:.1f}s behind a stuck git sync"
            assert calls, "git sync should still have been kicked off (in the loop thread)"
            assert not released.is_set()
            # Reconciliation ran before the sync, not after it.
            state = yaml.safe_load(
                (outputs / "REL-1" / "state" / "pipeline_state.yaml").read_text())
            assert state["phases"]["stp"]["status"] == "failed"
    finally:
        released.set()
        ui._shutdown_event.set()


# ---------------------------------------------------------------------------
# A2 — REL-01.SYNC-THREADPOOL: /api/sync is an authenticated POST that never queues
# ---------------------------------------------------------------------------

def test_sync_route_is_post_and_returns_busy_instead_of_queueing(monkeypatch):
    assert client.get("/api/sync").status_code == 405

    monkeypatch.setattr(ui, "_API_KEY", "testkey")
    monkeypatch.setenv("GIT_REPO_URL", "http://127.0.0.1:1/x.git")

    assert ui._git_sync_lock.acquire(timeout=5), "lock held by a previous test?"
    try:
        r = client.post("/api/sync", headers={"X-API-Key": "testkey"})
        assert r.status_code == 200
        assert r.json() == {"status": "busy"}
    finally:
        ui._git_sync_lock.release()


# ---------------------------------------------------------------------------
# B — REL-01.BG-PHASE-TERMINAL: the task always reaches a terminal status
# ---------------------------------------------------------------------------

def test_background_phase_is_terminal_even_when_the_error_handler_fails(outputs, monkeypatch):
    import pipeline_runner

    def _boom(*_a, **_k):
        raise RuntimeError("runner exploded")

    def _unwritable(*_a, **_k):
        raise PermissionError("state dir is 0500")

    monkeypatch.setattr(pipeline_runner, "run_phase", _boom)
    monkeypatch.setattr(ui, "_atomic_yaml_update", _unwritable)
    monkeypatch.setattr(ui, "_running_tasks", {})

    ui._run_phase_background("REL-1", "stp")

    assert ui._running_tasks["REL-1/stp"]["status"] == "failed"


# ---------------------------------------------------------------------------
# C — REL-01.LIST-CORRUPT-STATE: one bad file must not 500 the list
# ---------------------------------------------------------------------------

def test_corrupt_state_files_do_not_500(outputs):
    _write_state(outputs, "REL-3", {"jira_id": "REL-3",
                                    "phases": {"stp": {"status": "completed"}}})
    _write_state(outputs, "REL-4", {"jira_id": "REL-4", "phases": "oops-not-a-dict"})
    _write_state(outputs, "REL-5", ["not", "a", "mapping"])

    r = client.get("/api/pipelines")
    assert r.status_code == 200
    assert "REL-3" in [row["jira_id"] for row in r.json()]

    for jira_id in ("REL-4", "REL-5"):
        assert client.get(f"/api/pipelines/{jira_id}").status_code < 500


# ---------------------------------------------------------------------------
# D — REL-F04: the product-coverage worker always leaves a terminal task
# ---------------------------------------------------------------------------

def test_product_coverage_worker_fails_instead_of_wedging(monkeypatch):
    monkeypatch.setattr(ui, "_get_product_coverage_config",
                        lambda _p: {"namespace": "ns", "components": [
                            {"name": "c1", "label_selector": "app=c1"}]})

    def _down(*_a, **_k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(ui, "_k8s_list_pods", _down)

    task = {"task_id": "t1", "project": "relproj", "status": "pending"}
    monkeypatch.setitem(ui._product_coverage_tasks, "t1", task)

    ui._collect_product_coverage_worker("t1", "relproj")

    assert task["status"] == "failed"
    assert "down" in task["error"]


# ---------------------------------------------------------------------------
# E — REL-01.EXT-OIDC-LOGIN (REL-F10): an unreachable IdP is a 503, not a 500
# ---------------------------------------------------------------------------

def test_login_returns_503_when_the_idp_discovery_endpoint_is_down(monkeypatch):
    """authorize_redirect() fetches the discovery document lazily, so with the
    IdP down the failure used to escape as an unhandled 500 with a stack trace.
    It must be a plain upstream-failure status that names no internal host."""

    class _DeadIdP:
        async def authorize_redirect(self, request, redirect_uri):
            raise urllib.error.URLError(
                "connect https://idp.internal.example/.well-known/openid-configuration")

    monkeypatch.setattr(ui, "_OIDC_ENABLED", True)
    monkeypatch.setattr(ui, "_oauth", types.SimpleNamespace(oidc=_DeadIdP()))

    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503, "a dead IdP must not surface as a 500"
    assert "idp.internal.example" not in r.text
    assert "Traceback" not in r.text


# ---------------------------------------------------------------------------
# F — REL-01.RECONCILE-ALL-KINDS (REL-F05): coverage tasks survive a restart
# ---------------------------------------------------------------------------

def test_startup_reconciles_orphaned_coverage_collection_tasks(outputs, monkeypatch):
    """A collection running when the process died used to die with it, so the
    UI polled a task id that 404'd forever. The startup sweep now flips it to
    failed at the same point an in_progress pipeline phase is flipped."""
    monkeypatch.setattr(ui, "_start_git_sync_loop", lambda: None)
    monkeypatch.setattr(ui, "_shutdown_event", threading.Event())
    monkeypatch.setattr(ui, "_collection_tasks", {})
    (outputs / ".collection_tasks.yaml").write_text(yaml.safe_dump({
        "aaa111": {"task_id": "aaa111", "org": "o", "repo": "r", "status": "running"},
        "bbb222": {"task_id": "bbb222", "org": "o", "repo": "r2", "status": "completed"},
    }))

    with TestClient(ui.app) as c:
        orphan = c.get("/api/coverage/collect/aaa111")
        assert orphan.status_code == 200, "an orphaned task must not 404 forever"
        assert orphan.json()["status"] == "failed"
        assert "restart" in orphan.json()["message"].lower()
        # A task that finished before the restart is left exactly as it was.
        assert c.get("/api/coverage/collect/bbb222").json()["status"] == "completed"

    on_disk = yaml.safe_load((outputs / ".collection_tasks.yaml").read_text())
    assert on_disk["aaa111"]["status"] == "failed"


def test_collection_task_is_persisted_when_it_starts(outputs, monkeypatch):
    """Nothing is reconcilable unless the task reaches disk before the worker
    runs — the crash window is exactly the one this covers."""
    monkeypatch.setattr(ui, "_collection_tasks", {})
    monkeypatch.setattr(ui, "_find_repo_config", lambda o, r: {"org": o, "repo": r})
    monkeypatch.setattr(threading, "Thread",
                        lambda *a, **k: types.SimpleNamespace(start=lambda: None))

    r = client.post("/api/coverage/collect?org=o&repo=r")
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    on_disk = yaml.safe_load((outputs / ".collection_tasks.yaml").read_text())
    assert on_disk[task_id]["status"] == "pending"


# ---------------------------------------------------------------------------
# G — REL-01.ROLLUP-FANOUT-WIDTH (REL-F12): one timeout wave, not ceil(N/8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_peers,expected_workers", [(3, 3), (10, 10), (40, 32)])
def test_rollup_fans_out_to_every_peer_in_one_wave(monkeypatch, n_peers, expected_workers):
    """8 workers against 10 unreachable peers meant two 8s waves. The pool is
    sized to the peer count now, capped so a bad peers.yaml cannot spawn
    hundreds of threads."""
    peers = [{"label": f"p{i}", "url": f"http://127.0.0.1:{9000 + i}"} for i in range(n_peers)]
    monkeypatch.setattr(ui, "_get_peers", lambda: peers)
    monkeypatch.setattr(ui, "_local_rollup", lambda: {"cluster": "local", "projects": []})
    monkeypatch.setattr(ui, "_fetch_peer_rollup",
                        lambda p: {"cluster": p["label"], "projects": []})

    seen: list[int] = []
    real_pool = ui.concurrent.futures.ThreadPoolExecutor

    class _SpyPool(real_pool):
        def __init__(self, *a, max_workers=None, **kw):
            seen.append(max_workers)
            super().__init__(*a, max_workers=max_workers, **kw)

    monkeypatch.setattr(ui.concurrent.futures, "ThreadPoolExecutor", _SpyPool)

    result = ui.rollup(local=False)
    assert len(result["clusters"]) == n_peers + 1
    assert seen == [expected_workers]
