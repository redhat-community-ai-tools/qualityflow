# Pipeline State Tracker

Manages per-ticket pipeline state across all QualityFlow phases. Provides state
initialization, phase transitions, prerequisite validation, staleness detection,
and next-step suggestions.

## State File Location

```text
outputs/state/{JIRA_ID}/pipeline_state.yaml
```

## State Schema

```yaml
# Pipeline State v1
version: 1
ticket_id: "PROJ-12345"
project_id: "myproject"
display_name: "My Project"
created: "2026-03-30T07:00:00Z"
updated: "2026-03-30T07:15:00Z"

phases:
  stp:
    status: completed            # pending | in_progress | completed | failed | skipped
    started: "2026-03-30T07:01:00Z"
    completed: "2026-03-30T07:05:00Z"
    output: "outputs/stp/PROJ-12345/PROJ-12345_test_plan.md"
    output_checksum: "sha256:abc123..."
    skills_used:
      - requirement-mapper
      - scenario-builder
      - tier-classifier
      - template-engine
    error: null

  stp_review:
    status: completed
    started: "2026-03-30T07:06:00Z"
    completed: "2026-03-30T07:08:00Z"
    output: "outputs/reviews/PROJ-12345/PROJ-12345_stp_review.md"
    verdict: APPROVED_WITH_FINDINGS
    findings:
      critical: 0
      major: 3
      minor: 5
    error: null

  stp_refine:
    status: completed
    started: "2026-03-30T07:09:00Z"
    completed: "2026-03-30T07:12:00Z"
    output: "outputs/reviews/PROJ-12345/PROJ-12345_stp_refinement_log.md"
    iterations: 2
    final_verdict: APPROVED_WITH_FINDINGS
    findings:
      critical: 0
      major: 1
      minor: 3
    error: null

  std:
    status: completed
    started: "2026-03-30T07:13:00Z"
    completed: "2026-03-30T07:15:00Z"
    output: "outputs/std/PROJ-12345/PROJ-12345_test_description.yaml"
    output_checksum: "sha256:def456..."
    stp_checksum_at_generation: "sha256:abc123..."
    scenario_counts:
      total: 27
      tier1: 15
      tier2: 12
    stubs:
      go: "outputs/std/PROJ-12345/go-tests/"
      python: "outputs/std/PROJ-12345/python-tests/"
    error: null

  std_review:
    status: pending
    verdict: null
    findings: null
    error: null

  go_codegen:
    status: pending
    output: null
    error: null

  python_codegen:
    status: pending
    output: null
    error: null

  cluster_tests:
    status: pending
    output: null
    error: null
```

## Operations

### 1. Initialize State

**When:** First command run for a ticket (no state file exists).

**Action:**

1. Create directory `outputs/state/{JIRA_ID}/`
2. Write initial `pipeline_state.yaml` with all phases set to `pending`
3. Set `ticket_id`, `project_id`, `display_name` from `project_context`
4. Set `created` and `updated` to current ISO 8601 timestamp

**Output:** The initialized state object.

### 2. Read State

**When:** Every command invocation (Step 0.5).

**Action:**

1. Check if `outputs/state/{JIRA_ID}/pipeline_state.yaml` exists
2. If exists: read and parse YAML, return state object
3. If not exists: initialize state (Operation 1), return new state

**Output:** The current state object.

### 3. Update Phase Status

**When:** A phase starts, completes, or fails.

**Action:**

1. Read current state
2. Update the specified phase fields:
   - `status`: new status value
   - `started`: set to now if transitioning to `in_progress`
   - `completed`: set to now if transitioning to `completed`
   - `output`: path to output artifact (on completion)
   - `output_checksum`: SHA-256 of output file (on completion)
   - `error`: error message (on failure)
   - Any phase-specific fields (verdict, findings, scenario_counts, etc.)
3. Set top-level `updated` to now
4. Write state file

**Phase-specific fields by phase:**

| Phase | Extra Fields |
|:------|:-------------|
| `stp` | `skills_used` |
| `stp_review` | `verdict`, `findings` |
| `stp_refine` | `iterations`, `final_verdict`, `findings` |
| `std` | `stp_checksum_at_generation`, `scenario_counts`, `stubs` |
| `std_review` | `verdict`, `findings` |
| `go_codegen` | `test_count`, `lsp_patterns_used` |
| `python_codegen` | `test_count`, `lsp_patterns_used`, `conftest_generated` |
| `cluster_tests` | `tests_executed`, `tests_passed`, `tests_fixed` |

