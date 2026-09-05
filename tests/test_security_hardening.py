#!/usr/bin/env python3
"""Security regressions (wave W5): the SEC-01 lane plus the shared RATELIMIT
root cause.

SEC-01-F3  (C26) GET /api/status echoed GIT_REPO_URL verbatim — a
           https://user:TOKEN@host/... URL handed the token to anonymous callers
SEC-01-F4  (C25, RATE-LIMIT-CI-LOCKOUT) the write-endpoint rate limiter keyed on
           request.client.host: behind the chart's own Route every user shared
           one bucket, and widening forwarded_allow_ips let a client rotate
           X-Forwarded-For for an unbounded budget
SEC-01-F8  (C30) /api/beacon is unauthenticated by design and appended to
           _USAGE_LOG with no global budget and no size cap
SEC-01-F5  (C28) POST /api/github/org-repos had no key check, no rate limit and
           unbounded pagination (the authz matrix now covers the route too)
SEC-01-F2       onboard_coverage took dashboard_url from the body/Host and baked
           it into a workflow that POSTs the repo's QUALITYFLOW_API_KEY
SEC-01-F9  (C22) the OIDC session cookie lost Secure whenever the redirect URI
           was not itself https
SEC-01-F11 (C24) post-login redirect accepted "//host" (protocol-relative)

Same conventions as tests/test_reliability.py: QF_DEV/QF_OUTPUTS_DIR set before
`import ui`, ui is a module-level singleton so globals are monkeypatched per
test, and the module-level TestClient is NOT entered as a context manager.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_security_hardening.py -q
"""
import ipaddress
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))  # replaced per-test by the fixture
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import
from fastapi.testclient import TestClient  # noqa: E402

TRUSTED_PROXY = "10.0.0.0/8"  # stands in for the ingress controller's pod CIDR
PROXY_PEER = "10.0.0.1"  # the connection itself comes from that proxy

