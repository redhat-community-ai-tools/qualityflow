---
name: demo-pipeline
description: Run the full QualityFlow pipeline end-to-end (STP → STD → Go Tests → Python Tests) with demo-friendly phase banners and pauses
argument-hint: <JIRA-ID>
allowed-tools: Read, Write, Edit, Task, Glob, Grep, LSP, Skill, AskUserQuestion, Bash, mcp__mcp-atlassian__jira_get_issue, mcp__mcp-atlassian__jira_search, mcp__github__pull_request_read, mcp__github__get_file_contents
---

# QualityFlow Demo Pipeline for $ARGUMENTS

You are the **demo orchestrator**. Run the full QualityFlow pipeline sequentially with
clear phase banners and pauses between each phase so the presenter can talk through the demo.

## Input

The user has provided: `$ARGUMENTS`

This should be a Jira ticket ID (e.g., `MYPROJ-12345`, `PROJ-494`).

## Important: Demo Behavior

- **Before each phase**, print a large, visible banner (see format below).
- **After each phase completes**, print a completion banner, then **pause** using AskUserQuestion
  to let the presenter control pacing. Wait for any input before proceeding.
- If any phase fails, print the error clearly and stop. Do not continue to the next phase.

## Banner Format

Before starting a phase, output exactly this pattern (replace phase number and name):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PHASE {N}/4 — {PHASE_NAME}
  Ticket: {JIRA_ID}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

After a phase completes, output:

```
──────────────────────────────────────────────────────────────
  PHASE {N}/4 — {PHASE_NAME} — DONE
──────────────────────────────────────────────────────────────
```

Then **pause for the presenter** using AskUserQuestion:
- Question: `"Ready to start Phase {N+1} — {NEXT_PHASE_NAME}?"`
- Options: "Continue" (proceed to next phase), "Stop here" (exit pipeline)
- For the final phase: `"Pipeline finished! Review the outputs?"`
- Options: "Show summary" (print final summary), "Done" (exit)

This ensures the pipeline pauses at each phase for the presenter while remaining
compatible with interactive use. If running non-interactively, users should run
each phase command separately instead of using `/demo-pipeline`.

## Pipeline Phases

### Phase 1: Generate STP

Print the Phase 1 banner: `GENERATE SOFTWARE TEST PLAN (STP)`

Use the Skill tool to invoke the stp-builder command:

**Tool:** Skill
**Parameters:**
- skill: "stp-builder"
- args: "$ARGUMENTS"

This generates: `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md`

After completion, print the done banner and pause.

### Phase 2: Generate STD

Print the Phase 2 banner: `GENERATE SOFTWARE TEST DESCRIPTION (STD)`

Use the Skill tool to invoke the std-builder command:

**Tool:** Skill
**Parameters:**
- skill: "std-builder"
- args: "$ARGUMENTS"

This generates:
- `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`
- `outputs/{JIRA_ID}/std/go-tests/*_stubs_test.go`
- `outputs/{JIRA_ID}/std/python-tests/test_*_stubs.py`

After completion, print the done banner and pause.

### Phase 3: Generate Tests

Print the Phase 3 banner: `GENERATE TEST IMPLEMENTATIONS`

Use the Skill tool to invoke the generate-tests command:

**Tool:** Skill
**Parameters:**
- skill: "generate-tests"
- args: "$ARGUMENTS"

This generates test implementations based on project config:
- Tests are written to `outputs/{JIRA_ID}/{language}-tests/` (language from tier config)

After completion, print the final done banner.

## Final Summary

After Phase 4 completes, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  QUALITYFLOW PIPELINE COMPLETE
  Ticket: {JIRA_ID}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Phase 1: STP ........... outputs/{JIRA_ID}/stp/
  Phase 2: STD ........... outputs/{JIRA_ID}/std/
  Phase 3: Go Tests ...... outputs/{JIRA_ID}/go-tests/
  Phase 4: Python Tests .. outputs/{JIRA_ID}/python-tests/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Notes

- This command skips STP/STD review and refinement phases for demo speed.
- The pipeline-state skill checks are still active within each sub-command.
  If pipeline-state blocks a phase (e.g., STD requires STP approval gate),
  the sub-command will handle it. The STP and STD phases will set their own
  state as they complete.
- Each sub-command handles its own project-resolver call internally.
