# QF Metrics System — Implementation Plan

Goal: turn the dashboard from an adoption pitch (tests generated, estimated hours saved)
into a QE instrument (can I trust these tests, what's uncovered, is quality trending, what
did it cost per test kept). ~80% of the data already exists in `outputs/` — this plan
mostly renders existing exhaust, plus ONE new data source: real CI test-execution records.

## Ground truth (verified anchors)

- `ui.py` (~9.8k lines, FastAPI, single file) — all endpoints live here.
  - `_compute_value_metrics()` ~:1734. **Bug:** :1781 reads `summary.get("generated_tests")`
    but `outputs/{id}/python-tests/summary.yaml` writes `test_count` → silent regex fallback.
  - `_append_trend_snapshot()` :1692, invoked from a GET handler at :2261 (side-effect of a
    page view — trends only exist if someone visits).
  - `pipeline_traceability()` ~:4990 — requirement→scenario→test chain with per-link
    `link: "id" | "inferred"` quality flag.
  - `generation_checksums` written at :3388 = `hashlib.sha256(content.encode()).hexdigest()[:16]`,
    keyed by co-located target path (e.g. `tests/qualityflow/CNV-50425/qf_sriov.py`).
- `outputs/{JIRA_ID}/state/pipeline_state.yaml` — per-phase `status`, `verdict`,
  `usage{input_tokens, output_tokens, cost_usd, duration_ms, num_turns}`, `skill_version`,
  `findings{critical,major,minor}` (on review phases), `verification: passed`,
  `test_count`, timestamps, `history[]`. Two writer dialects exist (CLI `state.py` vs
  dashboard): `started_ts`/`finished_ts` vs `started`/`completed`, `codegen` vs
  `python_codegen`. Readers must tolerate both.
- `outputs/{JIRA_ID}/state/approvals.yaml` — human gate decisions (reviewer, decision).
- `outputs/_trends/{project}.yaml` — daily rows (pipelines, completed, tests,
  time_saved_hours, coverage_pct, auto_approved, human_approved), capped 104.
- `ui/index.html` (~10.4k lines, vanilla JS SPA) — views: command, runs, traceability,
  coverage, agentic, catalog. `usage.cost_usd` has ZERO references (biggest unused dataset).
  Agentic view has `available: false` placeholders for findings/eval data.
- CI: no workflow collects or persists any metric today.

## API contracts (fixed — frontend and backend build against these in parallel)

All endpoints follow existing ui.py conventions (same auth/dev-mode handling, same
`?project=` param style as existing metrics endpoints). All degrade gracefully: absent
data → `"available": false` on the affected field, never a 500.

### GET /api/metrics/confidence?project={id}
```json
{
  "project": "cnv",
  "rollup": {"score": 74, "band": "watch", "tickets": 3},
  "tickets": [
    {
      "jira_id": "CNV-50425",
      "score": 78,
      "band": "trusted|watch|at_risk|insufficient",
      "signals_present": 6,
      "signals_total": 7,
      "biggest_drag": "review_health",
      "signals": {
        "coverage":      {"value": 0.705, "available": true},
        "link_quality":  {"value": 1.0,   "available": true},
        "review_health": {"value": 0.55,  "available": true},
        "refinement":    {"value": 1.0,   "available": true},
        "verification":  {"value": 1.0,   "available": true},
        "effectiveness": {"value": null,  "available": false},
        "freshness":     {"value": 0.9,   "available": true}
      }
    }
  ]
}
```
**Signal formulas (normalize 0–1):**
- `coverage` = requirements_with_tests / total_requirements (reuse traceability computation).
- `link_quality` = strong_links / total_links where strong = `link == "id"`. No links → unavailable.
- `review_health` = mean over review phases that have data of
  `max(0, 1 - (critical*1.0 + major*0.2 + minor*0.05))` when `findings` present;
  else verdict fallback APPROVED=1.0, APPROVED_WITH_FINDINGS=0.7, NEEDS_REVISION=0.2.
  No reviews at all → unavailable.
- `refinement` = 1.0 if no `*_refine` phase ran; 0.5 if any refine loop ran.
- `verification` = 1.0 if any codegen phase has `verification: passed`, 0.0 if `failed`,
  absent → unavailable.
- `effectiveness` = pass rate of latest CI run from `outputs/{id}/ci/test_runs.yaml`
  (see schema below); file absent → unavailable.
- `freshness` from state `updated`: ≤7 days → 1.0, linear decay to 0.0 at 90 days.
- **Score** = mean(available signals) × 100, rounded. **Require ≥4 available signals**,
  else `band: "insufficient"` and `score: null` — never fake a green.
