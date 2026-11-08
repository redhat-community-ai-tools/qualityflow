---
test_case_id: TC-IMG-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-IMG-001: Verify FLUX.2 loading and serving via /v1/images/generations

**Objective**: Confirm that the FLUX.2 diffusion model can be loaded and served
via the vLLM-Omni runtime, returning a valid image response to a
/v1/images/generations request without quality or accuracy assertions.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed
- FLUX.2 model weights available in S3 models bucket (downloaded by KServe storage initializer
  at pod startup)
- GPU node with 2x GPUs available

**Test Steps**:

1. Deploy an InferenceService with FLUX.2 model via `create_isvc()` with
   2-GPU resources and S3 storage.
2. Wait for pod to reach Ready state — `create_isvc()` validates this.
3. Send one `/v1/images/generations` request via `OpenAIClient.post()`:

   ```json
   {"model": "FLUX.2-klein-4B", "prompt": "A simple red circle on white background",
    "size": "512x512", "seed": 42}
   ```

4. Assert HTTP 200 response.
5. Assert response Content-Type is `application/json`.
6. Assert response JSON has a `data` array with at least 1 element.
7. Assert `data[0].b64_json` is non-empty.
8. Decode `data[0].b64_json` from base64 and verify the first bytes are PNG
   (`89504e47`) or JPEG (`ffd8ff`) magic bytes.

**Expected Results**:

- InferenceService reaches Ready state
- `/v1/images/generations` returns HTTP 200
- Response Content-Type is `application/json`
- Response JSON contains `data` array with at least 1 element
- `data[0].b64_json` is non-empty and decodes to a valid PNG or JPEG image
- No pod restarts during the test

**Notes**: To be filled later in the process.
No image quality or accuracy assertions — FLUX.2 quality validation is RHAII
engine scope.
pytest.param id: `test_omni_flux2_image_generation`
@pytest.mark.vllm_omni
