---
test_case_id: TC-INIT-006
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-INIT-006: Verify initialization failure detection for empty S3 path

**Objective**: Confirm that the vLLM-Omni pod fails gracefully when pointed
at an empty S3 path (no model files), without entering an indefinite pending
state, and surfaces an error in pod logs.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- An S3 path configured to point at empty prefix (no model files)

**Test Steps**:

1. Via `create_isvc()`, create an InferenceService pointing to the empty S3 prefix.
2. Via `pod_is_ready()`, poll pod status with a timeout of 15 minutes.
3. Assert pod does not reach Ready state within the timeout.
4. Via `OpenAIClient.get("/health")`, assert the response status is non-200.
5. Via `Pod.get_logs()`, verify logs contain an error message indicating the
   model path is empty or model file is not found.

**Expected Results**:

- Pod remains in NotReady state throughout
- `/health` returns a non-200 response
- Pod logs contain error messages indicating model files not found
- The pod enters CrashLoopBackOff or Error state rather than a perpetual
  initialization loop
- InferenceService status reflects the failure condition

**Notes**: Applicable pytest markers: `@pytest.mark.slow` (15-min timeout expected).
Partial stage failure (LLM weights present but talker/code2wav missing) is covered
by TC-NEG-001, which deploys a non-Omni model (Llama-3.2-1B) with the vLLM-Omni
runtime — the `--omni` flag causes the 3-stage pipeline to fail when talker_config
is absent from the model's config.json. This produces the same stage-specific error
as a thinker-only Qwen3-Omni checkpoint (see upstream vllm-omni issue #4223).
