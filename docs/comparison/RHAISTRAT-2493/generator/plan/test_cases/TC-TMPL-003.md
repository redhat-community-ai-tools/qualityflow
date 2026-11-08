---
test_case_id: TC-TMPL-003
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-003: Verify container args in ServingRuntime template

**Objective**: Confirm that the vLLM-Omni ServingRuntime template
specifies the correct container command and arguments for the vLLM-Omni engine.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object.
2. Access `.instance.spec.containers[0].command` and assert it equals
   `["vllm", "serve"]`.
3. Access `.instance.spec.containers[0].args` and assert the args list includes:
   - `--port=8080`
   - `--model=/mnt/models`
   - `--omni`
   - `--log-stats`
4. Access `.instance.spec.containers[0].env` and assert the environment variable
   `HF_HOME` is present with value `/tmp/hf_home`.

**Expected Results**:

- Container command is `["vllm", "serve"]`
- Container args include `--port=8080`, `--model=/mnt/models`,
  `--omni`, and `--log-stats`
- Environment variable `HF_HOME` is set to `/tmp/hf_home`
- The `--omni` flag is present, distinguishing this from standard
  vLLM templates

**Notes**: To be filled later in the process.
