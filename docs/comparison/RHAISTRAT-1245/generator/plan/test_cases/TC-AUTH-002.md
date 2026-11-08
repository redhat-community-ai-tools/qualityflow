---
test_case_id: TC-AUTH-002
source_key: RHAISTRAT-1245
priority: P1
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_authentication.py
automation_function: TestGeminiPerRequestAuth::test_invalid_per_request_api_key_errors
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-AUTH-002: Invalid per-request API key returns error

**Objective**: Verify that an invalid API key in the
`x-ogx-provider-data` header causes an authentication error
without affecting the config-level key.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid primary `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST to `/v1/chat/completions` with
   `x-ogx-provider-data: {"gemini_api_key": "invalid-key-12345"}`
2. Verify the request fails with an authentication error
3. Send a follow-up request without the `x-ogx-provider-data`
   header (using the config-level key)
4. Verify the follow-up request succeeds

**Expected Results**:

- The request with the invalid key returns a non-2xx HTTP
  error indicating authentication failure (exact status code
  is implementation-defined)
- The follow-up request using the config-level key returns
  HTTP 200 with a valid response
- The invalid per-request key does not corrupt or affect the
  config-level key

**Notes**: To be filled later in the process.
