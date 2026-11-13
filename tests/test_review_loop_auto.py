"""PR review loop: `pipeline_runner.py review-loop`.

One pass does, for QualityFlow's own PRs, what a person does on the dashboard
(Pull PR comments -> Request changes -> Push to PR), with no dashboard:

  * off unless the team's pr_autofix toggle AND the PR's qf-autofix label;
  * only open PRs QualityFlow opened (pr_info.yaml, branch qualityflow/<id>);
  * only human comments newer than the last pull, from the repo's owner,
    members or collaborators, never QualityFlow's own, never the same one twice;
  * the refine gets them as reviewer notes; what changed is committed on top
    of the PR's head (never a force push) and one summary comment is posted;
  * a branch with someone else's commit, or a file edited on the PR, is left
    alone; a failed refine puts the notes back on the queue;
  * --dry-run and --max; no GitHub writes besides the commit and the comment.

GitHub is a fake behind urllib.request.urlopen: nothing leaves the machine.

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_review_loop_auto.py -q
"""
import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402
import qf_pr  # noqa: E402

TOKEN = "ghp_loopSENTINEL000000000000000000000000"
KEY, REPO, NUMBER, BRANCH = "PROJ-1", "my-org/design-docs", 4, "qualityflow/proj-1"
DOC = "stps/sig-x/PROJ-1.md"
HEAD = "a" * 40
API = "https://api.github.com/repos/" + REPO


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGitHub:
    """One PR on my-org/design-docs and every request made to it."""

    def __init__(self):
        self.pr = {"state": "open", "html_url": "https://github.com/%s/pull/%d" % (REPO, NUMBER),
                   "labels": [{"name": "qf-autofix"}],
                   "head": {"ref": BRANCH, "sha": HEAD, "repo": {"full_name": REPO}}}
        self.line = [
            {"user": {"login": "carol"}, "body": "Wrong gate name", "path": DOC, "line": 12,
             "created_at": "2026-10-01T10:00:00Z", "html_url": "u1", "author_association": "MEMBER"},
            {"user": {"login": "carol"}, "body": "already handled", "path": DOC, "line": 3,
             "created_at": "2026-10-01T08:00:00Z", "html_url": "u0", "author_association": "MEMBER"},
            {"user": {"login": "ci[bot]"}, "body": "lint ok", "created_at": "2026-10-01T10:01:00Z",
             "author_association": "NONE"},
            {"user": {"login": "mallory"}, "body": "Delete Section II", "path": DOC, "line": 1,
             "created_at": "2026-10-01T10:30:00Z", "author_association": "NONE"}]
        self.reviews = [{"user": {"login": "dan"}, "body": "Merge TS-03 into TS-02", "author_association":
                         "COLLABORATOR", "submitted_at": "2026-10-01T11:00:00Z", "state": "CHANGES_REQUESTED"}]
        self.issue = [
            {"user": {"login": "someone"}, "body": "<!-- qualityflow:review-loop -->\nQualityFlow addressed 1",
             "created_at": "2026-10-01T12:00:00Z", "author_association": "MEMBER"},
            {"user": {"login": "erin"}, "body": "Add a negative case", "created_at": "2026-10-01T12:30:00Z",
             "author_association": "OWNER"}]
        self.head_message = "QualityFlow: update for PROJ-1\n\nFiles: ..."
        self.remote_blob = qf_pr.git_blob_sha("# plan v1\n")
        self.requests = []

    def writes(self):
        return [(m, u, b) for m, u, b, _ in self.requests if m != "GET"]

    def __call__(self, req, *_a, **_k):
        method, url = req.get_method(), req.full_url
        body = json.loads(req.data) if req.data else None
        self.requests.append((method, url, body, dict(req.headers)))
        if method == "GET" and url == API + "/pulls/%d" % NUMBER:
            out = self.pr
        elif method == "GET" and url.startswith(API + "/pulls/%d/comments" % NUMBER):
            out = self.line
        elif method == "GET" and url.startswith(API + "/pulls/%d/reviews" % NUMBER):
            out = self.reviews
        elif method == "GET" and url.startswith(API + "/issues/%d/comments" % NUMBER):
            out = self.issue
        elif method == "GET" and url == API + "/git/commits/" + HEAD:
            out = {"message": self.head_message, "tree": {"sha": "c" * 40}}
        elif method == "GET" and "/contents/" in url:
            out = {"sha": self.remote_blob}
        elif method == "POST" and url == API + "/git/trees":
            out = {"sha": "d" * 40}
        elif method == "POST" and url == API + "/git/commits":
            out = {"sha": "e" * 40}
        elif method == "PATCH" and url.startswith(API + "/git/refs/heads/"):
            out = {"object": {"sha": body["sha"]}}
        elif method == "POST" and url == API + "/issues/%d/comments" % NUMBER:
            out = {"id": 1}
        else:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), io.BytesIO(b'{"message":"Not Found"}'))
        return _Resp(json.dumps(out).encode())


