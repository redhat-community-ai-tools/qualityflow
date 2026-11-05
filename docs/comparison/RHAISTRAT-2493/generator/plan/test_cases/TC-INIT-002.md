---
test_case_id: TC-INIT-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-INIT-002: Verify /health returns non-200 during initialization

**Objective**: Confirm that the `/health` endpoint returns a non-200
status code while any initialization stage (LLM, TTS, or Code2Wav)
is still loading.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- Model weights available in S3 models bucket (downloaded by KServe storage initializer at pod startup)
- GPU node with 2x GPUs (reference: NVIDIA H100 80GB) is available

**Test Steps**:

1. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=omni_serving_runtime, storage_uri=...,
   resources=OMNI_PREDICT_RESOURCES)`, deploy an InferenceService using the
   vLLM-Omni runtime.
2. Immediately after the container starts (before initialization completes),
   via `exec_http_probe(pod=omni_pod_resource,
   http_get={"path": "/health", "port": 8080, "scheme": "HTTP"})`, poll
   the `/health` endpoint at 5-second intervals.
3. Record the HTTP status code returned at each poll interval until the pod
   reaches Ready state.
4. Assert `/health` returns non-200 during initialization, transitioning
   to 200 only after all stages complete.
5. After `/health` transitions to 200, continue polling for 60 seconds
   to confirm stability — assert all responses remain HTTP 200 (no
   flapping back to non-200).

**Expected Results**:

- `/health` returns a non-200 HTTP status code (e.g., 503) while
  initialization stages are in progress
- The non-200 response persists until all three stages (LLM, TTS,
  Code2Wav) have completed loading
- The transition from non-200 to 200 occurs only after all stages
  report completion in the pod logs
- After transition to 200, `/health` remains stable at 200 for at
  least 60 seconds without flapping

**Notes**: This TC merges the former TC-INIT-003 (health stability check)
into a single flow: poll non-200 → observe transition to 200 → confirm
60-second stability.
