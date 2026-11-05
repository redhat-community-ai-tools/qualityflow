---
test_case_id: TC-API-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-API-001: Verify /v1/models returns available model list

**Objective**: Confirm that the `/v1/models` endpoint returns a
valid OpenAI-compatible response listing the served model.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready
- OpenShift Route or port-forward access is available

**Test Steps**:

1. Via `OpenAIClient.get(endpoint="/v1/models")`, send a GET request to the
   `/v1/models` endpoint.
2. Assert the response status code is 200.
3. Assert the response body contains `"object": "list"` and a `"data"` array.
4. Assert the `"data"` array includes at least one entry with an `"id"`
   matching the `--served-model-name` configured in the ServingRuntime.

**Expected Results**:

- Response HTTP status is 200
- Response body contains a JSON object with `"object": "list"`
  and a `"data"` array
- The `"data"` array includes at least one entry with an `"id"`
  matching the `--served-model-name` configured in the
  ServingRuntime
- Each model entry contains `"object": "model"` and `"id"` fields

**Expected Response**:

```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen3-Omni-30B-A3B",
      "object": "model",
      "created": 1722902400,
      "owned_by": "vllm"
    }
  ]
}
```

**Notes**: To be filled later in the process.
