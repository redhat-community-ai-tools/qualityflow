---
test_case_id: TC-METR-002
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-METR-002: Verify vllm:* metrics exposed with --log-stats

**Objective**: Confirm that the wrapped standard vLLM Prometheus
metrics (the `vllm:*` family) are exposed alongside vLLM-Omni
metrics when `--log-stats` is enabled.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready
- Template container args include `--log-stats`
- Prometheus is configured to scrape vLLM-Omni pods
- At least one inference request has been processed
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "Qwen3-Omni-30B-A3B",
   "prompt": "Test prompt for metrics.", "max_tokens": 10,
   "modalities": ["text"]})`,
   send an inference request to generate metric data.
2. Via `pod.execute(command=["curl", "-s",
   "http://localhost:8080/metrics"])`, query the metrics endpoint
   from within the pod. Filter output for lines prefixed with
   `vllm:`.
3. Assert `vllm:kv_cache_usage_perc` is present in the output with
   `stage` and `replica` labels.
4. Via `PrometheusClient.query_metadata()`, count all distinct metric family
   names matching `vllm:` prefix. Assert count >= 30 (strategy target: 32).
5. If count falls below threshold, list the metric family names found.

**Expected Results**:

- The metrics endpoint exposes metrics prefixed with `vllm:`
- `vllm:kv_cache_usage_perc` is present with `stage` and `replica`
  labels
- `vllm:*` metric family count is >= 30 (strategy target: 32;
  RHAISTRAT-2493, HLR-8)
- Both `vllm_omni:*` and `vllm:*` families are available from the
  same endpoint

**Notes**: pytest.param id: `test_omni_vllm_metrics_exposed`. Parametrize
with TC-METR-001 over metric prefix (`vllm_omni:*` vs `vllm:*`). This TC
now includes the family count assertion from the former TC-METR-004.