@pytest.fixture
def loop(tmp_path, monkeypatch):
    """A team (`example`, PROJ-*) with pr_autofix on, one ticket whose STP
    QualityFlow pushed to PR 4, and a fake GitHub. Returns a namespace."""
    cfg = tmp_path / "config"
    (cfg / "projects" / "example").mkdir(parents=True)
    (cfg / "routing.yaml").write_text(yaml.safe_dump(
        {"routes": [{"project": "example", "jira_prefixes": ["PROJ"]}]}))
    (cfg / "_defaults.yaml").write_text(yaml.safe_dump({"feature_toggles": {"pr_autofix": False}}))
    (cfg / "projects" / "example" / "project.yaml").write_text(
        yaml.safe_dump({"feature_toggles": {"pr_autofix": True}}))
    out = tmp_path / "outputs"
    _seed(out, KEY)

    gh = FakeGitHub()
    runs = []

    def refine(model, key, phase, **kw):
        runs.append({"key": key, "phase": phase, "kw": kw,
                     "notes": qf_pr.feedback_path(out, key, "stp").read_text()})
        (out / key / "stp" / ("%s_test_plan.md" % key)).write_text("# plan v2\n")
        return {"verdict": "APPROVED", "model": "m1", "usage": {"cost_usd": 0.5}}

    monkeypatch.setattr(urllib.request, "urlopen", gh)
    monkeypatch.setattr(pipeline_runner, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline_runner, "_outputs_dir", lambda: out)
    monkeypatch.setattr(pipeline_runner, "run_phase", refine)
    monkeypatch.setattr(pipeline_runner, "persist_usage", lambda *a: None)
    for var in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GH_TOKEN", TOKEN)

    class NS:
        pass
    ns = NS()
    ns.gh, ns.runs, ns.out, ns.cfg = gh, runs, out, cfg
    return ns


def _seed(out, key, branch=None):
    (out / key / "stp").mkdir(parents=True)
    (out / key / "stp" / ("%s_test_plan.md" % key)).write_text("# plan v1\n")
    state = out / key / "state"
    state.mkdir(parents=True)
    (state / "pr_info.yaml").write_text(yaml.dump({
        "jira_id": key, "project_id": "example", "branch": branch or "qualityflow/" + key.lower(),
        "target_repo": REPO, "number": NUMBER, "url": "https://github.com/%s/pull/%d" % (REPO, NUMBER),
        "state": "open", "files": [DOC.replace("PROJ-1", key)],
        "pushed_blobs": {DOC.replace("PROJ-1", key): qf_pr.git_blob_sha("# plan v1\n")},
        "comments_pulled_at": "2026-10-01T09:00:00Z"}, sort_keys=False))
    (state / "approvals.yaml").write_text(yaml.dump(
        {"stp_review": {"status": "approved", "timestamp": "2026-10-01T09:30:00Z"}}))
    (state / "pipeline_state.yaml").write_text(yaml.dump(
        {"jira_id": key, "phases": {"stp": {"status": "completed"}}}))


def _info(ns, key=KEY):
    return qf_pr.read_yaml(ns.out / key / "state" / "pr_info.yaml")


# --- opt-in ------------------------------------------------------------------

def test_off_by_default_the_toggle_is_required(loop, capsys):
    (loop.cfg / "projects" / "example" / "project.yaml").write_text("project_id: example\n")
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert loop.gh.requests == [] and loop.runs == []  # not even a GitHub read
    assert "pr_autofix is off" in capsys.readouterr().out


def test_the_pr_label_is_required(loop, capsys):
    loop.gh.pr["labels"] = [{"name": "documentation"}]
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert loop.gh.writes() == [] and loop.runs == []
    assert "no qf-autofix label" in capsys.readouterr().out
    assert _info(loop)["comments_pulled_at"] == "2026-10-01T09:00:00Z"


