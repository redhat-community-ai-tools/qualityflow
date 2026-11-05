---
test_case_id: TC-EMB-002
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_embeddings.py
automation_function: TestGeminiEmbeddings::test_embedding_missing_usage_handled
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-EMB-002: Embeddings handle missing usage statistics gracefully

**Objective**: Confirm that embedding requests complete without
error when Gemini's API omits `usage` statistics in the response,
which previously caused `AttributeError: 'NoneType' object has
no attribute 'prompt_tokens'` with the `remote::openai` provider.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to the embeddings endpoint with a
   sample input text
2. Inspect the response for the presence or absence of `usage`
   fields
3. Verify the request completes without error regardless of
   whether `usage` is present

**Expected Results**:

- Response status is HTTP 200
- Response body contains valid embedding vectors in the `data`
  array
- No `AttributeError` or server error (HTTP 500) occurs
- If `usage` is present, it contains valid token counts; if
  absent, the response still succeeds

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "input": "Test input for embedding with missing usage stats"
}
```

**Notes**: To be filled later in the process.
