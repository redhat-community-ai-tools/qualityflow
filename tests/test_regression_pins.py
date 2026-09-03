#!/usr/bin/env python3
"""Pins for three fixes that shipped with no automated check behind them.

TEST-01-F03  PAT-not-in-URL. A `repo`-scoped GitHub PAT used to travel as a
             query parameter, which puts it in the uvicorn access log, the
             ingress log and the browser history — none of them rotatable.
             The fix moved it into the Authorization header / POST body.
TEST-01-F04  Legacy-layout "zero metrics". Artifacts written in the older
             type-first layout (outputs/{sub}/{id}/…) were invisible to every
             path helper, so a migrated instance reported an empty dashboard.
             The fix is the canonical-first-with-legacy-fallback resolver
             (_canonical_or_legacy / _pick_dir / _state_dir / _iter_state_files).
TEST-01-F05  _collect_pr_files folding. Generated Python tests land in the
             "tier2" group; when no separate tier2 repo is configured they used
             to be silently DROPPED from the push — collected, credited in the
             metrics, committed nowhere. The fix folds them into the primary push.

Every GitHub-bound call in this file is monkeypatched at urllib.request.urlopen:
ui.py auto-loads the repo .env at import, so a real PAT is in the process
environment and an un-patched call would hit github.com for real.

Same conventions as tests/test_state_safety.py: QF_DEV/QF_OUTPUTS_DIR set before
`import ui`, ui is a module-level singleton so globals are monkeypatched per
test, and the module-level TestClient is NOT entered as a context manager.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_regression_pins.py -q
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))  # replaced per-test by the fixture
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)

KEY = "w8testkey"
HDR = {"X-API-Key": KEY}
# Distinctive enough that a substring search for it cannot false-positive.
TOKEN = "ghp_w8pinSENTINEL0000000000000000000000"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh tmp outputs/ + config/ per test, with every module global derived
    from them at import time re-pointed. Mirrors test_state_safety.py::env."""
    out = tmp_path / "outputs"
    out.mkdir()
    cfg = tmp_path / "config"
    (cfg / "projects").mkdir(parents=True)
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "CONFIG", cfg)
    monkeypatch.setattr(ui, "COVERAGE_DIR", out / "coverage")
    monkeypatch.setattr(ui, "_TEST_COVERAGE_DIR", out / "coverage" / "_tests")
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_routing_cache", (0.0, {}))
    monkeypatch.setattr(ui, "_USAGE_LOG", out / "_usage" / "dashboard_usage.jsonl")
    monkeypatch.setattr(ui, "_API_KEY", KEY)
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    monkeypatch.setattr(ui, "_slack_pipeline_event", lambda *a, **k: None)
    monkeypatch.setattr(ui, "_get_approval_gates", lambda _pid: ["stp", "std"])
    monkeypatch.setattr(ui, "_infer_project", lambda _jid: "example")
    return out


# ---------------------------------------------------------------------------
# TEST-01-F03 — the PAT never appears in a URL
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.fixture
def captured_requests(monkeypatch):
    """Capture every urllib Request ui.py would have sent, answer it with a
    plausible GitHub payload, and never touch the network."""
    seen: list[urllib.request.Request] = []

    def _fake_urlopen(req, *_a, **_k):
        seen.append(req)
        return _FakeResponse(_github_reply(req))

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    return seen


def _github_reply(req):
    """Minimum shape each _github_* helper unpacks from its response."""
    url = req.full_url
    if url.endswith("/user"):
        return {"login": "w8bot"}
    if "/git/ref/heads/" in url:
        return {"object": {"sha": "a" * 40}}
    if "/git/commits" in url:
        return {"sha": "b" * 40, "tree": {"sha": "c" * 40}}
    if "/git/trees" in url:
        return {"sha": "d" * 40}
    if url.endswith("/pulls"):
        return {"html_url": "https://github.com/o/r/pull/1", "number": 1, "state": "open"}
    if re.search(r"/repos/[^/]+/[^/]+$", url):
        # Repo lookup during fork resolution: claim direct push access so the
        # fork-creation branch (which sleeps 5s a try) is never taken.
        return {"permissions": {"push": True}, "fork": False}
    if "/repos" in url and "per_page" in url:
        return [{"name": "r1", "full_name": "w8org/r1", "language": "Go",
                 "description": "", "stargazers_count": 1, "updated_at": "",
                 "default_branch": "main", "fork": False, "archived": False}]
    return {}