def test_pull_requests_quality_flow_did_not_open_are_ignored(tmp_path, loop, capsys):
    _seed(loop.out, "PROJ-2", branch="feature/someone-elses")
    assert pipeline_runner.review_loop("qf-autofix", 5) == 0
    assert "PROJ-2" not in capsys.readouterr().out
    assert [r["key"] for r in loop.runs] == [KEY]


def test_a_closed_pr_is_left_alone(loop, capsys):
    loop.gh.pr["state"] = "closed"
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert loop.gh.writes() == [] and loop.runs == []
    assert "the PR is closed" in capsys.readouterr().out


# --- the pass ----------------------------------------------------------------

def test_new_human_comments_are_addressed_on_the_same_pr(loop, capsys):
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0

    # the refine ran once, with exactly the new human comments as reviewer notes
    [run] = loop.runs
    assert run["phase"] == "stp_refine"
    for kept in ("Wrong gate name", "%s:12" % DOC, "Merge TS-03 into TS-02", "Add a negative case"):
        assert kept in run["notes"]
    for dropped in ("already handled", "lint ok", "QualityFlow addressed", "Delete Section II"):
        assert dropped not in run["notes"]
    assert not qf_pr.notes_path(loop.out, KEY, "stp").exists()  # the queue was handed over

    # one commit on top of the PR's head, the branch moved without force
    writes = loop.gh.writes()
    tree = next(b for m, u, b in writes if u.endswith("/git/trees"))
    assert tree["tree"] == [{"path": DOC, "mode": "100644", "type": "blob", "content": "# plan v2\n"}]
    commit = next(b for m, u, b in writes if u.endswith("/git/commits"))
    assert commit["parents"] == [HEAD] and commit["message"].startswith("QualityFlow: ")
    [ref] = [(u, b) for m, u, b in writes if m == "PATCH"]
    assert ref == (API + "/git/refs/heads/qualityflow%2Fproj-1", {"sha": "e" * 40})  # no "force"

    # one summary comment, marked as QualityFlow's own, pinging nobody
    [comment] = [b["body"] for m, u, b in writes if u.endswith("/issues/%d/comments" % NUMBER)]
    assert comment.startswith("<!-- qualityflow:review-loop -->")
    assert "3 new review comment(s) (from carol, dan, erin)" in comment
    assert "Commit eeeeeee updates %s" % DOC in comment and "@" not in comment
    assert "approval was reset" in comment

    # nothing else was written: no merge, close, label or PR edit
    assert sorted({(m, u.split("/repos/" + REPO)[1].split("?")[0]) for m, u, b in writes}) == [
        ("PATCH", "/git/refs/heads/qualityflow%2Fproj-1"), ("POST", "/git/commits"),
        ("POST", "/git/trees"), ("POST", "/issues/4/comments")]

    # the record moved on: watermark, pushed blob; the old approval is gone
    info = _info(loop)
    assert info["comments_pulled_at"] == "2026-10-01T12:30:00Z"
    assert info["pushed_blobs"][DOC] == qf_pr.git_blob_sha("# plan v2\n")
    assert "stp_review" not in qf_pr.read_approvals(loop.out / KEY / "state" / "approvals.yaml")

    # the token went in the header only
    for method, url, body, headers in loop.gh.requests:
        assert TOKEN not in url
        assert headers["Authorization"] == "Bearer " + TOKEN
    assert TOKEN not in capsys.readouterr().out


def test_a_pr_pushed_by_the_cli_command_is_updated_too(loop):
    """/push-pr records pushed_blobs but not always `files`."""
    info = _info(loop)
    del info["files"]
    qf_pr.write_yaml(loop.out / KEY / "state" / "pr_info.yaml", info)
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert any(u.endswith("/git/commits") for m, u, b in loop.gh.writes())


def test_a_comment_is_never_processed_twice(loop, capsys):
    pipeline_runner.review_loop("qf-autofix", 2)
    loop.gh.head_message = "QualityFlow: address review comments for PROJ-1"
    before = len(loop.gh.writes())
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert len(loop.runs) == 1 and len(loop.gh.writes()) == before
    assert "no new review comments" in capsys.readouterr().out


