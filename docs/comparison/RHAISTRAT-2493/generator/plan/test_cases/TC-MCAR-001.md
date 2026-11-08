---
test_case_id: TC-MCAR-001
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-MCAR-001: Verify vLLM-Omni inference with OCI modelcar-backed Qwen3-TTS

**Objective**: Confirm the vLLM-Omni runtime correctly serves inference when
model weights are delivered via an OCI modelcar image.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- Qwen3-TTS OCI modelcar image is available: `quay.io/opendatahub/modelcar-vllm-omni:v1`
- GPU node with 1x GPU available

**Test Steps**:

1. Deploy an InferenceService with `storage_uri` pointing to the OCI modelcar
   URI via `create_isvc(storage_uri="oci://quay.io/opendatahub/modelcar-vllm-omni:v1")`.
2. Wait for pod to reach Ready state — `create_isvc()` validates this.
3. Send one `/v1/audio/speech` request via `OpenAIClient.post()`:

   ```json
   {"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "input": "Test",
    "voice": "vivian", "response_format": "wav"}
   ```

4. Assert HTTP 200 response.
5. Assert response Content-Type is `audio/wav` or `audio/x-wav`.
6. Assert response body is non-empty.

**Expected Results**:

- InferenceService reaches Ready state via OCI modelcar storage
- `/v1/audio/speech` returns HTTP 200 with valid audio response
- No pod restarts

**Notes**: To be filled later in the process.
pytest.param id: `test_omni_modelcar_qwen3_tts_inference`
Implementation: `vllm_omni/modelcar/test_omni_modelcar.py`
Register OMNI_MODELCAR_IMAGE = "quay.io/opendatahub/modelcar-vllm-omni:v1" with @sha256: digest
in image_constants.py once available.
@pytest.mark.vllm_omni
