---
test_case_id: TC-API-003
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-API-003: Verify /v1/chat/completions accepts valid chat request

**Objective**: Confirm that the `/v1/chat/completions` endpoint
accepts a valid OpenAI-compatible chat completion request and
returns a well-formed response.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a model
  loaded
- OpenShift Route or port-forward access is available

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/chat/completions",
   body={"model": "Qwen3-Omni-30B-A3B",
   "messages": [{"role": "user", "content": "What is machine learning?"}],
   "max_tokens": 100, "modalities": ["text"]})`, send a chat completion request.
2. Assert the response returns HTTP 200 with a JSON body.
3. Assert the response body contains `"object": "chat.completion"` and a
   `"choices"` array with at least one entry.

**Expected Results**:

- Response HTTP status is 200
- Response body contains `"object": "chat.completion"` and a
  `"choices"` array with at least one entry
- Each choice contains a `"message"` object with `"role":
  "assistant"` and a non-empty `"content"` field
- The `"finish_reason"` field is present (e.g., `"stop"` or
  `"length"`)
- The `"usage"` object contains `prompt_tokens`,
  `completion_tokens`, and `total_tokens`

**Test Data**:

```json
{
  "model": "Qwen3-Omni-30B-A3B",
  "messages": [
    {"role": "user", "content": "What is machine learning?"}
  ],
  "max_tokens": 100,
  "modalities": ["text"]
}
```

**Notes**: To be filled later in the process.
