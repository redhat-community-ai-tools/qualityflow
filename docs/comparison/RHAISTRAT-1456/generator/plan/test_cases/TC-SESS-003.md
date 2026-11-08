---
test_case_id: TC-SESS-003
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-SESS-003: Session ID collision prevention

**Objective**: Verify that two concurrent sessions with different
`session_id` values do not cross-contaminate conversation context.

**Preconditions**:

- OGX running on port 8321 with Memories API configured
- PostgreSQL session store on port 5432
- Two separate test repositories (repo-a and repo-b) available

**Test Steps**:

1. Generate two unique session IDs: `uuid-a` and `uuid-b`
2. Start session A (`session_id=uuid-a`): send a prompt requesting
   `read_file` on `repo-a/main.py`
3. Start session B (`session_id=uuid-b`): send a prompt requesting
   `read_file` on `repo-b/server.js`
4. In session A, send a follow-up prompt: "What file did I just read?"
   — do NOT resend history
5. In session B, send a follow-up prompt: "What file did I just read?"
   — do NOT resend history
6. In session A, send: "Do you know anything about server.js?" (a file
   only session B accessed)

**Expected Results**:

- Session A follow-up (step 4) references `repo-a/main.py` only
- Session B follow-up (step 5) references `repo-b/server.js` only
- Session A (step 6) has no knowledge of `server.js` — responds that
  it has no context about that file
- No cross-session context leakage in any response

**Validation**:

- Use the same Codex SDK session-state validation fixture as
  TC-SESS-001 to query the configured PostgreSQL session store by
  `session_id` and authenticated principal.
- Confirm `uuid-a` returns only session A turns, `uuid-b` returns only
  session B turns, and neither retrieval path exposes the other
  session's tool results.

**Notes**: To be filled later in the process.
