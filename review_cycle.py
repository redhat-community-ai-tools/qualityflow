#!/usr/bin/env python3
"""Whose court is the ball in on an open pull request, and for how long.

Pure functions only — no FastAPI, no network, no filesystem. `ui.py` does the
fetching, the persistence and the Slack nudging; everything here is a
deterministic function of the PR facts plus `now`, so it can be unit-tested
without a server.

STATES (precedence, highest first — the first rule that fires wins):

  stale            nothing at all has happened on the PR for `stale_days`.
                   waiting_on = author + every known reviewer.
  waiting_author   a reviewer asked for something and the author has not
                   responded: the latest review by some reviewer is
                   CHANGES_REQUESTED with no commit pushed since, OR an
                   unresolved thread's last comment is a reviewer's and the
                   author has neither replied nor pushed since.
                   waiting_on = [author].
  waiting_ack      the author answered and nobody picked it back up: an
                   unresolved thread carries a reviewer comment, and the author
                   replied (or pushed) after it, and the thread is still open.
                   waiting_on = the reviewers who own those threads.
  waiting_reviewer nobody has reviewed yet, or the head commit is newer than
                   every review (a fix landed and needs a re-review), or a
                   reviewer looked without approving.
                   waiting_on = requested reviewers + reviewers whose latest
                   review predates the head commit.
  approved         every reviewer who reviewed ended on APPROVED and no thread
                   is unresolved. Waiting on merge; never nudged.
  draft            PR is a draft. Tracked, never nudged. Checked before all of
                   the above.

Two rules the precedence list alone does not settle, resolved here and relied
on by the tests:

  * A new commit after CHANGES_REQUESTED is `waiting_reviewer`, not
    `waiting_ack` — the fix is pushed, the ball is plainly with the reviewer.
    `waiting_ack` is reserved for the *conversational* dangle: a reviewer's
    comment was answered and left hanging on an unresolved thread.
  * `waiting_author`'s thread arm requires that the author has not responded
    since (no later comment of theirs, no later push). If they did respond, the
    thread falls through to `waiting_ack` instead.

Bot logins (anything ending in `[bot]`) and configured `ignore_logins` are
stripped from reviews, threads and requested reviewers before any of this runs.
"""

from __future__ import annotations

from datetime import datetime, timezone

STATES = ("draft", "stale", "waiting_author", "waiting_ack", "waiting_reviewer", "approved")

# States that carry an SLA and can be nudged. draft/approved never are.
NUDGEABLE = ("waiting_reviewer", "waiting_author", "waiting_ack", "stale")

# The three states whose time-in-state the manager view reports on.
WAIT_STATES = ("waiting_reviewer", "waiting_author", "waiting_ack")

SHARE_KEYS = {"waiting_reviewer": "reviewer", "waiting_author": "author", "waiting_ack": "ack"}

DEFAULT_SLA = {
    "enabled": True,  # false = this project is not polled at all (template/placeholder projects)
    "reviewer_hours": 24,
    "author_hours": 48,
    "ack_hours": 24,
    "stale_days": 5,
    "renudge_hours": 24,
    "ignore_logins": [],
    "slack_users": {},
    "watch_repos": [],  # explicit org/repo list; empty = the project's primary_repo only
}

MIN_N = 3  # matches qf_metrics.MIN_N — below this, report a reason, not a number.


def to_ts(iso: str | None) -> float | None:
    """ISO-8601 (GitHub's trailing-Z form included) -> epoch seconds, or None."""
    if not iso:
        return None
    try:
        text = iso.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, AttributeError):
        return None


def to_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def is_ignored(login: str, ignore_logins) -> bool:
    """Bots and configured service accounts never own a review cycle."""
    if not login:
        return True
    return login.endswith("[bot]") or login in set(ignore_logins or ())


def sla_thresholds(sla: dict | None) -> dict:
    """Per-state SLA in seconds. draft/approved are absent (never breach)."""
    cfg = {**DEFAULT_SLA, **(sla or {})}

    def _num(key):
        val = cfg.get(key, DEFAULT_SLA[key])
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(DEFAULT_SLA[key])

    return {
        "waiting_reviewer": _num("reviewer_hours") * 3600,
        "waiting_author": _num("author_hours") * 3600,
        "waiting_ack": _num("ack_hours") * 3600,
        "stale": _num("stale_days") * 86400,
    }


def age_hours(since: str | None, now: float) -> float | None:
    ts = to_ts(since)
    if ts is None:
        return None
    return max(0.0, now - ts) / 3600


def is_over_sla(state: str, since: str | None, now: float, sla: dict | None) -> bool:
    threshold = sla_thresholds(sla).get(state)
    if threshold is None:
        return False
    ts = to_ts(since)
    return ts is not None and (now - ts) > threshold