def _assert_token_never_in_urls(seen, token=TOKEN):
    assert seen, "no GitHub request was captured — the test did not exercise the call path"
    for req in seen:
        assert token not in req.full_url, f"PAT leaked into the URL: {req.full_url}"
        assert token not in (req.selector or ""), f"PAT leaked into the path: {req.selector}"
    # …and it really was sent, in the header, or this test would pass on a
    # helper that simply forgot to authenticate.
    assert any(token in str(v) for req in seen for v in req.headers.values()), \
        "PAT never reached an Authorization header"


def test_github_api_sends_the_pat_in_the_header_not_the_url(captured_requests):
    ui._github_api("GET", "https://api.github.com/user", TOKEN)
    _assert_token_never_in_urls(captured_requests)
    assert captured_requests[0].headers["Authorization"] == f"Bearer {TOKEN}"


def test_org_repos_listing_posts_the_pat_in_the_body(env, captured_requests):
    r = client.post("/api/github/org-repos", headers=HDR,
                    json={"org": "w8org", "token": TOKEN})
    assert r.status_code == 200, r.text
    _assert_token_never_in_urls(captured_requests)


def test_push_to_pr_never_puts_the_pat_in_a_url(env, captured_requests, monkeypatch):
    jid = "PIN-1"
    _seed_canonical(env, jid)
    _seed_repos_yaml(ui.CONFIG, "example", primary="w8org/primary")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")

    r = client.post(f"/api/pipelines/{jid}/push-pr", headers=HDR,
                    json={"github_token": TOKEN})
    assert r.status_code == 200, r.text
    _assert_token_never_in_urls(captured_requests)


def test_no_github_url_in_ui_py_source_interpolates_a_token():
    """Static backstop for the call sites this file does not drive: nothing may
    build a GitHub URL with a token/access_token query parameter."""
    src = (ROOT / "ui.py").read_text()
    offenders = [line.strip() for line in src.splitlines()
                 if re.search(r"[?&](access_)?token=", line)
                 and "github" in line.lower()]
    assert not offenders, f"token in a GitHub URL: {offenders}"


# ---------------------------------------------------------------------------
# TEST-01-F04 — legacy type-first layout still produces metrics
# ---------------------------------------------------------------------------

_PHASES = {"stp": {"status": "completed", "output": "stp/plan.md"},
           "std": {"status": "completed", "output": "std/desc.yaml"},
           "codegen": {"status": "completed"}}


def _state_doc(jira_id, phases=None):
    return {"ticket_id": jira_id, "project_id": "example",
            "phases": phases if phases is not None else _PHASES,
            "updated": "2026-01-02T00:00:00Z"}


def _seed_canonical(out: Path, jira_id: str, phases=None, marker: str = "canonical"):
    """outputs/{id}/{sub}/… — the layout the pipeline-state skill writes today."""
    (out / jira_id / "stp").mkdir(parents=True, exist_ok=True)
    (out / jira_id / "stp" / f"{jira_id}_test_plan.md").write_text(f"# plan {marker}\n")
    (out / jira_id / "std").mkdir(parents=True, exist_ok=True)
    (out / jira_id / "std" / f"{jira_id}_test_description.yaml").write_text("scenarios: []\n")
    (out / jira_id / "python-tests").mkdir(parents=True, exist_ok=True)
    (out / jira_id / "python-tests" / "qf_widget.py").write_text("def test_widget():\n    pass\n")
    state = out / jira_id / "state" / "pipeline_state.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(yaml.safe_dump(_state_doc(jira_id, phases), sort_keys=False))


def _seed_legacy(out: Path, jira_id: str, phases=None, marker: str = "legacy"):
    """outputs/{sub}/{id}/… — the pre-migration type-first layout the DATA-01
    probe reproduced (audit-runs/RUN-2026-09-02/DATA-01/probe_layout.txt)."""
    (out / "stp" / jira_id).mkdir(parents=True, exist_ok=True)
    (out / "stp" / jira_id / f"{jira_id}_test_plan.md").write_text(f"# plan {marker}\n")
    (out / "std" / jira_id).mkdir(parents=True, exist_ok=True)
    (out / "std" / jira_id / f"{jira_id}_test_description.yaml").write_text("scenarios: []\n")
    (out / "python-tests" / jira_id).mkdir(parents=True, exist_ok=True)
    (out / "python-tests" / jira_id / "qf_widget.py").write_text("def test_widget():\n    pass\n")
    state = out / "state" / jira_id / "pipeline_state.yaml"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(yaml.safe_dump(_state_doc(jira_id, phases), sort_keys=False))


