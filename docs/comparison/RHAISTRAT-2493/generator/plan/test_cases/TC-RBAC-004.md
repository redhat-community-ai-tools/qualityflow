---
test_case_id: TC-RBAC-004
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-RBAC-004: Verify Monitoring User has Prometheus metrics read-only access

**Objective**: Confirm that a Monitoring User can query Prometheus metrics for
`vllm_omni:*` and `vllm:*` families but cannot perform inference operations or modify
serving resources.

**Preconditions**:

- A test user with Monitoring User role is available
- vLLM-Omni InferenceService is deployed and emitting metrics with `--log-stats`
  enabled
- Prometheus is configured to scrape vLLM-Omni metrics
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Authenticate as the Monitoring User via
   `DynamicClient.authenticate(role="monitoring-user")`.
2. Via `PrometheusClient.query("vllm_omni:audio_ttfp_s")`, query Prometheus for
   the `vllm_omni:audio_ttfp_s` metric family. Assert data is returned (non-empty
   result).
3. Via `OpenAIClient.post("/v1/audio/speech")` without a valid inference token,
   attempt to send a TTS inference request directly. Assert the response returns an
   authentication failure (HTTP 401 or 403).
4. Via `ServingRuntime.get()`, attempt to retrieve the vLLM-Omni ServingRuntime
   as the Monitoring User. Assert the operation returns HTTP 403.

**Expected Results**:

- Prometheus metric queries for `vllm_omni:*` families succeed and return data
- Direct inference endpoint access without a valid inference token is rejected with
  HTTP 401 or 403
- ServingRuntime resource access returns HTTP 403 Forbidden
- The Monitoring User has metrics read access but cannot perform inference or
  modify serving resources

**Notes**: This test validates RBAC behavior specifically for the new vLLM-Omni
ServingRuntime. The same RBAC rules apply generically to all RHOAI serving runtimes;
this TC confirms the new runtime integrates correctly with existing RBAC enforcement.
