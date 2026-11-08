---
test_case_id: TC-TTS-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TTS-002: Verify /v1/audio/speech handles single-word prompt

**Objective**: Confirm that the `/v1/audio/speech` endpoint handles
single-word prompts without producing white noise or errors, per
the known edge case in vllm-omni#5659.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a
  TTS-capable model
- 2 warm-up requests have been sent

**Test Steps**:

1. Via `OpenAIClient.get(endpoint='/v1/audio/voices')`, discover available
   voices. Use "Vivian" if available, else the first voice in the list.
2. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "input": "Hello",
   "voice": <discovered_voice>, "response_format": "wav",
   "task_type": "CustomVoice", "language": "English"})`,
   send a TTS request with a single-word input.
3. Assert the response returns HTTP 200.
4. Assert the response `Content-Type` is `audio/wav` or `audio/x-wav`.
5. Assert the response body is non-empty and exceeds 44 bytes (WAV header minimum).
6. Compare the response body size against a multi-word prompt output
   (from TC-TTS-001) to confirm the single-word response is proportionally
   shorter, not inflated by noise artifacts.

**Expected Results**:

- Response HTTP status is 200
- Response `Content-Type` is `audio/wav` or `audio/x-wav`
- The output audio body is non-empty and exceeds 44 bytes (WAV header minimum)
- The audio body size is proportionally smaller than a multi-word
  response (not inflated by white noise artifacts)
- No error or degradation compared to the multi-word case beyond
  the expected shorter duration

**Notes**: To be filled later in the process.
