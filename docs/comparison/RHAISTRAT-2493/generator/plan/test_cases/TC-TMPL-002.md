---
test_case_id: TC-TMPL-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-002: Verify dashboard discovery annotations on ServingRuntime

**Objective**: Confirm that the vLLM-Omni ServingRuntime has all required labels and
annotations in the correct locations for RHOAI dashboard discovery and correct metadata,
including `runtime-version` and the `supportedModelFormats` spec field.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object.
2. Extract `metadata.labels` and assert:
   - `opendatahub.io/dashboard: 'true'` is present in labels (NOT in annotations)
3. Extract `metadata.annotations` and verify each of the following is present
   with the correct value:
   - `opendatahub.io/support-status: "unsupported"`
   - `opendatahub.io/recommended-accelerators: '["nvidia.com/gpu"]'`
   - `opendatahub.io/runtime-version` is present and non-empty
4. Extract `spec.annotations` and assert each of the following is present:
   - `opendatahub.io/kserve-runtime: 'vllm-omni'`
   - `prometheus.io/path: '/metrics'`
   - `prometheus.io/port: '8080'`
   - `monitoring.opendatahub.io/scrape: 'true'`
5. Via `ServingRuntime.get()`, extract `spec.supportedModelFormats` and assert
   `supportedModelFormats[0].name == "vLLM"`.

**Expected Results**:

- `opendatahub.io/dashboard: 'true'` is in `metadata.labels` (not metadata.annotations)
- `metadata.annotations` contains support-status, recommended-accelerators, and runtime-version
- `spec.annotations` contains kserve-runtime, prometheus.io/path, prometheus.io/port,
  and monitoring.opendatahub.io/scrape with the correct values
- `opendatahub.io/runtime-version` annotation is present and non-empty
- `spec.supportedModelFormats[0].name` equals `"vLLM"` (exact string, required for
  KServe dashboard model deployment to work via string match)
- `opendatahub.io/support-status` is `"unsupported"`, indicating Tech Preview status

**Notes**: pytest.param id: `test_omni_dashboard_discovery_annotations`. The exact
value of `opendatahub.io/runtime-version` must be updated once RHAII confirms the
shipped vLLM-Omni build version.