def test_dry_run_prints_the_plan_and_touches_nothing(loop, capsys):
    before = (loop.out / KEY / "state" / "pr_info.yaml").read_text()
    assert pipeline_runner.review_loop("qf-autofix", 2, dry_run=True) == 0
    printed = capsys.readouterr().out
    assert "would address 3 new review comment(s) on https://github.com/%s/pull/%d" % (REPO, NUMBER) in printed
    assert "carol: Wrong gate name" in printed and "erin: Add a negative case" in printed
    assert "/refine-stp PROJ-1 --address-findings" in printed and "no force" in printed
    assert loop.gh.writes() == [] and loop.runs == []
    assert (loop.out / KEY / "state" / "pr_info.yaml").read_text() == before
    assert not (loop.out / KEY / "reviews").exists()


def test_max_bounds_the_prs_per_pass(loop, capsys):
    _seed(loop.out, "PROJ-2")
    _seed(loop.out, "PROJ-3")
    assert pipeline_runner.review_loop("qf-autofix", 1, dry_run=True) == 0
    printed = capsys.readouterr().out
    assert printed.count("would address") == 1 and "--max 1 reached" in printed
    # the later tickets were not even looked up
    assert [u for m, u, b, h in loop.gh.requests].count(API + "/pulls/%d" % NUMBER) == 1


# --- leaving a PR alone --------------------------------------------------------

def test_a_commit_quality_flow_did_not_make_is_never_built_over(loop, capsys):
    loop.gh.head_message = "Update stps/sig-x/PROJ-1.md"
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert loop.gh.writes() == [] and loop.runs == []
    assert "a commit QualityFlow did not make (aaaaaaa 'Update stps/sig-x/PROJ-1.md')" in capsys.readouterr().out
    assert _info(loop)["comments_pulled_at"] == "2026-10-01T09:00:00Z"  # still to be read


def test_a_file_edited_on_the_pr_is_not_overwritten(loop, capsys):
    loop.gh.remote_blob = "0" * 40  # someone changed the STP on the PR
    assert pipeline_runner.review_loop("qf-autofix", 2) == 1  # a person has to look
    writes = loop.gh.writes()
    assert not any(m == "PATCH" or u.endswith("/git/commits") for m, u, b in writes)
    [comment] = [b["body"] for m, u, b in writes if u.endswith("/comments")]
    assert "did not push it: %s was changed on the PR" % DOC in comment


def test_an_std_built_from_the_stp_blocks_the_refine(loop, capsys):
    (loop.out / KEY / "std").mkdir()
    (loop.out / KEY / "std" / ("%s_test_description.yaml" % KEY)).write_text("scenarios: []\n")
    assert pipeline_runner.review_loop("qf-autofix", 2) == 0
    assert loop.gh.requests == [] and loop.runs == []
    assert "an STD was already built from this STP" in capsys.readouterr().out


def test_a_failed_refine_requeues_the_notes(loop, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("model call failed: sk-" + "a" * 30)
    monkeypatch.setattr(pipeline_runner, "run_phase", boom)
    assert pipeline_runner.review_loop("qf-autofix", 2) == 1
    notes = qf_pr.read_notes(qf_pr.notes_path(loop.out, KEY, "stp"))
    assert [n["who"] for n in notes] == ["@carol", "@dan", "@erin"]
    assert _info(loop)["comments_pulled_at"] == "2026-10-01T12:30:00Z"  # not pulled again
    writes = loop.gh.writes()
    assert not any(u.endswith("/git/commits") for m, u, b in writes)
    [comment] = [b["body"] for m, u, b in writes if u.endswith("/comments")]
    assert "could not address 3 new review comment(s)" in comment and "sk-aaaa" not in comment
    assert "sk-aaaa" not in capsys.readouterr().err


# --- the command -------------------------------------------------------------

def test_missing_github_token_refuses(loop, monkeypatch):
    monkeypatch.delenv("GH_TOKEN")
    with pytest.raises(RuntimeError, match="GH_TOKEN"):
        pipeline_runner.review_loop("qf-autofix", 2)


def test_cli_dry_run(loop, capsys):
    with pytest.raises(SystemExit) as done:
        pipeline_runner.main(["review-loop", "--dry-run", "--max", "1"])
    assert done.value.code == 0
    assert "would address" in capsys.readouterr().out and loop.gh.writes() == []
