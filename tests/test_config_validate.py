"""Mutation tests for config/validate.py (FW-01-F5).

An invalid `test_strategy` used to pass validation with rc=0: the only rule that
mentioned it was tier_consistency, which a non-'tier' bogus value never fires.
Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_config_validate.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
VALIDATE = REPO / "config" / "validate.py"


def mutated_config(tmp_path, mutate):
    """A copy of config/ with `mutate(project_yaml_dict)` applied to the example
    project. Returns the copied config dir."""
    dst = tmp_path / "config"
    shutil.copytree(REPO / "config", dst)
    proj = dst / "projects" / "example" / "project.yaml"
    data = yaml.safe_load(proj.read_text())
    mutate(data)
    proj.write_text(yaml.safe_dump(data, sort_keys=False))
    return dst


def run_validate(config_dir):
    return subprocess.run([sys.executable, str(VALIDATE), str(config_dir)],
                          capture_output=True, text=True)


def test_unmutated_config_passes(tmp_path):
    """Control: the copy itself is valid, so a failure below is the mutation."""
    proc = run_validate(mutated_config(tmp_path, lambda d: None))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bogus_test_strategy_fails(tmp_path):
    def mutate(data):
        data.setdefault("feature_toggles", {})["test_strategy"] = "bogus_mode"

    proc = run_validate(mutated_config(tmp_path, mutate))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "test_strategy" in proc.stdout and "bogus_mode" in proc.stdout, proc.stdout


def test_tier_is_a_valid_strategy(tmp_path):
    """'tier' must not trip the enum. The example project ships no tier*.yaml, so
    it still fails — but on the tier_consistency rule, not on the enum."""
    def mutate(data):
        data.setdefault("feature_toggles", {})["test_strategy"] = "tier"

    proc = run_validate(mutated_config(tmp_path, mutate))
    assert proc.returncode == 1, proc.stdout
    assert "Invalid test_strategy" not in proc.stdout, proc.stdout
    assert "tier*.yaml" in proc.stdout, proc.stdout


def test_scenario_tiers_need_a_tier_label_and_description(tmp_path):
    """A malformed scenario_tiers list would silently fall back to test-type
    labels in the STP, so it must fail validation."""
    good = [{"tier": "Tier 1", "description": "single feature"},
            {"tier": "Tier 3", "description": "high cost", "marker": "tier3"}]
    proc = run_validate(mutated_config(tmp_path, lambda d: d.update(scenario_tiers=good)))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bads = ([], [{"tier": "Tier 1"}], [{"tier": "Functional", "description": "x"}])
    for i, bad in enumerate(bads):
        tmp = tmp_path / f"bad{i}"
        tmp.mkdir()
        proc = run_validate(mutated_config(tmp, lambda d, b=bad: d.update(scenario_tiers=b)))
        assert proc.returncode != 0 and "scenario_tiers" in proc.stdout + proc.stderr, bad


def test_resolver_hands_scenario_tiers_and_stp_header_through(tmp_path):
    """A team whose reviewers require tiers sets scenario_tiers; the resolver
    must hand them to the classifier, each marker included, with the team's
    STP header. resolve.py reads the config/ two levels above itself."""
    tiers = [{"tier": "Tier 1", "description": "single feature"},
             {"tier": "Tier 3", "description": "high cost", "marker": "tier3"}]
    mutated_config(tmp_path, lambda d: d.update(
        scenario_tiers=tiers, stp_document={"header": "My Project Test plan"}))
    resolver = tmp_path / "skills" / "project-resolver" / "resolve.py"
    resolver.parent.mkdir(parents=True)
    shutil.copy(REPO / "skills" / "project-resolver" / "resolve.py", resolver)
    out = subprocess.run([sys.executable, str(resolver), "MYPROJ-1"],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    ctx = yaml.safe_load(out.stdout)["project_context"]
    assert ctx["scenario_tiers"] == tiers
    assert ctx["stp_header"] == "My Project Test plan"


def test_stakeholders_entry_without_name_fails(tmp_path):
    def mutate(data):
        data["stakeholders"] = {"default_reviewers": [{"name": "Jane Smith", "role": "QE"}],
                                "default_approvers": [{"github": "samlee"}]}

    proc = run_validate(mutated_config(tmp_path, mutate))
    assert proc.returncode == 1, proc.stdout
    assert "stakeholders.default_approvers[0] needs a name" in proc.stdout, proc.stdout
    assert "default_reviewers" not in proc.stdout, proc.stdout
