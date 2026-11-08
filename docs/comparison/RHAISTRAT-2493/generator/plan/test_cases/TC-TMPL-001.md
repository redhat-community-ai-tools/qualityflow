---
test_case_id: TC-TMPL-001
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-001: Verify vLLM-Omni ServingRuntime template exists in cluster

**Objective**: Confirm that the vLLM-Omni ServingRuntime template is
deployed to the cluster and available for use.

**Preconditions**:

- RHOAI operator is installed with odh-model-controller configured
  to include `vllm-omni-cuda-runtime-template` in
  `config/runtimes/kustomization.yaml`
- KServe is installed and operational

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve all ServingRuntime resources in the
   RHOAI namespace.
2. Assert a ServingRuntime with name containing `vllm-omni` exists in the
   returned list.
3. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object
   and access `.instance.metadata.name` and `.instance.spec.containers[0].image`.
4. Assert `spec.containers[0].image` uses a `@sha256:` digest reference
   (not a mutable tag). The image is injected via `RELATED_IMAGE` from the
   operator CSV — do NOT assert a hardcoded registry path. The actual
   registry namespace varies by release channel (`registry.redhat.io/rhaii/`
   for GA, `registry.redhat.io/rhaii-early-access/` for EA); the AIPCC
   team pushes to both separately.

**Expected Results**:

- A ServingRuntime resource with `vllm-omni` in its name exists in
  the RHOAI namespace
- The resource status does not show any error conditions
- The `spec.containers[0].image` field uses a `@sha256:` digest
  reference (injected via `RELATED_IMAGE` from operator CSV)
- The image string contains `vllm-omni` in the path (registry
  namespace is release-channel-dependent and must NOT be hardcoded)

**Notes**: pytest.param id: `test_omni_runtime_template_exists`.
