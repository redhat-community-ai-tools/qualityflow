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


def test_codex_argv_uses_json_unsandboxed_and_prompt(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("gpt-5-codex", "PROJ-1", "stp", runtime="codex",
                              creds={"codex_api_key": "sk-test-key"})
    argv, kwargs = capture_run[0]
    # bubblewrap can't create a namespace in the pod, so the sandbox is off and
    # the container is the boundary — pinned so it can't silently regress.
    assert argv[:10] == ["codex", "exec", "--json", "--ephemeral", "--sandbox",
                         "danger-full-access", "--skip-git-repo-check", "--model",
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
    assert argv[8] == "gpt-5.6-sol"


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


def test_codex_tokens_are_priced():
    # 1M uncached input + 1M cached + 1M written + 1M output on Sol, whose
    # list price is $4 / $0.40 / $5 / $20 per 1M.
    u = {"input_tokens": 3_000_000, "cached_input_tokens": 1_000_000,
         "cache_write_input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert pipeline_runner._codex_cost("gpt-5.6-sol", u) == 29.4
    assert pipeline_runner._codex_cost("some-unknown-model", u) is None


def test_codex_run_records_a_dollar_cost(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    result = pipeline_runner.run_phase("gpt-6-astra", "PROJ-1", "stp", runtime="codex",
                                       creds={"codex_api_key": "sk-test-key"})
    # 8 uncached, 2 cached, 4 output tokens at Astra's $10 / $1 / $50.
    assert result["usage"]["cost_usd"] == round((8 * 10 + 2 * 1 + 4 * 50) / 1e6, 4)


def test_isolated_codex_run_exposes_running_cost(monkeypatch):
    """A dashboard run keeps Codex's session file in its private CODEX_HOME so
    the status poll can show spend mid-run; the registry is gone afterwards."""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    seen = {}

    def fake_run(argv, **kwargs):
        sessions = Path(kwargs["env"]["CODEX_HOME"], "sessions", "2026", "09")
        sessions.mkdir(parents=True)
        (sessions / "rollout-x.jsonl").write_text("\n".join([
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}}),
            json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 1_000_000, "cached_input_tokens": 0,
                                      "output_tokens": 1_000_000}}}}),
        ]) + "\n")
        seen["argv"] = argv
        seen["live"] = pipeline_runner.live_usage("PROJ-1", "stp", "")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    pipeline_runner.run_phase("gpt-5.6-terra", "PROJ-1", "stp", runtime="codex", isolate=True,
                              creds={"jira_username": "m@example.com", "jira_token": "t",
                                     "github_token": "g", "codex_api_key": "k"})
    assert "--ephemeral" not in seen["argv"]
    assert seen["live"] == {"cost_usd": 14.0, "model": "gpt-5.6-terra", "tokens": 2_000_000}
    assert pipeline_runner.live_usage("PROJ-1", "stp", "") == {}


def test_claude_running_cost_counts_each_api_call_once():
    # One API call arrives as two assistant events sharing a message id.
    call = {"id": "msg_1", "model": "claude-sonnet-4@20250514",
            "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
    stream = "\n".join(json.dumps({"type": "assistant", "message": dict(call, content=[c])})
                       for c in ({"type": "text"}, {"type": "tool_use", "name": "Read"}))
    assert pipeline_runner.live_usage("PROJ-9", "stp", stream) == {"cost_usd": 18.0,
                                                                  "tokens": 2_000_000}
