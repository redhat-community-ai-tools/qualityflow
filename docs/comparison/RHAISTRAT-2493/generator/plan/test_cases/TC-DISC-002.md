---
test_case_id: TC-DISC-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-DISC-002: Verify RELATED_IMAGE resolution in disconnected environment

**Objective**: Confirm that the `RELATED_IMAGE` reference in the
ServingRuntime template correctly resolves to the mirrored vLLM-Omni
image digest in a disconnected environment.

**Preconditions**:

- Disconnected OpenShift cluster with mirrored vLLM-Omni image
- RHOAI operator CSV includes the vLLM-Omni image in
  `relatedImages`
- ImageContentSourcePolicy or ImageDigestMirrorSet is configured

**Test Steps**:

1. Via `ClusterServiceVersion.get()`, retrieve the RHOAI operator CSV.
   Access `.instance.spec.relatedImages` and find the entry where `.image`
   contains `vllm-omni`.
2. Assert the SHA256 digest in the RELATED_IMAGE matches the mirrored image
   digest.
3. Via `create_isvc(client=admin_client, name=..., namespace=...,
   runtime=omni_serving_runtime, storage_uri=...,
   resources=OMNI_PREDICT_RESOURCES)`, deploy an InferenceService. Access
   `omni_pod_resource.instance.spec.containers[0].image` and verify the
   container image resolves correctly.
4. Assert the pod uses the mirrored registry path, not the original
   `registry.redhat.io` path.

**Expected Results**:

- The RELATED_IMAGE digest matches the mirrored image digest
- The pod's container image reference resolves through the
  ImageContentSourcePolicy to the mirrored registry
- No image pull errors occur in the disconnected environment
- The pod reaches Ready state using the mirrored image

**Notes**: Run only on disconnected clusters (inverse of skip_on_disconnected).
