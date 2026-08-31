#!/usr/bin/env python3
"""Tests for the six /api/metrics/* endpoints + POST /api/beacon (WP-1).

Each test builds its own tiny synthetic outputs/ tree under tmp_path — real
outputs/ is a read-only fixture, never touched here. ui.py is a long-lived
module-level singleton (OUTPUTS, caches), so the `outputs` fixture below
monkeypatches those globals per test rather than re-importing the module.

Run:
  uv run --with fastapi --with pyyaml --with pytest --with httpx --with uvicorn \\
      --with markdown --with bleach --with gitpython --with authlib --with itsdangerous \\
      pytest tests/test_metrics_endpoints.py
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))  # overridden per-test by the fixture
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import
from fastapi.testclient import TestClient  # noqa: E402

# Not entered as `with TestClient(...)`: that would run ui.py's lifespan
# (git sync, background thread, startup reconciliation over real OUTPUTS at
# import time) — none of which any of these endpoints need.
client = TestClient(ui.app)


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    """Fresh tmp outputs/ dir per test, with the module-level caches/paths
    that key off ui.OUTPUTS reset to match — a stale _jira_ids_cache or the
    _USAGE_LOG path computed once at import time would otherwise leak state
    across tests (or worse, write into the real repo's outputs/)."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_USAGE_LOG", out / "_usage" / "dashboard_usage.jsonl")
    return out


def _write_yaml(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _write_state(outputs: Path, jira_id: str, doc: dict) -> None:
    _write_yaml(outputs / jira_id / "state" / "pipeline_state.yaml", doc)


# ---------------------------------------------------------------------------
# confidence
# ---------------------------------------------------------------------------

def test_confidence_signals_and_insufficiency_rule(outputs):
    # Rich ticket: STD scenario fully STP<->STD linked (id) + a matching
    # generated test (coverage=1.0, link_quality=1.0), APPROVED verdicts on
    # both stp/std via the dashboard-dialect combined phase (review_health),
    # no refine phase (refinement=1.0 default), python_codegen verification
    # passed, a fresh `updated` timestamp (freshness=1.0). No ci/test_runs.yaml
    # -> effectiveness stays unavailable: exactly 6 of 7 signals.
    jid = "TCNF-1"
    _write_yaml(outputs / jid / "std" / f"{jid}_test_description.yaml", {
        "scenarios": [{
            "test_id": "TS-1", "test_objective": {"title": "Widget works"},
            "stp_scenario_id": "TS-01", "requirement_ids": ["REQ-1"],
            "priority": "P1", "test_type": "functional",
        }],
    })
    (outputs / jid / "python-tests").mkdir(parents=True)
    (outputs / jid / "python-tests" / "qf_widget.py").write_text(
        'def test_widget():\n    """[TS-1]"""\n    pass\n'
    )
    from datetime import datetime, timezone
    _write_state(outputs, jid, {
        "jira_id": jid, "project": "tcnf",
        "updated": datetime.now(timezone.utc).isoformat(),
        "phases": {
            "stp": {"status": "completed", "verdict": "APPROVED"},
            "std": {"status": "completed", "verdict": "APPROVED"},
            "python_codegen": {"status": "completed", "verification": "passed"},
        },
    })

    # Sparse ticket: a bare pending phase, nothing else -> only "refinement"
    # (always available, defaults to 1.0 when nothing ran) clears the bar.
    jid2 = "TCNF-2"
    _write_state(outputs, jid2, {"phases": {"stp": {"status": "pending"}}})

    resp = client.get("/api/metrics/confidence", params={"project": "tcnf"})
    assert resp.status_code == 200
    body = resp.json()
    by_id = {t["jira_id"]: t for t in body["tickets"]}

    rich = by_id[jid]
    assert rich["signals_total"] == 7
    assert rich["signals_present"] == 6
    assert rich["signals"]["effectiveness"]["available"] is False
    assert rich["signals"]["coverage"] == {"value": 1.0, "available": True}
    assert rich["signals"]["link_quality"] == {"value": 1.0, "available": True}
    assert rich["score"] == 100
    assert rich["band"] == "trusted"

    sparse = by_id[jid2]
    assert sparse["signals_present"] < 4
    assert sparse["band"] == "insufficient"
    assert sparse["score"] is None

    assert body["rollup"]["tickets"] == 2


# ---------------------------------------------------------------------------
# roi
# ---------------------------------------------------------------------------

def test_roi_sums_both_writer_dialects(outputs):
    jid = "TROI-1"
    _write_state(outputs, jid, {
        "jira_id": jid, "project": "troi",
        "phases": {
            # Dashboard dialect: started_ts/finished_ts, phase named "stp".
            "stp": {
                "status": "completed",
                "started_ts": "2026-08-01T00:00:00+00:00",
                "finished_ts": "2026-08-01T01:00:00+00:00",
                "usage": {"input_tokens": 10, "output_tokens": 100, "cost_usd": 1.5,
                          "duration_ms": 1000, "num_turns": 5},
            },
            # CLI dialect: started/completed, phase named "python_codegen"
            # (not "codegen") but still carries its own usage sub-dict.
            "python_codegen": {
                "status": "completed",
                "started": "2026-08-01T02:00:00Z", "completed": "2026-08-01T02:30:00Z",
                "usage": {"input_tokens": 5, "output_tokens": 50, "cost_usd": 0.5,
                          "duration_ms": 500, "num_turns": 2},
                "verification": "passed",
            },
        },
    })

    resp = client.get("/api/metrics/roi", params={"project": "troi"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["totals"]["cost_usd"] == pytest.approx(2.0)
    assert body["totals"]["input_tokens"] == 15
    assert body["totals"]["output_tokens"] == 150
    assert body["totals"]["duration_ms"] == 1500
    assert body["totals"]["num_turns"] == 7

    per = {p["jira_id"]: p for p in body["per_ticket"]}
    assert per[jid]["phases"]["stp"] == pytest.approx(1.5)
    assert per[jid]["phases"]["codegen"] == pytest.approx(0.5)  # python_codegen -> codegen bucket
    assert per[jid]["cost_usd"] == pytest.approx(2.0)

    assert body["time_saved_hours"]["estimated"] is True


# ---------------------------------------------------------------------------
# gaps
# ---------------------------------------------------------------------------

def test_gaps_ranking_order(outputs):
    jid = "TGAP-1"
    _write_yaml(outputs / jid / "std" / f"{jid}_test_description.yaml", {
        "scenarios": [
            # Solidly linked (id) + has a test -> fully covered, excluded.
            {"test_id": "TS-COV-1", "test_objective": {"title": "Covered thing"},
             "stp_scenario_id": "TS-01", "requirement_ids": ["REQ-OK"],
             "priority": "P1", "test_type": "functional"},
            # No matching test anywhere -> uncovered, base score 5.
            {"test_id": "TS-GAP-1", "test_objective": {"title": "Gap one"},
             "requirement_id": "GAP-1", "priority": "P2", "test_type": "functional"},
            # Has a test but only an inferred link, P0 -> 3 base + 3 bonus = 6.
            {"test_id": "TS-GAP-2", "test_objective": {"title": "Gap two"},
             "requirement_id": "GAP-2", "priority": "P0", "test_type": "functional"},
        ],
    })
    (outputs / jid / "python-tests").mkdir(parents=True)
    (outputs / jid / "python-tests" / "qf_gap.py").write_text(
        'def test_covered():\n    """[TS-COV-1]"""\n    pass\n\n'
        'def test_gap_two():\n    """[TS-GAP-2]"""\n    pass\n'
    )
    _write_state(outputs, jid, {"jira_id": jid, "project": "tgap", "phases": {}})

    resp = client.get("/api/metrics/gaps", params={"project": "tgap"})
    assert resp.status_code == 200
    gaps = resp.json()["gaps"]

    ids = [g["jira_id"] for g in gaps]
    assert "REQ-OK" not in ids  # fully covered — not a gap
    assert ids == ["GAP-2", "GAP-1"]  # descending priority_score: 6 then 5

    assert gaps[0]["status"] == "inferred_only"
    assert gaps[0]["priority_score"] == 6
    assert gaps[0]["epic"] == jid
    assert gaps[1]["status"] == "uncovered"
    assert gaps[1]["priority_score"] == 5


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------

def test_drift_unchanged_modified_missing(outputs, tmp_path, monkeypatch):
    jid = "TDRIFT-1"
    src_repo = tmp_path / "src_repo"
    unchanged_path = f"tests/qualityflow/{jid}/qf_a.py"
    modified_path = f"tests/qualityflow/{jid}/qf_b.py"
    missing_path = f"tests/qualityflow/{jid}/qf_c.py"
    (src_repo / "tests" / "qualityflow" / jid).mkdir(parents=True)
    (src_repo / unchanged_path).write_text("original content\n")
    (src_repo / modified_path).write_text("EDITED content\n")
    # missing_path deliberately not created on disk.

    checksums = {
        unchanged_path: hashlib.sha256("original content\n".encode()).hexdigest()[:16],
        modified_path: hashlib.sha256("original but different\n".encode()).hexdigest()[:16],
        missing_path: hashlib.sha256("whatever\n".encode()).hexdigest()[:16],
    }
    _write_state(outputs, jid, {
        "jira_id": jid, "project": "tdrift", "phases": {},
        "generation_checksums": checksums,
    })
    monkeypatch.setenv("SOURCE_REPO_PATH", str(src_repo))

    resp = client.get("/api/metrics/drift", params={"project": "tdrift"})
    assert resp.status_code == 200
    ticket = resp.json()["tickets"][0]
    assert ticket["available"] is True
    by_path = {f["path"]: f["status"] for f in ticket["files"]}
    assert by_path[unchanged_path] == "unchanged"
    assert by_path[modified_path] == "modified"
    assert by_path[missing_path] == "missing"
    assert ticket["modified"] == 1
    assert ticket["missing"] == 1


def test_drift_unresolvable_root_is_unavailable(outputs, monkeypatch):
    jid = "TDRIFT-2"
    _write_state(outputs, jid, {
        # NOTE: project filtering keys off the jira-id PREFIX ("TDRIFT" ->
        # "tdrift" via _infer_project), not this "project" field — it's
        # informational only, matching real pipeline_state.yaml.
        "jira_id": jid, "project": "tdrift", "phases": {},
        "generation_checksums": {"tests/qualityflow/TDRIFT-2/qf_x.py": "deadbeef00000000"},
    })
    monkeypatch.setenv("SOURCE_REPO_PATH", "/no/such/path/anywhere")

    resp = client.get("/api/metrics/drift", params={"project": "tdrift"})
    assert resp.status_code == 200
    ticket = resp.json()["tickets"][0]
    assert ticket["available"] is False
    assert ticket["files"] == []


# ---------------------------------------------------------------------------
# beacon / usage
# ---------------------------------------------------------------------------

def test_beacon_append_and_usage_readback(outputs):
    assert client.post("/api/beacon", json={"view": "command"}).status_code == 200
    assert client.post("/api/beacon", json={"view": "command"}).status_code == 200
    assert client.post("/api/beacon", json={"view": "runs"}).status_code == 200

    resp = client.get("/api/metrics/usage")
    assert resp.status_code == 200
    views = resp.json()["views"]
    assert views["command"]["hits"] == 2
    assert views["command"]["active_days"] == 1
    assert views["runs"]["hits"] == 1


def test_beacon_ignores_empty_view(outputs):
    resp = client.post("/api/beacon", json={"view": "  "})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# graceful degradation — no data anywhere for the project
# ---------------------------------------------------------------------------

def test_endpoints_never_500_with_no_data(outputs):
    for path in ("/api/metrics/confidence", "/api/metrics/roi", "/api/metrics/gaps",
                 "/api/metrics/quality-trend", "/api/metrics/drift", "/api/metrics/usage"):
        resp = client.get(path, params={"project": "nope"})
        assert resp.status_code == 200, f"{path} returned {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# GET /api/trends/all — cross-project merge by date
# ---------------------------------------------------------------------------

def test_trends_all_merges_projects_by_date(outputs, monkeypatch):
    trends = outputs / "_trends"
    monkeypatch.setattr(ui, "_TRENDS_DIR", trends)
    _write_yaml(trends / "cnv.yaml", {"history": [
        {"date": "2026-08-30", "pipelines": 2, "completed": 1, "tests": 10,
         "time_saved_hours": 8.0, "coverage_pct": 60.0, "auto_approved": 1, "human_approved": 0},
    ]})
    _write_yaml(trends / "other.yaml", {"history": [
        {"date": "2026-08-30", "pipelines": 1, "completed": 1, "tests": 5,
         "time_saved_hours": 2.5, "coverage_pct": 80.0, "auto_approved": 0, "human_approved": 1},
        {"date": "2026-08-31", "pipelines": 1, "completed": 0, "tests": 5,
         "time_saved_hours": 2.5, "coverage_pct": None, "auto_approved": 0, "human_approved": 1},
    ]})
    hist = client.get("/api/trends/all").json()["history"]
    assert [h["date"] for h in hist] == ["2026-08-30", "2026-08-31"]
    d0 = hist[0]
    assert d0["pipelines"] == 3 and d0["tests"] == 15 and d0["time_saved_hours"] == 10.5
    assert d0["coverage_pct"] == 70.0  # mean of 60 and 80
    assert hist[1]["coverage_pct"] is None  # no project reported that day


def test_trends_all_empty_dir(outputs, monkeypatch):
    monkeypatch.setattr(ui, "_TRENDS_DIR", outputs / "_trends")
    assert client.get("/api/trends/all").json() == {"history": []}
