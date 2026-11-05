---
test_case_id: TC-API-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-API-002: Verify /v1/completions accepts valid text completion request

**Objective**: Confirm that the `/v1/completions` endpoint accepts a
valid OpenAI-compatible text completion request and returns a
well-formed response.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a model
  loaded
- OpenShift Route or port-forward access is available

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "Qwen3-Omni-30B-A3B", "prompt": "The capital of France is",
   "max_tokens": 50, "modalities": ["text"]})`, send a text completion request.
2. Assert the response returns HTTP 200 with a JSON body.
3. Assert the response body contains `"object": "text_completion"` and a
   `"choices"` array with at least one entry.

**Expected Results**:

- Response HTTP status is 200
- Response body contains `"object": "text_completion"` and a
  `"choices"` array with at least one entry
- Each choice contains a `"text"` field with generated content
  and a `"finish_reason"` field
- The `"model"` field in the response matches the requested model
- The `"usage"` object contains `prompt_tokens`,
  `completion_tokens`, and `total_tokens`

**Test Data**:

```json
{
  "model": "Qwen3-Omni-30B-A3B",
  "prompt": "The capital of France is",
  "max_tokens": 50,
  "modalities": ["text"]
}
```

**Notes**: modalities: text-only output required to avoid audio data in second choice when using Qwen3-Omni.
