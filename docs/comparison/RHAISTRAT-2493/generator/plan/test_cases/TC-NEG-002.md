---
test_case_id: TC-NEG-002
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-NEG-002: Verify deployment failure with insufficient GPU count (1 GPU)

**Objective**: Confirm that a vLLM-Omni deployment with only 1 GPU fails with a clear,
actionable error rather than silently crashing or hanging (the model requires 2x GPU
minimum).

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster
- A HardwareProfile specifying only 1 GPU is available or can be created
- Model weights available in S3 models bucket (downloaded by KServe storage initializer at pod startup)
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `create_isvc()`, create an InferenceService with the vLLM-Omni runtime
   and a HardwareProfile that specifies only 1 GPU (below the 2-GPU minimum).
2. Via `pod_is_ready()`, poll pod status with a timeout of 10 minutes.
3. Assert pod does not reach Ready state within the timeout.
4. Via `Pod.get_events()` and `Pod.get_logs()`, retrieve pod events and logs.
5. Assert the pod fails to reach Ready state.
6. Assert pod events or logs contain an error message indicating insufficient GPU
   resources (minimum 2 required); the error must not appear as OOMKilled or a
   silent crash.
7. Deploy a VALID InferenceService with the correct 2-GPU HardwareProfile
   via `create_isvc()`.
8. Via `pod_is_ready()`, assert the valid deployment reaches Ready state.
9. Via `OpenAIClient.post("/v1/audio/speech")`, assert HTTP 200 response.
10. Confirms the insufficient-GPU deployment did not leave orphaned resources.

**Expected Results**:

- Pod fails to reach Ready state
- Error message in pod events or logs indicates GPU count is insufficient
  (minimum 2 required)
- The error does not manifest as OOMKilled or a silent crash
- The failure is clearly distinguishable from a model incompatibility error
  (TC-NEG-001)
- A subsequent valid deployment (correct 2-GPU profile) reaches Ready state
  and serves inference successfully, confirming no orphaned resources remain

**Notes**: Applicable pytest markers: `@pytest.mark.tier3`.
