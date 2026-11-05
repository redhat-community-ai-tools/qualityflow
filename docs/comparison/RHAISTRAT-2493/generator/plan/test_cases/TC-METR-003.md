---
test_case_id: TC-METR-003
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-METR-003: Verify metrics not exposed without --log-stats

**Objective**: Confirm that Prometheus metrics are not exposed when
the `--log-stats` flag is removed from the container args, verifying
that metric emission is correctly gated.

**Preconditions**:

- A modified vLLM-Omni ServingRuntime is deployed without the
  `--log-stats` flag in container args
- InferenceService is deployed and Ready
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `ServingRuntimeFromTemplate(...)` with container args that
   exclude `--log-stats`, deploy a modified vLLM-Omni ServingRuntime.
2. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=modified_serving_runtime, ...)`, deploy an InferenceService.
3. Via `pod_is_ready(pod=omni_pod_resource)`, wait for the pod to
   reach Ready state.
4. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "Qwen3-Omni-30B-A3B",
   "prompt": "Test without log-stats.", "max_tokens": 10,
   "modalities": ["text"]})`,
   send an inference request. Assert HTTP 200 (inference still works).
5. Via `pod.execute(command=["curl", "-s",
   "http://localhost:8080/metrics"])`, query the metrics endpoint.
   Count lines matching `^vllm`. Assert count == 0 or HTTP 404.

**Expected Results**:

- The metrics endpoint returns no `vllm_omni:*` or `vllm:*` metric
  families, or the endpoint returns HTTP 404
- The inference request itself still succeeds with HTTP 200
  regardless of metric emission status

**Notes**: pytest.param id: `test_omni_metrics_not_exposed_without_log_stats`.
Marker: `@pytest.mark.tier3`.
