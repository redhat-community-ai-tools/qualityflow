---
test_case_id: TC-NEG-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-NEG-001: Verify actionable error when unsupported model used with --omni flag

**Objective**: Confirm that deploying an InferenceService with a non-omni model
(e.g., Qwen3-0.6B text-only) using the vLLM-Omni runtime produces an actionable error
message rather than silent CrashLoopBackOff.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster
- S3 path containing a standard (non-omni) text-only model (e.g., Qwen3-0.6B) is available
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `create_isvc()`, create an InferenceService with the vLLM-Omni runtime
   but specify a standard non-omni model URI (e.g., S3 path to Qwen3-0.6B
   text-only weights).
2. Via `pod_is_ready()`, poll pod status with a timeout of 6 minutes
   (12 * 30s probe failure threshold window).
3. Assert pod does not reach Ready state within the timeout.
4. Via `Pod.get_events()` and `Pod.get_logs()`, retrieve pod events and logs.
5. Assert the pod enters a Failed or CrashLoopBackOff state.
6. Assert pod logs or events contain an error message identifying the incompatible
   model or missing `--omni` configuration (error must not be a silent crash with no
   diagnostic text).
7. Deploy a VALID InferenceService with a correct omni-compatible model
   via `create_isvc()` with the standard vLLM-Omni runtime.
8. Via `pod_is_ready()`, assert the valid deployment reaches Ready state.
9. Via `OpenAIClient.post("/v1/audio/speech")`, assert HTTP 200 response.
10. Confirms the failed deployment did not corrupt the ServingRuntime state.

**Expected Results**:

- Pod enters Failed or CrashLoopBackOff state within the probe failureThreshold
  window (12 * 30s = 6 minutes)
- Pod logs contain an error message identifying the incompatible model or the
  missing/incorrect `--omni` configuration
- The error does not manifest as a silent crash with no diagnostic output
- Error surfaces within the probe failureThreshold window
- A subsequent valid deployment reaches Ready state and serves inference
  successfully, confirming no ServingRuntime state corruption

**Notes**: Applicable pytest markers: `@pytest.mark.tier3`.
