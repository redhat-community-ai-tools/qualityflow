"""Credential redaction in run_phase()'s failure path (P1-B,
RUN-2026-09-08-dual-runtime FIX-P1).

pipeline_runner.run_phase() embeds subprocess stderr into the RuntimeError
message it raises on a non-zero exit; ui.py's _mark_failed then persists
str(e)[:500] to pipeline_state.yaml on the PVC. If the `claude`/`agent` CLI
ever echoes a rejected credential back on stderr, it must never survive into
that persisted string — for either runtime, since both share the same raise
site in run_phase().

Expectations below are hand-labelled (literal strings), never produced by
calling _redact_secrets and asserting equality with its own output.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_redaction.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402

# Fake secret literals — obviously not real credentials.
FAKE_CURSOR_KEY = "key_FAKENOTAREALSECRET0000000000"
FAKE_ATLASSIAN_TOKEN = "ATATT3xFAKE0000000000000000000000000000FAKE"
FAKE_GITHUB_PAT = "ghp_FAKENOTAREALSECRET00000000000A"
FAKE_GITHUB_FINE_PAT = "github_pat_FAKENOTAREALSECRET000000000000000000000000"
FAKE_GOOGLE_KEY = "AIzaFAKENOTAREALSECRET0000000000000"
FAKE_REFRESH_TOKEN = "1//0FAKEFAKEFAKEFAKEFAKEFAKE"
FAKE_CLIENT_SECRET = "GOCSPX-FAKEFAKEFAKE"


# --- unit: the helper itself, one hand-labelled case per credential shape --

def test_redact_secrets_cursor_key():
    text = f"rejected key {FAKE_CURSOR_KEY} for workspace"
    assert pipeline_runner._redact_secrets(text) == "rejected key [redacted] for workspace"


def test_redact_secrets_cursor_crsr_prefix():
    text = "rejected key crsr_FAKENOTAREALSECRET0000000000000000000000000000 for workspace"
    assert pipeline_runner._redact_secrets(text) == "rejected key [redacted] for workspace"


def test_redact_secrets_atlassian_token():
    text = f"auth failed: token {FAKE_ATLASSIAN_TOKEN} invalid"
    assert pipeline_runner._redact_secrets(text) == "auth failed: token [redacted] invalid"


def test_redact_secrets_github_pat():
    text = f"bad credentials ({FAKE_GITHUB_PAT})"
    assert pipeline_runner._redact_secrets(text) == "bad credentials ([redacted])"


def test_redact_secrets_github_fine_grained_pat():
    text = f"bad credentials ({FAKE_GITHUB_FINE_PAT})"
    assert pipeline_runner._redact_secrets(text) == "bad credentials ([redacted])"


def test_redact_secrets_google_key():
    text = f"API key {FAKE_GOOGLE_KEY} rejected"
    assert pipeline_runner._redact_secrets(text) == "API key [redacted] rejected"


def test_redact_secrets_google_refresh_token():
    text = f"invalid_grant for {FAKE_REFRESH_TOKEN} here"
    assert pipeline_runner._redact_secrets(text) == "invalid_grant for [redacted] here"


def test_redact_secrets_google_oauth_client_secret():
    text = f"client secret {FAKE_CLIENT_SECRET} rejected"
    assert pipeline_runner._redact_secrets(text) == "client secret [redacted] rejected"


def test_redact_secrets_adc_json_fields_quoted_back_by_google_auth():
    """google-auth can echo the ADC file's own contents, not just its path."""
    text = ('failed to parse {"type": "authorized_user", "refresh_token": "whatever-shape", '
            '"client_secret": "also-secret"}')
    out = pipeline_runner._redact_secrets(text)
    assert "whatever-shape" not in out
    assert "also-secret" not in out
    assert out.count("[redacted]") == 2
    assert '"type": "authorized_user"' in out  # not a secret, keep it diagnosable


def test_redact_secrets_no_secret_passthrough():
    assert pipeline_runner._redact_secrets("plain error, nothing sensitive") == \
        "plain error, nothing sensitive"


def test_redact_secrets_empty_and_none():
    assert pipeline_runner._redact_secrets("") == ""
    assert pipeline_runner._redact_secrets(None) is None


# --- integration: the fake secret must not survive into the raised message,
# for EITHER runtime, since both go through the same raise site -----------

def _fake_nonzero_run(stderr_text):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout='{"type":"result","result":"failed"}\n', stderr=stderr_text)
    return fake_run


def test_cursor_error_path_redacts_leaked_key(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setattr(pipeline_runner.subprocess, "run",
                        _fake_nonzero_run(f"error: rejected api key {FAKE_CURSOR_KEY}\n"))
    with pytest.raises(RuntimeError) as exc_info:
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="cursor")
    message = str(exc_info.value)
    assert FAKE_CURSOR_KEY not in message
    assert "[redacted]" in message


def test_expired_vertex_credential_gets_an_actionable_hint(monkeypatch):
    """A ~daily event (Red Hat's 16h Google Cloud session). Without this it
    surfaces as a raw google-auth trace 30 minutes into a failed phase."""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setattr(pipeline_runner.subprocess, "run",
                        _fake_nonzero_run(
                            f'{{"error": "invalid_grant", "refresh_token": "{FAKE_REFRESH_TOKEN}"}}\n'))
    with pytest.raises(RuntimeError) as exc_info:
        pipeline_runner.run_phase("", "PROJ-1", "stp")
    message = str(exc_info.value)
    assert "gcloud auth application-default login" in message
    assert "16h" in message
    assert FAKE_REFRESH_TOKEN not in message


def test_claude_error_path_redacts_leaked_token(monkeypatch):
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.delenv("QF_OUTPUTS_DIR", raising=False)
    monkeypatch.setattr(pipeline_runner.subprocess, "run",
                        _fake_nonzero_run(f"error: token {FAKE_ATLASSIAN_TOKEN} rejected\n"))
    with pytest.raises(RuntimeError) as exc_info:
        pipeline_runner.run_phase("", "PROJ-1", "stp", runtime="claude")
    message = str(exc_info.value)
    assert FAKE_ATLASSIAN_TOKEN not in message
    assert "[redacted]" in message
