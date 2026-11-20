#!/usr/bin/env python3
"""The ways a person can prove who they are before a write (README "Signing
in"): the shared key, personal keys, their own Jira or GitHub token, SSO, and
the cluster login in front of the dashboard. Each is off until configured, any
one is enough, and the person it proves is who the write is recorded under.

Same conventions as tests/test_authz_matrix.py: env set before `import ui`,
TestClient not entered (no lifespan threads).
"""
import hashlib
import io
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)
ADA = {"account_id": "acc-1", "email": "ada@example.com", "display_name": "Ada"}


@pytest.fixture(autouse=True)
def nothing_on(monkeypatch):
    """Every way off; each test switches on the one it is about."""
    for name, value in (("_API_KEY", ""), ("_OIDC_ENABLED", False), ("_API_KEYS_FILE", ""),
                        ("_AUTH_JIRA", False), ("_AUTH_GITHUB_ORG", ""), ("_PROXY_SECRET", ""),
                        ("_AUTH_ALLOWED_DOMAINS", []), ("_rate_limits", {}),
                        ("_personal_keys_cache", (0.0, {})), ("_github_member_cache", {}),
                        ("_sign_in_failures", {})):
        monkeypatch.setattr(ui, name, value)


def whoami(headers=None):
    return client.post("/api/whoami", json={}, headers=headers or {})


def test_a_laptop_dashboard_needs_no_sign_in():
    assert whoami().status_code == 200


def test_the_403_says_what_to_do_and_names_settings(monkeypatch):
    monkeypatch.setattr(ui, "_API_KEY", "team-secret")
    monkeypatch.setattr(ui, "_AUTH_JIRA", True)
    monkeypatch.setattr(ui, "_jira_identity", lambda *a: (None, None))
    r = whoami()
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert "Jira email and API token in Settings" in detail and "team's dashboard key" in detail


def test_team_key(monkeypatch):
    monkeypatch.setattr(ui, "_API_KEY", "team-secret")
    assert whoami({"X-API-Key": "wrong"}).status_code == 403
    r = whoami({"X-API-Key": "team-secret"})
    assert r.status_code == 200 and r.json()["source"] == "none"  # the shared key names no one


def test_personal_key_names_the_person_and_removing_it_revokes(monkeypatch, tmp_path):
    keys = tmp_path / "keys.yaml"
    keys.write_text(f"- name: Ada\n  email: Ada@Example.com\n  sha256: {hashlib.sha256(b'qfp_ada').hexdigest()}\n")
    monkeypatch.setattr(ui, "_API_KEYS_FILE", str(keys))
    r = whoami({"X-API-Key": "qfp_ada"})
    assert r.status_code == 200 and r.json()["actor"] == "ada@example.com"
    assert r.json()["source"] == "personal_key"
    assert whoami({"X-API-Key": "qfp_someone_else"}).status_code == 403
    keys.write_text("[]\n")
    os.utime(keys, (1, 1))  # a different mtime, as an edit would leave
    assert whoami({"X-API-Key": "qfp_ada"}).status_code == 403


