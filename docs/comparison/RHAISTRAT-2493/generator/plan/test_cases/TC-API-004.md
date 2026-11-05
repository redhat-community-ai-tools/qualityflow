---
test_case_id: TC-API-004
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-API-004: Verify /v1/completions rejects malformed request

**Objective**: Confirm that the `/v1/completions` endpoint returns
an appropriate error response when given a malformed request body.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"prompt": "test"})`, send a request with missing required `model`
   field. Assert the response returns HTTP 422 or 400.
2. Via `OpenAIClient.post(endpoint="/v1/completions", body={})`, send a
   request with an empty body. Assert the response returns HTTP 422 or 400.
3. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "nonexistent-model", "prompt": "test"})`, send a request
   with an invalid model name. Assert the response returns HTTP 404 or 400.
4. Assert all error responses follow the OpenAI error format with `"error"`
   object containing `"message"`, `"type"`, and `"code"`.

**Expected Results**:

- Missing `model` field: returns HTTP 422 or 400 with an error
  message indicating the required field
- Empty body: returns HTTP 422 or 400 with a validation error
- Invalid model name: returns HTTP 404 or 400 with an error
  indicating the model was not found
- All error responses follow the OpenAI error format with
  `"error"` object containing `"message"`, `"type"`, and `"code"`

**Notes**: To be filled later in the process.
