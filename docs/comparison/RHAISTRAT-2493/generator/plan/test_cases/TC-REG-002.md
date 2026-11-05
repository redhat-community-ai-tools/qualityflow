---
test_case_id: TC-REG-002
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-REG-002: Verify existing vLLM ROCm/Gaudi/CPU/Spyre templates unaffected

**Objective**: Confirm that the addition of the vLLM-Omni
ServingRuntime template does not modify or break existing vLLM
accelerator-specific templates (ROCm, Gaudi, CPU, Spyre).

**Preconditions**:

- RHOAI operator is installed with the vLLM-Omni template and
  other existing vLLM accelerator templates enabled

**Test Steps**:

1. Via `ServingRuntime.get()`, list all vLLM-related ServingRuntimes in
   the RHOAI namespace.
2. For each non-Omni vLLM template (ROCm, Gaudi, CPU, Spyre), via
   `ServingRuntime.get()`, retrieve the template and access
   `.instance.spec.containers[0].args` and
   `.instance.spec.supportedModelFormats` to verify it exists and has not
   been modified.
3. Assert none of the existing templates contain the `--omni` flag in
   their container args.
4. Assert the `supportedModelFormats` in each existing template remain
   unchanged.

**Expected Results**:

- All previously existing vLLM accelerator templates are present
  and unchanged
- None of the existing templates include `--omni` in container
  args
- Template annotations, container images, and model format
  declarations are unmodified
- The vLLM-Omni template is an additive change only

**Notes**: To be filled later in the process.
