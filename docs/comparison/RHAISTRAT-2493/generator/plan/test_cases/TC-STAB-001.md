---
test_case_id: TC-STAB-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-STAB-001: Verify 50-turn voice session stability

**Objective**: Confirm that the vLLM-Omni deployment handles 50
consecutive voice turns (TTS requests) without pod restart, session
reset, or error responses.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a
  TTS-capable model (model weights available in S3 models bucket,
  downloaded by KServe storage initializer at pod startup)
- GPU hardware: 2x GPUs (reference: NVIDIA H100 80GB)
- 2 warm-up requests completed

**Test Steps**:

1. Via `pod_is_ready(pod=omni_pod_resource)`, confirm the pod is in Ready
   state before starting.
2. Record initial pod restart count via
   `get_restart_counts(pod=omni_pod_resource)`.
3. Send 50 sequential `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS", "input": <prompt>, "voice": "vivian"})`
   requests using the prompt corpus (15-word median prompts, including
   single-word edge cases). Record the HTTP status code and response size
   for each request.
4. After all 50 requests, via `get_restart_counts(pod=omni_pod_resource)`,
   assert the restart count is unchanged from the initial value.

**Expected Results**:

- All 50 requests return HTTP 200 with valid audio output
- Pod restart count remains 0 throughout the test
- No session reset or connection errors occur between turns
- Pod remains in Ready state after the 50th turn

**Notes**: Applicable pytest markers: `@pytest.mark.soak`,
`@pytest.mark.vllm_omni_nvidia_multi_gpu`.