client = TestClient(ui.app, client=(PROXY_PEER, 50000))


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Filesystem in tmp, limiter state fresh, one trusted proxy hop."""
    monkeypatch.setattr(ui, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(ui, "_USAGE_LOG", tmp_path / "outputs" / "_usage" / "dashboard_usage.jsonl")
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_beacon_hits", [])
    monkeypatch.setattr(ui, "_TRUSTED_HOPS", [ipaddress.ip_network(TRUSTED_PROXY)])
    monkeypatch.setattr(ui, "_TRUST_ANY_HOP", False)


class _Req:
    """Just enough Request for _client_key."""

    def __init__(self, xff="", host=PROXY_PEER):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": host})()


def _beacon(xff, view="dash"):
    return client.post("/api/beacon", json={"view": view}, headers={"X-Forwarded-For": xff})


# --- SEC-01-F3 / C26 -------------------------------------------------------

def test_status_does_not_leak_git_credentials(monkeypatch):
    monkeypatch.setenv("GIT_REPO_URL", "https://qfbot:ghp_FAKE@git.example.com/t/r.git")
    body = client.get("/api/status").text
    assert "git.example.com/t/r.git" in body
    assert "ghp_FAKE" not in body
    assert "qfbot" not in body


# --- SEC-01-F4 / C25, RATE-LIMIT-CI-LOCKOUT --------------------------------

def test_client_key_is_the_last_untrusted_hop():
    assert ui._client_key(_Req("203.0.113.9, 10.0.0.1")) == "203.0.113.9"


def test_client_key_ignores_xff_when_the_peer_is_not_a_trusted_proxy(monkeypatch):
    """A pod reachable directly must not let the caller pick its own key."""
    monkeypatch.setattr(ui, "_TRUSTED_HOPS", [])
    assert ui._client_key(_Req("203.0.113.9, 10.0.0.1", host="127.0.0.1")) == "127.0.0.1"
    assert ui._client_key(_Req("1.2.3.4", host="203.0.113.5")) == "203.0.113.5"


def test_client_key_star_trusts_exactly_the_connecting_hop(monkeypatch):
    monkeypatch.setattr(ui, "_TRUSTED_HOPS", [])
    monkeypatch.setattr(ui, "_TRUST_ANY_HOP", True)
    assert ui._client_key(_Req("203.0.113.9, 10.0.0.1")) == "10.0.0.1"


def test_rotating_xff_cannot_buy_a_fresh_bucket(monkeypatch):
    """The attacker controls the LEFT of X-Forwarded-For; the proxy appends on
    the right. Prepending rotating addresses must not reset the budget."""
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 5)
    for _ in range(5):
        assert _beacon("203.0.113.9, 10.0.0.1").status_code == 200
    for i in range(10):
        resp = _beacon(f"198.51.100.{i}, 203.0.113.9, 10.0.0.1")
        assert resp.status_code == 429, f"rotation {i} bought a fresh bucket"
        assert resp.headers.get("Retry-After") == "60"


def test_distinct_clients_do_not_share_one_bucket(monkeypatch):
    """RATE-LIMIT-CI-LOCKOUT: behind a Route every user used to key on the
    router pod's address, so 30 UI clicks 429'd everybody."""
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 5)
    for _ in range(5):
        assert _beacon("203.0.113.9, 10.0.0.1").status_code == 200
    assert _beacon("203.0.113.9, 10.0.0.1").status_code == 429
    assert _beacon("203.0.113.77, 10.0.0.1").status_code == 200


# --- SEC-01-F8 / C30 -------------------------------------------------------

def test_beacon_has_a_global_budget(monkeypatch):
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    assert ui._BEACON_MAX_PER_WINDOW == 600
    last = None
    for i in range(601):
        last = _beacon(f"203.0.113.{i % 200}, 10.0.0.1")
    assert last.status_code == 200
    assert last.json() == {"status": "ignored"}
    assert len(ui._USAGE_LOG.read_text().splitlines()) == 600


def test_usage_log_is_rotated_when_oversized(monkeypatch):
    monkeypatch.setattr(ui, "_USAGE_LOG_MAX_BYTES", 100)
    ui._USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    ui._USAGE_LOG.write_text("x" * 200 + "\n")
    assert _beacon("203.0.113.9, 10.0.0.1").status_code == 200
    rotated = ui._USAGE_LOG.with_name(ui._USAGE_LOG.name + ".1")
    assert rotated.exists()
    assert len(ui._USAGE_LOG.read_text().splitlines()) == 1


# --- SEC-01-F5 / C28 -------------------------------------------------------

def test_org_repos_is_covered_by_the_authz_matrix():
    """The route used to sit in that test's ALLOWLIST as a known gap."""
    import test_authz_matrix

    assert "/api/github/org-repos" not in test_authz_matrix.ALLOWLIST
    assert any(p == "/api/github/org-repos" for _, p, _ in test_authz_matrix.ROUTES)


