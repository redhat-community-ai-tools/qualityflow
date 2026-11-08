---
test_case_id: TC-PVC-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-PVC-001: Verify vLLM-Omni inference with PVC-backed Qwen3-TTS

**Objective**: Confirm the vLLM-Omni runtime correctly serves inference requests
when model weights are mounted from a PVC (as opposed to S3 download).

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- Qwen3-TTS model weights (~4.2 GB) are pre-loaded on a PVC at /mnt/models
- GPU node with 1x GPU available (Qwen3-TTS is single-GPU)

**Test Steps**:

1. Deploy an InferenceService with `storage_uri` pointing to a PVC path
   (not an S3 URI) via `create_isvc(storage_uri="pvc://<pvc-name>/")`.
2. Wait for pod to reach Ready state — `create_isvc()` validates this.
3. Send one `/v1/audio/speech` request via `OpenAIClient.post()`:

   ```json
   {"model": "Qwen3-TTS-12Hz-1.7B-CustomVoice", "input": "Test",
    "voice": "vivian", "response_format": "wav"}
   ```

4. Assert HTTP 200 response.
5. Assert response Content-Type is `audio/wav` or `audio/x-wav`.
6. Assert response body is non-empty and exceeds 44 bytes (WAV header minimum).

**Expected Results**:

- InferenceService reaches Ready state via PVC-backed storage
- `/v1/audio/speech` returns HTTP 200 with valid WAV audio response
- No pod restarts during the test

**Notes**: To be filled later in the process.
This TC intentionally uses PVC storage. All other TCs use S3.
pytest.param id: `test_omni_pvc_qwen3_tts_inference`
Implementation: `vllm_omni/pvc/test_omni_pvc.py`
@pytest.mark.vllm_omni
