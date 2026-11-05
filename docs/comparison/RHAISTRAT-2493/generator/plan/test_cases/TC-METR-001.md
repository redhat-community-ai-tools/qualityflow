---
test_case_id: TC-METR-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-METR-001: Verify vllm_omni:* metrics exposed with --log-stats

**Objective**: Confirm that vLLM-Omni-specific Prometheus metrics
(the `vllm_omni:*` family) are exposed when the `--log-stats` flag
is enabled in the ServingRuntime template.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready
- Template container args include `--log-stats`
- Prometheus is configured to scrape vLLM-Omni pods
- At least one TTS request has been processed to generate metrics

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/audio/speech",
   body={"model": "Qwen3-TTS",
   "input": "Generating metrics for test validation.",
   "voice": "vivian"})`, send a TTS request to generate metric data.
2. Via `exec_http_probe(pod=omni_pod_resource,
   http_get={"path": "/metrics", "port": 8080, "scheme": "HTTP"})`, query
   the metrics endpoint directly from within the pod network. Search the
   response for lines prefixed with `vllm_omni`.
3. Assert `vllm_omni:audio_ttfp_s` and `vllm_omni:e2e_request_latency_s`
   are present.
4. Via `prometheus.query("vllm_omni:audio_ttfp_s")`, query Prometheus for
   the same metrics and assert data is returned.
5. Via `PrometheusClient.query_metadata()`, count all distinct metric family
   names matching `vllm_omni:` prefix. Assert count >= 15 (strategy target:
   17; use >= threshold as exact count varies by midstream build version).
6. If count falls below threshold, list the metric family names found to
   identify missing families.

**Expected Results**:

- The metrics endpoint exposes metrics prefixed with `vllm_omni:`
- At minimum, `vllm_omni:audio_ttfp_s` and
  `vllm_omni:e2e_request_latency_s` are present with non-zero
  values after a TTS request
- Prometheus successfully scrapes and stores the `vllm_omni:*`
  metrics
- `vllm_omni:*` metric family count is >= 15 (strategy target: 17;
  upstream confirmed 6 pipeline + 7 audio + 4 transfer families)

**Notes**: The /metrics path on port 8080 is confirmed from the ServingRuntime
template `spec.annotations` (`prometheus.io/path: '/metrics'`,
`prometheus.io/port: '8080'`). This TC merges the former TC-METR-004 family
count assertion. The `vllm:*` family count (>= 30) is validated in
TC-METR-002.
