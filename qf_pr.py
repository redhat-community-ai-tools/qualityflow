"""A ticket's pull request, handled the same way by the dashboard (ui.py: Pull
PR comments, Request changes, Push to PR) and by the headless review loop
(`pipeline_runner.py review-loop`): the review comments people leave on it,
the reviewer-notes queue a refine reads them from, the approval a refine
invalidates, and a commit on top of the PR's own branch.

Stdlib and PyYAML only, no FastAPI, so the runner can import it. It holds no
credentials: callers pass the token.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

API = "https://api.github.com"
# Every commit QualityFlow puts on a PR branch starts with this (Push to PR,
# /push-pr, the review loop). The review loop leaves a branch alone unless its
# head commit is one: anything else is someone's commit it must not build over.
COMMIT_PREFIX = "QualityFlow:"
# QualityFlow's own PR comments (the /fix-pr report, the review loop's summary)
# carry a marker starting like this; they are never read back as a review.
MARKER = "<!-- qualityflow:"


# --- files -----------------------------------------------------------------

class TextTimestampLoader(yaml.SafeLoader):
    """safe_load, except an unquoted timestamp stays the string it was written as.

    State files are also written by agents, by hand: an import run wrote
    `timestamp: 2026-10-08T05:45:33Z` to approvals.yaml, safe_load made it a
    datetime, and sorting it against the dashboard's own ISO strings 500'd
    /api/activity for every ticket. Every reader here expects strings."""


TextTimestampLoader.yaml_implicit_resolvers = {
    first: [r for r in resolvers if r[0] != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def read_yaml(path) -> dict:
    """Read a YAML file, return empty dict on failure.

    Parseable-but-wrong-shaped YAML (a top-level list, a bare string) counts as
    failure: every caller indexes the result like a mapping, so returning the
    list only moves the crash one line down."""
    try:
        data = yaml.load(Path(path).read_text(), Loader=TextTimestampLoader)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_text(path, text: str) -> None:
    """Write via a sibling temp file + os.replace, so no reader ever sees half
    a file. ui.py passes its own writer, which also drops its read caches."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_yaml(path, data, write=write_text) -> None:
    write(Path(path), yaml.dump(data, default_flow_style=False, sort_keys=False))


@contextlib.contextmanager
def file_lock(path):
    """Exclusive lock on a `.lock` sidecar next to `path`.

    A sidecar rather than flock on the data file itself: the data file gets
    replaced, so a lock held on it protects nothing. Every writer of the same
    file shares it, in the dashboard and in the review loop's process alike."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(path.suffix + ".lock"), "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


# --- reviewer notes ----------------------------------------------------------

def notes_path(outputs, jira_id: str, doc: str) -> Path:
    """Reviewer notes queued for the next refine of `doc` (stp/std): several
    people add theirs (Add note, Pull PR comments, the review loop), and one
    refine applies them all."""
    return Path(outputs) / jira_id / "reviews" / f"{jira_id}_{doc}_notes_pending.md"


def feedback_path(outputs, jira_id: str, doc: str) -> Path:
    """The notes file `/refine-{doc} --address-findings` reads."""
    return Path(outputs) / jira_id / "reviews" / f"{jira_id}_{doc}_feedback.md"


def note_block(who: str, text: str) -> str:
    return f"<!-- {who} {datetime.now(timezone.utc).isoformat(timespec='seconds')} -->\n{text.strip()}\n"


def append_note(path, who: str, text: str, write=write_text) -> None:
    path = Path(path)
    with file_lock(path):
        prior = path.read_text(errors="replace") if path.exists() else ""
        write(path, prior + ("\n" if prior else "") + note_block(who, text))


_NOTE_HEADER_RE = re.compile(r"^<!-- (.+?) (\d{4}-\d\d-\d\dT[^ ]+) -->$", re.M)


def read_notes(path) -> list[dict]:
    path = Path(path)
    text = path.read_text(errors="replace") if path.exists() else ""
    heads = list(_NOTE_HEADER_RE.finditer(text))
    return [{"who": h.group(1), "at": h.group(2),
             "text": text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()}
            for i, h in enumerate(heads)]


def take_notes(pending, feedback, extra: str = "", write=write_text) -> str:
    """Hand every queued note, plus `extra` (one more note_block), to the
    refine: write them to `feedback` and empty the queue. With nothing queued
    the feedback file is removed, so an earlier request's notes are never
    re-applied. Returns what was handed over, for requeue_notes."""
    pending, feedback = Path(pending), Path(feedback)
    with file_lock(pending):
        queued = pending.read_text(errors="replace").strip() if pending.exists() else ""
        if extra.strip():
            queued += ("\n\n" if queued else "") + extra.strip()
        if queued:
            feedback.parent.mkdir(parents=True, exist_ok=True)
            write(feedback, f"<!-- Reviewer notes -->\n{queued}\n")
        else:
            feedback.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
    return queued


def requeue_notes(pending, queued: str, write=write_text) -> None:
    """Put the notes take_notes handed to a refine that then failed back at
    the front of the queue, ahead of any added meanwhile."""
    if not queued:
        return
    pending = Path(pending)
    with file_lock(pending):
        later = pending.read_text(errors="replace").strip() if pending.exists() else ""
        write(pending, queued + ("\n\n" + later if later else "") + "\n")


# --- approval gate -----------------------------------------------------------

def read_approvals(path) -> dict:
    """Decisions sit at the top level (ui.py and `state.py approve` write them
    there); a file written by hand from older docs nests them under
    `approvals:`. Both count, the top level winning: reading only one shape
    left a hand-written approval invisible to the dashboard while the CLI gate
    passed, and a dashboard approval invisible to the CLI."""
    doc = read_yaml(path)
    wrapped = doc.get("approvals")
    merged = dict(wrapped) if isinstance(wrapped, dict) else {}
    merged.update({k: v for k, v in doc.items() if k != "approvals"})
    return merged


def drop_gate_decision(path, doc: str, write=write_text) -> bool:
    """Drop the approve/reject decision on `doc` (stp|std), both keys, once
    the document it was made on no longer exists in that form (a refine
    changed it). True if there was one."""
    approvals = read_approvals(path)
    dropped = [k for k in (f"{doc}_review", doc) if k in approvals]
    for k in dropped:
        del approvals[k]
    if dropped:
        write_yaml(path, approvals, write)
    return bool(dropped)


# --- GitHub ----------------------------------------------------------------

def github_api(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """One GitHub REST call. The token goes in the header, never the URL."""
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"GitHub API error ({e.code}): {error_body}")


def github_get(url: str, token: str):
    """GET, or None when GitHub answers with an error (e.g. a file not on the branch yet)."""
    try:
        return github_api("GET", url, token)
    except RuntimeError:
        return None


def git_blob_sha(content: str) -> str:
    """The sha GitHub's contents API reports for a file with this content."""
    data = content.encode()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def is_bot(login: str) -> bool:
    return not login or login.endswith("[bot]")


