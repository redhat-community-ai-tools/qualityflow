"""Cursor CLI backend for run_phase() (B-01/B-02, RUN-2026-09-08-dual-runtime).

Covers: cursor argv shape, the API key reaching env NOT argv (fact C-1b, P0),
blank creds not clearing ambient env, unknown runtime falling back to
"claude", timeout/not-found error mapping, model precedence, and the
Cursor-schema branch of _parse_stream (fact C-2).

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_cursor.py -q
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
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","result":"ok"}\n', stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    return calls


def _run(monkeypatch, capture_run, **kwargs):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("", "PROJ-1", "stp", **kwargs)
    return capture_run[0]


# --- argv shape -------------------------------------------------------

def test_cursor_argv_shape(monkeypatch, capture_run):
    argv, kwargs = _run(monkeypatch, capture_run, runtime="cursor")
    assert argv == ["agent", "-p", "/stp-builder PROJ-1",
                     "--output-format", "stream-json", "--force",
                     "--approve-mcps", "--trust", "--model", "cursor-grok-4.6-high"]
    assert kwargs["cwd"] == str(pipeline_runner.ROOT)
    assert kwargs["timeout"] == pipeline_runner._TIMEOUT


def test_cursor_argv_with_explicit_model(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("grok-4.6-xhigh", "PROJ-1", "stp", runtime="cursor")
    argv, _ = capture_run[0]
    assert argv[-2:] == ["--model", "grok-4.6-xhigh"]


def test_legacy_grok_4_6_id_maps_to_cli_id(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("grok-4.6", "PROJ-1", "stp", runtime="cursor")
    argv, _ = capture_run[0]
    assert argv[-2:] == ["--model", "cursor-grok-4.6-high"]


def test_cursor_model_precedence_env_over_default(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER_CURSOR_MODEL", "grok-4.6-env")
    argv, _ = _run(monkeypatch, capture_run, runtime="cursor")
    assert argv[-2:] == ["--model", "grok-4.6-env"]


# --- unknown/absent runtime falls back to claude, never errors --------

@pytest.mark.parametrize("bad_runtime", [None, "", "bogus", "CLAUDE", "Cursor"])
def test_unknown_or_absent_runtime_falls_back_to_claude(monkeypatch, capture_run, bad_runtime):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    kwargs = {} if bad_runtime is None else {"runtime": bad_runtime}
    pipeline_runner.run_phase("", "PROJ-1", "stp", **kwargs)
    argv, _ = capture_run[0]
    assert argv[0] == "claude"


# --- API key: env only, never argv (fact C-1b, P0) ---------------------

def test_cursor_api_key_reaches_env_not_argv(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor",
                              creds={"cursor_api_key": "sk-super-secret"})
    argv, kwargs = capture_run[0]
    assert "sk-super-secret" not in argv
    assert not any("sk-super-secret" in str(a) for a in argv)
    assert kwargs["env"]["CURSOR_API_KEY"] == "sk-super-secret"


def test_cursor_blank_creds_do_not_clear_ambient_env(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setenv("CURSOR_API_KEY", "server-cursor-key")
    pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor",
                              creds={"cursor_api_key": ""})
    _, kwargs = capture_run[0]
    assert kwargs["env"]["CURSOR_API_KEY"] == "server-cursor-key"


# --- error mapping ------------------------------------------------------

def test_cursor_not_found_gives_actionable_message(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    def fake_run(argv, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="`agent` \\(Cursor CLI\\) not found on PATH"):
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor")


def test_cursor_timeout_error_mapping(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out after"):
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor")


def test_cursor_nonzero_exit_surfaces_real_error(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout='{"type":"result","result":"MCP server auth failed"}\n',
            stderr="fatal: bad credentials\n")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="MCP server auth failed"):
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor")


# --- claude path stays byte-identical when runtime="claude" is explicit -

def test_explicit_claude_runtime_matches_default_argv(monkeypatch, capture_run):
    argv, _ = _run(monkeypatch, capture_run, runtime="claude")
    assert argv == ["claude", "-p", "/stp-builder PROJ-1",
                     "--output-format", "stream-json", "--verbose",
                     "--dangerously-skip-permissions"]


# --- Cursor stream-json parser (fact C-2) --------------------------------

def _cursor_sample():
    return "\n".join([
        json.dumps({"type": "system", "subtype": "init", "model": "grok-4.6",
                    "session_id": "s1", "cwd": "/app"}),
        json.dumps({"type": "tool_call", "subtype": "started", "call_id": "c1",
                    "session_id": "s1",
                    "tool_call": {"function": {"name": "jira-collector", "arguments": "{}"}}}),
        json.dumps({"type": "tool_call", "subtype": "completed", "call_id": "c1",
                    "session_id": "s1",
                    "tool_call": {"function": {"name": "jira-collector"}, "result": "ok"}}),
        json.dumps({"type": "tool_call", "subtype": "started", "call_id": "c2",
                    "session_id": "s1",
                    "tool_call": {"readToolCall": {"path": "STP.md"}}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False,
                    "result": "STP generated. Verdict: APPROVED",
                    "duration_ms": 5000, "session_id": "s1"}),
    ])


def test_cursor_stream_progress_uses_tool_call_events():
    progress, out, usage, model = pipeline_runner._parse_stream(_cursor_sample())
    assert progress == ["jira-collector", "read"]
    assert model == "grok-4.6"
    assert pipeline_runner._extract_verdict(out) == "APPROVED"


def test_cursor_stream_missing_usage_degrades_to_none_not_invented():
    _, _, usage, _ = pipeline_runner._parse_stream(_cursor_sample())
    assert usage["cost_usd"] is None
    assert usage["input_tokens"] is None
    assert usage["duration_ms"] == 5000  # present on cursor's result event too


def test_cursor_tool_call_completed_is_not_double_counted():
    progress, _, _, _ = pipeline_runner._parse_stream(_cursor_sample())
    assert progress.count("jira-collector") == 1


def test_claude_schema_still_parses_unchanged():
    sample = "\n".join([
        json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "stp-generator"}]}}),
        json.dumps({"type": "result", "result": "done", "usage": {"input_tokens": 10},
                    "total_cost_usd": 0.1}),
    ])
    progress, out, usage, model = pipeline_runner._parse_stream(sample)
    assert progress == ["stp-generator"]
    assert model == "claude-sonnet-5"
    assert usage["cost_usd"] == 0.1 and usage["input_tokens"] == 10
