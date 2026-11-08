---
test_case_id: TC-INIT-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-INIT-001: Verify multi-stage initialization completes successfully

**Objective**: Confirm that the vLLM-Omni predictor pod completes
all three initialization stages (LLM, TTS, Code2Wav) and reaches
the Ready state.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- Qwen3-Omni-30B-A3B model weights (~86 GB) available in S3 models bucket (downloaded by KServe
  storage initializer at pod startup)
- GPU node with 2x GPUs (reference: NVIDIA H100 80GB) is available

**Test Steps**:

1. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=omni_serving_runtime, storage_uri=...,
   resources=OMNI_PREDICT_RESOURCES)`, deploy an InferenceService using the
   vLLM-Omni runtime with Qwen3-Omni-30B-A3B model.
2. Via `Pod.get_events()`, retrieve pod events during startup and verify
   initialization progress.
3. Via `Pod.get_logs()`, retrieve pod logs and verify sequential completion
   of each initialization stage (LLM, TTS, Code2Wav).
4. Via `pod_is_ready(pod=omni_pod_resource)` with `TimeoutSampler`
   (timeout=600s), wait for the pod to reach Ready state (expected ~206 s
   on 2x H100 80GB).

**Expected Results**:

- Pod logs show sequential completion of LLM stage, TTS stage,
  and Code2Wav stage
- Pod reaches `Ready` condition within approximately 206 seconds
  on 2x H100 80GB hardware
- No CrashLoopBackOff events occur during initialization
- The InferenceService status shows `Ready: True`

**Notes**: To be filled later in the process.
