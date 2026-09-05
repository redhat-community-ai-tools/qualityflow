---
name: stp-cursor
description: Cursor-native STP generation - the main agent orchestrates the stages itself instead of delegating to the stp-orchestrator subagent
argument-hint: <JIRA-ID or URL>
---

# Generate STP for $ARGUMENTS (Cursor-native, flattened)

You are the STP entry point **and** the orchestrator. Do NOT activate the
`stp-orchestrator` subagent. In Cursor a subagent that tries to launch its own
child stalls, so you run the orchestration yourself and launch each stage agent
directly. Every stage below is a subagent you spawn from this, the main agent.

Follow `agents/stp-orchestrator.md` for the detailed contract of each stage
(inputs, outputs, phase summaries, error handling). This file only changes WHO
launches the stages.

## Step 0: Resolve project

Read and follow `skills/project-resolver/SKILL.md` yourself, applied to `$ARGUMENTS`,
to build `project_context` (`project_id`, `display_name`, `jira_id`, `config_dir`,
`feature_toggles`, `stp_header`, `versioning`).

If resolution fails, report and stop. If `feature_toggles.stp_generation` is false,
say so and stop.

Initialize state: `python3 skills/pipeline-state/state.py` per that skill, moving
`stp` to `in_progress`.

## Step 1: Stages you launch directly (in order)

1. **jira-collector** — pass `jira_id` and `project_context`. Use the
   `mcp__mcp-atlassian__*` tools. If a GitHub tool is unavailable, skip it and
   continue; `gh` on the command line is an acceptable substitute for any
   GitHub read (it is already authenticated).
2. **ticket-assessor** (skill, `skills/ticket-assessor/SKILL.md`) — run it on the
   collected data. Honour its verdict strictly:
   - `INSUFFICIENT` → **halt**, do not generate an STP, report the reasons and the
     assessment path. This is a correct outcome for a thin ticket, not a failure.
   - `PARTIAL` → continue, carrying `data_completeness_caveat`.
   - `READY` → continue.
3. **github-pr-fetcher** — only if the collector found PR URLs. If none, skip and
   say so.
4. **regression-analyzer** — only if there are changed files from step 3.
5. **stp-generator** — the aggregated data, plus `data_completeness_caveat` if set.
6. **document-formatter** — saves `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md`.

After each stage print one line: `Phase {N} Complete — {name}: {key metrics}`.

If a stage subagent fails to start or returns nothing, do NOT silently wait. Say
which stage stalled, then carry out that stage's work yourself by following its
agent file directly, and continue the pipeline.

## Step 2: Review, then refine only if needed

Skip if `feature_toggles.stp_review` is false; report the STP as unreviewed.

Otherwise follow `commands/review-stp.md` for `{JIRA_ID}` to produce
`outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md`. Only when the verdict is
`NEEDS_REVISION`, follow `commands/refine-stp.md`.

**Failure isolation:** never delete or regenerate the STP because review failed.
Report the STP path, the error, and the manual recovery commands.

## Output

- STP: `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md`
- Review: `outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md`

Close with: initial verdict → final verdict (and refinement iterations if the loop
ran), then the next step `/std-builder {JIRA_ID}`, noting the STD approval gate
still needs a human.