# ---------------------------------------------------------------------------
# State derivation
# ---------------------------------------------------------------------------

def _clean_threads(threads, author: str, ignore_logins) -> list[dict]:
    """Threads with bot/ignored comments dropped; empty threads discarded.

    Each cleaned thread keeps `is_resolved` and a chronologically sorted
    `comments` list of {login, ts}.
    """
    out = []
    for th in threads or ():
        comments = []
        for c in (th.get("comments") or ()):
            login = c.get("login") or ""
            ts = to_ts(c.get("created_at"))
            if ts is None or (login != author and is_ignored(login, ignore_logins)):
                continue
            comments.append({"login": login, "ts": ts})
        if not comments:
            continue
        comments.sort(key=lambda c: c["ts"])
        out.append({"is_resolved": bool(th.get("is_resolved")), "comments": comments})
    return out


def _latest_reviews(reviews, author: str, ignore_logins) -> dict[str, dict]:
    """Latest non-PENDING review per reviewer: {login: {state, ts}}."""
    latest: dict[str, dict] = {}
    for r in reviews or ():
        login = r.get("login") or ""
        state = (r.get("state") or "").upper()
        ts = to_ts(r.get("submitted_at"))
        if ts is None or state in ("PENDING", "DISMISSED"):
            continue
        if login == author or is_ignored(login, ignore_logins):
            continue
        prev = latest.get(login)
        if prev is None or ts >= prev["ts"]:
            latest[login] = {"state": state, "ts": ts}
    return latest


def derive_state(pr: dict, now: float, sla: dict | None = None) -> dict:
    """Return {state, since, waiting_on, reason} for one open PR.

    `pr` keys: author, draft, created_at, head_commit_at, requested_reviewers,
    reviews [{login, state, submitted_at}], review_threads
    [{is_resolved, comments: [{login, created_at}]}]. See the module docstring
    for the rules.
    """
    cfg = {**DEFAULT_SLA, **(sla or {})}
    ignore = cfg.get("ignore_logins") or []
    author = pr.get("author") or ""
    created = to_ts(pr.get("created_at"))
    head = to_ts(pr.get("head_commit_at"))
    base_ts = head if head is not None else created
    base_iso = to_iso(base_ts)

    requested = sorted({r for r in (pr.get("requested_reviewers") or ())
                        if r and r != author and not is_ignored(r, ignore)})
    latest = _latest_reviews(pr.get("reviews"), author, ignore)
    threads = _clean_threads(pr.get("review_threads"), author, ignore)
    reviewers_known = sorted(set(requested) | set(latest))

    if pr.get("draft"):
        return {"state": "draft", "since": base_iso, "waiting_on": [author] if author else [],
                "reason": "PR is still a draft"}

    # --- stale: newest activity of ANY kind older than stale_days -----------
    activity = [t for t in (created, head) if t is not None]
    activity += [r["ts"] for r in latest.values()]
    activity += [c["ts"] for th in threads for c in th["comments"]]
    newest = max(activity) if activity else None
    stale_seconds = sla_thresholds(cfg)["stale"]
    if newest is not None and (now - newest) > stale_seconds:
        days = (now - newest) / 86400
        return {
            "state": "stale", "since": to_iso(newest),
            "waiting_on": ([author] if author else []) + reviewers_known,
            "reason": f"no activity of any kind for {days:.0f} days",
        }

    # --- waiting_author ----------------------------------------------------
    author_triggers: list[tuple[float, str]] = []
    for login, rev in latest.items():
        if rev["state"] == "CHANGES_REQUESTED" and (head is None or head <= rev["ts"]):
            author_triggers.append((rev["ts"], f"{login} requested changes and no commit has been pushed since"))
    for th in threads:
        if th["is_resolved"]:
            continue
        last = th["comments"][-1]
        if last["login"] == author:
            continue  # author already replied -> waiting_ack territory
        if head is not None and head > last["ts"]:
            continue  # author pushed since -> waiting_ack territory
        author_triggers.append((last["ts"], f"unresolved thread last commented by {last['login']}"))
    if author_triggers:
        ts, reason = min(author_triggers, key=lambda t: t[0])
        return {"state": "waiting_author", "since": to_iso(ts),
                "waiting_on": [author] if author else [], "reason": reason}

    # --- waiting_ack -------------------------------------------------------
    ack_triggers: list[float] = []
    ack_owners: set[str] = set()
    for th in threads:
        if th["is_resolved"]:
            continue
        others = [c for c in th["comments"] if c["login"] != author]
        if not others:
            continue
        last_other = others[-1]["ts"]
        responses = [c["ts"] for c in th["comments"] if c["login"] == author and c["ts"] > last_other]
        if head is not None and head > last_other:
            responses.append(head)
        if not responses:
            continue
        ack_triggers.append(min(responses))
        ack_owners.update(c["login"] for c in others)
    if ack_triggers:
        ts = min(ack_triggers)
        owners = sorted(ack_owners)
        return {"state": "waiting_ack", "since": to_iso(ts), "waiting_on": owners,
                "reason": "author responded on an unresolved thread; no reviewer follow-up since"}

    # --- waiting_reviewer --------------------------------------------------
    unreviewed_since_head = sorted(
        login for login, rev in latest.items()
        if head is not None and rev["ts"] < head
    )
    if not latest or unreviewed_since_head:
        waiting_on = sorted(set(requested) | set(unreviewed_since_head))
        # "later of (review request time if known, else PR created) and head commit"
        since_ts = max([t for t in (created, head) if t is not None], default=None)
        reason = ("no review submitted yet" if not latest
                  else "head commit is newer than every review — needs a re-review")
        if not waiting_on and not latest:
            reason = "no reviewer requested yet"
        return {"state": "waiting_reviewer", "since": to_iso(since_ts),
                "waiting_on": waiting_on, "reason": reason}

    # --- approved ----------------------------------------------------------
    unresolved = [th for th in threads if not th["is_resolved"]]
    if latest and all(r["state"] == "APPROVED" for r in latest.values()) and not unresolved:
        return {"state": "approved", "since": to_iso(max(r["ts"] for r in latest.values())),
                "waiting_on": [], "reason": "approved — waiting on merge"}

    # Terminal fallback: somebody looked but nobody approved (a COMMENTED
    # review, or an approval alongside another reviewer who only commented).
    pending = sorted(set(requested) | {login for login, r in latest.items() if r["state"] != "APPROVED"})
    return {"state": "waiting_reviewer",
            "since": to_iso(max(r["ts"] for r in latest.values())),
            "waiting_on": pending, "reason": "reviewed but not approved"}