def test_org_repos_reaches_its_body_with_a_valid_key(monkeypatch):
    monkeypatch.setattr(ui, "_API_KEY", "testkey")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")
    resp = client.post("/api/github/org-repos", json={"org": "acme"},
                       headers={"X-API-Key": "testkey", "X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert resp.status_code == 503  # "No GitHub token available" — past both guards


def test_org_repos_pagination_is_capped():
    assert ui._ORG_REPOS_MAX_PAGES <= 10


# --- SEC-01-F2 -------------------------------------------------------------

def test_onboard_rejects_a_foreign_dashboard_url(monkeypatch):
    monkeypatch.setattr(ui, "_API_KEY", "testkey")
    monkeypatch.setattr(ui, "_BASE_URL", "https://qf.example.com")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_server")
    monkeypatch.setattr(ui, "_github_detect_language",
                        lambda *a, **k: pytest.fail("reached the network"))
    resp = client.post("/api/coverage/onboard",
                       json={"org": "o", "repo": "r", "dashboard_url": "https://collector.attacker.tld"},
                       headers={"X-API-Key": "testkey", "X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert resp.status_code == 400
    assert "dashboard_url" in resp.text


# --- SEC01-C29 (wave W10) --------------------------------------------------
# The F2 guard above only engaged when QUALITYFLOW_BASE_URL was set, and
# nothing in the chart set it; unset, dashboard_url fell through to the body or
# the Host header and was baked into the workflow that POSTs the API key.

@pytest.mark.parametrize("path,body", [
    ("/api/coverage/onboard", {"org": "o", "repo": "r",
                               "dashboard_url": "https://collector.attacker.tld"}),
    ("/api/coverage/onboard", {"org": "o", "repo": "r"}),
    ("/api/projects/example/bulk-onboard", {}),
])
def test_onboarding_refuses_a_caller_chosen_url_when_base_url_is_unset(
        monkeypatch, tmp_path, path, body):
    monkeypatch.setattr(ui, "_API_KEY", "testkey")
    monkeypatch.setattr(ui, "_BASE_URL", "")  # the default — chart sets nothing
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "ghp_server")
    monkeypatch.setattr(ui, "CONFIG", tmp_path / "config")
    (tmp_path / "config" / "projects" / "example").mkdir(parents=True)
    (tmp_path / "config" / "projects" / "example" / "coverage.yaml").write_text(
        "repos:\n  - org: o\n    repo: r\n")
    for fn in ("_github_detect_language", "_generate_go_instrumentation",
               "_generate_python_instrumentation", "_github_api"):
        monkeypatch.setattr(ui, fn, lambda *a, **k: pytest.fail("reached the network"))

    resp = client.post(path, json=body, headers={
        "X-API-Key": "testkey", "Host": "qualityflow.evil.example",
        "X-Forwarded-For": "203.0.113.9, 10.0.0.1"})

    assert resp.status_code == 503, resp.text
    assert "QUALITYFLOW_BASE_URL" in resp.text
    assert "evil.example" not in resp.text
    assert "attacker.tld" not in resp.text


def test_no_route_derives_its_own_url_from_the_request():
    """_request_base_url is gone; nothing may resurrect a Host-derived base URL."""
    source = (ROOT / "ui.py").read_text()
    assert "def _request_base_url" not in source
    assert source.count("dashboard_url = _key_carrying_base_url()") == 2


# --- SEC-01-F9 / C22 -------------------------------------------------------

def test_session_cookie_is_secure_by_default(monkeypatch):
    monkeypatch.delenv("QF_INSECURE_COOKIES", raising=False)
    assert ui._insecure_cookies() is False  # https_only=True
    monkeypatch.setenv("QF_INSECURE_COOKIES", "1")
    assert ui._insecure_cookies() is True


# --- SEC-01-F11 / C24 ------------------------------------------------------

@pytest.mark.parametrize("dest,expected", [
    ("//evil.example/x", "/"),
    ("/\\evil.example", "/"),
    ("https://evil.example", "/"),
    ("/pipelines/PROJ-1", "/pipelines/PROJ-1"),
    ("/", "/"),
])
def test_post_login_redirect_stays_on_this_host(dest, expected):
    assert ui._safe_dest(dest) == expected


# --- SEC01-C10 / SEC-01-F10 ------------------------------------------------

@pytest.mark.parametrize("segment", ["%2e%2e", "%2e", ".."])
def test_project_route_does_not_walk_out_of_the_projects_dir(segment):
    """GET /api/projects/%2e%2e used to resolve to config/ itself and hand an
    anonymous caller a listing of _defaults.yaml, routing.yaml and friends."""
    r = client.get(f"/api/projects/{segment}")
    assert r.status_code == 404, "a traversal segment must not resolve to a real dir"
    assert "_defaults.yaml" not in r.text


def test_project_id_route_params_are_all_sanitized():
    """The guard belongs on every handler that joins the path param, not only
    the one the audit probed — a new sibling handler inherits the omission."""
    import inspect

    for route in ui.app.routes:
        if not getattr(route, "path", "").startswith("/api/projects/{project_id}"):
            continue
        src = inspect.getsource(route.endpoint)
        assert "_safe_path_segment(project_id)" in src, f"{route.path} joins project_id raw"


# --- REL-F13: /readyz 503 must not echo the path the probe tripped over ----

def test_readyz_503_does_not_leak_the_outputs_path(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")  # OUTPUTS under a regular file => NotADirectoryError
    monkeypatch.setattr(ui, "OUTPUTS", blocker / "outputs")

    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["detail"] == "Not ready: outputs directory check failed"
    assert str(tmp_path) not in r.text


def test_readyz_503_names_the_config_probe_without_its_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(ui, "CONFIG", tmp_path / "gone" / "config")

    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["detail"] == "Not ready: config directory check failed"
    assert str(tmp_path) not in r.text
