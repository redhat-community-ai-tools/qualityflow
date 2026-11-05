---
test_case_id: TC-SEC-002
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-SEC-002: Verify safetensors-only model loading enforcement

**Objective**: Confirm that the vLLM-Omni runtime loads only
safetensors-format model weights and rejects pickle-format model
files, mitigating deserialization attack risk.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and Ready
- Model weights (downloaded from S3 to pod local storage) are in safetensors format

**Test Steps**:

1. Via `Pod.get_logs()`, retrieve pod logs and search for strings matching
   `safetensors`, `.bin`, or `pickle` to verify the model was loaded from
   safetensors files.
2. Via `pod.execute(command=["find", "/mnt/models/", "-name", "*.safetensors",
   "-o", "-name", "*.bin"])`, confirm the model directory at `/mnt/models` contains
   `.safetensors` files and no `.bin` (pickle) files.
3. If feasible in a test environment, place a `.bin` pickle file alongside
   the safetensors files and verify that the runtime loads from safetensors,
   not pickle.

**Expected Results**:

- Pod logs show model loading from `.safetensors` files
- No `.bin` or pickle-format files are loaded by the runtime
- The model directory contains `.safetensors` files as the primary
  weight format

**Notes**: To be filled later in the process.