# ---------------------------------------------------------------------------
# Time-in-state, from the persisted `history` of each record
# ---------------------------------------------------------------------------

def history_durations(history: list[dict], now: float) -> dict[str, float]:
    """Seconds spent in each state by one PR: closed intervals + the open one.

    `history` is append-on-transition ({state, since}, oldest first). A state's
    `since` is the moment the state *began*, which is derived from PR facts and
    so is not guaranteed to move forward between transitions — negative
    intervals are clamped to zero rather than subtracted from the totals.
    """
    out: dict[str, float] = {}
    entries = [(e.get("state"), to_ts(e.get("since"))) for e in (history or ())]
    entries = [(s, t) for s, t in entries if s and t is not None]
    for i, (state, start) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else now
        out[state] = out.get(state, 0.0) + max(0.0, end - start)
    return out


def _median(values: list[float]) -> float:
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2


def wait_metrics(records: list[dict], now: float, min_n: int = MIN_N) -> dict:
    """`median_hours` + `share_of_wait_pct` over every PR's persisted history.

    Below `min_n` PRs with history the medians are null with an
    `unavailable_reason`, the same honest-empty shape qf_metrics uses.
    """
    per_state: dict[str, list[float]] = {s: [] for s in WAIT_STATES}
    totals: dict[str, float] = {s: 0.0 for s in WAIT_STATES}
    n = 0
    for rec in records or ():
        history = rec.get("history") or []
        if not history:
            continue
        n += 1
        durations = history_durations(history, now)
        for state in WAIT_STATES:
            secs = durations.get(state)
            if secs:
                per_state[state].append(secs / 3600)
                totals[state] += secs

    if n < min_n:
        return {
            "median_hours": {s: None for s in WAIT_STATES},
            "share_of_wait_pct": {k: None for k in SHARE_KEYS.values()},
            "unavailable_reason": f"fewer than {min_n} PRs with review history",
            "n": n,
        }

    grand = sum(totals.values())
    return {
        "median_hours": {s: (round(_median(per_state[s]), 1) if per_state[s] else None)
                         for s in WAIT_STATES},
        "share_of_wait_pct": {SHARE_KEYS[s]: (round(totals[s] / grand * 100, 1) if grand else None)
                              for s in WAIT_STATES},
        "n": n,
    }


def summarize(records: list[dict], now: float, sla: dict | None = None) -> dict:
    """`summary` block for /api/metrics/review-cycle."""
    by_state: dict[str, int] = {}
    over = 0
    for rec in records or ():
        state = rec.get("state") or "unknown"
        by_state[state] = by_state.get(state, 0) + 1
        if is_over_sla(state, rec.get("since"), now, sla):
            over += 1
    # wait_metrics' own `n` counts PRs that have history, which is a different
    # number from the PR count — renamed so the spread can't shadow it.
    metrics = wait_metrics(records, now)
    metrics["n_with_history"] = metrics.pop("n")
    return {"n": len(records or ()), "by_state": by_state, "over_sla": over, **metrics}
