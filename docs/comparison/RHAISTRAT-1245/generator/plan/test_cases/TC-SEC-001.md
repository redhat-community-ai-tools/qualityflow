---
test_case_id: TC-SEC-001
source_key: RHAISTRAT-1245
priority: P1
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_security.py
automation_function: TestGeminiSecurity::test_api_key_not_exposed
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-SEC-001: Gemini API key not exposed in pod specs or logs

**Objective**: Verify that Gemini API keys injected via
Kubernetes Secrets are not exposed in pod specifications,
container logs, or API responses.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider
  active
- `GEMINI_API_KEY` injected via Kubernetes Secret

**Test Steps**:

1. Inspect the OGX pod spec:
   `kubectl get pod <pod> -o yaml`
2. Verify `GEMINI_API_KEY` value is referenced from a
   Secret, not hardcoded in plaintext
3. Inspect OGX container logs:
   `kubectl logs <pod>`
4. Search logs for the API key value
5. Send a request to `/v1/providers` and inspect the
   response for any leaked key material
6. Send a chat completion request and inspect the response

**Expected Results**:

- Pod spec references the Secret by name, not the raw key
  value
- Container logs do not contain the Gemini API key value
- API responses (`/v1/providers`, chat completions) do not
  include the API key in any field
- The key is only used internally for authenticating to the
  Gemini API

**Notes**: To be filled later in the process.
