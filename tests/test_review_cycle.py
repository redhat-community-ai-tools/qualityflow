#!/usr/bin/env python3
"""Review-cycle bottleneck flags (wave W12).

Covers the three layers of the feature:
  * review_cycle.derive_state — pure, one test per state plus precedence,
    bot filtering, draft, author-reply-then-unresolved, and new-commit-after-
    changes-requested.
  * ui._review_cycle_pass — persistence, append-on-transition history, and the
    SLA nudges (breach once, silence inside renudge_hours, again after it,
    and a transition into `stale` that nudges through the renudge gate).
  * GET /api/metrics/review-cycle and /api/insights.

Same conventions as tests/test_state_safety.py: QF_DEV/QF_OUTPUTS_DIR set
before `import ui`, ui is a module-level singleton so globals are monkeypatched
per test, and the module-level TestClient is NOT entered as a context manager
(that would run the lifespan — and its poller — against the real outputs/).

NOTHING here touches the network: _github_api / _github_api_get / _slack_notify
are all monkeypatched with fakes.

Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_review_cycle.py -q
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import review_cycle  # noqa: E402
import ui  # noqa: E402 — env must be set before import
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)

KEY = "w12testkey"
HDR = {"X-API-Key": KEY}
REPO = "example-org/repo"

NOW = time.time()


def ago(hours: float = 0, days: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours, days=days)
    return dt.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Pure derivation
# ---------------------------------------------------------------------------

def _pr(**over) -> dict:
    base = {
        "author": "alice", "draft": False,
        "created_at": ago(hours=10), "head_commit_at": ago(hours=10),
        "requested_reviewers": [], "reviews": [], "review_threads": [],
    }
    base.update(over)
    return base


def test_draft_is_never_anything_else():
    out = review_cycle.derive_state(_pr(draft=True, requested_reviewers=["bob"]), NOW)
    assert out["state"] == "draft"
    assert out["waiting_on"] == ["alice"]


def test_waiting_reviewer_when_nobody_has_reviewed():
    out = review_cycle.derive_state(_pr(requested_reviewers=["bob", "carol"]), NOW)
    assert out["state"] == "waiting_reviewer"
    assert out["waiting_on"] == ["bob", "carol"]
    # since = later of PR-created and the head commit
    assert review_cycle.to_ts(out["since"]) == pytest.approx(NOW - 10 * 3600, abs=5)


def test_waiting_author_on_changes_requested_with_no_newer_commit():
    out = review_cycle.derive_state(_pr(
        head_commit_at=ago(hours=30),
        reviews=[{"login": "bob", "state": "CHANGES_REQUESTED", "submitted_at": ago(hours=20)}],
    ), NOW)
    assert out["state"] == "waiting_author"
    assert out["waiting_on"] == ["alice"]
    assert "bob" in out["reason"]


def test_new_commit_after_changes_requested_is_waiting_reviewer():
    """A pushed fix puts the ball back with the reviewer, not in waiting_ack."""
    out = review_cycle.derive_state(_pr(
        head_commit_at=ago(hours=2),
        requested_reviewers=[],
        reviews=[{"login": "bob", "state": "CHANGES_REQUESTED", "submitted_at": ago(hours=20)}],
    ), NOW)
    assert out["state"] == "waiting_reviewer"
    assert out["waiting_on"] == ["bob"]


def test_author_reply_on_unresolved_thread_is_waiting_ack():
    out = review_cycle.derive_state(_pr(
        head_commit_at=ago(hours=30),
        review_threads=[{"is_resolved": False, "comments": [
            {"login": "bob", "created_at": ago(hours=20)},
            {"login": "alice", "created_at": ago(hours=18)},
        ]}],
    ), NOW)
    assert out["state"] == "waiting_ack"
    assert out["waiting_on"] == ["bob"]
    assert review_cycle.to_ts(out["since"]) == pytest.approx(NOW - 18 * 3600, abs=5)


def test_unanswered_thread_is_waiting_author_and_beats_waiting_ack():
    """Two threads: one answered (ack), one not (author). Author wins."""
    out = review_cycle.derive_state(_pr(
        head_commit_at=ago(hours=40),
        review_threads=[
            {"is_resolved": False, "comments": [
                {"login": "bob", "created_at": ago(hours=20)},
                {"login": "alice", "created_at": ago(hours=18)}]},
            {"is_resolved": False, "comments": [
                {"login": "carol", "created_at": ago(hours=9)}]},
        ],
    ), NOW)
    assert out["state"] == "waiting_author"


def test_approved_when_every_reviewer_approved_and_no_open_threads():
    out = review_cycle.derive_state(_pr(
        head_commit_at=ago(hours=30),
        reviews=[{"login": "bob", "state": "APPROVED", "submitted_at": ago(hours=5)}],
        review_threads=[{"is_resolved": True, "comments": [{"login": "bob", "created_at": ago(hours=6)}]}],
    ), NOW)
    assert out["state"] == "approved"
    assert out["waiting_on"] == []


def test_stale_overrides_everything_else():
    out = review_cycle.derive_state(_pr(
        created_at=ago(days=30), head_commit_at=ago(days=30),
        requested_reviewers=["bob"],
        reviews=[{"login": "carol", "state": "CHANGES_REQUESTED", "submitted_at": ago(days=20)}],
    ), NOW, {"stale_days": 5})
    assert out["state"] == "stale"
    assert out["waiting_on"] == ["alice", "bob", "carol"]


def test_bots_and_ignore_logins_are_stripped():
    """A bot approval must not turn an unreviewed PR into `approved`, and an
    ignored service account must not own a thread."""
    out = review_cycle.derive_state(_pr(
        requested_reviewers=["bob", "ci-bot[bot]", "svc-account"],
        reviews=[{"login": "ci-bot[bot]", "state": "APPROVED", "submitted_at": ago(hours=1)}],
        review_threads=[{"is_resolved": False, "comments": [
            {"login": "svc-account", "created_at": ago(hours=2)}]}],
    ), NOW, {"ignore_logins": ["svc-account"]})
    assert out["state"] == "waiting_reviewer"
    assert out["waiting_on"] == ["bob"]


def test_over_sla_uses_the_state_specific_threshold():
    sla = {"reviewer_hours": 24, "author_hours": 48, "ack_hours": 24, "stale_days": 5}
    assert review_cycle.is_over_sla("waiting_reviewer", ago(hours=30), NOW, sla)
    assert not review_cycle.is_over_sla("waiting_author", ago(hours=30), NOW, sla)
    # draft and approved carry no SLA at all
    assert not review_cycle.is_over_sla("draft", ago(days=90), NOW, sla)
    assert not review_cycle.is_over_sla("approved", ago(days=90), NOW, sla)


def test_wait_metrics_below_min_n_reports_a_reason_not_a_number():
    records = [{"history": [{"state": "waiting_reviewer", "since": ago(hours=10)}]}] * 2
    out = review_cycle.wait_metrics(records, NOW)
    assert out["unavailable_reason"]
    assert out["median_hours"]["waiting_reviewer"] is None
    assert out["share_of_wait_pct"]["reviewer"] is None


def test_wait_metrics_medians_and_shares_from_history():
    # Each PR: 10h waiting_reviewer (closed out), then waiting_author until now.
    records = []
    for _ in range(3):
        records.append({"history": [
            {"state": "waiting_reviewer", "since": ago(hours=30)},
            {"state": "waiting_author", "since": ago(hours=20)},
        ]})
    out = review_cycle.wait_metrics(records, NOW)
    assert out["n"] == 3
    assert out["median_hours"]["waiting_reviewer"] == pytest.approx(10, abs=0.2)
    assert out["median_hours"]["waiting_author"] == pytest.approx(20, abs=0.2)
    assert out["median_hours"]["waiting_ack"] is None
    assert out["share_of_wait_pct"]["reviewer"] == pytest.approx(33.3, abs=1.0)
    assert out["share_of_wait_pct"]["author"] == pytest.approx(66.7, abs=1.0)


# ---------------------------------------------------------------------------
# Poll pass — fake GitHub, captured Slack
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    cfg = tmp_path / "config"
    (cfg / "projects" / "example").mkdir(parents=True)
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "CONFIG", cfg)
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_API_KEY", KEY)
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "fake-token")
    (cfg / "projects" / "example" / "project.yaml").write_text(yaml.safe_dump(
        {"project_id": "example", "display_name": "Example"}))
    (cfg / "projects" / "example" / "repositories.yaml").write_text(yaml.safe_dump(
        {"primary_repo": {"full_name": REPO, "url": f"https://github.com/{REPO}"}}))
    return out


def _fake_github(monkeypatch, prs: list[dict], details: dict):
    """Wire _github_api_get / _github_api to canned payloads.

    `prs` are open-PR list entries; `details[number]` carries
    {commit_at, reviews, threads}.
    """
    def fake_get(url, token=""):
        if "/pulls?" in url:
            return prs
        if "/commits/" in url:
            sha = url.rsplit("/", 1)[-1]
            number = int(sha.split("-")[-1])
            return {"commit": {"committer": {"date": details[number]["commit_at"]}}}
        if url.endswith("/reviews?per_page=100"):
            number = int(url.split("/pulls/")[1].split("/")[0])
            return [{"user": {"login": r["login"]}, "state": r["state"],
                     "submitted_at": r["submitted_at"]} for r in details[number].get("reviews", [])]
        raise AssertionError(f"unexpected GitHub GET {url}")

    def fake_post(method, url, token, data=None):
        assert url.endswith("/graphql") and method == "POST"
        number = data["variables"]["number"]
        nodes = [{"isResolved": t["is_resolved"],
                  "comments": {"nodes": [{"author": {"login": c["login"]},
                                          "createdAt": c["created_at"]} for c in t["comments"]]}}
                 for t in details[number].get("threads", [])]
        return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}}

    monkeypatch.setattr(ui, "_github_api_get", fake_get)
    monkeypatch.setattr(ui, "_github_api", fake_post)


def _pr_entry(number: int, **over) -> dict:
    entry = {
        "number": number, "html_url": f"https://github.com/{REPO}/pull/{number}",
        "title": f"PR {number}", "user": {"login": "alice"}, "draft": False,
        "created_at": ago(hours=10), "updated_at": ago(hours=10),
        "requested_reviewers": [{"login": "bob"}],
        "head": {"sha": f"sha-{number}"},
    }
    entry.update(over)
    return entry


def _nudges(monkeypatch) -> list:
    sent = []
    monkeypatch.setattr(ui, "_slack_notify", lambda text, blocks=None: sent.append(text))
    monkeypatch.setattr(ui, "_SLACK_WEBHOOK", "https://hooks.example.com/x")
    return sent


def _records(out: Path) -> dict:
    return json.loads((out / "_review_cycle" / "example.json").read_text())["prs"]


def test_pass_persists_records_and_appends_history_only_on_transition(env, monkeypatch):
    _nudges(monkeypatch)
    details = {1: {"commit_at": ago(hours=3), "reviews": [], "threads": []}}
    _fake_github(monkeypatch, [_pr_entry(1)], details)

    assert ui._review_cycle_pass()["status"] == "ok"
    rec = _records(env)[f"{REPO}#1"]
    assert rec["state"] == "waiting_reviewer"
    assert rec["waiting_on"] == ["bob"]
    assert rec["repo"] == REPO and rec["number"] == 1
    assert len(rec["history"]) == 1

    # Second pass, nothing changed -> no new history entry.
    ui._review_cycle_pass()
    assert len(_records(env)[f"{REPO}#1"]["history"]) == 1

    # A real transition appends exactly one entry.
    details[1]["reviews"] = [{"login": "bob", "state": "CHANGES_REQUESTED",
                              "submitted_at": ago(hours=1)}]
    ui._review_cycle_pass()
    hist = _records(env)[f"{REPO}#1"]["history"]
    assert [h["state"] for h in hist] == ["waiting_reviewer", "waiting_author"]


def test_sla_breach_nudges_once_then_respects_renudge_hours(env, monkeypatch):
    sent = _nudges(monkeypatch)
    details = {1: {"commit_at": ago(hours=48), "reviews": [], "threads": []}}
    _fake_github(monkeypatch, [_pr_entry(1, created_at=ago(hours=48))], details)

    ui._review_cycle_pass()
    assert len(sent) == 1, sent
    assert "Review stuck — waiting on reviewer" in sent[0]
    assert f"{REPO}#1" in sent[0] and "bob" in sent[0]

    # Immediate re-run: inside renudge_hours, silence.
    ui._review_cycle_pass()
    assert len(sent) == 1

    # Backdate the last nudge past renudge_hours -> it nudges again.
    path = env / "_review_cycle" / "example.json"
    data = json.loads(path.read_text())
    data["prs"][f"{REPO}#1"]["last_nudge_ts"] = ago(hours=30)
    path.write_text(json.dumps(data))
    ui._review_cycle_pass()
    assert len(sent) == 2


def test_transition_into_stale_nudges_through_the_renudge_gate(env, monkeypatch):
    sent = _nudges(monkeypatch)
    details = {1: {"commit_at": ago(hours=48), "reviews": [], "threads": []}}
    _fake_github(monkeypatch, [_pr_entry(1, created_at=ago(hours=48))], details)
    ui._review_cycle_pass()
    assert len(sent) == 1  # waiting_reviewer breach

    # Everything ages past stale_days while the renudge window is still open.
    details[1]["commit_at"] = ago(days=30)
    _fake_github(monkeypatch, [_pr_entry(1, created_at=ago(days=30), updated_at=ago(days=30))], details)
    ui._review_cycle_pass()
    assert len(sent) == 2
    assert "stale" not in sent[1]  # the side label, not the state name
    assert _records(env)[f"{REPO}#1"]["state"] == "stale"


def test_draft_and_approved_are_tracked_but_never_nudged(env, monkeypatch):
    sent = _nudges(monkeypatch)
    details = {
        1: {"commit_at": ago(hours=48), "reviews": [], "threads": []},
        2: {"commit_at": ago(hours=48),
            "reviews": [{"login": "bob", "state": "APPROVED", "submitted_at": ago(hours=40)}],
            "threads": []},
    }
    _fake_github(monkeypatch, [
        _pr_entry(1, draft=True, created_at=ago(hours=48)),
        _pr_entry(2, created_at=ago(hours=48), requested_reviewers=[]),
    ], details)
    ui._review_cycle_pass()
    recs = _records(env)
    assert recs[f"{REPO}#1"]["state"] == "draft"
    assert recs[f"{REPO}#2"]["state"] == "approved"
    assert sent == []


def test_pass_is_disabled_without_a_token(env, monkeypatch):
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")
    assert ui._review_cycle_pass()["status"] == "disabled"


def test_gitlab_repos_are_skipped(env):
    (env.parent / "config" / "projects" / "example" / "repositories.yaml").write_text(yaml.safe_dump({
        "primary_repo": {"full_name": "example-org/gl", "url": "https://gitlab.com/example-org/gl"},
        "additional_repos": [{"full_name": "example-org/extra",
                              "url": "https://github.com/example-org/extra"}],
    }))
    assert ui._github_repos_for_project("example") == ["example-org/extra"]


# ---------------------------------------------------------------------------
# Endpoint + insights
# ---------------------------------------------------------------------------

def _seed_records(out: Path, records: dict) -> None:
    path = out / "_review_cycle" / "example.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated": ago(hours=0), "prs": records}))


def _over_sla_record(n: int) -> dict:
    return {
        "url": f"https://github.com/{REPO}/pull/{n}", "title": f"PR {n}", "author": "alice",
        "repo": REPO, "number": n, "state": "waiting_reviewer", "since": ago(hours=30),
        "waiting_on": ["bob"], "reason": "no review submitted yet", "last_nudge_ts": None,
        "history": [{"state": "waiting_reviewer", "since": ago(hours=30)},
                    {"state": "waiting_author", "since": ago(hours=20)}],
    }


def test_endpoint_shape_and_medians(env):
    _seed_records(env, {f"{REPO}#{n}": _over_sla_record(n) for n in (1, 2, 3)})
    r = client.get("/api/metrics/review-cycle?project=example")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["available"] is True and data["project"] == "example"
    s = data["summary"]
    assert s["n"] == 3 and s["over_sla"] == 3
    assert s["by_state"] == {"waiting_reviewer": 3}
    assert s["median_hours"]["waiting_reviewer"] == pytest.approx(10, abs=0.3)
    assert s["share_of_wait_pct"]["author"] == pytest.approx(66.7, abs=1.5)
    pr = data["prs"][0]
    assert set(pr) == {"url", "title", "repo", "number", "author", "state", "since",
                       "age_hours", "over_sla", "waiting_on", "reason"}
    assert pr["over_sla"] is True and pr["age_hours"] == pytest.approx(30, abs=0.3)


def test_endpoint_below_min_n_reports_unavailable_reason(env):
    _seed_records(env, {f"{REPO}#1": _over_sla_record(1)})
    s = client.get("/api/metrics/review-cycle?project=example").json()["summary"]
    assert s["unavailable_reason"]
    assert s["median_hours"]["waiting_reviewer"] is None


def test_endpoint_unavailable_without_a_token(env, monkeypatch):
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")
    data = client.get("/api/metrics/review-cycle?project=example").json()
    assert data == {"available": False, "reason": "no GitHub token configured"}


def test_insights_include_review_stuck_items(env):
    _seed_records(env, {f"{REPO}#{n}": _over_sla_record(n) for n in (1, 2, 3)})
    items = client.get("/api/insights?project=example").json()["insights"]
    stuck = [i for i in items if i["type"] == "review_stuck"]
    assert len(stuck) == 3
    one = stuck[0]
    assert one["severity"] == "warn" and one["jira_id"] is None
    assert one["url"].startswith(f"https://github.com/{REPO}/pull/")
    assert f"{REPO}#" in one["title"]


def test_refresh_route_is_write_gated(env, monkeypatch):
    _nudges(monkeypatch)
    _fake_github(monkeypatch, [], {})
    assert client.post("/api/review-cycle/refresh").status_code in (401, 403)
    r = client.post("/api/review-cycle/refresh", headers=HDR)
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_project_sla_overrides_defaults(env):
    cfg = env.parent / "config"
    (cfg / "_defaults.yaml").write_text(yaml.safe_dump({"review_sla": {"reviewer_hours": 8}}))
    (cfg / "projects" / "example" / "project.yaml").write_text(yaml.safe_dump(
        {"project_id": "example", "display_name": "Example",
         "review_sla": {"author_hours": 12}}))
    sla = ui._load_review_sla("example")
    assert sla["reviewer_hours"] == 8      # from _defaults.yaml
    assert sla["author_hours"] == 12       # project override
    assert sla["stale_days"] == 5          # built-in