def test_an_unreadable_keys_file_lets_no_one_in(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_API_KEYS_FILE", str(tmp_path / "missing.yaml"))
    assert whoami({"X-API-Key": "anything"}).status_code == 403


def test_own_jira_token(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_JIRA", True)
    seen = []
    monkeypatch.setattr(ui, "_jira_identity", lambda u, t, _url: (seen.append((u, t)) or (ADA if t == "jira-tok" else None), None))
    assert whoami({"X-Jira-Username": "ada@example.com", "X-Jira-Token": "bad"}).status_code == 403
    r = whoami({"X-Jira-Username": "ada@example.com", "X-Jira-Token": "jira-tok"})
    assert r.status_code == 200 and r.json()["actor"] == "ada@example.com" and r.json()["source"] == "jira"
    assert ("ada@example.com", "jira-tok") in seen


def test_allowed_domains_keep_other_accounts_out(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_JIRA", True)
    monkeypatch.setattr(ui, "_AUTH_ALLOWED_DOMAINS", ["redhat.com"])
    monkeypatch.setattr(ui, "_jira_identity", lambda *a: (ADA, None))
    assert whoami({"X-Jira-Username": "ada@example.com", "X-Jira-Token": "t"}).status_code == 403


def test_own_github_token(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_GITHUB_ORG", "example-org")
    monkeypatch.setattr(ui, "_github_member",
                        lambda tok: {"login": "ada", "name": "Ada", "email": ""} if tok == "gh-tok" else None)
    assert whoami({"X-GitHub-Token": "other"}).status_code == 403
    r = whoami({"X-GitHub-Token": "gh-tok"})
    assert r.status_code == 200 and r.json()["actor"] == "ada" and r.json()["source"] == "github"


class _Resp(io.BytesIO):
    def __init__(self, body=b"{}", status=200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.mark.parametrize("member_status, expected", [(204, "ada"), (404, None)])
def test_github_membership_check(monkeypatch, member_status, expected):
    monkeypatch.setattr(ui, "_AUTH_GITHUB_ORG", "example-org")
    calls = []

    def fake(req, timeout=None, context=None):
        calls.append(req.full_url)
        if req.full_url.endswith("/user"):
            return _Resp(b'{"login": "ada", "name": "Ada"}')
        if member_status != 204:
            raise urllib.error.HTTPError(req.full_url, member_status, "no", {}, None)
        return _Resp(status=204)

    monkeypatch.setattr(ui.urllib.request, "urlopen", fake)
    got = ui._github_member("gh-tok")
    assert (got or {}).get("login") == expected
    assert calls[-1] == "https://api.github.com/orgs/example-org/members/ada"
    ui._github_member("gh-tok")
    assert len(calls) == 2  # cached: no second round trip


def _basic(user, password):
    import base64
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_cluster_login_counts_only_with_the_proxy_secret(monkeypatch):
    monkeypatch.setattr(ui, "_PROXY_SECRET", "proxy-secret")
    r = whoami(_basic("ada@example.com", "proxy-secret"))
    assert r.status_code == 200 and r.json()["actor"] == "ada@example.com" and r.json()["source"] == "proxy"
    assert whoami(_basic("ada@example.com", "guess")).status_code == 403  # went round the proxy
    # X-Forwarded-* alone proves nothing: anyone can send them.
    assert whoami({"X-Forwarded-User": "ada", "X-Forwarded-Email": "ada@example.com"}).status_code == 403


def test_status_names_the_cluster_login_user(monkeypatch):
    monkeypatch.setattr(ui, "_PROXY_SECRET", "proxy-secret")
    assert client.get("/api/status", headers=_basic("ada", "proxy-secret")).json()["user"] == {"name": "ada", "email": ""}


def test_sso_session_is_enough(monkeypatch):
    monkeypatch.setattr(ui, "_OIDC_ENABLED", True)
    monkeypatch.setattr(ui, "_session_user", lambda _r: {"email": "ada@example.com", "name": "Ada"})
    r = whoami()
    assert r.status_code == 200 and r.json()["source"] == "oidc"


def test_status_lists_the_ways_on(monkeypatch):
    monkeypatch.setattr(ui, "_API_KEY", "team-secret")
    monkeypatch.setattr(ui, "_AUTH_JIRA", True)
    body = client.get("/api/status").json()
    assert body["auth_modes"] == ["jira", "team_key"] and body["auth_enabled"] is True


def test_half_configured_sso_does_not_start_with_open_writes(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("QF_DEV", "QUALITYFLOW_API_KEY")}
    env.update(OIDC_CLIENT_ID="x", QF_OUTPUTS_DIR=str(tmp_path), QF_CONFIG_DIR=str(tmp_path))
    r = subprocess.run([sys.executable, "-c", "import ui"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "no sign-in is configured" in r.stderr


def test_cluster_login_refuses_a_change_from_another_site(monkeypatch):
    monkeypatch.setattr(ui, "_PROXY_SECRET", "proxy-secret")
    h = _basic("ada", "proxy-secret")
    assert whoami({**h, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert whoami({**h, "Origin": "https://evil.example"}).status_code == 403
    assert whoami({**h, "Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_a_github_outage_is_not_cached_as_not_a_member(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_GITHUB_ORG", "example-org")
    state = {"down": True}

    def fake(req, timeout=None, context=None):
        if state["down"]:
            raise urllib.error.HTTPError(req.full_url, 502, "bad gateway", {}, None)
        if req.full_url.endswith("/user"):
            return _Resp(b'{"login": "ada"}')
        return _Resp(status=204)

    monkeypatch.setattr(ui.urllib.request, "urlopen", fake)
    assert ui._github_member("gh-tok") is None
    state["down"] = False
    assert ui._github_member("gh-tok")["login"] == "ada"


def test_github_cache_stays_bounded(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_GITHUB_ORG", "example-org")
    monkeypatch.setattr(ui.urllib.request, "urlopen",
                        lambda req, **k: (_ for _ in ()).throw(urllib.error.HTTPError(req.full_url, 401, "no", {}, None)))
    for i in range(ui._GITHUB_MEMBER_MAX + 50):
        ui._github_member(f"junk-{i}")
    assert len(ui._github_member_cache) == ui._GITHUB_MEMBER_MAX


def test_a_client_guessing_tokens_stops_being_checked(monkeypatch):
    monkeypatch.setattr(ui, "_AUTH_JIRA", True)
    calls = []
    monkeypatch.setattr(ui, "_jira_identity", lambda u, t, _url: (calls.append(t), (None, None))[1])
    for i in range(ui._SIGN_IN_FAILURES_MAX + 5):
        assert whoami({"X-Jira-Username": "victim@example.com", "X-Jira-Token": f"guess-{i}"}).status_code == 403
    assert len(calls) == ui._SIGN_IN_FAILURES_MAX


def test_verify_checks_the_typed_jira_creds_even_when_signed_in_another_way(monkeypatch, tmp_path):
    keys = tmp_path / "keys.yaml"
    keys.write_text(f"- name: Ada\n  email: ada@example.com\n  sha256: {hashlib.sha256(b'qfp_ada').hexdigest()}\n")
    monkeypatch.setattr(ui, "_API_KEYS_FILE", str(keys))
    monkeypatch.setattr(ui, "_jira_identity", lambda u, t, _url: (None, "invalid Jira credentials") if u else (None, None))
    r = client.post("/api/whoami", json={"jira_username": "ada@example.com", "jira_token": "wrong"},
                    headers={"X-API-Key": "qfp_ada"})
    # Signed in by the personal key, but the Jira creds being verified are wrong: say so.
    assert r.status_code == 200 and r.json()["verified"] is False
    assert r.json()["error"] == "invalid Jira credentials"