**Output:** The updated state object.

### 4. Validate Prerequisites

**When:** Before starting a phase that depends on a prior phase.

**Action:**

1. Read current state
2. Read approval gates from `project.yaml` (`approval_gates` list, default: `[stp_review, std_review]`)
3. Read approval state from `outputs/state/{JIRA_ID}/approvals.yaml` (if exists)
4. Check the prerequisite chain for the requested phase:

| Phase | Prerequisites |
|:------|:-------------|
| `stp` | None |
| `stp_review` | `stp.status == completed` |
| `stp_refine` | `stp.status == completed` |
| `std` | `stp.status == completed` AND `stp_review` approved (if gated) |
| `std_review` | `std.status == completed` |
| `go_codegen` | `std.status == completed` AND `std_review` approved (if gated) |
| `python_codegen` | `std.status == completed` AND `std_review` approved (if gated) |
| `cluster_tests` | `python_codegen.status == completed` |

5. **Approval gate check:** If a prerequisite phase is listed in `approval_gates`, verify
   that `approvals.yaml` contains an entry for that phase with `status: approved`.
   If the entry is missing or has `status: rejected`, the gate blocks progression.
6. If prerequisites are not met: return `{valid: false, missing: [...], suggestion: "..."}`
7. If prerequisites are met: return `{valid: true}`

**Prerequisite failure messages:**

| Missing Phase | Suggestion |
|:-------------|:-----------|
| `stp` | "Run `/stp-builder {JIRA_ID}` first." |
| `stp_review` | "Run `/review-stp {JIRA_ID}` to review the STP." |
| `stp_review` (awaiting approval) | "STP Review is awaiting human approval. Approve it in the QualityFlow dashboard before proceeding." |
| `stp_review` (rejected) | "STP Review was rejected. Address the reviewer feedback and re-run `/review-stp {JIRA_ID}`." |
| `std` | "Run `/std-builder {JIRA_ID}` first." |
| `std_review` | "Run `/review-std {JIRA_ID}` to review the STD." |
| `std_review` (awaiting approval) | "STD Review is awaiting human approval. Approve it in the QualityFlow dashboard before proceeding." |
| `std_review` (rejected) | "STD Review was rejected. Address the reviewer feedback and re-run `/review-std {JIRA_ID}`." |
| `codegen` | "Run `/generate-tests {JIRA_ID}` first." |

**Output:** Validation result with missing prerequisites and suggestions.

### 4a. Approval Gate Resolution

**Mapping from downstream phase to required gate:**

| Downstream Phase | Required Gate (if configured) |
|:----------------|:-----------------------------|
| `std` | `stp_review` |
| `go_codegen` | `std_review` |
| `python_codegen` | `std_review` |

**Resolution logic:**

1. For each prerequisite phase, check if it appears in `approval_gates`
2. If it does, read `outputs/state/{JIRA_ID}/approvals.yaml`
3. Check `approvals[phase].status`:
   - `approved` → gate passes, continue
   - `rejected` → gate blocks with rejection message
   - missing → gate blocks with "awaiting approval" message

### 5. Check Staleness

**When:** Before starting a phase that consumes output from a prior phase.

**Action:**

1. Read current state
2. For the requested phase, identify upstream output files:

| Phase | Upstream File | Checksum Field |
|:------|:-------------|:--------------|
| `std` | STP file | `stp.output_checksum` |
| `std_review` | STD YAML | `std.output_checksum` |
| `go_codegen` | STD YAML | `std.output_checksum` |
| `python_codegen` | STD YAML | `std.output_checksum` |

3. Compute current SHA-256 of the upstream file
4. Compare with stored checksum
5. If different: return `{stale: true, file: "...", reason: "STP was modified after STD generation"}`
6. If same: return `{stale: false}`

**Staleness warnings (do not block — inform the user):**

- STP modified after STD: "Warning: The STP has been modified since STD was generated. Consider re-running `/std-builder {JIRA_ID}` to update the STD."
- STD modified after code gen: "Warning: The STD has been modified since code was generated. Consider re-running `/generate-tests {JIRA_ID}`."

**Output:** Staleness check result.

### 6. Suggest Next Step

**When:** After a phase completes successfully.

**Action:**

1. Read current state
2. Determine the next logical phase based on current progress:

