---
test_case_id: TC-TMPL-006
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-006: Verify supportedModelFormats declares name: vLLM

**Objective**: Confirm that the vLLM-Omni ServingRuntime's `supportedModelFormats`
field declares exactly `name: vLLM` (required for KServe dashboard model deployment
to work via exact string match).

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object.
2. Extract `spec.supportedModelFormats` from the returned object.
3. Assert the list contains exactly one entry.
4. Assert `supportedModelFormats[0].name == "vLLM"` (exact string comparison,
   case-sensitive).

**Expected Results**:

- `spec.supportedModelFormats` contains exactly one entry
- The single entry has `name: "vLLM"` (exact string, case-sensitive)
- No additional or missing format entries exist

**Notes**: To be filled later in the process.
