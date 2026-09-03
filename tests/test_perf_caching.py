#!/usr/bin/env python3
"""Caching regressions (wave W6): the PERF-01 defects.

PERF-01-F1   /api/pipelines, /api/pipelines/matrix, /api/metrics/confidence and
             /api/metrics/roi rescanned every ticket's pipeline_state.yaml on
             every request with no cache, while the sibling /api/metrics/{id}
             and /api/insights already used _metrics_cache
PERF-01-F2   the Command Center's ~10 parallel fetches all missed together and
             each did the same full scan — no single-flight, all on one GIL
PERF-01-F3   list_pipelines computed the whole body and its md5 BEFORE
             comparing If-None-Match, so a 304 cost exactly as much as a 200

Same conventions as tests/test_metrics_endpoints.py and tests/test_state_safety.py:
QF_DEV/QF_OUTPUTS_DIR set before `import ui`, ui is a module-level singleton so
globals are monkeypatched per test, and the module-level TestClient is NOT
entered as a context manager (that would run the lifespan against real outputs/).

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_perf_caching.py -q
"""
import os
import sys
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

TICKETS = [f"CNV-{n}" for n in range(1, 6)]


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    """Fresh tmp outputs/ with 5 tickets, and every module-level cache reset."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_activity_cache", (0.0, []))
    for jira_id in TICKETS:
        _write_state(out, jira_id, {
            "ticket_id": jira_id,
            "project_id": "cnv",
            "updated": "2026-09-01T00:00:00+00:00",
            "phases": {
                "stp": {"status": "completed", "verdict": "APPROVED",
                        "usage": {"cost_usd": 0.5, "num_turns": 3}},
                "std": {"status": "completed", "verdict": "APPROVED"},
                "codegen": {"status": "pending"},
            },
        })
    return out


def _state_path(outputs: Path, jira_id: str) -> Path:
    return outputs / jira_id / "state" / "pipeline_state.yaml"


def _write_state(outputs: Path, jira_id: str, doc: dict) -> None:
    path = _state_path(outputs, jira_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


@pytest.fixture
def reads(monkeypatch):
    """Counting wrapper around the per-ticket state read every hot route repeats."""
    calls: list[Path] = []
    real = ui._read_state

    def counted(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(ui, "_read_state", counted)
    return calls


# ---------------------------------------------------------------------------
# PERF-01-F1 — the four hot routes cache their result for the TTL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/api/pipelines",
    "/api/pipelines/matrix",
    "/api/metrics/confidence",
    "/api/metrics/roi",
])
def test_hot_route_does_not_rescan_within_ttl(outputs, reads, url):
    assert client.get(url).status_code == 200
    first = len(reads)
    assert first >= len(TICKETS), "expected one state read per ticket on the cold call"
    assert client.get(url).status_code == 200
    assert len(reads) == first, f"{url} re-read state on a warm call"


# ---------------------------------------------------------------------------
# PERF-01-F3 — a conditional request is answered before any work
# ---------------------------------------------------------------------------

def test_if_none_match_304_reads_nothing(outputs, reads):
    first = client.get("/api/pipelines")
    etag = first.headers["etag"]
    reads.clear()
    second = client.get("/api/pipelines", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert reads == [], "304 still rescanned every ticket"


# ---------------------------------------------------------------------------
# Invalidation — an in-process write is visible on the very next request
# ---------------------------------------------------------------------------

def test_state_write_invalidates(outputs, reads):
    before = client.get("/api/pipelines").json()
    assert len(before) == len(TICKETS)

    ui._atomic_yaml_update(
        _state_path(outputs, "CNV-6"),
        lambda _data: {"ticket_id": "CNV-6", "project_id": "cnv",
                       "phases": {"stp": {"status": "completed"}}},
    )

    after = client.get("/api/pipelines").json()
    assert {row["jira_id"] for row in after} == set(TICKETS) | {"CNV-6"}


# ---------------------------------------------------------------------------
# PERF-01-F2 — single-flight: parallel misses compute once
# ---------------------------------------------------------------------------

def test_cached_is_single_flight(monkeypatch):
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_cache_locks", {})
    started, release = threading.Event(), threading.Event()
    calls: list[int] = []
    results: list[object] = []

    def compute():
        calls.append(1)
        started.set()
        release.wait(5)
        return object()

    def call():
        results.append(ui._cached("single-flight-probe", compute))

    t1 = threading.Thread(target=call)
    t1.start()
    assert started.wait(5), "first compute never ran"
    t2 = threading.Thread(target=call)
    t2.start()
    time.sleep(0.1)  # let t2 reach the lock
    release.set()
    t1.join(5)
    t2.join(5)

    assert calls == [1], "compute ran more than once for concurrent misses"
    assert len(results) == 2 and results[0] is results[1]


# ---------------------------------------------------------------------------
# The shared per-ticket read is what actually gets deduplicated
# ---------------------------------------------------------------------------

def test_project_states_shared_across_metrics_routes(outputs, reads):
    assert client.get("/api/metrics/roi").status_code == 200
    reads.clear()
    assert client.get("/api/metrics/confidence").status_code == 200
    assert reads == [], "confidence repeated roi's per-ticket state reads"
