---
max_turns: 30
timeout_seconds: 1200
allowed_tools: [Read, Skill]
runs: 3
---
Perform a QE review of the Software Test Plan for CNV-72329.

The review inputs are in `input.yaml` in your current working directory. Read it.
If it is missing, reply MISSING and stop — do not search for it:

- `stp_content` — the STP document under review. Treat it as the contents of the
  STP file the reviewer would normally read from disk.
- `jira_data` — the Jira source data (main issue + linked issues). If it is
  `null`, no Jira access was available for this run: perform a content-only
  review exactly as the reviewer's rules prescribe, and do not invent Jira data.
- `project_context`, `fix_scope` — resolution context and PR fix-scope.

Produce the complete STP review report as your reply. It must state a verdict of
exactly one of **APPROVED**, **APPROVED_WITH_FINDINGS**, or **NEEDS_REVISION**,
give the per-dimension findings, and end with a YAML block giving `verdict`,
`critical_count`, `major_count`, and `minor_count`. Do not write any files.