| Current Phase Completed | Next Step | Command |
|:----------------------|:----------|:--------|
| `stp` | Review the STP | `/review-stp {JIRA_ID}` |
| `stp_review` (APPROVED*) | Generate STD | `/std-builder {JIRA_ID}` |
| `stp_review` (NEEDS_REVISION) | Refine the STP | `/refine-stp {JIRA_ID}` |
| `stp_refine` | Generate STD | `/std-builder {JIRA_ID}` |
| `std` | Review the STD | `/review-std {JIRA_ID}` |
| `std_review` (APPROVED*) | Generate tests | `/generate-tests {JIRA_ID}` |
| `std_review` (NEEDS_REVISION) | Refine the STD | `/refine-std {JIRA_ID}` (or manual fix) |
| `codegen` | Run cluster tests | `/run-cluster-tests {JIRA_ID}` |
| `cluster_tests` | Pipeline complete | None |

*APPROVED includes APPROVED_WITH_FINDINGS.

3. Check feature toggles to filter suggestions:
   - If both `tier1_tests: false` and `tier2_tests: false`, do not suggest `/generate-tests`

**Output:** Next step suggestion string.

### 7. Show Pipeline Status

**When:** User wants to see overall progress (called by `/pipeline-status` command or embedded in other commands).

**Action:**

1. Read current state
2. Build status display:

```text
Pipeline Status: {JIRA_ID} ({display_name})

Phase              Status              Verdict/Details
─────              ──────              ───────────────
STP Generation     completed           outputs/stp/{ID}/{ID}_test_plan.md
STP Review         completed           APPROVED_WITH_FINDINGS (0C, 3M, 5m)
STP Refinement     completed           2 iterations → APPROVED_WITH_FINDINGS
STD Generation     completed           27 scenarios (15 T1, 12 T2)
STD Review         in_progress         ...
Go Code Gen        pending             Blocked by: STD Review
Python Code Gen    pending             Blocked by: STD Review
Cluster Tests      pending             Blocked by: Python Code Gen

Next step: Complete STD review, then run /generate-tests {ID}

Staleness: None detected
```

**Output:** Formatted status string.

## Checksum Computation

Use SHA-256 of file content. Compute via:

```bash
shasum -a 256 <file_path> | cut -d ' ' -f 1
```

Prefix stored value with `sha256:` for clarity.

## Command-to-Phase Mapping

Each command maps to exactly one phase for state tracking:

| Command | Phase Key | Toggle Gate |
|:--------|:----------|:-----------|
| `/stp-builder` | `stp` | `stp_generation` |
| `/review-stp` | `stp_review` | `stp_review` |
| `/refine-stp` | `stp_refine` | `stp_review` |
| `/std-builder` | `std` | `std_generation` |
| `/review-std` | `std_review` | `std_review` |
| `/generate-tests` | `codegen` | `tier1_tests` / `tier2_tests` |
| `/run-cluster-tests` | `cluster_tests` | `tier2_tests` |

Commands not tracked: `/stp-from-doc` (alternative entry point, creates STP phase state), `/refine-std` (when implemented).

## Integration Pattern (Step 0.5)

Every command integrates state tracking after Step 0 (project-resolver):

```text
Step 0: project-resolver → project_context
Step 0.5: pipeline-state
  a) Read or initialize state
  b) Validate prerequisites for this phase
  c) Check staleness of upstream outputs
  d) If prerequisites not met → show suggestion, exit
  e) If stale upstream → show warning, continue
  f) Update phase status to in_progress
... (command work) ...
Final: pipeline-state
  a) Update phase status to completed (or failed)
  b) Record output path and checksum
  c) Record phase-specific fields
  d) Show next-step suggestion
```

## Re-run Behavior

Commands can be re-run. State is updated to reflect the latest run:

- If a phase was `completed` and is re-run, status transitions:
  `completed → in_progress → completed` (overwriting previous output/checksum)
- Downstream phases are NOT automatically invalidated. Staleness checks will
  detect the mismatch on next downstream run.
- Previous state is not archived (state file reflects current pipeline state only).

## Error State

If a command fails:

1. Phase status is set to `failed`
2. `error` field records the error message
3. `completed` timestamp is NOT set
4. Next-step suggestion recommends re-running the same command

A failed phase does NOT block re-running the same phase. It only blocks
downstream phases via prerequisite validation.
