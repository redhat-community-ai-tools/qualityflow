---
test_case_id: TC-NEG-002
source_key: RHAISTRAT-1246
objectives: [3]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-NEG-002: Invalid per-request API key override

**Objective**: Verify that an invalid API key passed via the
`x-ogx-provider-data` header returns an authentication error without
affecting the config-level key.

**Preconditions**:

- RHOAI 3.5 cluster with `remote::anthropic` provider activated
- Valid config-level `ANTHROPIC_API_KEY` (Key A)

**Test Steps**:

1. Send a request with an invalid key in the override header:

   ```bash
   curl -s -w "\n%{http_code}" -X POST <ogx-route>/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H 'x-ogx-provider-data: {"anthropic_api_key": "invalid-key-123"}' \
     -d '{"model": "<model>", "messages": [{"role": "user", "content": "test"}]}'
   ```

2. Verify the response returns an authentication error
3. Send a follow-up request without the override header (uses
   config-level Key A)
4. Verify the follow-up request succeeds, confirming the
   config-level key was not corrupted

**Expected Results**:

- First request returns HTTP 401 or 403
- Error message does not leak the invalid key value
- Second request (without override) returns HTTP 200 with a valid
  completion, proving config-level key is unaffected

**Notes**: To be filled later in the process.
