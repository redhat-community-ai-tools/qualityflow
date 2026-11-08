---
test_case_id: TC-EMB-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_embeddings.py
automation_function: TestGeminiEmbeddings::test_embedding_generation
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-EMB-001: Successful embedding generation via remote::gemini

**Objective**: Verify that embedding requests through the
`remote::gemini` provider return valid embedding vectors.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to `/v1/embeddings` with a
   sample input text
2. Inspect the response body for valid embedding data

**Expected Results**:

- Response status is HTTP 200
- Response body contains `data` array with at least one entry
- Each entry contains an `embedding` array of floating-point
  numbers
- The embedding vector has a consistent, non-zero dimension

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "input": "Sample text for embedding generation"
}
```

**Notes**: To be filled later in the process.
