---
test_case_id: TC-REG-001
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-REG-001: Verify existing vLLM CUDA template is unaffected

**Objective**: Confirm that the addition of the vLLM-Omni
ServingRuntime template does not modify or break the existing vLLM
CUDA ServingRuntime template.

**Preconditions**:

- RHOAI operator is installed with both the existing vLLM CUDA
  template and the new vLLM-Omni template enabled
- A working InferenceService using the standard vLLM CUDA runtime
  exists

**Test Steps**:

1. Via `ServingRuntime.get()`, list all ServingRuntimes and verify both
   vLLM CUDA and vLLM-Omni templates exist.
2. Via `ServingRuntime.get()`, retrieve the standard vLLM CUDA template
   and access `.instance.metadata.annotations` and
   `.instance.spec.containers[0].args` to verify it has not changed.
3. Assert the vLLM CUDA template's container args do NOT contain the
   `--omni` flag.
4. If an existing InferenceService on the vLLM CUDA runtime is available,
   via `OpenAIClient.post(endpoint="/v1/completions",
   body={"model": "<cuda-model>", "prompt": "Regression test prompt.",
   "max_tokens": 10})`, verify it still serves inference with HTTP 200.

**Expected Results**:

- The standard vLLM CUDA ServingRuntime template is present and
  unchanged
- The vLLM CUDA template does not contain `--omni` in its
  container args
- Existing InferenceService deployments on the vLLM CUDA runtime
  continue to serve inference with HTTP 200 responses
- The vLLM CUDA template annotations remain unchanged

**Notes**: To be filled later in the process.
