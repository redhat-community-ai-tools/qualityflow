---
test_case_id: TC-NEG-001
source_key: RHAISTRAT-1246
objectives: [2]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-NEG-001: Invalid Anthropic API key returns authentication error

**Objective**: Verify that an invalid API key in the
`ANTHROPIC_API_KEY` config produces a clear authentication error
without leaking key material.

**Preconditions**:

- RHOAI 3.5 cluster with `remote::anthropic` provider activated
- `ANTHROPIC_API_KEY` set to an invalid value

**Test Steps**:

1. Deploy the OGX distribution with an invalid `ANTHROPIC_API_KEY`
2. Send a chat completion request:

   ```bash
   curl -s -w "\n%{http_code}" -X POST <ogx-route>/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "<model>", "messages": [{"role": "user", "content": "test"}]}'
   ```

3. Verify the response returns an error status code (401 or 403)
4. Verify the error message does not contain the API key value

**Expected Results**:

- HTTP 401 or 403 response indicating authentication failure
- Error response body contains a descriptive message (e.g.,
  "invalid API key" or "authentication failed")
- No API key material appears in the error response body or
  pod logs

**Notes**: To be filled later in the process.
