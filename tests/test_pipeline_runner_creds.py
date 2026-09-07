"""Per-user credentials into the `claude` CLI subprocess.

A shared dashboard has no Jira/GitHub identity of its own — each run must
carry the clicking user's own tokens (browser-stored in Settings, sent only
for that request) so mcp-atlassian/github read THEIR credentials via the
${VAR} placeholders in .mcp.json, not a server-wide one. See _env_for in
pipeline_runner.py and the run-route plumbing in test_mutating_routes.py.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_creds.py -q
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402


def test_env_for_without_creds_is_the_ambient_environment(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "server-tok")
    env = pipeline_runner._env_for(None)
    assert env["JIRA_API_TOKEN"] == "server-tok"
    assert env == os.environ.copy() | {"JIRA_API_TOKEN": "server-tok"}


def test_env_for_overlays_only_the_given_keys(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "server-tok")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "server-gh")
    env = pipeline_runner._env_for({"jira_username": "alice@example.com",
                                    "jira_token": "alice-tok"})
    assert env["JIRA_USERNAME"] == "alice@example.com"
    assert env["JIRA_API_TOKEN"] == "alice-tok"
    assert env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "server-gh"  # untouched


def test_env_for_blank_values_do_not_clear_the_ambient_token(monkeypatch):
    """A user who hasn't set a GitHub token in Settings sends '' — that must
    not blank out a server-configured fallback, only skip overriding it."""
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "server-gh")
    env = pipeline_runner._env_for({"jira_username": "", "jira_token": "", "github_token": ""})
    assert env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "server-gh"
    assert "JIRA_USERNAME" not in env or env.get("JIRA_USERNAME") != ""


@pytest.fixture
def capture_run(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","result":"ok"}\n', stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    return calls


def test_run_phase_passes_the_callers_creds_into_the_subprocess_env(monkeypatch, capture_run):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    creds = {"jira_username": "bob@example.com", "jira_token": "bob-tok", "github_token": "bob-gh"}

    pipeline_runner.run_phase("", "PROJ-1", "stp", creds=creds)

    _, kwargs = capture_run[0]
    env = kwargs["env"]
    assert env["JIRA_USERNAME"] == "bob@example.com"
    assert env["JIRA_API_TOKEN"] == "bob-tok"
    assert env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "bob-gh"


def test_run_phase_without_creds_is_unchanged_for_local_cli_use(monkeypatch, capture_run):
    """`python3 pipeline_runner.py run` from a laptop passes no creds — the
    subprocess must still inherit the caller's own shell environment exactly
    as before this feature existed."""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setenv("JIRA_API_TOKEN", "my-laptop-tok")

    pipeline_runner.run_phase("", "PROJ-1", "stp")

    _, kwargs = capture_run[0]
    assert kwargs["env"]["JIRA_API_TOKEN"] == "my-laptop-tok"
