---
test_case_id: TC-DISC-003
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-DISC-003: Verify model loading from local S3 without external network access

**Objective**: Confirm that vLLM-Omni loads model weights exclusively
from the local S3 store and requires no external network access at
inference time, validating the air-gapped deployment model.

**Preconditions**:

- Disconnected OpenShift cluster with no external internet access
- vLLM-Omni image mirrored to local registry
- Model weights available in local S3 (MinIO) on disconnected cluster
- `HF_HOME=/tmp/hf_home` is set in the container environment

**Test Steps**:

1. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=omni_serving_runtime, storage_uri=...,
   resources=OMNI_PREDICT_RESOURCES)`, deploy an InferenceService on the
   disconnected cluster using the vLLM-Omni runtime with S3-stored model weights (local MinIO).
2. Via `pod_is_ready(pod=omni_pod_resource)` with `TimeoutSampler`
   (timeout=600s), wait for the pod to reach Ready state.
3. Via `Pod.get_logs()`, retrieve pod logs and search for `loading model`
   to verify the model loads from `/mnt/models`.
4. Via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "Qwen3-Omni-30B-A3B",
   "prompt": "Disconnected inference test.", "max_tokens": 10})`, send an
   inference request. Assert the response returns HTTP 200.
5. Via `Pod.get_logs()`, verify no network errors, DNS failures, or download
   attempts in pod logs.

**Expected Results**:

- Pod reaches Ready state without any external network access
- Pod logs show model loading from `/mnt/models` (downloaded from local S3/MinIO)
- Inference request returns HTTP 200 with a valid response
- No DNS resolution failures, download errors, or network
  timeouts appear in pod logs
- Total air-gapped footprint (image + model weights) is
  approximately 95 GB

**Notes**: Run only on disconnected clusters (inverse of skip_on_disconnected).
