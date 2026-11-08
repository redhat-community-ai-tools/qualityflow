---
test_case_id: TC-TTS-005
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TTS-005: Verify OmniVoice (k2-fsa) loading and serving via /v1/audio/speech

**Objective**: Confirm that the OmniVoice (k2-fsa, 0.6B) model can be loaded
and served via the vLLM-Omni runtime, returning a valid audio response to a
/v1/audio/speech request without quality or latency thresholds.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- OmniVoice (k2-fsa, 0.6B) model weights available in S3 models bucket
  (downloaded by KServe storage initializer at pod startup)
- GPU node with 2x GPUs available

**Test Steps**:

1. Deploy an InferenceService with OmniVoice model via `create_isvc()` with
   2-GPU resources and S3 storage.
2. Wait for pod to reach Ready state — `create_isvc()` validates this.
3. Via `OpenAIClient.get(endpoint='/v1/audio/voices')`, discover available
   voices. Assert HTTP 200. Use "Vivian" if available, else first voice.
4. Send one `/v1/audio/speech` request via `OpenAIClient.post()`:

   ```json
   {"model": "OmniVoice-k2-fsa", "input": "Hello",
    "voice": <discovered_voice>, "response_format": "wav",
    "task_type": "CustomVoice", "language": "English"}
   ```

5. Assert HTTP 200 response.
6. Assert response Content-Type is `audio/wav` or `audio/x-wav`.
7. Assert response body is non-empty and exceeds 44 bytes (WAV header minimum).

**Expected Results**:

- InferenceService reaches Ready state after multi-stage initialization
- `GET /v1/audio/voices` returns HTTP 200 with available voice names
- `/v1/audio/speech` returns HTTP 200
- Response Content-Type is `audio/wav` or `audio/x-wav`
- Response body is non-empty and exceeds 44 bytes (WAV header minimum)
- No pod restarts during the test

**Notes**: To be filled later in the process.
No TTFB or E2E latency assertions — OmniVoice quality thresholds are deferred to
eval framework per strategy. pytest.param id: `test_omni_omnivoice_loading_serving`
@pytest.mark.vllm_omni
