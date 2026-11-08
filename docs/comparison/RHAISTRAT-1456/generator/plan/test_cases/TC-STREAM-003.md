---
test_case_id: TC-STREAM-003
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-STREAM-003: Malformed SSE stream handling

**Objective**: Verify that the Codex CLI handles interrupted or
malformed SSE streams gracefully without crashing or executing partial
tool calls.

**Preconditions**:

- OGX distribution running on port 8321
- Active Codex CLI session connected via OPENAI_BASE_URL
- Ability to kill OGX pod or inject network disruption
  (e.g., `oc delete pod` or `iptables` rule)

**Test Steps**:

1. Start a Codex CLI session with
   `OPENAI_BASE_URL=http://llamastack:8321/v1`
2. Issue a prompt that triggers a tool call (e.g., "Read the file
   README.md")
3. While the SSE stream is actively delivering delta chunks, kill the
   OGX pod: `oc delete pod <ogx-pod> --grace-period=0`
4. Observe the Codex CLI terminal output for error handling behavior
5. Verify no partial tool execution occurred (e.g., no incomplete
   file read or partial bash command executed)
6. Verify the Codex CLI remains responsive and can accept new prompts
   or exit cleanly

**Expected Results**:

- Codex CLI displays a connection error or timeout message
- Codex CLI does not crash or produce an unhandled exception
- No tool is partially executed based on incomplete arguments
- Codex CLI session remains interactive after the error

**Notes**: To be filled later in the process.