- Bands: ≥80 trusted, ≥60 watch, else at_risk.
- `biggest_drag` = key of the lowest-valued available signal.

### GET /api/metrics/roi?project={id}
```json
{
  "project": "cnv",
  "totals": {"cost_usd": 12.63, "duration_ms": 2191148, "num_turns": 66,
             "input_tokens": 100, "output_tokens": 43603},
  "tests_accepted": 33,
  "requirements_covered": 31,
  "cost_per_test": 0.38,
  "cost_per_requirement": 0.41,
  "time_saved_hours": {"value": 41.5, "estimated": true},
  "per_ticket": [{"jira_id": "CNV-50425", "cost_usd": 12.63, "tests": 33,
                  "phases": {"stp": 2.88, "std": 5.88, "codegen": 3.86}}]
}
```
Sum `usage` across all phases of all pipeline_state files for the project. Tolerate both
writer dialects. `time_saved_hours` stays but is explicitly flagged estimated.

### GET /api/metrics/gaps?project={id}
```json
{
  "project": "cnv",
  "gaps": [
    {"jira_id": "CNV-70932", "epic": "CNV-50425", "summary": "NetworkPolicy tests",
     "status": "uncovered|inferred_only", "priority_score": 8,
     "links": {"strong": 0, "inferred": 0}}
  ]
}
```
Derived from the traceability chain: requirements with zero test links (`uncovered`) or
only `inferred` links (`inferred_only`). `priority_score` = 5 for uncovered + 3 for
inferred_only + 3 if the requirement's issue type/priority field marks it P0/critical
(when that data is in collected state; else omit the bonus). Sorted descending.

### GET /api/metrics/quality-trend?project={id}
```json
{
  "project": "cnv",
  "runs": [
    {"jira_id": "CNV-50425", "date": "2026-08-29",
     "verdicts": {"stp": "APPROVED_WITH_FINDINGS", "std": "APPROVED_WITH_FINDINGS"},
     "findings": {"critical": 0, "major": 4, "minor": 7},
     "first_time_approve": false, "refine_loops": 0}
  ],
  "ftar": {"value": 0.0, "n": 1},
  "findings_trend": [{"date": "2026-08-29", "critical": 0, "major": 4, "minor": 7}]
}
```
`first_time_approve` = every review verdict APPROVED, zero refine phases, zero human
rejection in approvals.yaml. `ftar` = fraction of completed runs that are first_time_approve.

### GET /api/metrics/drift?project={id}
```json
{
  "project": "cnv",
  "tickets": [{"jira_id": "CNV-50425", "available": true, "files": [
    {"path": "tests/qualityflow/CNV-50425/qf_sriov.py",
     "status": "unchanged|modified|missing"}
  ], "modified": 0, "missing": 12}]
}
```
Recompute `sha256(content).hexdigest()[:16]` for each `generation_checksums` key, resolved
against `SOURCE_REPO_PATH` (env) or repo root. Unresolvable root → `available: false`.

### POST /api/beacon   body: {"view": "command"}
Append `{"date": "YYYY-MM-DD", "view": "..."}` counts into
`outputs/_usage/dashboard_usage.jsonl` (one JSON line per day+view with a count, upsert by
rewrite or plain append — plain append is fine, aggregation happens at read time).
`GET /api/metrics/usage` returns `{views: {command: {hits: N, active_days: M}, ...}}`.
Purpose: after a few weeks, DELETE panels nobody opens.

### CI record schema — outputs/{JIRA_ID}/ci/test_runs.yaml  (written by CI, read by backend)
```yaml
runs:                     # append-only, newest last, cap 50
  - run_id: "gh-1234567"
    date: "2026-08-30T02:00:00Z"
    commit: "abc123"
    total: 33
    passed: 33
    failed: 0
    skipped: 0
    duration_s: 41.2
    tests:
      - nodeid: "qf_sriov.py::test_sriov_basic"
        qf_test_id: "TS-III.1-1"    # from @pytest.mark.qf_test_id, empty if absent
        outcome: "passed"
```
Flakiness (frontend, later): a test whose outcome flips across the last N runs.

## Work packages

### WP-1 Backend (ui.py + scripts/qf_trend_snapshot.py) — one agent, serial
1. Fix :1781 — read `test_count`, fall back to `generated_tests`, then regex.
2. Implement the six GET endpoints + POST /api/beacon per contracts above. Reuse existing
   helpers (traceability computation, state loading/merging) — do NOT reimplement parsing.