def _pipeline_row(jira_id):
    r = client.get("/api/pipelines")
    assert r.status_code == 200, r.text
    rows = [row for row in r.json() if row["jira_id"] == jira_id]
    assert rows, f"{jira_id} missing from /api/pipelines"
    return rows[0]


def _metrics(project_id="example"):
    r = client.get(f"/api/metrics/{project_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _layout_snapshot(jira_id):
    """Everything the dashboard derives from the artifact tree for one ticket."""
    row = _pipeline_row(jira_id)
    m = _metrics()
    return {
        "has_state_file": row["has_state_file"],
        "phases": {k: v["status"] for k, v in row["phases"].items()},
        "totals": m["totals"],
        "phase_completion": m["phase_completion"],
        "artifacts_produced": m["value"]["artifacts_produced"],
        "tests_generated": m["value"]["tests_generated"],
        "stp_resolved": ui._artifact_path(jira_id, "stp").exists(),
        "std_resolved": ui._artifact_path(jira_id, "std").exists(),
        "state_resolved": (ui._state_dir(jira_id) / "pipeline_state.yaml").exists(),
        "swept": [j for j, _p in ui._iter_state_files()],
        "py_tests": [p.name for p in ui._find_test_files(jira_id, "python")],
    }


def test_legacy_layout_reports_the_same_non_zero_metrics_as_canonical(env, tmp_path, monkeypatch):
    """The zero-metrics regression: a legacy-layout instance listed the ticket
    but every artifact-derived number came back 0. Both trees hold the same
    ticket, so every derived number must match."""
    jid = "LEG-1"
    _seed_legacy(env, jid)
    legacy = _layout_snapshot(jid)

    canonical_root = tmp_path / "outputs_canonical"
    canonical_root.mkdir()
    _seed_canonical(canonical_root, jid)
    monkeypatch.setattr(ui, "OUTPUTS", canonical_root)
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_metrics_cache", {})
    canonical = _layout_snapshot(jid)

    assert legacy == canonical, "legacy layout does not resolve like canonical"
    # …and the shared numbers are real, not a matched pair of zeros.
    assert canonical["totals"]["pipelines"] == 1
    assert canonical["artifacts_produced"] == {"stps": 1, "stds": 1, "reviews": 0, "total": 2}
    assert canonical["tests_generated"]["python_files"] == 1
    assert canonical["phases"]["codegen"] == "completed"
    assert canonical["swept"] == [jid]
    assert canonical["py_tests"] == ["qf_widget.py"]
    assert all(canonical[k] for k in ("has_state_file", "stp_resolved",
                                      "std_resolved", "state_resolved"))


def test_canonical_wins_when_both_layouts_exist(env):
    """Legacy is a fallback, never an override: a half-migrated tree must read
    the canonical copy, or a stale pre-migration artifact silently wins."""
    jid = "BOTH-1"
    _seed_legacy(env, jid, phases={"stp": {"status": "failed"}}, marker="legacy")
    _seed_canonical(env, jid, marker="canonical")

    assert "canonical" in ui._artifact_path(jid, "stp").read_text()
    assert ui._state_dir(jid) == env / jid / "state"
    # Canonical says completed (→ awaiting_approval under the gate overlay);
    # the legacy state file says failed, and must not be the one that is read.
    assert _pipeline_row(jid)["phases"]["stp"]["status"] == "awaiting_approval"
    # De-duped: one ticket, not one per layout.
    assert [j for j, _p in ui._iter_state_files()] == [jid]
    assert ui._pick_dir(env / jid / "python-tests",
                        env / "python-tests" / jid) == env / jid / "python-tests"


# ---------------------------------------------------------------------------
# TEST-01-F05 — generated Python tests reach the primary push
# ---------------------------------------------------------------------------

def _seed_repos_yaml(cfg: Path, project_id: str, primary: str, tier2: str = ""):
    doc = {"primary_repo": {"full_name": primary, "default_branch": "main",
                            "url": f"https://github.com/{primary}"}}
    if tier2:
        doc["tier2_repo"] = {"full_name": tier2, "default_branch": "main",
                             "url": f"https://github.com/{tier2}"}
    d = cfg / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "repositories.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def test_collect_pr_files_groups_and_paths(env):
    """Group keys and destination paths _run_phase_background's generation
    checksums and push_to_pr both index by."""
    jid = "COL-1"
    _seed_canonical(env, jid)
    (env / jid / "go-tests").mkdir(parents=True)
    (env / jid / "go-tests" / "qf_widget_test.go").write_text("package p\n")
    (env / jid / "reviews").mkdir(parents=True)
    (env / jid / "reviews" / f"{jid}_stp_review.md").write_text("APPROVED\n")

    groups = ui._collect_pr_files(jid)
    assert set(groups) == {"primary", "tier2", "docs"}
    assert [f["path"] for f in groups["primary"]] == [f"tests/qualityflow/{jid}/qf_widget_test.go"]
    assert [f["path"] for f in groups["tier2"]] == [f"tests/qualityflow/{jid}/qf_widget.py"]
    assert sorted(f["path"] for f in groups["docs"]) == [
        f"docs/qualityflow/{jid}/reviews/{jid}_stp_review.md",
        f"docs/qualityflow/{jid}/std/{jid}_test_description.yaml",
        f"docs/qualityflow/{jid}/stp/{jid}_test_plan.md",
    ]


def _pushed_paths(captured):
    """Every file path that actually made it into a create-tree request."""
    pushed = []
    for req in captured:
        if "/git/trees" in req.full_url and req.data:
            pushed.extend(item["path"] for item in json.loads(req.data)["tree"])
    return pushed


def test_python_tests_are_folded_into_the_primary_push(env, captured_requests, monkeypatch):
    """No tier2_repo configured — the Python tests must ride along with the
    primary push. They used to be collected, counted, and dropped."""
    jid = "PUSH-1"
    _seed_canonical(env, jid)
    _seed_repos_yaml(ui.CONFIG, "example", primary="w8org/primary")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")

    r = client.post(f"/api/pipelines/{jid}/push-pr", headers=HDR, json={"github_token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"

    trees = [req for req in captured_requests if "/git/trees" in req.full_url]
    assert len(trees) == 1, "expected exactly one push, not a second tier2 PR"
    pushed = _pushed_paths(captured_requests)
    assert f"tests/qualityflow/{jid}/qf_widget.py" in pushed, pushed
    assert f"docs/qualityflow/{jid}/stp/{jid}_test_plan.md" in pushed, pushed


def test_python_tests_split_out_when_a_distinct_tier2_repo_exists(env, captured_requests, monkeypatch):
    """The other half of the same branch: with a real tier2 repo the folding
    must NOT happen, or the Python tests land in the wrong repository."""
    jid = "PUSH-2"
    _seed_canonical(env, jid)
    _seed_repos_yaml(ui.CONFIG, "example", primary="w8org/primary", tier2="w8org/e2e")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")

    r = client.post(f"/api/pipelines/{jid}/push-pr", headers=HDR, json={"github_token": TOKEN})
    assert r.status_code == 200, r.text

    by_repo = {}
    for req in captured_requests:
        if "/git/trees" in req.full_url and req.data:
            repo = re.search(r"/repos/([^/]+/[^/]+)/git/trees", req.full_url).group(1)
            by_repo[repo] = [item["path"] for item in json.loads(req.data)["tree"]]
    assert by_repo["w8org/e2e"] == [f"tests/qualityflow/{jid}/qf_widget.py"]
    assert f"tests/qualityflow/{jid}/qf_widget.py" not in by_repo["w8org/primary"]


def test_legacy_layout_tests_are_still_pushed(env, captured_requests, monkeypatch):
    """F04 x F05: _collect_pr_files resolves through _pick_dir, so a legacy
    tree must not push an empty PR."""
    jid = "PUSH-3"
    _seed_legacy(env, jid)
    _seed_repos_yaml(ui.CONFIG, "example", primary="w8org/primary")
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")

    r = client.post(f"/api/pipelines/{jid}/push-pr", headers=HDR, json={"github_token": TOKEN})
    assert r.status_code == 200, r.text
    assert f"tests/qualityflow/{jid}/qf_widget.py" in _pushed_paths(captured_requests)
