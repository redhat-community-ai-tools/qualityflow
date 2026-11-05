---
test_case_id: TC-DISC-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-DISC-001: Verify vLLM-Omni image mirroring to disconnected registry

**Objective**: Confirm that the vLLM-Omni container image can be
mirrored to a disconnected registry and used in an air-gapped
environment.

**Preconditions**:

- A disconnected OpenShift cluster with a local container registry
  is available
- The vLLM-Omni image (from `registry.redhat.io/rhaii/` or
  `registry.redhat.io/rhaii-early-access/` depending on release
  channel) has been mirrored using `oc mirror` or `skopeo copy`
- RHOAI operator is installed on the disconnected cluster

**Test Steps**:

1. Via `pod.execute(command=["skopeo", "inspect",
   "docker://<mirror-registry>/<rhaii-namespace>/vllm-omni-cuda-rhel9@<sha256-digest>"])`,
   verify the mirrored image exists in the disconnected registry.
2. Verify the image size is approximately 8.6 GB compressed.
3. Create an ImageContentSourcePolicy or ImageDigestMirrorSet to redirect
   pulls to the mirrored registry.
4. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=omni_serving_runtime, storage_uri=...,
   resources=OMNI_PREDICT_RESOURCES)`, deploy an InferenceService using the
   vLLM-Omni runtime. Access
   `omni_pod_resource.instance.status.containerStatuses[0].imageID` and
   assert the pod pulled from the mirrored registry.

**Expected Results**:

- The mirrored image is present in the disconnected registry
  with the correct SHA256 digest
- The pod successfully pulls the image from the mirrored registry
  (not from `registry.redhat.io`)
- The pod starts and initializes using the mirrored image

**Notes**: Run only on disconnected clusters (inverse of skip_on_disconnected).
