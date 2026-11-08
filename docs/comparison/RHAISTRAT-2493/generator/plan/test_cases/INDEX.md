# Test Cases Index — vLLM-Omni Serving

**Parent Test Plan**: [TestPlan.md](../TestPlan.md)
**Strategy**: [RHAISTRAT-2493](https://issues.redhat.com/browse/RHAISTRAT-2493)

---

## Quick Stats

| Metric | Count |
|--------|-------|
| **Total Test Cases** | 51 |
| **P0 (Critical)** | 21 |
| **P1 (High)** | 24 |
| **P2 (Medium)** | 6 |

---

## ServingRuntime Template (TC-TMPL)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-TMPL-001](TC-TMPL-001.md) | Verify vLLM-Omni ServingRuntime template exists in cluster | P0 |
| [TC-TMPL-002](TC-TMPL-002.md) | Verify dashboard discovery annotations on ServingRuntime | P0 |
| [TC-TMPL-003](TC-TMPL-003.md) | Verify container args in ServingRuntime template | P0 |
| [TC-TMPL-004](TC-TMPL-004.md) | Verify 3-probe architecture: startupProbe, readinessProbe, and livenessProbe | P0 |
| [TC-TMPL-005](TC-TMPL-005.md) | Verify RELATED_IMAGE reference in operator CSV | P0 |
| [TC-TMPL-006](TC-TMPL-006.md) | Verify supportedModelFormats declares name: vLLM | P1 |
| [TC-TMPL-007](TC-TMPL-007.md) | Verify runtime-version annotation is present | P1 |
| [TC-TMPL-008](TC-TMPL-008.md) | Verify all 3 vLLM-Omni template variants exist in kustomization.yaml | P2 |
| [TC-TMPL-009](TC-TMPL-009.md) | Verify securityContext in ServingRuntime template | P1 |

## Multi-Stage Initialization (TC-INIT)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-INIT-001](TC-INIT-001.md) | Verify multi-stage initialization completes successfully | P0 |
| [TC-INIT-002](TC-INIT-002.md) | Verify /health non-200 during init, transition to 200, and 60s stability | P0 |
| [TC-INIT-005](TC-INIT-005.md) | Verify liveness probe detects pod health failure | P1 |
| [TC-INIT-006](TC-INIT-006.md) | Verify initialization failure detection for empty S3 path | P1 |

## OpenAI API Conformance (TC-API)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-API-001](TC-API-001.md) | Verify /v1/models returns available model list | P0 |
| [TC-API-002](TC-API-002.md) | Verify /v1/completions accepts valid text completion request | P0 |
| [TC-API-003](TC-API-003.md) | Verify /v1/chat/completions accepts valid chat request | P0 |
| [TC-API-004](TC-API-004.md) | Verify /v1/completions rejects malformed request | P0 |
| [TC-API-005](TC-API-005.md) | Verify /v1/chat/completions rejects malformed request | P0 |

## Text-to-Speech (TC-TTS)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-TTS-001](TC-TTS-001.md) | Verify /v1/audio/speech returns audio for valid text input | P0 |
| [TC-TTS-002](TC-TTS-002.md) | Verify /v1/audio/speech handles single-word prompt | P0 |
| [TC-TTS-003](TC-TTS-003.md) | Verify /v1/audio/speech rejects empty and invalid input | P1 |
| [TC-TTS-004](TC-TTS-004.md) | Verify /v1/audio/speech with multiple TTS models | P1 |
| [TC-TTS-005](TC-TTS-005.md) | Verify OmniVoice (k2-fsa) loading and serving via /v1/audio/speech | P1 |

## Performance (TC-PERF)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-PERF-001](TC-PERF-001.md) | Verify TTFB p95 <= 350 ms and E2E p95 <= 1.2 s for TTS models | P1 |

## Session Stability (TC-STAB)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-STAB-001](TC-STAB-001.md) | Verify 50-turn voice session stability | P1 |
| [TC-STAB-002](TC-STAB-002.md) | Verify composite 10-minute voice dialogue stability (TTFB + GPU memory + stability) | P1 |
| [TC-STAB-003](TC-STAB-003.md) | Verify Qwen3-Omni-30B-A3B 50-turn session stability (no latency thresholds) | P1 |
| [TC-STAB-004](TC-STAB-004.md) | Verify OmniVoice (k2-fsa) 50-turn session stability | P1 |

## Prometheus Metrics (TC-METR)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-METR-001](TC-METR-001.md) | Verify vllm_omni:* metrics exposed with --log-stats | P1 |
| [TC-METR-002](TC-METR-002.md) | Verify vllm:* metrics exposed with --log-stats | P1 |
| [TC-METR-003](TC-METR-003.md) | Verify metrics not exposed without --log-stats | P2 |

## Security (TC-SEC)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-SEC-001](TC-SEC-001.md) | Verify no audio content logged in pod logs (biometric PII) | P0 |
| [TC-SEC-002](TC-SEC-002.md) | Verify safetensors-only model loading enforcement | P0 |
| [TC-SEC-004](TC-SEC-004.md) | Verify egress NetworkPolicy blocks external registry access | P1 |

## Disconnected/Air-Gapped (TC-DISC)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-DISC-001](TC-DISC-001.md) | Verify vLLM-Omni image mirroring to disconnected registry | P0 |
| [TC-DISC-002](TC-DISC-002.md) | Verify RELATED_IMAGE resolution in disconnected environment | P0 |
| [TC-DISC-003](TC-DISC-003.md) | Verify model loading from PVC without network access | P0 |

## Regression (TC-REG)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-REG-001](TC-REG-001.md) | Verify existing vLLM CUDA template is unaffected | P2 |
| [TC-REG-002](TC-REG-002.md) | Verify existing vLLM ROCm/Gaudi/CPU/Spyre templates unaffected | P2 |

## End-to-End Scenarios (TC-E2E)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-E2E-001](TC-E2E-001.md) | Deploy vLLM-Omni with Qwen3-Omni-30B-A3B and validate end-to-end TTS workflow | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Disconnected deployment to inference end-to-end | P0 |

## Negative Scenarios (TC-NEG)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-NEG-001](TC-NEG-001.md) | Verify actionable error when unsupported model used with --omni flag | P1 |
| [TC-NEG-002](TC-NEG-002.md) | Verify deployment failure with insufficient GPU count (1 GPU) | P1 |

## RBAC Authorization (TC-RBAC)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-RBAC-001](TC-RBAC-001.md) | Verify Cluster Admin can manage ServingRuntime and InferenceService | P1 |
| [TC-RBAC-002](TC-RBAC-002.md) | Verify Data Science Project User cannot modify ServingRuntime | P1 |
| [TC-RBAC-003](TC-RBAC-003.md) | Verify Namespace-Scoped User has read-only InferenceService access | P1 |
| [TC-RBAC-004](TC-RBAC-004.md) | Verify Monitoring User has Prometheus metrics read-only access | P1 |

## Manual Quality Evaluations (TC-QUAL)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-QUAL-001](TC-QUAL-001.md) | Blind listening evaluation for timbre drift (MANUAL) | P2 |

## Image Generation (TC-IMG)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-IMG-001](TC-IMG-001.md) | Verify FLUX.2 loading and serving via /v1/images/generations | P1 |

## PVC Storage (TC-PVC)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-PVC-001](TC-PVC-001.md) | Verify vLLM-Omni inference with PVC-backed Qwen3-TTS | P1 |

## OCI Modelcar Storage (TC-MCAR)

| Test Case ID | Title | Priority |
|-------------|-------|----------|
| [TC-MCAR-001](TC-MCAR-001.md) | Verify vLLM-Omni inference with OCI modelcar-backed Qwen3-TTS | P2 |