3. Flag `time_saved_hours` as estimated in the existing value-metrics payload.
4. `scripts/qf_trend_snapshot.py`: imports the snapshot logic from ui.py and runs
   `_append_trend_snapshot` for every project with outputs, exit 0. (Keeps the in-request
   call as-is for now; the script gives CI/cron a path that doesn't need a page view.)
5. One test file `tests/test_metrics_endpoints.py` (FastAPI TestClient, tmp_path fixture
   outputs tree with one synthetic ticket) covering: confidence formula incl. <4-signal
   insufficiency, roi sums both writer dialects, gaps ranking, drift unchanged/modified,
   beacon round-trip.

### WP-2 Frontend (ui/index.html) — one agent, parallel with WP-1 (builds against contracts)
1. Command view: Confidence hero replaces time_saved hero — score, band chip
   (trusted/watch/at-risk colors from existing CSS vars), "Confidence N/7", "Biggest drag:
   {signal}". time_saved moves into the ROI panel labeled "estimated".
2. ROI panel on command view: total cost, cost per accepted test, cost per requirement,
   per-ticket phase cost breakdown (small table).
3. Coverage view: "Coverage gaps" ranked list from /api/metrics/gaps — clickable rows
   navigating to the ticket's pipeline detail; uncovered=red chip, inferred_only=amber.
4. Agentic view: replace `available:false` findings placeholder with quality-trend data —
   findings-by-severity over time + FTAR tile. Keep graceful empty states.
5. Runs view rows: freshness dot (green ≤7d, amber ≤30d, red >30d, gray unknown) from
   state `updated`.
6. `navigator.sendBeacon('/api/beacon', ...)` once per view render.
7. Match existing vanilla-JS idioms, CSS variables, fetch helpers in index.html. Every new
   panel has an explicit "no data yet" state.

### WP-3 CI (.github/workflows/qf-metrics.yml + scripts/qf_record_ci.py) — one agent, parallel
1. Workflow triggers: nightly cron + pull_request touching `outputs/**` — job is
   NON-BLOCKING (never fails the PR; policy becomes a trend before it becomes a gate).
2. Steps: for each `outputs/*/python-tests/` dir with qf_* files, run
   `uv run --with pytest pytest --junitxml` (collection-only failures recorded as failed),
   then `python scripts/qf_record_ci.py` parses junitxml → append a run into
   `outputs/{id}/ci/test_runs.yaml` per the schema (stdlib xml.etree + pyyaml; extract
   qf_test_id marker via `-o` properties or nodeid mapping from summary.yaml — best effort,
   empty string when unknown).
3. On pull_request: post/update a single sticky "QE Scorecard" comment: per-ticket
   pass/fail counts + link to the dashboard. (Confidence score in the comment is a
   follow-up — requires importing scoring logic; out of scope now.)
4. Nightly job also runs `python scripts/qf_trend_snapshot.py` (contract: exists at that
   path, exit 0 — WP-1 provides it; workflow must tolerate its absence with
   `if: hashFiles(...)` or `|| true` until merged).
5. Commit of test_runs.yaml artifacts from CI: upload as workflow artifact only — do NOT
   auto-commit to the repo (avoids bot-commit loops). Dashboard reads local files;
   documented as "download artifact / run locally" for now.

## Explicitly deferred (Wave 3 — do not build now)
- Slack/push digest — no webhook configured yet (YAGNI until one exists).
- AI analyst layer (per-widget next-actions) — optional, after panels prove used.
- State-schema unification (state.py vs dashboard writer dialects) — high regression risk,
  own session; readers in WP-1 tolerate both dialects meanwhile.
- z-score anomaly detection on cycle time / flakiness — needs baseline history that the
  nightly snapshot will accumulate first.
- Panel pruning — needs a few weeks of beacon data.

## Acceptance
- `uv run --with fastapi --with pyyaml --with pytest --with httpx pytest tests/test_metrics_endpoints.py` green.
- Dashboard loads with real `outputs/` data: confidence hero shows a banded score for
  CNV-50425 (expect band watch/trusted with 6/7 signals, effectiveness unavailable),
  ROI shows ~$12.63 total / ~$0.38 per test, gaps list non-empty (13 uncovered from
  31/44 coverage), agentic placeholders gone.
- Workflow YAML passes `actionlint`/`gh workflow` syntax check; scorecard comment renders
  in a dry-run (or the comment step is verified by unit-testing the script only).
