---
test_case_id: TC-REG-002
source_key: RHAISTRAT-1245
priority: P1
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_regression.py
automation_function: TestGeminiRegression::test_other_providers_unaffected
last_updated: "2026-06-05"
upgrade_phase: both
---
# TC-REG-002: Other providers unaffected by remote::gemini addition

**Objective**: Verify that other existing providers in the
distribution (Bedrock, WatsonX, Azure, Vertex AI) remain
functional after adding `remote::gemini`.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` and at
  least one other cloud provider configured

**Test Steps**:

1. Send GET `/v1/providers` and verify all previously
   configured providers are still listed
2. Send a test inference request through a non-Gemini
   provider (e.g., `remote::openai` or another configured
   provider)
3. Verify the response is valid

**Expected Results**:

- `/v1/providers` lists all previously configured providers
  alongside `remote::gemini`
- Inference requests through non-Gemini providers return
  valid responses
- Provider activation patterns for other providers are
  unaffected

**Notes**: To be filled later in the process.
