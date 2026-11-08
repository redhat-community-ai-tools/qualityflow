---
test_case_id: TC-PERF-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-PERF-001: Verify TTFB p95 <= 350 ms and E2E p95 <= 1.2 s for TTS models

**Objective**: Confirm that both TTFB p95 (<=350 ms) and E2E latency
p95 (<=1.2 s) are within thresholds for TTS models on reference
hardware at the OpenShift Route. Both metrics are measured from the
same set of 200+ sequential requests.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a
  TTS-capable model (Qwen3-TTS or Voxtral-TTS)
- GPU hardware: 2x NVIDIA H100 80GB
- 2 warm-up requests have been sent before measurement begins
- 1 concurrent user (no concurrent load)

**Test Steps**:

1. Send at least 200 sequential `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS", "input": <prompt>, "voice": "vivian"})`
   requests using the fixed prompt corpus (50 prompts, 15-word median,
   10-20 word uniform distribution, including single-word edge cases).
   Cycle through the corpus 4 times.
2. For each request, record the TTFB using the TTFB timing wrapper from
   `vllm_omni/utils.py` (time from request sent to first byte received
   at the route).
3. Calculate p95 TTFB and p95 E2E latency via the p95 calculator from
   `vllm_omni/utils.py` across all 200+ measurements.
4. Cross-reference with `prometheus.query("vllm_omni:audio_ttfp_s")` and
   `prometheus.query("vllm_omni:e2e_request_latency_s")` if available.
5. Assert TTFB p95 <= 350 ms AND E2E p95 <= 1.2 s.

**Expected Results**:

- TTFB p95 is <= 350 ms measured at the OpenShift Route
- E2E latency p95 is <= 1.2 s measured at the OpenShift Route
- Both measurements include ~50 ms network overhead from route-level
  measurement (RHAISTRAT-2493, NFR Latency)
- Both p95 values are calculated from at least 200 data points for
  statistical validity (RHAISTRAT-2493, AC-4)

**Notes**: This TC merges the former TC-PERF-002 (E2E latency). Both
metrics are measured from the same 200 sequential requests — the
`timed_tts_request()` utility records both TTFB and E2E for each request.
Applicable pytest markers: `@pytest.mark.slow`,
`@pytest.mark.vllm_omni_nvidia_multi_gpu`.
