"""Codex runtime contract tests.

These tests deliberately stub the CLI: the API key must never be needed by the
unit suite. The authenticated end-to-end check belongs in the deployed POC
smoke test because it consumes OpenAI quota and exercises the real MCP tools.
"""
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
        return subprocess.CompletedProcess(
            argv, 0,
            stdout="\n".join([
                json.dumps({"type": "thread.started", "thread_id": "t1"}),
                json.dumps({"type": "item.started", "item": {
                    "type": "mcp_tool_call", "name": "jira_get_issue"}}),
                json.dumps({"type": "item.completed", "item": {
                    "type": "agent_message", "text": "STP generated. Verdict: APPROVED"}}),
                json.dumps({"type": "turn.completed", "usage": {
                    "input_tokens": 10, "cached_input_tokens": 2,
                    "output_tokens": 4, "reasoning_output_tokens": 1}}),
            ]) + "\n", stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    return calls


def test_codex_argv_uses_json_workspace_write_and_prompt(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("gpt-5-codex", "PROJ-1", "stp", runtime="codex",
                              creds={"codex_api_key": "sk-test-key"})
    argv, kwargs = capture_run[0]
    assert argv[:10] == ["codex", "exec", "--json", "--ephemeral", "--sandbox",
                         "workspace-write", "--skip-git-repo-check", "--model",
                         "gpt-5-codex", argv[9]]
    assert "commands/stp-builder.md" in argv[-1]
    assert "PROJ-1" in argv[-1]
    assert kwargs["cwd"] == str(pipeline_runner.ROOT)
    assert kwargs["env"]["CODEX_API_KEY"] == "sk-test-key"
    assert "sk-test-key" not in argv[-1]


def test_codex_refine_prompt_carries_the_request_changes_flags(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("gpt-5-codex", "PROJ-1", "stp_refine", runtime="codex",
                              creds={"codex_api_key": "sk-test-key"}, rereview=True)
    prompt = capture_run[0][0][-1]
    assert "commands/refine-stp.md" in prompt
    assert "PROJ-1 --address-findings --rereview" in prompt


def test_codex_uses_the_current_cli_default_model(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.delenv("QF_RUNNER_CODEX_MODEL", raising=False)
    pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="codex",
                              creds={"codex_api_key": "sk-test-key"})
    argv, _ = capture_run[0]
    assert argv[8] == "gpt-6-astra"


def test_codex_api_key_is_never_in_argv_and_is_isolated(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setenv("CODEX_API_KEY", "owner-key")
    pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="codex", isolate=True,
                              creds={"jira_username": "member@example.com",
                                     "jira_token": "jira-token",
                                     "github_token": "gh-token",
                                     "codex_api_key": "member-key"})
    argv, kwargs = capture_run[0]
    assert "member-key" not in str(argv)
    assert kwargs["env"]["CODEX_API_KEY"] == "member-key"
    assert "CODEX_HOME" in kwargs["env"]


def test_codex_stream_parser_returns_progress_usage_and_final_text():
    stream = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "t1"}),
        json.dumps({"type": "item.started", "item": {
            "type": "command_execution", "command": "bash -lc pytest"}}),
        json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": "done"}}),
        json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 20, "cached_input_tokens": 5,
            "output_tokens": 8, "reasoning_output_tokens": 3}}),
    ])
    progress, final, usage, model = pipeline_runner._parse_stream(stream)
    assert progress == ["command: bash -lc pytest"]
    assert final == "done"
    assert usage["input_tokens"] == 20
    assert usage["cache_read_input_tokens"] == 5
    assert usage["reasoning_output_tokens"] == 3
    assert model is None


def test_codex_not_found_has_actionable_error(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    def fake_run(argv, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="OpenAI Codex CLI"):
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="codex",
                                  creds={"codex_api_key": "sk-test-key"})
