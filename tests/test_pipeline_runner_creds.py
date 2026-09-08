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


def test_run_phase_with_no_runtime_arg_still_builds_claude_argv(monkeypatch, capture_run):
    """Every existing caller (no `runtime` kwarg at all) must produce the
    exact same `claude` argv as before runtime selection existed — the
    laptop path stays byte-identical in behaviour."""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    pipeline_runner.run_phase("", "PROJ-1", "stp")

    argv, _ = capture_run[0]
    assert argv == ["claude", "-p", "/stp-builder PROJ-1",
                     "--output-format", "stream-json", "--verbose",
                     "--dangerously-skip-permissions"]


def test_env_for_cursor_api_key_goes_to_env_not_argv(monkeypatch):
    env = pipeline_runner._env_for({"cursor_api_key": "sk-secret"})
    assert env["CURSOR_API_KEY"] == "sk-secret"


def test_env_for_blank_cursor_api_key_does_not_clear_ambient(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "server-cursor-key")
    env = pipeline_runner._env_for({"cursor_api_key": ""})
    assert env["CURSOR_API_KEY"] == "server-cursor-key"


# ---------------------------------------------------------------------------
# Per-user Vertex identity (gcp_adc): the pasted ADC becomes a 0600 per-run
# file, reaches the child only via GOOGLE_APPLICATION_CREDENTIALS, and is gone
# when run_phase returns — including when it raises.
# ---------------------------------------------------------------------------

FAKE_ADC = ('{"type": "authorized_user", "client_id": "fake.apps.googleusercontent.com",'
            ' "client_secret": "GOCSPX-FAKEFAKEFAKE",'
            ' "refresh_token": "1//0FAKEFAKEFAKEFAKEFAKEFAKE"}')


@pytest.fixture
def capture_adc(monkeypatch):
    """Record the credential path/mode/content *while the subprocess runs* —
    after run_phase returns the file is gone, which is the point."""
    seen = {}

    def fake_run(argv, **kwargs):
        env = kwargs["env"]
        seen["argv"] = argv
        seen["path"] = env.get("GOOGLE_APPLICATION_CREDENTIALS")
        if seen["path"] and Path(seen["path"]).exists():
            p = Path(seen["path"])
            seen["mode"] = p.stat().st_mode & 0o777
            seen["content"] = p.read_text()
            seen["dir_mode"] = p.parent.stat().st_mode & 0o777
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","result":"ok"}\n', stderr="")

    monkeypatch.setattr(pipeline_runner.subprocess, "run", fake_run)
    return seen


def test_gcp_adc_lands_in_a_0600_file_named_only_by_the_env(monkeypatch, capture_adc):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)

    pipeline_runner.run_phase("", "PROJ-1", "stp", creds={"gcp_adc": FAKE_ADC})

    assert capture_adc["content"] == FAKE_ADC
    assert capture_adc["mode"] == 0o600
    assert capture_adc["dir_mode"] == 0o700
    # Never in argv (/proc/<pid>/cmdline is world-readable).
    assert not any(FAKE_ADC in a or capture_adc["path"] in a for a in capture_adc["argv"])
    # And gone once the run is over.
    assert not Path(capture_adc["path"]).exists()
    assert not Path(capture_adc["path"]).parent.exists()


def test_gcp_adc_file_is_removed_even_when_the_subprocess_raises(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    seen = {}

    def boom(argv, **kwargs):
        seen["path"] = kwargs["env"]["GOOGLE_APPLICATION_CREDENTIALS"]
        assert Path(seen["path"]).exists()
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(pipeline_runner.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        pipeline_runner.run_phase("", "PROJ-1", "stp", creds={"gcp_adc": FAKE_ADC})
    assert not Path(seen["path"]).exists()
    assert not Path(seen["path"]).parent.exists()


def test_blank_gcp_adc_leaves_the_ambient_credential_untouched(monkeypatch, capture_adc):
    """R-2's contract: a blank value never clears ambient env. (On the cluster
    the route refuses a blank one before it gets here — see ui.py.)"""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/etc/gcp/shared.json")

    pipeline_runner.run_phase("", "PROJ-1", "stp", creds={"gcp_adc": ""})

    assert capture_adc["path"] == "/etc/gcp/shared.json"


def test_cursor_runtime_ignores_gcp_adc(monkeypatch, capture_adc):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    pipeline_runner.run_phase("", "PROJ-1", "stp", creds={"gcp_adc": FAKE_ADC}, runtime="cursor")

    assert capture_adc["path"] is None


@pytest.mark.parametrize("bad", ["not json at all",
                                 "/home/alice/my-adc.json",  # pasted the path, not the contents
                                 '{"client_id": "x", "refresh_token": "1//0SECRETSECRETSECRET"}'])
def test_malformed_gcp_adc_raises_without_echoing_the_content(monkeypatch, capture_run, bad):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    with pytest.raises(ValueError) as exc_info:
        pipeline_runner.run_phase("", "PROJ-1", "stp", creds={"gcp_adc": bad})
    assert bad not in str(exc_info.value)
    assert capture_run == []  # never reached the CLI
