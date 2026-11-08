# vLLM-Omni Serving

Tech Preview integration of vLLM-Omni as a platform-shipped ServingRuntime on RHOAI, enabling
operators to deploy multimodal voice models from the dashboard without authoring YAML.

## Links

- **Strategy**: [RHAISTRAT-2493](https://issues.redhat.com/browse/RHAISTRAT-2493)
- **Source RFE**: [RHAIRFE-3014](https://issues.redhat.com/browse/RHAIRFE-3014)
- **Integration Epic**: [RHOAIENG-78709](https://issues.redhat.com/browse/RHOAIENG-78709)

## Test Plan

- [TestPlan.md](TestPlan.md) — Full test plan for vLLM-Omni serving integration

## Test Cases

- [test_cases/INDEX.md](test_cases/INDEX.md) — 56 test cases (24 P0, 26 P1, 6 P2)

## Changelog

### v1.10.0 (2026-08-11)

- Incorporated `CONSOLIDATED_FEEDBACK_v1.md` (verified against files on disk)
- **Voice fix**: 7 TCs updated: `"alloy"` → `"vivian"` (confirmed default from upstream Speech API)
- **Storage fix**: TC-DISC-003 and TC-RBAC-002 corrected to S3 (local MinIO on disconnected)
- **Modalities**: 5 TCs (TC-API-002/003, TC-E2E-002, TC-METR-002/003) — added
  `"modalities": ["text"]` to prevent audio data in text endpoint responses
- **New endpoint**: `/v1/audio/voices` (GET, P1) added to Section 4
- **Section 9.2**: Modalities parameter documented with options and rationale
- **Gaps**: 14 → **2** open (only SHA256 digest and `--load-format safetensors` OQ3 remain)
- **Quality score**: 9/10, Verdict: Ready
- Final: 56 TCs (24 P0, 26 P1, 6 P2)

### v1.8.0 (2026-08-11)

- Incorporated `CONSOLIDATED_FEEDBACK.md` (confirmed API schemas, model constants, S3 storage)
- **New TCs**: TC-PVC-001 (PVC storage validation, P1), TC-MCAR-001 (modelcar storage, P2)
- **Storage model correction**: 14 TCs updated from PVC to S3 references (all models are in S3;
  KServe storage initializer downloads at pod startup; MinIO on disconnected clusters)
- **Confirmed schemas**: `/v1/images/generations` — JSON with `data[].b64_json` base64 PNG/JPEG;
  `/v1/audio/speech` — binary WAV/MP3/FLAC with magic byte validation; voice discovery via
  `/v1/audio/voices`
- **Confirmed model constants**: all 5 model S3 paths, sizes (Qwen3-Omni 65.7GB, Qwen3-TTS
  4.2GB, Voxtral 7.5GB, OmniVoice 4.0GB, FLUX.2 22.1GB), GPU counts, timeouts
- **TC improvements**: TC-IMG-001 full JSON schema assertions; TC-TTS-001–005 voice discovery +
  magic byte validation; TC-METR-004 uses ≥15 threshold; TC-NEG-001/002 recovery steps added;
  TC-STAB-002 notes fixed; TC-SEC-004 HF_HUB_OFFLINE fixed
- **Gaps**: FP-3, NEW-18, FP-4 resolved; NEW-17 and NEW-1 partially resolved; 14 open
- **Quality score**: 9/10 (unchanged), Verdict: Ready
- Final: 56 TCs (24 P0, 26 P1, 6 P2)

### v1.6.0 (2026-08-11)

- Incorporated `FUTURE_PROOF_UPDATE.md` (template alignment + future-proofing + redundancy)
- **Template alignment**: Corrected probe architecture to actual 3-probe design (startupProbe
  40/30, readinessProbe 10/3, livenessProbe 15/3, no initialDelaySeconds); removed
  HF_HUB_OFFLINE=1 (not in template); corrected annotation locations (labels vs
  metadata.annotations vs spec.annotations); confirmed Prometheus `/metrics` path
- **Scope expansion**: OmniVoice (k2-fsa) and FLUX.2 loading/serving moved from Out to In scope
- **New TCs**: TC-TMPL-009 (securityContext), TC-TTS-005 (OmniVoice), TC-STAB-004 (OmniVoice
  stability), TC-IMG-001 (FLUX.2 /v1/images/generations)
- **Deleted TCs**: TC-SEC-003 (HF_HUB_OFFLINE not in template), TC-UI-003 (redundant with fixture)
- **Future-proofing**: OMNI_TEMPLATE_MAP (accelerator-agnostic), supported_accelerator_type
  fixture, deployment class grouping (~14 deployments/run)
- **Quality score**: 9/10 (unchanged), Verdict: Ready
- **Gaps**: 4 resolved (Prometheus path, 10-min script, OmniVoice scope, TTS validator), 4 new
  (OmniVoice/FLUX.2 model weights, /v1/images/generations schema, OmniVoice storage size), total 16
- Final: 54 TCs (24 P0, 25 P1, 5 P2)

### v1.4.0 (2026-08-11)

- Incorporated `TEST_PLAN_UPDATE_INSTRUCTIONS.md` (full parity review vs strategy +
  opendatahub-tests standards)
- Resolved 13 of 27 gaps; 16 remain open
- Quality score improved: 8/10 → 9/10 (grounding: 1/2 → 2/2 with inline strategy citations)
- Deleted 4 redundant TCs: TC-MEM-001, TC-PERF-003, TC-UI-001, TC-UI-002 (52 total)
- Elevated TC-E2E-003 to P0 (disconnected E2E aligns with P0 TC-DISC ship gate)
- Rewrote 38 original TCs from CLI (oc/curl) to openshift-python-wrapper / OpenAIClient patterns
- Added 6 inline strategy citations resolving all grounding gaps
- Added 5 new Out of Scope items (OmniVoice, FLUX.2, German TTS, per-GPU, safetensors OQ3)
- Added 6 new risks (perf utility blocking, CLI rewrite, Prometheus path, metric names, per-GPU,
  German TTS)
- Updated Section 9 with probe constants table, vLLM alignment patterns, shared import guidance
- Final: 52 TCs (25 P0, 22 P1, 5 P2)

### v1.2.0 (2026-08-11)

- Regenerated test cases: 13 new TCs, 11 updated TCs
- TC-UI-001/002/003 rewritten as API-level annotation checks (no browser)
- TC-E2E-001 fixed: Qwen3-Omni-30B-A3B (was Qwen3-TTS) for correct 3-stage init coverage
- TC-STAB-002 consolidated: single composite soak test covering stability + TTFB + GPU memory (AC-5)
- TC-SEC-001 expanded to all log levels (DEBUG/INFO/WARN/ERROR)
- TC-INIT-006 extended to cover partial stage failure (valid LLM + corrupt TTS artifact)
- TC-DISC priority corrected to P0 (strategy requirement)
- New categories: TC-NEG (2), TC-RBAC (4), TC-QUAL (1)
- New TCs: TC-TMPL-006/007/008, TC-STAB-003 (Qwen3-Omni), TC-SEC-004, TC-METR-004
- Total: 43 → 56 test cases (26 P0, 25 P1, 5 P2)

### v1.1.0 (2026-08-11)

- Updated with `TEST_PLAN_REVIEW.md` (opendatahub-tests repo standards review)
- Resolved 0 gaps; identified 18 new gaps (total: 27 open)
- Added 8 new endpoints/config entries to Section 4 (supportedModelFormats, runtime-version,
  support-status annotation, AC-2 three-stage init, 2 negative tests, biometric PII all levels,
  Prometheus count validation)
- Added 11 new risk rows to Section 8 (composite stability split, Qwen3-Omni stability gap,
  missing negative tests, RBAC absent, egress NetworkPolicy, partial stage failure, blind
  listening, fast templates, soak duration, PII scope, TC-DISC priority)
- Updated Section 9 (openshift-python-wrapper + OpenAIClient replace curl/browser; added
  constant.py/image_constants.py/fixture/soak env vars/pytest markers/file structure)
- Updated Section 2 (test levels/types/priorities with new negative paths, Qwen3-Omni stability,
  RBAC, egress NetworkPolicy)
- Updated Section 7 (RBAC per-role definitions; Upgrade/Migration note on PVC persistence)

### v1.0.0 (2026-08-06)

- Initial test plan

## Test Implementation

Automated tests will be implemented in the `odh-model-controller` component repository
(unit/integration tests for template and probe behavior) and the downstream E2E test repository
(API conformance, performance, dashboard integration).
