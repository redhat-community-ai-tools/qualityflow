---
test_case_id: TC-SESS-004
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-SESS-004: Invalid session_id handling

**Objective**: Verify graceful handling when a non-existent
`session_id` is provided to `/v1/chat/completions`.

**Test Steps**:

1. Generate a random UUID that does not exist in the PostgreSQL
   session store
2. POST to `/v1/chat/completions` on port 8321 with the non-existent
   `session_id` and a prompt requesting `read_file` on a known file
3. Observe the HTTP response code and body
4. Verify the response body uses the documented error schema and the
   same safe error shape for "not found" and "not owned" cases
5. Repeat with an existing `session_id` owned by a different
   authenticated principal
6. From an isolated test pod with no background load, repeat both
   cases enough times to compare response latency distributions

**Expected Results**:

- OGX does not return HTTP 500 or crash
- HTTP 404 or 422 with the documented JSON error schema, including a
  stable error code such as `session_not_accessible`
- Error details do not expose stack traces, SQL queries, database
  schema names, framework exception names, internal resource names, or
  whether the `session_id` exists for another principal
- The non-existent and not-owned `session_id` cases return the same
  status code family and safe error shape
- Response latency for non-existent and not-owned `session_id` cases
  stays within the same expected distribution, so session existence
  cannot be inferred from timing alone
- No stale or orphaned data from other sessions is returned

**Notes**: To be filled later in the process.
