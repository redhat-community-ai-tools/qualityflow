---
test_case_id: TC-PROV-003
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_providers.py
automation_function: TestGeminiProviders::test_gemini_conditional_activation_with_key
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-PROV-003: Verify conditional provider activation with GEMINI_API_KEY

**Objective**: Confirm that the `remote::gemini` provider activates
only when the `GEMINI_API_KEY` environment variable is set.

**Preconditions**:

- OGX distribution deployed with `config.yaml` containing the
  conditional activation pattern
  `${env.GEMINI_API_KEY:+gemini-inference}`

**Test Steps**:

1. Deploy the OGX distribution with `GEMINI_API_KEY` set to a
   valid Gemini API key
2. Send GET `/v1/providers` and verify `remote::gemini` is listed
3. Redeploy the OGX distribution without the `GEMINI_API_KEY`
   environment variable (remove it from the ConfigMap or CR spec)
4. Wait for rollout completion and pod readiness
   (`kubectl rollout status` or equivalent)
5. Send GET `/v1/providers` and check the response

**Expected Results**:

- With `GEMINI_API_KEY` set: `/v1/providers` includes
  `remote::gemini` in the provider list
- Without `GEMINI_API_KEY`: `/v1/providers` does not include
  `remote::gemini` in the provider list
- No errors or crashes occur in either configuration

**Notes**: To be filled later in the process.
