---
test_case_id: TC-REG-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_regression.py
automation_function: TestGeminiRegression::test_remote_openai_unaffected
last_updated: "2026-06-05"
upgrade_phase: both
---
# TC-REG-001: Existing remote::openai configurations unaffected

**Objective**: Verify that existing `remote::openai` provider
configurations continue to function correctly after the
`remote::gemini` provider is added to the distribution.

**Preconditions**:

- OGX distribution deployed with both `remote::openai` and
  `remote::gemini` providers available
- Valid OpenAI API key configured for `remote::openai`

**Test Steps**:

1. Send a POST to `/v1/chat/completions` using an OpenAI
   model configured via `remote::openai` provider
2. Verify the response is valid
3. Send a POST to the embeddings endpoint using an OpenAI
   model via `remote::openai`
4. Verify the embedding response is valid

**Expected Results**:

- Chat completion via `remote::openai` returns HTTP 200 with
  valid response structure
- Embeddings via `remote::openai` return HTTP 200 with valid
  embedding vectors
- No errors or regressions in `remote::openai` functionality
- The addition of `remote::gemini` does not interfere with
  other providers

**Notes**: To be filled later in the process.
