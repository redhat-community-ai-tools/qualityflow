"""CNV project config (cnv branch only): what the resolver hands the pipeline.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_cnv_config.py
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def test_cnv_labels_scenarios_with_tiers():
    """CNV reviewers require Tier 1/2/3; the resolver must hand them to the
    classifier, with Tier 3's marker and the design-docs header."""
    out = subprocess.run([sys.executable, str(REPO / "skills/project-resolver/resolve.py"),
                          "CNV-96511"], capture_output=True, text=True, cwd=REPO)
    ctx = yaml.safe_load(out.stdout)["project_context"]
    assert [t["tier"] for t in ctx["scenario_tiers"]] == ["Tier 1", "Tier 2", "Tier 3"]
    assert ctx["scenario_tiers"][2]["marker"] == "tier3"
    assert ctx["stp_header"] == "Openshift-virtualization-tests Test plan"
