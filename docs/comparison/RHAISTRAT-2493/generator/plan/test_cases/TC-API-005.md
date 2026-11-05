---
test_case_id: TC-API-005
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-API-005: Verify /v1/chat/completions rejects malformed request

**Objective**: Confirm that the `/v1/chat/completions` endpoint
returns an appropriate error response when given a malformed request
body.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/chat/completions",
   body={"model": "Qwen3-Omni-30B-A3B"})`, send a request with missing
   `messages` field. Assert the response returns HTTP 422 or 400.
2. Via `OpenAIClient.post(endpoint="/v1/chat/completions",
   body={"model": "Qwen3-Omni-30B-A3B", "messages": "invalid"})`, send a
   request with invalid `messages` format. Assert the response returns HTTP
   422 or 400.
3. Via `OpenAIClient.post(endpoint="/v1/chat/completions",
   body={"model": "Qwen3-Omni-30B-A3B",
   "messages": [{"content": "test"}]})`, send a request with a message
   missing the `role` field. Assert the response returns HTTP 422 or 400.
4. Assert all error responses follow the OpenAI error format with `"error"`
   object containing `"message"`, `"type"`, and `"code"`.

**Expected Results**:

- Missing `messages` field: returns HTTP 422 or 400 with an error
  message indicating the required field
- Invalid `messages` format: returns HTTP 422 or 400 with a type
  validation error
- Missing `role` in message: returns HTTP 422 or 400 with a
  validation error for the messages array
- All error responses follow the OpenAI error format with
  `"error"` object containing `"message"`, `"type"`, and `"code"`

**Notes**: To be filled later in the process.
