#!/usr/bin/env python3
"""A run reads the team's checkouts and must never move one: a CNV run did
`git checkout main && git pull` in a product checkout to read a merged PR. The
runner puts a moved checkout back (keeping local changes) and says so on the run,
or only says so when the dashboard manages the checkouts (QF_REPOS_DIR).

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
     python -m pytest tests/test_runner_checkout_guard.py
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline_runner as runner  # noqa: E402


def git(repo, *args):
    # subprocess.call, not run: run() is the stubbed CLI in these tests.
    assert subprocess.call(["git", "-C", str(repo), *args], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0, args


def head(repo):
    return runner._git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A checkout on branch `work` at commit A, with `main` one commit ahead (B)."""
    r = tmp_path / "product"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "A")
    git(r, "branch", "work")
    git(r, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "B")
    git(r, "checkout", "-q", "work")
    (r / "notes.txt").write_text("a person's local change\n")
    return r


def run_with(monkeypatch, repo, move):
    """run_phase whose CLI does `move` to the checkout."""
    monkeypatch.setenv("QF_RUNNER", "cli")
    monkeypatch.setenv("SOURCE_REPO_PATH", str(repo))
    monkeypatch.setattr(runner, "_codex_lsp_args", lambda *a: [])
    monkeypatch.setattr(runner, "_claude_lsp_args", lambda *a, **k: [])
    monkeypatch.setattr(runner, "_parse_stream", lambda _: ([], "Completed", {}, "m"))

    def cli(argv, **kwargs):
        move(repo)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", cli)
    return runner.run_phase("", "PROJ-12345", "stp", runtime="claude")


def test_a_run_that_switches_branch_is_put_back(monkeypatch, repo):
    before = head(repo)
    result = run_with(monkeypatch, repo, lambda r: git(r, "checkout", "-q", "main"))
    assert runner._git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "work"
    assert head(repo) == before
    assert (repo / "notes.txt").exists()  # local changes kept
    assert "moved the" in result["output"] and "from work to main; put it back" in result["output"]
    assert "put it back" in result["progress"][-1]


def test_a_run_that_pulls_on_the_same_branch_is_put_back(monkeypatch, repo):
    before = head(repo)
    result = run_with(monkeypatch, repo, lambda r: git(r, "merge", "-q", "--ff-only", "main"))
    assert head(repo) == before
    assert "put it back" in result["output"]


def test_a_detached_checkout_is_put_back(monkeypatch, repo):
    git(repo, "checkout", "-q", "--detach", "work")
    before = head(repo)
    run_with(monkeypatch, repo, lambda r: git(r, "checkout", "-q", "--detach", "main"))
    assert head(repo) == before


def test_dashboard_managed_checkouts_only_warn(monkeypatch, repo, tmp_path):
    monkeypatch.setenv("QF_REPOS_DIR", str(tmp_path))
    result = run_with(monkeypatch, repo, lambda r: git(r, "checkout", "-q", "main"))
    assert runner._git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"
    assert "Warning: the run moved the" in result["output"] and "put it back" not in result["output"]


def test_a_run_that_leaves_the_checkout_alone_says_nothing(monkeypatch, repo):
    result = run_with(monkeypatch, repo, lambda r: None)
    assert "moved the" not in result["output"]
