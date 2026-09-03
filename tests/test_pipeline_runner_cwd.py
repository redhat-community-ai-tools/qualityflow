"""Pins DATA-01-F16: the CLI runner and the dashboard must agree on which tree
pipeline_state.yaml and the phase artifacts live in.

The `claude` subprocess has to run with cwd=ROOT (it resolves .claude/ resources,
config/ and its own relative outputs/{ID}/ writes from cwd), so ROOT/outputs is
where artifacts land. Two invariants keep that honest:
  1. pipeline_runner refuses to run at all when QF_OUTPUTS_DIR points elsewhere,
     instead of stranding every artifact where the dashboard never looks.
  2. state.py resolves QF_OUTPUTS_DIR itself, so state written by any process
     (the runner's record-usage call, the slash command's own skill calls) lands
     in the tree the dashboard reads, whatever its cwd.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_cwd.py
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import pipeline_runner  # noqa: E402


def _load_state_module():
    """state.py lives under skills/ (not importable by name) — load it by path."""
    spec = importlib.util.spec_from_file_location(
        "qf_state", REPO / "skills" / "pipeline-state" / "state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


state = _load_state_module()


@pytest.fixture
def capture_run(monkeypatch):
    """Capture subprocess.run kwargs instead of spawning `claude`."""
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","result":"ok"}\n',
                                           stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    return calls


def test_run_phase_cwd_is_the_dashboard_outputs_tree(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("", "PROJ-1", "stp")

    argv, kwargs = capture_run[0]
    assert argv[0] == "claude"
    cwd = Path(kwargs["cwd"]).resolve()
    # The invariant that matters: the outputs dir the subprocess writes into is
    # the one the dashboard reads — not merely "cwd happens to be ROOT".
    assert (cwd / "outputs").resolve() == pipeline_runner._outputs_dir()


def test_run_phase_refuses_a_divergent_outputs_dir(monkeypatch, capture_run, tmp_path):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.setenv("QF_OUTPUTS_DIR", str(tmp_path / "elsewhere"))
    with pytest.raises(RuntimeError, match="QF_OUTPUTS_DIR"):
        pipeline_runner.run_phase("", "PROJ-1", "stp")
    assert capture_run == [], "must refuse before spawning anything"


def test_state_path_follows_qf_outputs_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("QF_OUTPUTS_DIR", str(tmp_path))
    assert Path(state.state_path("PROJ-1")) == tmp_path / "PROJ-1" / "state" / "pipeline_state.yaml"
    assert Path(state.outputs_dir()) == tmp_path

    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    assert Path(state.state_path("PROJ-1")) == Path("outputs") / "PROJ-1" / "state" / "pipeline_state.yaml"


def test_state_writes_land_under_qf_outputs_dir_regardless_of_cwd(monkeypatch, tmp_path):
    """The end-to-end shape of the bug: state.py invoked from the repo root (as
    pipeline_runner does) must still write into the dashboard's outputs tree."""
    outputs = tmp_path / "pvc-outputs"
    monkeypatch.setenv("QF_OUTPUTS_DIR", str(outputs))
    monkeypatch.chdir(REPO)
    state.main(["init", "PROJ-1", "--project-id", "example", "--display-name", "x"])
    assert (outputs / "PROJ-1" / "state" / "pipeline_state.yaml").exists()
    # ...and it took the same .lock sidecar name ui.py's _atomic_yaml_update uses
    assert (outputs / "PROJ-1" / "state" / "pipeline_state.yaml.lock").exists()
