---
test_case_id: TC-AUTH-001
source_key: RHAISTRAT-1245
priority: P1
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_authentication.py
automation_function: TestGeminiPerRequestAuth::test_per_request_api_key_override
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-AUTH-001: Per-request API key override via x-ogx-provider-data

**Objective**: Confirm that setting `gemini_api_key` in the
`x-ogx-provider-data` header successfully overrides the
config-level Gemini API key for that specific request.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Primary `GEMINI_API_KEY` configured in the distribution
- A secondary valid Gemini API key available

**Test Steps**:

1. Send a POST request to `/v1/chat/completions` without the
   `x-ogx-provider-data` header (uses config-level key)
2. Verify the request succeeds
3. Send the same request with the `x-ogx-provider-data` header
   containing `{"gemini_api_key": "<SECONDARY-API-KEY>"}`
4. Verify the request succeeds using the secondary key

**Expected Results**:

- Both requests return HTTP 200
- The request with `x-ogx-provider-data` header authenticates
  using the secondary API key (verified by successful response
  when the secondary key is valid)
- The config-level key is not affected by the per-request
  override

**Test Data**:

```bash
PROVIDER_DATA=$(jq -cn --arg k "$SECONDARY_GEMINI_API_KEY" \
  '{"gemini_api_key":$k}')

curl -X POST "https://${OGX_ROUTE}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "x-ogx-provider-data: ${PROVIDER_DATA}" \
  -d '{
    "model": "<GEMINI-MODEL-ID>",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**Notes**: To be filled later in the process.
