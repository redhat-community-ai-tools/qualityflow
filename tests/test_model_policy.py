"""Model defaults and recorded-cost warnings, without provider calls."""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pipeline_runner as runner
from config.model_policy import load_policy, default_model


@pytest.mark.parametrize("runtime", ["claude", "codex", "cursor"])
def test_policy_and_run_warning(tmp_path, monkeypatch, capsys, runtime):
    config = tmp_path / "config"
    project = config / "projects" / "example"
    project.mkdir(parents=True)
    defaults = {"model_policy": {"cheap": {runtime: "small"},
                "standard": {runtime: "medium"}, "review": {runtime: "large"},
                "max_cost_usd": 1}}
    (config / "_defaults.yaml").write_text(yaml.safe_dump(defaults))
    (config / "routing.yaml").write_text(yaml.safe_dump({"routes": [
        {"project": "example", "jira_prefixes": ["PROJ"],
         "github_repos": ["my-org/my-repo"]}]}))
    (project / "project.yaml").write_text(yaml.safe_dump({"model_policy": {
        "standard": {runtime: "project-medium"}, "max_cost_usd": 2}}))
    policy = load_policy(tmp_path, "PROJ-12345")
    assert load_policy(tmp_path, "my-org-my-repo-123") == policy
    assert load_policy(tmp_path, "UNKNOWN-1")["max_cost_usd"] == 1
    assert default_model(policy, "formatting", runtime) == "small"
    assert default_model(policy, "collection", runtime) == "small"
    assert default_model(policy, "stp_review", runtime) == "large"
    assert default_model(policy, "stp_refine", runtime) == "project-medium"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    env_key = {"claude": "QF_RUNNER_MODEL", "codex": "QF_RUNNER_CODEX_MODEL",
               "cursor": "QF_RUNNER_CURSOR_MODEL"}[runtime]
    monkeypatch.delenv(env_key, raising=False)
    monkeypatch.setattr(runner, "_codex_lsp_args", lambda *a: [])
    seen = []
    def fake_run(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    cost = [3]
    monkeypatch.setattr(runner, "_parse_stream", lambda _: (
        [], "Completed", {"cost_usd": cost[0]}, "reported-model"))
    for phase, explicit, expected in [("stp", "", "project-medium"),
                                      ("stp_review", "", "large"),
                                      ("stp", "large", "large")]:
        result = runner.run_phase(explicit, "PROJ-12345", phase, runtime=runtime)
        argv = seen[-1]
        assert argv[argv.index("--model") + 1] == expected
        if explicit:
            assert "Explicit user model choice" in " ".join(argv)
        assert "Cost warning" in result["output"]
        assert "Cost warning" in result["progress"][-1]
        assert "Cost warning" in capsys.readouterr().err
    monkeypatch.setenv(env_key, "user-env")
    for value in [2, None]:
        cost[0] = value
        result = runner.run_phase("", "PROJ-12345", "stp", runtime=runtime)
        assert seen[-1][seen[-1].index("--model") + 1] == "user-env"
        assert "Cost warning" not in result["output"]
