---
name: pipeline-state
description: Track per-ticket QualityFlow pipeline state across all phases. Use when a command needs to initialize state, transition phases, validate prerequisites, detect stale state, or suggest the next step for a ticket.
---

# Pipeline State Tracker

Manages per-ticket pipeline state across all QualityFlow phases: state
initialization, phase transitions, prerequisite validation, staleness
detection, and next-step suggestions.

**All state reads and writes go through the bundled script — never hand-edit
`pipeline_state.yaml`.** Run every operation via Bash from the repo root:

```bash
python3 skills/pipeline-state/state.py <operation> <args>
```

The script writes atomically (tmp + rename), computes SHA-256 checksums, and
enforces the contract below. It exits non-zero with a clear message on
contract violations; prerequisite failures print the suggestion and exit 1.

## State File Location

```text
outputs/{JIRA_ID}/state/pipeline_state.yaml
```

## Operations

### 1. Initialize / Read State

**When:** Every command invocation (Step 0.5). Idempotent: if the state file
already exists, it is printed unchanged; otherwise it is created with all
phases `pending`.

```bash
python3 skills/pipeline-state/state.py init {JIRA_ID} \
  --project-id {project_id} --display-name "{display_name}"
```

### 2. Start a Phase

**When:** A phase begins work. Sets `status: in_progress`, `started`, clears
`error`, bumps `updated`.

```bash
python3 skills/pipeline-state/state.py start-phase {JIRA_ID} {phase}
```

### 3. Complete a Phase

**When:** A phase finishes. Sets `status: completed`, `completed` timestamp,
records `output` and its `output_checksum` (SHA-256, computed by the script).
Phase-specific extra fields are passed as inline YAML/JSON via `--extra`
(or `--extra -` to read them from stdin).

```bash
python3 skills/pipeline-state/state.py complete-phase {JIRA_ID} std \
  --output outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml \
  --extra '{"scenario_counts": {"total": 27, "tier1": 15, "tier2": 12}}'
```

Completing a phase that is not `in_progress` is allowed (re-runs overwrite
previous output/checksum) but prints a warning.

**Phase-specific extra fields by phase:**

| Phase | Extra Fields |
|:------|:-------------|
| `stp` | `skills_used` |
| `stp_review` | `verdict`, `findings` |
| `stp_refine` | `iterations`, `final_verdict`, `findings` |
| `std` | `stp_checksum_at_generation`, `scenario_counts`, `stubs` |
| `std_review` | `verdict`, `findings` |
| `codegen` | `test_count`, `lsp_patterns_used`, `conftest_generated` |

### 3b. Record Usage on a Phase

**When:** A headless runner (e.g. `python3 pipeline_runner.py run {JIRA_ID} {phase}`)
knows the run's token/cost usage and actual model after the slash command
already completed the phase. Merges the given fields onto the phase WITHOUT
touching `status` or timestamps. Agents running inside a Claude session do
NOT call this — a session cannot see its own usage; it exists for wrappers
that parse the CLI's stream output.

```bash
python3 skills/pipeline-state/state.py record-usage {JIRA_ID} stp \
  --extra '{"usage": {"input_tokens": 65000, "output_tokens": 32555, "cost_usd": 3.12}, "model": "claude-sonnet-5"}'
```

### 4. Fail a Phase

**When:** A command fails. Sets `status: failed` and `error`; the `completed`
timestamp is NOT set. A failed phase does not block re-running the same
phase — only downstream phases, via prerequisite validation.

```bash
python3 skills/pipeline-state/state.py fail-phase {JIRA_ID} {phase} \
  --error "what went wrong"
```

### 5. Check Prerequisites, Approval Gates, and Staleness

**When:** Before starting a phase. Prints a YAML result
(`valid`, `missing`, `suggestion`, `stale`, `stale_reason`). Exit code 0 when
prerequisites are met, 1 when not (show the `suggestion` to the user and
stop). Staleness never blocks — it is reported as a warning; relay it to the
user and continue.

```bash
python3 skills/pipeline-state/state.py check {JIRA_ID} {phase}
```

### 6. Show Pipeline Status

**When:** User wants overall progress (`/pipeline-status` or embedded in
other commands). Prints the phase table, next-step suggestion, and staleness
notes.

```bash
python3 skills/pipeline-state/state.py status {JIRA_ID}
```

