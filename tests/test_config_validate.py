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
