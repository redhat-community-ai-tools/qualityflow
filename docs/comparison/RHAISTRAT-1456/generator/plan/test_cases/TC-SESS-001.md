---
test_case_id: TC-SESS-001
source_key: RHAISTRAT-1456
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-SESS-001: Session persistence across 5+ chained tool calls

**Objective**: Validate that server-side session state persists
conversation context across 5+ chained tool calls without the client
resending full conversation history.

**Preconditions**:

- OGX running on port 8321 with Memories API provider
  registered in config.yaml
- PostgreSQL session store running on port 5432
- Target OSS model deployed on vLLM (port 8000) with
  `--tool-call-parser` enabled
- Codex CLI configured with `OPENAI_BASE_URL` pointing to OGX

**Test Steps**:

1. Generate a unique `session_id` (UUID format)
2. Send turn 1: prompt requesting `read_file` on a known file in the
   test repo, include `session_id` parameter
3. Send turn 2: prompt requesting `grep_search` referencing content
   from turn 1 result, same `session_id`
4. Send turn 3: prompt requesting `edit_file` to modify a line found
   in turn 2, same `session_id`
5. Send turn 4: prompt requesting `bash` to run a test command on the
   edited file, same `session_id`
6. Send turn 5: prompt requesting `read_file` to verify the edit from
   turn 3, same `session_id`
7. Send turn 6: prompt asking the model to summarize all five prior
   actions — do NOT resend any conversation history, rely solely on
   server-side session state

**Expected Results**:

- Turn 6 response correctly references all five prior tool results
  (file read, grep match, edit, bash output, verification read)
- No "I don't have context" or "I don't have information about
  previous" errors in the response
- Each turn returns HTTP 200 with valid tool_calls or assistant content
- Session state is retrieved from PostgreSQL, not from client-side
  history

**Validation**:

- Use the Codex SDK session-state validation fixture to query the
  configured PostgreSQL session store by `session_id` and authenticated
  principal.
- Verify the fixture returns the expected five prior turns from the
  `session_turns` records without requiring client-resubmitted history.
- Verify returned turns are chronological or sequential by the stored
  turn number or timestamp fields.

**Notes**: To be filled later in the process.
