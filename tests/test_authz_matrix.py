#!/usr/bin/env python3
"""Authz matrix: every mutating route must reject an unauthenticated write.

Pins SEC-01-F1 (check SEC01-C02): POST /api/coverage/onboard and
POST /api/projects/{project_id}/bulk-onboard used to skip the API-key guard
whenever the request body carried a non-empty `github_token` — auth decided by
attacker-controlled body content. A user's GitHub PAT is a *GitHub* credential,
never a dashboard one.

Routes are enumerated from ui.app.routes rather than hardcoded, so a new
mutating route added without a guard fails here instead of shipping.

Same conventions as tests/test_metrics_endpoints.py: QF_DEV/QF_OUTPUTS_DIR set
before `import ui`, and TestClient NOT entered as a context manager (that would
run the lifespan: git sync + background threads over the real outputs/).

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_authz_matrix.py -q
"""
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

client = TestClient(ui.app)

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Routes that are deliberately reachable without a dashboard API key.
ALLOWLIST = {
    "/api/beacon": "documented unauthenticated: navigator.sendBeacon fire-and-forget view counter",
    "/api/post-check": "documented unauthenticated: no side effect, echoes the posted body",
    # KNOWN GAP, tracked separately as SEC-01-F5 (P1, wave W5): unauthenticated
    # and it spends the *server's* GitHub token. Out of scope for the SEC-01-F1
    # fix; delete this entry when W5 lands its guard.
    "/api/github/org-repos": "KNOWN GAP SEC-01-F5 (P1, wave W5): no guard yet, fixed in a separate lane",
}

# Path-param fillers chosen so nothing exists and no route can have a side effect.
PARAMS = {"jira_id": "PROJ-999", "project_id": "sec01probe",
          "phase": "stp", "from_phase": "std"}

# Bodies + query strings reused verbatim from the audit probe
# (audit-runs/RUN-2026-09-02/SEC-01/probe.sh) so this test exercises the same
# requests the live probe did.
BODIES = {
    "/api/projects/{project_id}/toggles": {"toggles": {"stp_generation": True}},
    "/api/projects": {"id": "sec01created", "name": "x"},
    "/api/projects/{project_id}/import-repos": {"repos": []},
    "/api/projects/{project_id}/bulk-onboard": {"github_token": "ghp_fake"},
    "/api/pipelines/init": {"jira_id": "PROJ-2"},
    "/api/outputs/{jira_id}": {"path": "stp/x.md", "content": "hi"},
    "/api/pipelines/{jira_id}/approve/{phase}": {"status": "approved"},
    "/api/coverage/upload": {"org": "o", "repo": "r"},
    "/api/coverage/product/upload": {"project_id": "sec01probe"},
    "/api/coverage/test/upload": {"project_id": "sec01probe"},
    "/api/coverage/onboard": {"github_token": "ghp_fake"},
}
# Required query params — FastAPI validates these before the handler's guard runs,
# so omitting them would mask the 403 behind a 422.
QUERY = {
    "/api/coverage/collect": {"org": "sec01org", "repo": "sec01repo"},
    "/api/coverage/collect-product": {"project_id": "sec01probe"},
}

# The two routes SEC-01-F1 broke: the bypass body must not buy access.
BYPASS_ROUTES = {"/api/coverage/onboard", "/api/projects/{project_id}/bulk-onboard"}

FORGED = {
    "Referer": "https://qualityflow.example.com/dashboard",
    "Origin": "https://qualityflow.example.com",
    "Host": "qualityflow.example.com",
}


def _guarded_routes():
    out = []
    for route in ui.app.routes:
        for method in sorted((getattr(route, "methods", set()) or set()) & MUTATING):
            if route.path in ALLOWLIST:
                continue
            url = route.path
            for name, value in PARAMS.items():
                url = url.replace("{%s}" % name, value)
            assert "{" not in url, f"no PARAMS filler for {route.path}"
            out.append((method, route.path, url))
    return out


ROUTES = _guarded_routes()
IDS = [f"{m} {p}" for m, p, _ in ROUTES]


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Real key set, rate limiter defanged, filesystem pointed at tmp.

    _check_rate_limit runs *before* auth on several routes and allows only 30
    writes/min per client host — TestClient's host is constant, so the matrix
    would trip it partway through and turn 403s into 429s.
    """
    monkeypatch.setattr(ui, "_API_KEY", "testkey")
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 100000)
    monkeypatch.setattr(ui, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(ui, "CONFIG", tmp_path / "config")


def _request(method, url, path, **kw):
    return client.request(method, url, params=QUERY.get(path), json=BODIES.get(path, {}), **kw)


@pytest.mark.parametrize("method,path,url", ROUTES, ids=IDS)
def test_no_api_key_is_rejected(method, path, url):
    resp = _request(method, url, path)
    assert resp.status_code == 403, f"{method} {path} accepted a request with NO API key: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("method,path,url", ROUTES, ids=IDS)
def test_wrong_api_key_is_rejected(method, path, url):
    resp = _request(method, url, path, headers={"X-API-Key": "wrongkey"})
    assert resp.status_code == 403, f"{method} {path} accepted a WRONG API key: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("method,path,url", ROUTES, ids=IDS)
def test_forged_origin_headers_are_rejected(method, path, url):
    """Referer/Origin/Host are attacker-controlled; they must not stand in for the key."""
    resp = _request(method, url, path, headers=FORGED)
    assert resp.status_code == 403, f"{method} {path} accepted forged Referer/Origin/Host: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("path", sorted(BYPASS_ROUTES))
def test_bypass_routes_still_work_with_a_valid_key(path):
    """The fix must not lock out legitimate callers: with the key, these get
    past auth and fail on validation instead (no GitHub call is reached —
    onboard stops on the missing org/repo, bulk-onboard on the missing project)."""
    url = path
    for name, value in PARAMS.items():
        url = url.replace("{%s}" % name, value)
    resp = client.post(url, json=BODIES[path], headers={"X-API-Key": "testkey"})
    assert resp.status_code != 403, f"POST {path} rejected a VALID API key"
    assert resp.status_code in (400, 404), f"POST {path} expected a validation error, got {resp.status_code} {resp.text[:200]}"
