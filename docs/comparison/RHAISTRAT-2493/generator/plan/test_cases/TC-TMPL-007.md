---
test_case_id: TC-TMPL-007
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-007: Verify runtime-version annotation is present

**Objective**: Confirm that the `opendatahub.io/runtime-version` annotation is present
on the ServingRuntime and reflects the shipped vLLM-Omni version (value to be confirmed
by RHAII).

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object.
2. Extract `metadata.annotations` from the returned object.
3. Assert `opendatahub.io/runtime-version` key is present in annotations.
4. Assert the annotation value is non-empty (not `None`, not `""`).

**Expected Results**:

- `opendatahub.io/runtime-version` annotation is present on the ServingRuntime
- Annotation value is non-empty

**Notes**: To be filled later in the process. Exact value is TBD until RHAII confirms
the v0.26.0 build version. This test case must be updated with a value assertion once
the shipped version string is confirmed.
