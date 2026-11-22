"""EnMaaS runtime: the Codex CLI with Red Hat's AI gateway as its model
provider and the run's own key. Stubbed CLI; no key or network needed."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402


@pytest.fixture
def capture_run(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[:3] == ["codex", "debug", "models"]:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(
                {"models": [{"slug": "gpt-5.5", "apply_patch_tool_type": "freeform"}]}), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="\n".join([
            json.dumps({"type": "thread.started", "thread_id": "t1"}),
            json.dumps({"type": "item.completed", "item": {
                "type": "agent_message", "text": "Verdict: APPROVED"}}),
            json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 200}}),
        ]) + "\n", stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    return calls


def _exec_call(calls):
    return next(c for c in calls if c[0][:2] == ["codex", "exec"])


def test_enmaas_runs_codex_against_the_gateway_with_the_members_key(monkeypatch, capture_run):
    monkeypatch.setenv("ENMAAS_KEY", "owner-key")
    result = pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="enmaas", isolate=True,
                                       creds={"jira_username": "m@example.com", "jira_token": "j",
                                              "github_token": "g", "enmaas_api_key": "member-key"})
    argv, kwargs = _exec_call(capture_run)
    assert argv[argv.index("--model") + 1] == "rits/zai-org/glm-5-3"
    assert 'model_provider="enmaas"' in argv
    assert 'model_providers.enmaas.base_url="https://api.enmaas.devshift.net/v1"' in argv
    assert any(a.startswith("model_catalog_json=") for a in argv)
    assert "commands/stp-builder.md" in argv[-1]  # the prompt stays last
    assert "member-key" not in str(argv)
    assert kwargs["env"]["ENMAAS_KEY"] == "member-key" and "CODEX_HOME" in kwargs["env"]
    assert result["usage"]["cost_usd"] == 0.0  # hosted models are free


def test_enmaas_without_a_key_refuses_before_running(monkeypatch, capture_run):
    monkeypatch.setenv("ENMAAS_KEY", "owner-key")
    with pytest.raises(ValueError, match="EnMaaS key required"):
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="enmaas", isolate=True,
                                  creds={"jira_username": "m@example.com", "jira_token": "j",
                                         "github_token": "g"})
    assert not any(c[0][:2] == ["codex", "exec"] for c in capture_run)


def test_every_hosted_model_is_offered_free_in_the_dashboard():
    """A hosted EnMaaS model needs three entries: Codex's catalog (ENMAAS_HOSTED),
    the dashboard picker's label, and a zero price, or a run on it shows a cost."""
    import os as _os
    _os.environ.setdefault("QF_DEV", "1")
    import ui
    for mid in pipeline_runner.ENMAAS_HOSTED:
        assert pipeline_runner._price(mid) == (0.0, 0.0, 0.0, 0.0), mid
        assert "free" in ui._ENMAAS_MODEL_LABELS.get(mid, ""), mid
    assert "rits/meta-models/Muse-Spark-Open-816B-A42B-NVFP4" in pipeline_runner.ENMAAS_HOSTED


@pytest.mark.parametrize("phase, named", [("stp", True), ("std", False)])
def test_the_prompt_names_the_lsp_servers_to_find_behind_tool_search(monkeypatch, capture_run, tmp_path,
                                                                     phase, named):
    """gpt-6.1-sol defers MCP tools behind tool search; unnamed, a run once said
    "no lsp_* MCP tools are registered" with three bridges running (#211)."""
    repo = tmp_path / "src"
    repo.mkdir()
    (repo / "go.mod").write_text("module x\n")
    monkeypatch.setenv("SOURCE_REPO_PATH", str(repo))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setenv("ENMAAS_KEY", "k")
    pipeline_runner.run_phase("", "PROJ-1", phase, runtime="enmaas")
    prompt = _exec_call(capture_run)[0][-1]
    assert ("starts these LSP MCP servers: lsp_source" in prompt and "tool search" in prompt) is named
