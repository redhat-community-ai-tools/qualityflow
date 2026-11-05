---
test_case_id: TC-SEC-004
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-SEC-004: Verify egress NetworkPolicy blocks external registry access

**Objective**: Confirm that applying an egress NetworkPolicy restricting the vLLM-Omni
pod to PVC, K8s API, and Prometheus scrape only does not break inference while blocking
external model registry access.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready with model weights from S3
  (downloaded by KServe storage initializer at pod startup)
- `HF_HOME=/tmp/hf_home` is set in the container environment (redirects HF cache)
- A sample egress NetworkPolicy (as referenced in the TP guide) is available,
  restricting outbound traffic to: S3 storage, Kubernetes API, and Prometheus
  scrape endpoint only
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Via `NetworkPolicy.create()`, apply the sample egress NetworkPolicy to the
   namespace containing the vLLM-Omni pod.
2. Via `OpenAIClient.post("/v1/audio/speech")`, send a TTS inference request.
   Assert the response returns HTTP 200 (inference still works with S3-downloaded
   weights already loaded in the pod).
3. Via a test pod in the same namespace, attempt an outbound connection to an
   external host (e.g., `huggingface.co` or `registry.redhat.io`). Assert the
   connection times out or is explicitly rejected (confirming egress block is
   active).
4. Via `Pod.get_logs()`, verify no network download errors appear (confirming the
   egress NetworkPolicy blocks external access at the network level).

**Expected Results**:

- Inference via `/v1/audio/speech` succeeds (HTTP 200) with the egress
  NetworkPolicy applied
- Outbound connections to external hosts (e.g., huggingface.co,
  registry.redhat.io) fail or timeout, confirming the egress block is active
- vLLM-Omni pod logs show no network download attempts or failures
- Egress isolation is enforced at the network level by the NetworkPolicy

**Notes**: To be filled later in the process.
