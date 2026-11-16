#!/usr/bin/env python3
"""The run log link (#223): what the latest run of a step did, readable from the
dashboard instead of `oc exec … cat outputs/<ticket>/.runs/<step>.jsonl`.

Same conventions as tests/test_metrics_endpoints.py: env set before `import ui`,
TestClient not entered (no lifespan threads), ui.OUTPUTS monkeypatched per test.
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402
import ui  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)
TOKEN = "ghp_" + "a" * 36


def lines(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


CLAUDE = lines(
    {"type": "system", "subtype": "init", "model": "glm-5-3"},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Reading the ticket."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "git log -1", "description": "last commit"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": f"abc123 fix\nGH_TOKEN={TOKEN}"}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "is_error": True, "content": [{"type": "text", "text": "Permission denied"}]}]}},
    {"type": "result", "subtype": "success", "num_turns": 7, "result": "Verdict: APPROVED"},
)


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "OUTPUTS", tmp_path)
    return tmp_path


def stream(outputs, jid, phase, text):
    d = outputs / jid / ".runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{phase}.jsonl").write_text(text)


def test_the_log_is_readable_and_redacted(outputs):
    stream(outputs, "CNV-1", "stp", CLAUDE)
    r = client.get("/api/pipelines/CNV-1/runs/stp/log")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "== session started, model glm-5-3" in body
    assert "$ git log -1    # last commit" in body and "  abc123 fix" in body
    assert "  [error] Permission denied" in body
    assert "== result: success after 7 turns" in body and "Verdict: APPROVED" in body
    assert TOKEN not in body and "[redacted]" in body


def test_raw_is_the_stream_itself_redacted(outputs):
    stream(outputs, "CNV-1", "std_review", CLAUDE)
    r = client.get("/api/pipelines/CNV-1/runs/std_review/log?raw=1")
    assert r.status_code == 200 and 'filename="CNV-1-std_review.jsonl"' in r.headers["content-disposition"]
    assert TOKEN not in r.text and json.loads(r.text.splitlines()[0])["model"] == "glm-5-3"


@pytest.mark.parametrize("path, code", [
    ("/api/pipelines/CNV-1/runs/stp/log", 404),          # never ran here
    ("/api/pipelines/CNV-1/runs/secrets/log", 400),      # not a step
    ("/api/pipelines/x y/runs/stp/log", 400),            # not a ticket id
])
def test_refusals(outputs, path, code):
    assert client.get(path).status_code == code


def test_codex_stream():
    out = pipeline_runner.render_stream(lines(
        {"type": "thread.started", "thread_id": "t"},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "ls", "aggregated_output": "a\nb", "exit_code": 2}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lsp_src", "tool": "references",
                                            "arguments": {"symbol": "X"}, "status": "completed", "result": {"content": [{"type": "text", "text": "x.go:3"}]}}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}},
        {"type": "error", "message": "rate limited"},
    ))
    assert "$ ls\n  a\n  b\n  (exit 2)" in out
    assert '[lsp_src.references] {"symbol": "X"} -> completed' in out and "x.go:3" in out
    assert "> Done." in out and "[error] rate limited" in out


def test_cursor_stream_and_clipping():
    out = pipeline_runner.render_stream(lines(
        {"type": "tool_call", "subtype": "started", "tool_call": {"shellToolCall": {"args": {"command": "pwd"}}}},
        {"type": "tool_call", "subtype": "completed", "tool_call": {"shellToolCall": {"result": "x" * 5000}}},
    ))
    assert "$ pwd" in out and "… (3000 more characters)" in out
