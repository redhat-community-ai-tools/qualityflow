#!/usr/bin/env python3
"""Ops/observability metrics (wave W7): OPS-01-F3 + OBS-01-F3.

The /metrics exporter had no signal for the three things that actually page
someone at 3am — the PVC filling up, git-sync silently going stale, and
pipeline phases failing. This pins all three.

Same conventions as tests/test_reliability.py: QF_DEV/QF_OUTPUTS_DIR set before
`import ui`, ui is a module-level singleton so globals are monkeypatched
per test, and the module-level TestClient is NOT entered as a context manager.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_ops_metrics.py -q
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
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


def _metrics_text() -> str:
    r = client.get("/metrics")
    assert r.status_code == 200
    return r.text


# ---------------------------------------------------------------------------
# A — OPS-01-F3: disk headroom is exported, so ENOSPC is visible before it hits
# ---------------------------------------------------------------------------

def test_disk_gauges_are_exported_for_both_mounts(outputs):
    body = _metrics_text()
    assert 'qf_disk_free_bytes{mount="outputs"}' in body
    assert 'qf_disk_free_bytes{mount="config"}' in body
    assert 'qf_disk_total_bytes{mount="outputs"}' in body
    assert "# TYPE qf_disk_total_bytes gauge" in body


def test_disk_gauges_are_positive_numbers(outputs):
    for line in _metrics_text().splitlines():
        if line.startswith("qf_disk_"):
            assert int(line.rsplit(" ", 1)[1]) > 0


# ---------------------------------------------------------------------------
# B — OBS-01-F3: git-sync freshness is exported as a timestamp, not just a string
# ---------------------------------------------------------------------------

def test_git_sync_timestamp_is_zero_when_never_synced(monkeypatch):
    monkeypatch.setattr(ui, "_last_sync", None)
    assert "qf_git_sync_last_success_timestamp 0" in _metrics_text()


def test_git_sync_timestamp_reflects_the_last_sync(monkeypatch):
    monkeypatch.setattr(ui, "_last_sync", "2026-09-02T12:00:00+00:00")
    line = next(l for l in _metrics_text().splitlines()
                if l.startswith("qf_git_sync_last_success_timestamp "))
    assert float(line.split()[1]) == 1788350400.0  # 2026-09-02T12:00:00Z


def test_git_sync_timestamp_survives_an_unparseable_last_sync(monkeypatch):
    monkeypatch.setattr(ui, "_last_sync", "not-a-timestamp")
    assert "qf_git_sync_last_success_timestamp 0" in _metrics_text()


# ---------------------------------------------------------------------------
# C — OPS-01-F3: a failed phase run increments a per-phase counter
# ---------------------------------------------------------------------------

def test_failed_phase_run_increments_the_failure_counter(outputs, monkeypatch):
    import pipeline_runner

    def _boom(*_a, **_k):
        raise RuntimeError("runner exploded")

    monkeypatch.setattr(pipeline_runner, "run_phase", _boom)
    monkeypatch.setattr(ui, "_running_tasks", {})
    ui._pipeline_run_failures.clear()

    ui._run_phase_background("OPS-1", "stp")

    assert 'qf_pipeline_run_failures_total{phase="stp"} 1' in _metrics_text()
