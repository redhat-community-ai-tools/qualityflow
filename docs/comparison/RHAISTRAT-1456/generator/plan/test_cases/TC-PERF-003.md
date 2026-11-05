---
test_case_id: TC-PERF-003
source_key: RHAISTRAT-1456
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-PERF-003: Concurrent session performance

**Objective**: Validate PostgreSQL session store performance under
concurrent session load, ensuring session retrieval stays within the
configured performance budget.

**Preconditions**:

- OGX deployed on port 8321 with PostgreSQL session store
- PostgreSQL on port 5432 with connection pooling configured
- Sufficient cluster resources for 100 concurrent sessions
- Target model served via vLLM on port 8000

**Test Steps**:

1. Start 100 concurrent Codex CLI sessions, each with a unique
   `session_id`
2. Each session performs 10 tool-call turns sequentially (mix of
   `bash`, `read_file`, and `grep_search` calls)
3. Measure per-turn latency for each session, focusing on the
   session state retrieval component (time between request
   received and first vLLM call)
4. Monitor PostgreSQL session retrieval behavior:
   - Query execution time for the concrete session retrieval query
     used by TC-SESS-001
   - Connection pool active and idle counts from the configured
     pooling layer
   - Any pool exhaustion or retry signals reported by the service
5. After all sessions complete, verify no sessions were dropped
   or returned stale state

**Expected Results**:

- Session state retrieval latency remains within the configured
  budget across all sessions
- No PostgreSQL connection pool exhaustion (active connections
  remain below pool max)
- All 100 sessions complete their 10 turns without error
- No dropped sessions or HTTP 503 responses

**Validation**:

- `pg_stat_statements` or the equivalent database telemetry identifies
  the session retrieval query from TC-SESS-001 and shows it remains
  within the configured latency budget
- Pooler metrics show active connections remain below pool capacity
  throughout the test

**Notes**: To be filled later in the process.
