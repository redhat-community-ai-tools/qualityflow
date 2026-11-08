---
test_case_id: TC-TMPL-008
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-008: Verify all 3 vLLM-Omni template variants exist in kustomization.yaml

**Objective**: Confirm that stable, fast-1, and fast-2 vLLM-Omni runtime templates are
all present in the odh-model-controller kustomization.yaml resources, enabling
`filterFastResources` auto-hide behavior.

**Preconditions**:

- odh-model-controller repository is accessible (or a deployed version of the
  kustomization.yaml is retrievable from the cluster)
- The three template variant names are known:
  - `vllm-omni-cuda-runtime-template` (stable)
  - `vllm-omni-cuda-runtime-template-fast-1` (fast-1)
  - `vllm-omni-cuda-runtime-template-fast-2` (fast-2)

**Test Steps**:

1. Retrieve the odh-model-controller kustomization.yaml resources list (either
   from the repository or via cluster ConfigMap/resource inspection).
2. Assert `vllm-omni-cuda-runtime-template` is present in the resources list.
3. Assert `vllm-omni-cuda-runtime-template-fast-1` is present in the resources
   list.
4. Assert `vllm-omni-cuda-runtime-template-fast-2` is present in the resources
   list.

**Expected Results**:

- All 3 template variants are listed in the kustomization.yaml resources
- No variant is missing or misspelled
- The presence of all 3 enables the `filterFastResources` auto-hide behavior to
  function correctly

**Notes**: To be filled later in the process.
