---
test_case_id: TC-TTS-003
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TTS-003: Verify /v1/audio/speech rejects empty and invalid input

**Objective**: Confirm that the `/v1/audio/speech` endpoint returns
appropriate error responses for empty or invalid request payloads.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "input": "",
   "voice": "Vivian", "response_format": "wav"})`, send a
   request with an empty `input` field. Assert the response returns HTTP
   400 or 422.
2. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
   "voice": "Vivian", "response_format": "wav"})`, send a request with a
   missing `input` field. Assert the response returns HTTP 400 or 422.
3. Via `OpenAIClient.post(endpoint="/v1/audio/speech", body={})`, send a
   request with an empty JSON body. Assert the response returns HTTP 400
   or 422.
4. Assert all error responses include a descriptive error message, not a
   server crash or 500 error.

**Expected Results**:

- Empty `input`: returns HTTP 400 or 422 with an error indicating
  the input text is required or empty
- Missing `input` field: returns HTTP 400 or 422 with a validation
  error for the required field
- Empty body: returns HTTP 400 or 422 with a validation error
- Error responses include a descriptive error message, not a
  server crash or 500 error

**Notes**: To be filled later in the process.
