---
test_case_id: TC-STAB-003
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-STAB-003: Verify Qwen3-Omni-30B-A3B 50-turn session stability (no latency thresholds)

**Objective**: Confirm that Qwen3-Omni-30B-A3B sustains 50 consecutive voice turns
without pod restart or session reset — without the 350ms/1.2s latency thresholds that
apply only to TTS models.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with Qwen3-Omni-30B-A3B model
  (~86 GB, all 3 initialization stages complete; model weights available in S3
  models bucket, downloaded by KServe storage initializer at pod startup)
- GPU hardware: 2x GPUs (reference: NVIDIA H100 80GB)
- Fixed 50-prompt corpus available for sequential requests
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `pod_is_ready()`, confirm the pod is in Ready state before starting.
2. Record initial pod restart count via `get_restart_counts()`.
3. Via `OpenAIClient.post("/v1/audio/speech")`, send 50 sequential requests using
   the fixed prompt corpus, one at a time, waiting for each response before sending
   the next.
4. Assert each request returns HTTP 200 with a non-empty response body.
5. Record success count and failure count across all 50 requests.
6. After all 50 requests, via `get_restart_counts()`, assert the restart count is
   unchanged from the initial value.
7. Assert all 50 requests returned successful responses (100% success rate).

**Expected Results**:

- All 50 requests return successful responses (HTTP 200, non-empty body)
- Pod restart count remains 0 (unchanged) throughout the session
- No OOM events or session resets occur
- No TTFB or E2E latency assertions are applied (stability only — latency
  thresholds apply to TTS models, not Qwen3-Omni-30B-A3B)

**Notes**: Applicable pytest markers: `@pytest.mark.soak`,
`@pytest.mark.vllm_omni_nvidia_multi_gpu`. Latency thresholds (TTFB p95 <= 350ms,
E2E p95 <= 1.2s) are tested separately in TC-PERF-001 and TC-PERF-002 for TTS models.
This test case validates stability only for the full Omni model.
