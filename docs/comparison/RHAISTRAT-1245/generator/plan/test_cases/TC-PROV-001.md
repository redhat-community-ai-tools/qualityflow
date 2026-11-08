---
test_case_id: TC-PROV-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_providers.py
automation_function: TestGeminiProviders::test_gemini_provider_listed
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-PROV-001: Verify remote::gemini provider listed in /v1/providers

**Objective**: Confirm that the `remote::gemini` provider appears
in the list of available providers returned by the OGX distribution.

**Preconditions**:

- RHOAI 3.5 EA2+ deployed with OGX distribution including
  `remote::gemini` provider
- `GEMINI_API_KEY` environment variable set in the
  `LlamaStackDistribution` CR or ConfigMap

**Test Steps**:

1. Send a GET request to the `/v1/providers` endpoint on the
   deployed OGX distribution
2. Parse the JSON response and inspect the list of providers

**Expected Results**:

- Response status is HTTP 200
- Response body contains a provider entry with
  `provider_type: remote::gemini`
- The provider entry indicates the Gemini inference provider
  is active

**Test Data**:

```bash
curl -s https://<OGX_ROUTE>/v1/providers | jq .
```

**Notes**: To be filled later in the process.