## State Schema (reference)

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
    output: "outputs/PROJ-12345/stp/PROJ-12345_test_plan.md"
    output_checksum: "sha256:abc123..."
    skills_used: [requirement-mapper, scenario-builder]
    error: null
  stp_review:
    status: completed
    verdict: APPROVED_WITH_FINDINGS
    findings: {critical: 0, major: 3, minor: 5}
    error: null
  stp_refine: {status: pending, error: null}
  std: {status: pending, error: null}
  std_review: {status: pending, error: null}
  codegen: {status: pending, error: null}
```

## Prerequisite Chains (enforced by `check`)

| Phase | Prerequisites |
|:------|:-------------|
| `stp` | None |
| `stp_review` | `stp.status == completed` |
| `stp_refine` | `stp.status == completed` |
| `std` | `stp.status == completed` AND `stp_review` approved (if gated) |
| `std_review` | `std.status == completed` |
| `codegen` | `std.status == completed` AND `std_review` approved (if gated) |

## Approval Gates

Gates come from `project.yaml` (`approval_gates` list, default:
`[stp_review, std_review]`). Approval state lives in
`outputs/{JIRA_ID}/state/approvals.yaml`:

```yaml
approvals:
  stp_review: {status: approved}   # approved | rejected
```

| Downstream Phase | Required Gate (if configured) |
|:----------------|:-----------------------------|
| `std` | `stp_review` |
| `codegen` | `std_review` |

`approved` passes; `rejected` or a missing entry blocks with the
corresponding message from `check`.

## Staleness

`check` compares the current SHA-256 of the upstream output file against the
stored checksum:

| Phase | Upstream File | Checksum Field |
|:------|:-------------|:--------------|
| `std` | STP file | `stp.output_checksum` |
| `std_review` | STD YAML | `std.output_checksum` |
| `codegen` | STD YAML | `std.output_checksum` |

Staleness warns but never blocks — suggest re-running the upstream builder
(`/std-builder` when the STP changed, `/generate-tests` when the STD changed).

## Next-Step Suggestions (produced by `status`)

| Current Phase Completed | Next Step | Command |
|:----------------------|:----------|:--------|
| `stp` | Review the STP | `/review-stp {JIRA_ID}` |
| `stp_review` (APPROVED*) | Generate STD | `/std-builder {JIRA_ID}` |
| `stp_review` (NEEDS_REVISION) | Refine the STP | `/refine-stp {JIRA_ID}` |
| `stp_refine` | Generate STD | `/std-builder {JIRA_ID}` |
| `std` | Review the STD | `/review-std {JIRA_ID}` |
| `std_review` (APPROVED*) | Generate tests | `/generate-tests {JIRA_ID}` |
| `std_review` (NEEDS_REVISION) | Refine the STD | `/refine-std {JIRA_ID}` |
| `codegen` | Pipeline complete | None |

*APPROVED includes APPROVED_WITH_FINDINGS. If both `tier1_tests` and
`tier2_tests` toggles are false, `/generate-tests` is not suggested.

## Command-to-Phase Mapping

| Command | Phase Key | Toggle Gate |
|:--------|:----------|:-----------|
| `/stp-builder` | `stp` | `stp_generation` |
| `/review-stp` | `stp_review` | `stp_review` |
| `/refine-stp` | `stp_refine` | `stp_review` |
| `/std-builder` | `std` | `std_generation` |
| `/review-std` | `std_review` | `std_review` |
| `/refine-std` | `std_review` | `std_review` |
| `/generate-tests` | `codegen` (one phase, all languages) | `tier1_tests` / `tier2_tests` |

## Integration Pattern (Step 0.5)

```text
Step 0: project-resolver → project_context
Step 0.5:
  a) python3 skills/pipeline-state/state.py init {JIRA_ID} --project-id ... --display-name ...
  b) python3 skills/pipeline-state/state.py check {JIRA_ID} {phase}
     - exit 1 → show suggestion, stop
     - stale warning → show warning, continue
  c) python3 skills/pipeline-state/state.py start-phase {JIRA_ID} {phase}
... (command work) ...
Final:
  d) complete-phase (with --output and --extra) or fail-phase (with --error)
  e) python3 skills/pipeline-state/state.py status {JIRA_ID}  # next-step suggestion
```

## Re-run Behavior

- Re-running a completed phase transitions `completed → in_progress →
  completed`, overwriting previous output/checksum (with a warning if
  `start-phase` was skipped).
- Downstream phases are NOT automatically invalidated; staleness checks
  detect the mismatch on the next downstream `check`.
- Previous state is not archived — the file reflects current state only.
