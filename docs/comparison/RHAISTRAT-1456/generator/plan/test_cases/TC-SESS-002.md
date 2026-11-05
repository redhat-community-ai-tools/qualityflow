---
test_case_id: TC-SESS-002
source_key: RHAISTRAT-1456
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-SESS-002: Session recovery after network disconnect

**Objective**: Validate that sessions resume with full conversation
context intact after a network interruption, using the same
`session_id`.

**Preconditions**:

- OGX running on port 8321 with Memories API and PostgreSQL
  session store configured
- Network disruption tooling available (iptables, tc, or ability to
  kill/restart pods)
- Target OSS model serving on vLLM (port 8000)

**Test Steps**:

1. Generate a unique `session_id` and establish a session by sending
   turn 1: prompt requesting `read_file` on a known test file
2. Send turn 2: prompt requesting `grep_search` for a pattern in the
   file, same `session_id`
3. Send turn 3: prompt requesting `edit_file` to modify a matched
   line, same `session_id`
4. Record the turn count in PostgreSQL before disruption
5. Simulate network disruption: apply `iptables -A OUTPUT -p tcp
   --dport 8321 -j DROP` or kill the OGX pod
6. Wait 10 seconds, then restore connectivity: remove iptables rule
   or wait for pod restart
7. Send turn 4 with the same `session_id`: prompt asking the model to
   describe what edits were made — do NOT resend prior history

**Expected Results**:

- Turn 4 response correctly references the edit made in turn 3
- No session data loss — model has full conversation context from
  PostgreSQL
- HTTP 200 response on reconnection, no 500 or timeout errors
- Session continuity is seamless from the client perspective

**Validation**:

- Query PostgreSQL: `SELECT count(*) FROM session_turns WHERE
  session_id = '<uuid>';` increases by the expected increment after
  appending turn 4, without duplicating earlier turns
- Verify session metadata: `SELECT last_accessed FROM sessions WHERE
  session_id = '<uuid>';` shows updated timestamp after reconnection

**Notes**: To be filled later in the process.
