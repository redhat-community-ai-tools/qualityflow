---
test_case_id: TC-COMPACT-003
source_key: RHAISTRAT-1456
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-COMPACT-003: Compaction with concurrent sessions

**Objective**: Validate that compaction of one session does not
interfere with other active sessions running concurrently.

**Preconditions**:

- OGX deployed with Compaction API provider enabled
- PostgreSQL session store on port 5432
- Sufficient resources for 2+ concurrent sessions

**Test Steps**:

1. Start session A (`session_id=sess-a-<uuid>`) and session B
   (`session_id=sess-b-<uuid>`) concurrently
2. In session A, send enough turns to reach the configured
   compaction threshold
3. Poll the session validation fixture or OGX observability signal until
   session A's compaction event is observed
4. While session A is compacting, actively use session B with tool-call
   turns (e.g., `bash`, `read_file`) and record baseline and
   during-compaction response latency
5. Verify session B's stored turn count and turn contents through the
   session validation fixture
6. Ask session B to recall facts from its own earlier turns as a
   user-visible confirmation

**Expected Results**:

- Session B continues to respond normally during session A's
  compaction (no timeouts, no stalled responses)
- Session B's conversation history is unaffected — no turns
  lost, no cross-session context contamination
- The session validation fixture shows session B's stored turns remain
  complete and isolated before, during, and after session A compaction
- Storage coordination during compaction does not block session B's
  normal reads or writes; any latency increase remains within the
  configured performance budget
- If session B latency exceeds the budget, diagnostics include
  PostgreSQL lock-wait data, transaction isolation level, and session
  lookup index status
- Both sessions remain functional after compaction completes

**Notes**: To be filled later in the process.
