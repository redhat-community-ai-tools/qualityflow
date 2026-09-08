# FIX-P1 verdict — RUN-2026-09-08-dual-runtime

**VERDICT: PASS** (computed from real exit codes, see checks.json)

- Worked directly on `feat/dual-runtime` (already checked out in the repo's
  primary worktree at task start; `git worktree add /tmp/fix-p1
  feat/dual-runtime` refused with "already used by worktree" — the branch
  cannot be checked out twice, so all commits were made in place, no
  worktree needed).

## P1-A — UI misreports the backend
Re-grepped before editing: all 7 line numbers named in the task prompt
(4774, 4893, 5803, 8359, 8386, 8775, 8787) matched exactly.
Fixed by reusing the existing `getUserRuntime()` (ui/index.html:6227,
lane C) — no second source of truth:
- 4774, 4893, 8359→8362, 8386→8389: live run-status strings now read
  `getUserRuntime() === 'cursor' ? 'Cursor' : 'Claude'/'Claude AI'`.
- 5803: section comment updated (comment only).
- 8775, 8787: made **runtime-neutral** ("using your selected AI runtime")
  instead of runtime-conditional. Chosen over conditioning because these are
  static onboarding-tour copy (`TOUR_STEPS` array, rendered once, not
  re-evaluated per selected runtime) — conditioning them would mean turning
  `text` into a callback and touching the tour-render call site, for copy
  that only explains the product, never shows live run state. Neutral
  wording is the smaller, equally-correct fix.

Post-fix grep for "Claude AI" shows exactly 2 remaining occurrences, both
inside the runtime ternary (the Claude-branch value) — no more
unconditional backend claims.

## P1-B — rejected Cursor key could be persisted
Root-caused to the single `raise RuntimeError(...)` in
`pipeline_runner.run_phase()` (previously lines ~176-186) that both the
Claude and Cursor code paths converge on before ui.py's `_mark_failed`
persists `str(e)[:500]` to `pipeline_state.yaml`. Added one helper,
`_redact_secrets()` (backed by `_SECRET_RE`), and one call site —
`detail = _redact_secrets(detail)` — right before that shared raise, so
both runtimes are covered without per-backend duplication.
Covers: Cursor key (`key_[A-Za-z0-9]{20,}`), Atlassian (`ATATT...`),
GitHub (`ghp_`/`ghs_`/`github_pat_`), Google (`AIza...`).

Added `tests/test_pipeline_runner_redaction.py`: 7 unit tests against
`_redact_secrets` with hand-typed literal expected strings (one per
credential shape, plus no-secret passthrough and None/empty), and 2
integration tests (one per runtime) that feed a synthetic leaked token
(`key_FAKENOTAREALSECRET0000000000`,
`ATATT3xFAKE0000000000000000000000000000FAKE`) into fake subprocess
stderr and assert the raised message excludes the literal and includes
`[redacted]`. None of the expectations were produced by calling the
function under test.

## Suite
Full suite run raw via `rtk proxy` (the global PreToolUse hook filters
plain Bash output — not trusted for a verdict): **406 passed, exit=0**
(was 397 before this fix; +9 from the new redaction test file, 0
regressions, 0 skips introduced).

## Scope discipline
Only 2 files changed for the fixes (`ui/index.html`, `pipeline_runner.py`)
plus 1 new test file. Nothing in `agents/`, `commands/`, `skills/`
touched. No merge, no branch-protection change, no cnv2 build/deploy, no
mutating `oc` verb run.

## Token scan
`grep -rEc 'ATATT|ghp_|ghs_|key_[A-Za-z0-9]{20,}|AIza'` over this
directory returns non-zero (2 files, 6 lines total). Verified every hit
with `grep -n`: all are either (a) the regex pattern source
(`pipeline_runner-py.diff`), (b) prose in `checks.json` quoting the
pattern/scan command, or (c) the test file's `FAKE_*` constants, which are
self-labelled as fake (`...FAKENOTAREALSECRET...`) and never resemble a
real, currently-valid credential. No real token appeared anywhere in this
task's inputs or outputs.