def new_review_comments(get, repo: str, number: int, since: str = "",
                        associations=None) -> list[tuple[str, str, str]]:
    """The review comments people left on PR `number` of `repo` after `since`
    (a GitHub timestamp; "" for all), oldest first, as (created_at, login,
    note text): line comments, reviews and conversation comments. Bots and
    QualityFlow's own comments are skipped, and so is anyone whose
    author_association is not in `associations`, when given. `get(url)`
    returns parsed JSON.

    ponytail: the first 100 of each kind; page through them if a PR ever
    collects more than that."""
    base = f"{API}/repos/{repo}"
    found = []
    for path, kind in ((f"/pulls/{number}/comments", "line"), (f"/pulls/{number}/reviews", "review"),
                       (f"/issues/{number}/comments", "comment")):
        items = get(base + path + "?per_page=100") or []
        for c in items if isinstance(items, list) else []:
            login = (c.get("user") or {}).get("login") or ""
            text = (c.get("body") or "").strip()
            when = c.get("created_at") or c.get("submitted_at") or ""
            if is_bot(login) or not text or when <= since or MARKER in text:
                continue
            if associations is not None and c.get("author_association") not in associations:
                continue
            where = f" on {c['path']}:{c.get('line') or c.get('original_line') or ''}" if kind == "line" and c.get("path") else ""
            found.append((when, login, f"{text}\n(from the PR{where}: {c.get('html_url', '')})"))
    return sorted(found)


class EditedOnPR(Exception):
    """A file QualityFlow pushed was changed on the PR since: committing over
    it would undo someone's edit."""


def commit_on_branch(repo: str, branch: str, head_sha: str, files: list[dict], pushed_blobs: dict,
                     message: str, token: str, api=github_api, get=github_get) -> str:
    """Commit `files` ([{path, content}]) on top of `head_sha`, the tip of
    `branch` on `repo`, and move the branch to the new commit. Never a force
    push: if someone pushes in between, GitHub refuses the move instead of
    dropping their commit. Raises EditedOnPR when a file QualityFlow pushed
    before (`pushed_blobs`: path -> the blob sha it pushed) was changed on the
    PR since. Returns the new commit's sha."""
    base = f"{API}/repos/{repo}"
    for f in files:
        remote = get(f"{base}/contents/{urllib.parse.quote(f['path'])}?ref={head_sha}", token) or {}
        if pushed_blobs.get(f["path"]) and remote.get("sha") and remote["sha"] != pushed_blobs[f["path"]]:
            raise EditedOnPR(f["path"])
    base_tree = api("GET", f"{base}/git/commits/{head_sha}", token)["tree"]["sha"]
    tree = api("POST", f"{base}/git/trees", token, {"base_tree": base_tree, "tree": [
        {"path": f["path"], "mode": "100644", "type": "blob", "content": f["content"]} for f in files]})["sha"]
    sha = api("POST", f"{base}/git/commits", token,
              {"message": message, "tree": tree, "parents": [head_sha]})["sha"]
    api("PATCH", f"{base}/git/refs/heads/{urllib.parse.quote(branch, safe='')}", token, {"sha": sha})
    return sha
