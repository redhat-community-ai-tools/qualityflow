---
feature: vllm_omni_serving
source_key: RHAISTRAT-2493
status: Open
gap_count: 2
last_updated: '2026-08-11'
---
# Gaps — vLLM-Omni Serving

## Open Gaps (2 remaining)

### NEW-16: SHA256 digest for `vllm-omni-cuda-rhel9` not yet available

Image not yet published to `registry.redhat.io`. `image_constants.py` entry cannot be finalized.

**Mitigation**: `--vllm-omni-runtime-image` CLI option / `VLLM_OMNI_RUNTIME_IMAGE` env var
bypasses the hardcoded digest; tests run with any image URI until the digest is confirmed.

**Requires**: RHAII image publication to `registry.redhat.io`.

---

### NEWER-1: `--load-format safetensors` flag validation contingent on OQ3

TC-TMPL-003 expected container args list cannot include `--load-format safetensors` until RHAII
confirms whether vLLM-Omni supports the flag (strategy open question OQ3). If OQ3 does not land
before EA1, this validation step is skipped.

**Mitigation**: TC-SEC-002 validates safetensors-only model format via file inspection on the
PVC/S3 path; this is sufficient for the pickle deserialization risk mitigation even without
the server flag.

**Requires**: RHAII engineering confirmation of OQ3.

---

## Resolved Gaps

All other gaps are resolved. The table below is the authoritative record.

### Resolved from Strategy & Architecture Review

| Gap | Resolution |
|-----|-----------|
| `/v1/audio/speech` request/response schema | RESOLVED — complete parameter table from upstream Speech API docs: model, input, voice=vivian, response_format (wav/mp3/flac/pcm/opus), speed (0.25–4.0), task_type, language, instructions, max_new_tokens=2048, stream, stream_format. Response is binary audio with format-specific Content-Type and magic bytes. |
| `/v1/completions` and `/v1/chat/completions` scope | RESOLVED — vLLM-Omni adds `modalities` parameter: `["text"]` for text-only output, `["audio"]` for audio-only, `["text", "audio"]` for both. Default is text+audio for Omni models. Tests use `"modalities": ["text"]` for text endpoint validation. |
| Prometheus `/metrics` endpoint path | RESOLVED — confirmed from actual template `spec.annotations`: `prometheus.io/path: '/metrics'`, `prometheus.io/port: '8080'`. |
| OmniVoice quality thresholds deferred | CLOSED BY DESIGN — no quality evaluation criteria defined upstream. TC-TTS-005 + TC-STAB-004 cover loading/stability only. |
| German TTS (ITZ) test scope | CLOSED — out of TP scope per strategy: "All TP acceptance criteria are evaluated against English prompts and responses only." |
| Native model baseline not established | CLOSED — out of test plan scope; engineering/PM investigation decision, not a test case. |
| H100 GPU availability | RESOLVED — cluster provisioned with H100. `skip_if_no_multi_gpu` fixture prevents CI failure; OMNI_TEMPLATE_MAP makes tests accelerator-agnostic. |
| Performance test prompt corpus | RESOLVED — `prompts.json` generated with 50 English prompts (5 single-word edge cases per vllm-omni#5659, 45 in 14-19 word range, median 16 words). |
| 10-minute dialogue script | RESOLVED — prompt corpus cycled for `OMNI_SOAK_DURATION` seconds (default 600s); no separate script artifact needed. |
| Liveness probe / Prometheus E2E gap | CLOSED BY DESIGN — E2E coverage required for P0 endpoints only; P1 items have dedicated TCs. |

### Resolved from TEST_PLAN_REVIEW.md (v1.2.0 update)

| Gap | Resolution |
|-----|-----------|
| NEW-2: TC-E2E-001 model mismatch | TC-E2E-001 updated to Qwen3-Omni-30B-A3B |
| NEW-3: TC-UI browser automation | TC-UI-001/002/003 rewritten as API-level annotation checks |
| NEW-5: PII log-level coverage | TC-SEC-001 expanded to DEBUG/INFO/WARN/ERROR |
| NEW-6: Missing negative TCs | TC-NEG-001 and TC-NEG-002 added |
| NEW-7: AC-5 composite test | TC-STAB-002 is the composite AC-5 test |
| NEW-8: Qwen3-Omni stability | TC-STAB-003 added |
| NEW-9: TC-RBAC category absent | TC-RBAC-001 through TC-RBAC-004 added |
| NEW-10: Egress NetworkPolicy | TC-SEC-004 added |
| NEW-11: Partial stage failure | TC-INIT-006 extended |
| NEW-12: Blind listening manual | TC-QUAL-001 added |
| NEW-13: Fast template rollout | TC-TMPL-008 added |
| NEW-14: TC-DISC priority | TC-DISC elevated to P0 |
| NEW-15: Soak duration hardcoded | OMNI_SOAK_DURATION env var added |

### Resolved from FUTURE_PROOF_UPDATE.md + CONSOLIDATED_FEEDBACK

| Gap | Resolution |
|-----|-----------|
| NEW-1: Prometheus metric family names | RESOLVED — all 17 `vllm_omni:*` families enumerated from upstream `definitions.py` and `prometheus.py` (6 pipeline + 7 audio + 4 transfer families). TC-METR-004 asserts exact count == 17. |
| NEW-4: Performance test utilities | RESOLVED — full implementation plan with code specs (~110 lines, 5 functions: TTFB wrapper, p95 calculator, windowed aggregator, Prometheus helper, `validate_tts_output()`). No new pip dependencies. |
| NEW-17: TTS query constants | RESOLVED — complete request schema from upstream Speech API: model, input, voice=vivian, response_format, speed, task_type=CustomVoice, language=English, instructions, max_new_tokens=2048, stream. `OMNI_TTS_QUERY` constant defined. |
| NEW-18: Per-model serving args | RESOLVED — all model types use same base arg set; model type determines endpoint, not serving args. |
| FP-1: OmniVoice model in S3 | RESOLVED — model at `OmniVoice-k2-fsa/` (4 GB), confirmed in S3 bucket. |
| FP-2: FLUX.2 model in S3 | RESOLVED — model at `FLUX.2-klein-4B/` (22.1 GB), confirmed in S3 bucket. |
| FP-3: `/v1/images/generations` schema | RESOLVED — JSON response with `data[].b64_json` (base64 PNG/JPEG). Request: model, prompt, size, seed, n, negative_prompt, guidance_scale, num_inference_steps. TC-IMG-001 updated with full assertions. |
| FP-4: OmniVoice storage size | RESOLVED — ~4.0 GB confirmed. |
| NEWER-3: TTS output validator | RESOLVED — `validate_tts_output()` in `vllm_omni/utils.py` checks Content-Type, body > 44 bytes, WAV magic bytes. |
