#!/usr/bin/env python3
"""The STP parser behind /api/pipelines/{id}/traceability reads the template's
Section III: "- **[KEY]** — story" groups and "*Test Scenario:*" lines, with the
label before or after the id. Before this it read only a "**TS-01: title**"
heading no template writes, so every STP showed 0 requirements."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import

STP = """### **III. Test Scenarios & Traceability**

- **[ABC-1]** — As an admin, I want X
  - *Test Scenario:* **TS-01**: [Tier 1] Verify X happens
  - *Test Scenario:* [Tier 2] **TS-02:** Verify X again
  - *Priority:* P0

- **[ABC-1]** -- As an admin, I want Y
  - *Test Scenario:* **TS-03**: Verify Y [Tier 1]
"""


def test_template_section_iii_is_parsed():
    reqs, ts = ui._parse_stp_requirements(STP, "ABC-1")
    assert reqs == ["ABC-1"]
    assert ts["TS-01"] == {"requirements": ["ABC-1"], "title": "Verify X happens", "labels": ["Tier 1"]}
    assert ts["TS-02"]["labels"] == ["Tier 2"] and ts["TS-02"]["title"] == "Verify X again"
    assert ts["TS-03"]["labels"] == ["Tier 1"] and ts["TS-03"]["title"] == "Verify Y"


def test_stp_only_ticket_lists_its_planned_scenarios(tmp_path, monkeypatch):
    stp = tmp_path / "ABC-1_test_plan.md"
    stp.write_text(STP)
    missing = tmp_path / "none"
    monkeypatch.setattr(ui, "_artifact_path", lambda j, kind: stp if kind == "stp" else missing)
    monkeypatch.setattr(ui, "_match_tests_to_scenarios", lambda j: {})
    body = ui.pipeline_traceability("ABC-1")
    assert body["summary"]["requirements_total"] == 1
    assert body["summary"]["scenarios_total"] == 3
    assert {s["link"] for s in body["requirements"][0]["scenarios"]} == {"stp"}
    assert body["summary"]["coverage_status"] == {}
