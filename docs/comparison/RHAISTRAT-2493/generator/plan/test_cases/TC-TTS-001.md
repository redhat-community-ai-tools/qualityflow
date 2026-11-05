---
test_case_id: TC-TTS-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TTS-001: Verify /v1/audio/speech returns audio for valid text input

**Objective**: Confirm that the `/v1/audio/speech` endpoint accepts
a valid text-to-speech request and returns an audio response.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a TTS-capable
  model (Qwen3-TTS or Voxtral-TTS)
- OpenShift Route or port-forward access is available
- 2 warm-up requests have been sent

**Test Steps**:

1. Call `GET /v1/audio/voices` via `OpenAIClient.get(endpoint='/v1/audio/voices')`.
   Assert HTTP 200. Store available voice names. Use "Vivian" if available, else
   the first voice in the list.
2. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
   "input": "Welcome to Red Hat OpenShift AI. This is a test of the text to speech capability.",
   "voice": <discovered_voice>, "response_format": "wav",
   "task_type": "CustomVoice", "language": "English"})`, send a TTS request
   with a standard text input.
3. Assert the response returns HTTP 200.
4. Assert the response `Content-Type` header is `audio/wav` or `audio/x-wav`.
5. Assert the response body is non-empty and exceeds 44 bytes (WAV header minimum).
6. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
   "input": "<20-word prompt from corpus>",
   "voice": <discovered_voice>, "response_format": "wav"})`, send a max-length
   prompt (20-word prompt from the fixed corpus). Assert the request completes
   without HTTP 504 Gateway Timeout (30s OpenShift Route default).

**Expected Results**:

- `GET /v1/audio/voices` returns HTTP 200 with a list of available voice names
- Response HTTP status is 200
- Response `Content-Type` is `audio/wav` or `audio/x-wav`
- The response body is non-empty and exceeds 44 bytes (WAV header minimum)
- No error messages are present in the response body
- Max-length prompt (20 words) completes without HTTP 504 Gateway
  Timeout within the 30s OpenShift Route default timeout

**Notes**: To be filled later in the process.
