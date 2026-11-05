---
test_case_id: TC-TTS-004
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TTS-004: Verify /v1/audio/speech with multiple TTS models

**Objective**: Confirm that the `/v1/audio/speech` endpoint produces
valid audio output with each supported TTS model (Qwen3-TTS and
Voxtral-TTS).

**Preconditions**:

- Two separate vLLM-Omni InferenceService deployments are available,
  one serving Qwen3-TTS and one serving Voxtral-TTS
- Both pods are in Ready state with 2 warm-up requests completed

**Test Steps**:

1. For each deployment, call `GET /v1/audio/voices` via
   `OpenAIClient.get(endpoint='/v1/audio/voices')`. Assert HTTP 200.
   Use "Vivian" if available, else first voice in the list.
2. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
   "input": "OpenShift AI enables data scientists to deploy models at scale.",
   "voice": <discovered_voice>, "response_format": "wav",
   "task_type": "CustomVoice", "language": "English"})`, send a TTS request
   to the Qwen3-TTS deployment. Assert the response returns HTTP 200 with
   a body exceeding 44 bytes (WAV header minimum).
3. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Voxtral-4B-TTS-2603",
   "input": "OpenShift AI enables data scientists to deploy models at scale.",
   "voice": <discovered_voice>, "response_format": "wav",
   "task_type": "CustomVoice", "language": "English"})`, send the same TTS
   request to the Voxtral-TTS deployment. Assert the response returns HTTP
   200 with a body exceeding 44 bytes.
4. Assert both responses have `Content-Type` header of `audio/wav` or
   `audio/x-wav`.

**Expected Results**:

- Both deployments return HTTP 200 for the `/v1/audio/speech` request
- Response `Content-Type` is `audio/wav` or `audio/x-wav` for both
- Both response bodies are non-empty and exceed 44 bytes (WAV header minimum)
- No error responses or 500 status codes from either deployment

**Notes**: To be filled later in the process.
