---
name: stp-builder
description: Generate a Software Test Plan (STP) from a Jira ticket, then auto-run review and refinement so the command finishes with a final STP
argument-hint: <JIRA-ID or URL>
allowed-tools: Read, Write, Edit, Task, Glob, Grep, LSP, Skill, mcp__mcp-atlassian__jira_get_issue, mcp__mcp-atlassian__jira_search, mcp__github__pull_request_read, mcp__github__get_file_contents
---

# Generate STP for $ARGUMENTS

You are the STP Builder entry point. Initiate the STP generation workflow by activating the **stp-orchestrator** subagent, then chain the review cycle so the invocation ends with a reviewed STP, not a draft.

## Input

The user has provided: `$ARGUMENTS`

This should be a Jira ticket ID (e.g., `PROJ-12345`, `PROJ-494`) or a Jira URL (e.g., `https://your-jira.example.com/browse/PROJ-12345`).

## Workflow

### Step 0: Resolve Project

Use the Skill tool to invoke the project-resolver skill:

**Tool:** Skill
**Parameters:**

- skill: "project-resolver"
- args: "$ARGUMENTS"

This returns `project_context` containing:

- `project_id`, `display_name`, `jira_id`
- `config_dir` (path to project config files)
- `feature_toggles` (what capabilities are enabled)
- `stp_header`, `versioning`

**If project resolution fails:** Display the error and exit. Do not proceed.

**Check stp_generation toggle:**
If `project_context.feature_toggles.stp_generation` is false:

- Output: "STP generation is disabled for project {project_context.display_name} (stp_generation toggle is false)."
- Exit. Do not proceed.

### Step 1: Activate Orchestrator

Activate the **stp-orchestrator** subagent with the resolved Jira ticket ID **and** `project_context`.

Pass to orchestrator:

```yaml
jira_id: "{JIRA_ID}"
project_context: <from project-resolver>
```

The orchestrator will:

1. **Pre-processing Phase (Sequential Pipeline)**:
   - Launch **jira-collector** (cyan) to fetch Jira issue data and PR URLs
   - Launch **github-pr-fetcher** (green) with PR URLs from jira-collector
   - Launch **regression-analyzer** (yellow) with changed files from github-pr-fetcher

2. **Core Processing Phase (Sequential)**:
   - Pass aggregated data to **stp-generator** (purple)
   - Generate complete STP document with test scenarios

3. **Post-processing Phase (Sequential)**:
   - Pass document to **document-formatter** (orange)
   - Sanitize PII, validate structure, format tables
   - Save to `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md`

### Step 2: Review & Refine (automatic)

The STP the orchestrator just saved is a draft. Chain the review cycle now —
do not stop and wait for the user to trigger it. Review and refinement stay
separate commands with separate artifacts and verdicts (they are chained, not
merged): the reviewer runs in its own context against freshly fetched Jira
data, so it can genuinely reject what the generator produced.

**Check the `stp_review` toggle first:** if
`project_context.feature_toggles.stp_review` is false, skip this step and
report the STP as generated but unreviewed. Do not invoke review or refine.

1. Invoke the review:

   **Tool:** Skill
   **Parameters:**
   - skill: "review-stp"
   - args: "{JIRA_ID}"

   This produces `outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md` with a
   verdict (APPROVED / APPROVED_WITH_FINDINGS / NEEDS_REVISION).

2. **Only if the verdict is `NEEDS_REVISION`**, invoke the refine loop:

   **Tool:** Skill
   **Parameters:**
   - skill: "refine-stp"
   - args: "{JIRA_ID}"

   This iterates fix → re-review until the verdict clears (0 critical
   findings) or its iteration cap is hit. An APPROVED or
   APPROVED_WITH_FINDINGS verdict needs no refinement — skip this invocation
   entirely; `/refine-stp` would exit immediately anyway.

**Failure isolation:** if review or refinement fails, do NOT delete or regenerate
the STP. Report the saved STP path, the sub-command's error, and the manual
recovery (`/review-stp {JIRA_ID}`, then `/refine-stp {JIRA_ID}` if needed).
A failed review leaves a draft STP — that is strictly better than no STP.

## Expected Output

When `stp_review` is enabled (the default), one invocation ends with a
**final** STP:

- STP: `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md`
- Review report: `outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md`

Close with a short summary: initial verdict → final verdict (and refinement
iterations, if the loop ran), then the next step —
`/std-builder {JIRA_ID}`, noting that the STD approval gate still requires a
human to approve the reviewed STP first (dashboard, or
`outputs/{JIRA_ID}/state/approvals.yaml`). The automatic review does not
self-approve the gate.

When `stp_review` is disabled: just the STP file, reported as unreviewed.

## Activation

1. Invoke the **project-resolver** skill with `$ARGUMENTS` to get `project_context`.
2. Activate the **stp-orchestrator** agent, passing both the Jira ticket ID and `project_context`.
3. When the orchestrator finishes, run Step 2 (review, then refine only on NEEDS_REVISION).
