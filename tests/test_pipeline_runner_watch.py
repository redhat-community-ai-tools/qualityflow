"""Jira label trigger: `pipeline_runner.py watch`.

Runs without the dashboard, so any team can schedule it (cron, CI, a CronJob,
the Fullsend runner). One pass finds tickets in the routed Jira projects that
carry the trigger label, claims each one, runs the STP, and reports back on
the ticket with a result label and a comment.

  * the query covers only routed projects;
  * claim before the run, result label after, comment either way;
  * a failing ticket is reported and does not stop the rest of the pass;
  * Cloud's /search/jql is tried first, Server/DC's /search on 404;
  * --dry-run and missing credentials change nothing.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_watch.py -q
"""
import io
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402

ROUTES = yaml.safe_load((ROOT / "config" / "routing.yaml").read_text())["routes"]
PREFIXES = {p for r in ROUTES for p in r.get("jira_prefixes") or []}


@pytest.fixture
def jira(tmp_path, monkeypatch):
    """A fake Jira behind _jira(): two queued tickets; every write recorded."""
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return {"issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}]}
        return None

    for var in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"):
        monkeypatch.setenv(var, "test-value")
    monkeypatch.setattr(pipeline_runner, "_jira", fake)
    monkeypatch.setattr(pipeline_runner, "_outputs_dir", lambda: tmp_path)
    monkeypatch.setattr(pipeline_runner, "persist_usage", lambda *a: None)
    return calls


def _writes(calls):
    return [(m, p, b) for m, p, b in calls if m != "GET"]


def test_query_covers_only_routed_projects(jira):
    pipeline_runner.watch("qf-generate", 2, dry_run=True)
    path = jira[0][1]
    assert path.startswith("/rest/api/2/search/jql?")
    for prefix in PREFIXES:
        assert "%22" + prefix + "%22" in path
    assert "maxResults=2" in path
    assert _writes(jira) == []  # dry run: nothing claimed or commented


def test_claims_runs_and_reports(jira, tmp_path, monkeypatch):
    def run(model, key, phase):
        if key == "PROJ-2":
            raise RuntimeError("model call failed: sk-" + "a" * 30)
        (tmp_path / key / "stp").mkdir(parents=True)
        (tmp_path / key / "stp" / f"{key}_test_plan.md").write_text("# plan")
        return {"verdict": "NEEDS_REVISION", "model": "m1", "usage": {"cost_usd": 0.5}}

    monkeypatch.setattr(pipeline_runner, "run_phase", run)
    assert pipeline_runner.watch("qf-generate", 2) == 1  # one failure

    labels = [(p, b["update"]["labels"]) for m, p, b in _writes(jira) if m == "PUT"]
    assert labels == [
        ("/rest/api/2/issue/PROJ-1", [{"remove": "qf-generate"}, {"add": "qf-running"}]),
        ("/rest/api/2/issue/PROJ-1", [{"remove": "qf-running"}, {"add": "qf-stp-needs-revision"}]),
        ("/rest/api/2/issue/PROJ-2", [{"remove": "qf-generate"}, {"add": "qf-running"}]),
        ("/rest/api/2/issue/PROJ-2", [{"remove": "qf-running"}, {"add": "qf-stp-failed"}]),
    ]
    comments = {p: b["body"] for m, p, b in _writes(jira) if m == "POST"}
    assert "NEEDS_REVISION (model m1, $0.50)" in comments["/rest/api/2/issue/PROJ-1/comment"]
    failure = comments["/rest/api/2/issue/PROJ-2/comment"]
    assert "add the qf-generate label again" in failure.lower()
    assert "sk-aaaa" not in failure  # a key echoed in an error never reaches Jira


def test_no_test_plan_means_blocked(jira, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "run_phase",
                        lambda *a: {"verdict": None, "model": None, "usage": {}})
    pipeline_runner.watch("qf-generate", 1)
    assert ("PUT", "/rest/api/2/issue/PROJ-1",
            {"update": {"labels": [{"remove": "qf-running"}, {"add": "qf-stp-blocked"}]}}) in jira


def test_server_dc_search_fallback(monkeypatch):
    seen = []

    def fake(method, path, body=None):
        seen.append(path)
        if path.startswith("/rest/api/2/search/jql"):
            raise urllib.error.HTTPError(path, 404, "Not Found", Message(), io.BytesIO())
        return {"issues": [{"key": "PROJ-9"}]}

    monkeypatch.setattr(pipeline_runner, "_jira", fake)
    assert pipeline_runner._search("labels = x", 1) == ["PROJ-9"]
    assert seen[1].startswith("/rest/api/2/search?")


def test_missing_credentials_refuse(monkeypatch):
    for var in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN"):
        pipeline_runner.watch("qf-generate", 1)


def test_comment_links_public_dashboard_page(jira, tmp_path, monkeypatch):
    """--push may be an in-cluster address; the comment must link the public page."""
    monkeypatch.setenv("QUALITYFLOW_BASE_URL", "https://dash.example.com/")
    monkeypatch.setattr(pipeline_runner, "push_outputs", lambda *a: True)

    def run(model, key, phase):
        (tmp_path / key / "stp").mkdir(parents=True, exist_ok=True)
        (tmp_path / key / "stp" / f"{key}_test_plan.md").write_text("# plan")
        return {"verdict": "APPROVED", "model": "m1", "usage": {}}

    monkeypatch.setattr(pipeline_runner, "run_phase", run)
    pipeline_runner.watch("qf-generate", 1, push="http://qualityflow-dashboard:8420")
    body = [b["body"] for m, p, b in _writes(jira) if m == "POST"][0]
    assert "Results: https://dash.example.com/#pipeline/PROJ-1" in body
    assert "qualityflow-dashboard:8420" not in body


def test_pushed_without_public_url_names_no_address(jira, tmp_path, monkeypatch):
    monkeypatch.delenv("QUALITYFLOW_BASE_URL", raising=False)
    monkeypatch.setattr(pipeline_runner, "push_outputs", lambda *a: True)
    monkeypatch.setattr(pipeline_runner, "run_phase",
                        lambda *a: {"verdict": None, "model": None, "usage": {}})
    pipeline_runner.watch("qf-generate", 1, push="http://qualityflow-dashboard:8420")
    body = [b["body"] for m, p, b in _writes(jira) if m == "POST"][0]
    assert "Results were sent to the team dashboard." in body


def test_imported_team_stp_is_labelled_and_explained(jira, tmp_path, monkeypatch):
    def run(model, key, phase):
        d = tmp_path / key / "stp"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}_test_plan.md").write_text("# the team's plan")
        (d / f"{key}_stp_source.yaml").write_text(
            "url: https://github.com/org/design-docs/blob/abc/stps/x.md\n"
            "pull_request: https://github.com/org/design-docs/pull/128\n")
        return {"verdict": None, "model": "m1", "usage": {"cost_usd": 0.25}}

    monkeypatch.setattr(pipeline_runner, "run_phase", run)
    pipeline_runner.watch("qf-generate", 1)
    assert ("PUT", "/rest/api/2/issue/PROJ-1",
            {"update": {"labels": [{"remove": "qf-running"}, {"add": "qf-stp-imported"}]}}) in jira
    body = [b["body"] for m, p, b in _writes(jira) if m == "POST"][0]
    assert "imported it unchanged: https://github.com/org/design-docs/pull/128" in body
    assert "No new plan was generated (model m1, $0.25)" in body


def test_stale_source_file_is_not_an_import(jira, tmp_path, monkeypatch):
    """A source file left by an earlier run must not relabel a fresh generation."""
    import os as _os
    d = tmp_path / "PROJ-1" / "stp"
    d.mkdir(parents=True)
    src = d / "PROJ-1_stp_source.yaml"
    src.write_text("url: https://example.com/old.md\n")
    _os.utime(src, (1, 1))

    def run(model, key, phase):
        (d / f"{key}_test_plan.md").write_text("# new plan")
        return {"verdict": "APPROVED", "model": "m1", "usage": {}}

    monkeypatch.setattr(pipeline_runner, "run_phase", run)
    pipeline_runner.watch("qf-generate", 1)
    assert ("PUT", "/rest/api/2/issue/PROJ-1",
            {"update": {"labels": [{"remove": "qf-running"}, {"add": "qf-stp-approved"}]}}) in jira
