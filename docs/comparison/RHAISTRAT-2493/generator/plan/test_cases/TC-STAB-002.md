---
test_case_id: TC-STAB-002
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-STAB-002: Verify composite 10-minute voice dialogue stability (TTFB + GPU memory + stability)

**Objective**: Confirm that a single 10-minute voice dialogue session simultaneously meets
stability (no OOM/restart), latency degradation (TTFB p95 at min-10 <= 1.25x min-1), and
GPU memory growth (< 15%) requirements — as AC-5 defines all three measured in the same
session.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with a TTS-capable model
  (model weights available in S3 models bucket, downloaded by KServe storage
  initializer at pod startup)
- GPU hardware: 2x NVIDIA H100 80GB
- 2 warm-up requests completed before recording baseline
- Fixed 50-prompt dialogue corpus available
- Prometheus is configured to scrape `vllm_omni:audio_ttfp_s` and
  `vllm:kv_cache_usage_perc{stage,replica}` metrics
- `OMNI_SOAK_DURATION` environment variable available (default: 600 seconds)

**Test Steps**:

1. Start Prometheus scraping for `vllm_omni:audio_ttfp_s` and
   `vllm:kv_cache_usage_perc{stage,replica}`.
2. Record baseline GPU memory at T=0 after 2 warm-up requests via
   `PrometheusClient.query("vllm:kv_cache_usage_perc")`.
3. Run `OMNI_SOAK_DURATION` seconds (default 600) of sequential
   `OpenAIClient.post("/v1/audio/speech")` requests using the fixed 50-prompt corpus,
   cycling through prompts as needed.
4. At minute 1, capture TTFB p95 from Prometheus:
   `ttfb_min1 = PrometheusClient.query_range("vllm_omni:audio_ttfp_s", end=T+60s)`.
5. At minute 10 (session end), capture TTFB p95:
   `ttfb_min10 = PrometheusClient.query_range("vllm_omni:audio_ttfp_s", end=T+600s)`.
6. Capture final GPU memory at T+600s via
   `PrometheusClient.query("vllm:kv_cache_usage_perc")`.
7. Via `get_restart_counts()`, verify no pod restarts occurred during the session.
8. Assert all three conditions:
   - `ttfb_min10 <= 1.25 * ttfb_min1` (latency degradation threshold)
   - GPU memory delta < 15% (growth from baseline to T+600s)
   - Restart count == 0 (stability)

**Expected Results**:

- TTFB p95 at minute 10 does not exceed 1.25x TTFB p95 at minute 1
- GPU memory growth from baseline to session end is less than 15%
- Pod restart count remains 0 throughout the session
- No OOM events are recorded
- All three assertions pass in the same single session

**Test Data**: (if applicable)

```text
OMNI_SOAK_DURATION=600
Prompt corpus: fixed 50-prompt set (cycling)
GPU baseline: T=0 after 2 warm-up requests
```

**Notes**: Applicable pytest markers: `@pytest.mark.soak`, `@pytest.mark.slow`,
`@pytest.mark.vllm_omni_nvidia_multi_gpu`. This composite TC is the primary AC-5
validation. It measures TTFB degradation, GPU memory growth, and restart count
simultaneously in a single session. Per-GPU memory distribution (GPU 0: ~60GB LLM;
GPU 1: ~6.6GB TTS+Code2Wav) deferred to engine-level testing (RHAII scope).
TC-STAB-002 validates aggregate GPU memory behavior only.
