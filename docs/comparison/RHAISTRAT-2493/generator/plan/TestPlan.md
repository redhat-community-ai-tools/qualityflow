---
feature: vllm_omni_serving
source_key: RHAISTRAT-2493
source_type: strat
status: In Review
author: Model Runtimes
components:
- Model Runtimes
additional_docs:
- TEST_PLAN_REVIEW.md
- TEST_PLAN_UPDATE_INSTRUCTIONS.md
- FUTURE_PROOF_UPDATE.md
- CONSOLIDATED_FEEDBACK.md
- CONSOLIDATED_FEEDBACK_v1.md
last_updated: '2026-08-12'
version: 1.10.0
reviewers: []
---
# vLLM-Omni Serving Test Plan

**Model Runtimes – Tech Preview vLLM-Omni Integration on RHOAI**

**Strategy**: [RHAISTRAT-2493](https://issues.redhat.com/browse/RHAISTRAT-2493)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates the Tech Preview integration of vLLM-Omni as a
platform-shipped ServingRuntime on Red Hat OpenShift AI (RHOAI). The
vLLM-Omni runtime enables operators to deploy multimodal voice models
(text-to-speech) from the RHOAI dashboard without authoring YAML,
consuming the RHAII-built container image from registry.redhat.io.

Testing focuses on the platform integration surface owned by Model
Runtimes: ServingRuntime template correctness, dashboard discovery via
annotations, multi-stage initialization probe fidelity, OpenAI API
conformance on the `/v1/audio/speech` endpoint, and voice-agent-grade
latency and session stability on the reference hardware profile
(2x H100 80GB). Engine-level model validation (quality, accuracy) is
RHAII scope and excluded from this plan.

### 1.2 Scope

#### In Scope (Model Runtimes Responsibilities)

- ServingRuntime template deployment and annotation-driven dashboard
  discovery
- Multi-stage initialization probe behavior (LLM, TTS, Code2Wav
  readiness gating)
- `/health` endpoint fidelity — must return non-200 until all stages
  complete
- OpenAI-compatible REST API conformance (`/v1/audio/speech`,
  `/v1/completions`, `/v1/chat/completions`, `/v1/models`)
- TTFB and E2E latency validation for TTS models (Qwen3-TTS,
  Voxtral-TTS) at the OpenShift Route
- 50-turn voice session stability and 10-minute dialogue stability
- GPU memory growth monitoring (< 15% delta over 10 minutes)
- Tech Preview labeling and "Limited support" badge (acceptance modal
  verified at API level via `opendatahub.io/support-status` annotation
  value = `"unsupported"`; browser rendering is not verified)
- Disconnected/air-gapped deployment via RELATED_IMAGE and
  relatedImages mirroring
- Prometheus metrics exposure (`vllm_omni:*` and `vllm:*` families
  gated by `--log-stats`)
- Biometric PII verification — no audio logged, cached, or persisted
  at any log level (DEBUG/INFO/WARN/ERROR)
- OmniVoice (k2-fsa, 0.6B): loading/serving validation + 50-turn
  session stability (no latency or quality thresholds)
- FLUX.2 (Diffusion): loading/serving validation + one inference
  request to `/v1/images/generations` (no quality or accuracy
  assertions)

#### Out of Scope (Other Teams)

- Engine-level model quality validation (RHAII scope: RHAISTRAT-2486
  through 2490)
- Gen AI Studio multimodal playground UX (RHAIRFE-3015)
- Dedicated `vLLM-Omni` model format with Dashboard API auto-select
  (deferred to GA under RHAISTRAT-2495)
- KEDA autoscaling documentation for vLLM-Omni
- Non-NVIDIA GPU validation (AMD ROCm, Intel Gaudi, CPU variants)
- Full-duplex `/v1/realtime` WebSocket endpoint (WIP upstream,
  vllm-omni PR #5727)
- LLMInferenceService (v1alpha2) integration
- OmniConnector / llm-d disaggregation (RHAIRFE-1016)
- Video generation (Wan2.2)
- GA support SLA and full QE sign-off
- Browser/UI automation (opendatahub-tests has zero browser automation
  capability; all dashboard-related verification is performed via
  API-level annotation checks only)
- OmniVoice quality thresholds — deferred to eval framework per
  strategy; loading/serving validation is now in scope
- FLUX.2 image quality/accuracy validation — RHAII engine scope;
  loading/serving validation is now in scope
- German TTS (ITZ) non-English loading/serving validation — deferred
  pending model availability and PM confirmation (OQ7); if added later,
  implement as a parametrized variant of TC-TTS-001 with a German text
  prompt
- Per-GPU memory distribution validation (GPU 0: ~60 GB LLM; GPU 1:
  ~6.6 GB TTS+Code2Wav) — deferred to engine-level testing (RHAII
  scope); platform tests validate aggregate memory behavior only
- `--load-format safetensors` flag validation in TC-TMPL-003 —
  contingent on RHAII confirming OQ3; tracked as an open item until
  resolved

### 1.3 Test Objectives

1. Verify that the vLLM-Omni ServingRuntime template is discoverable
   in the RHOAI dashboard with correct Tech Preview labeling and
   annotations.
2. Confirm that InferenceService deployment from the dashboard
   succeeds without authoring YAML and the predictor pod reaches
   Ready state after multi-stage initialization, and that
   `--served-model-name={{.Name}}` resolves correctly as validated
   by the `/v1/models` response.
3. Validate `/health` endpoint fidelity — returns non-200 until all
   three stages (LLM, TTS, Code2Wav) complete loading.
4. Verify OpenAI API conformance for `/v1/audio/speech`,
   `/v1/completions`, `/v1/chat/completions`, and `/v1/models`
   endpoints.
5. Confirm voice-agent-grade latency (TTFB p95 <= 350 ms, E2E p95
   <= 1.2 s) for TTS models on reference hardware at the OpenShift
   Route.
6. Validate session stability (50 consecutive voice turns) and
   long-session stability (10-minute dialogue without OOM, pod
   restart, or GPU memory growth > 15%).
7. Verify disconnected/air-gapped deployment via RELATED_IMAGE and
   Prometheus metrics exposure via `--log-stats`.

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — REST endpoint testing against the
  vLLM-Omni OpenAI-compatible API (`/v1/audio/speech`, `/health`,
  `/v1/completions`, `/v1/chat/completions`, `/v1/models`)
- **Functional Testing** — Multi-stage pipeline initialization (LLM,
  TTS, Code2Wav), dashboard runtime discovery via annotations,
  ServingRuntime template deployment, probe behavior validation
- **Performance Testing** — Voice-agent-grade latency validation
  (TTFB/E2E thresholds), 50-turn session stability, 10-minute
  dialogue stability, GPU memory growth monitoring
- **UI Testing** — RHOAI dashboard properties verified via API-level
  annotation checks; no browser automation (opendatahub-tests has
  zero browser automation capability)
- **Security Testing** — Biometric PII non-retention validation at
  all log levels (DEBUG/INFO/WARN/ERROR), pickle deserialization
  safety with safetensors-only enforcement, `HF_HOME=/tmp/hf_home`
  configuration validation, egress NetworkPolicy enforcement
  (RISK-002 mitigation)

### 2.2 Test Types

- **Positive Testing** — Valid voice inputs, expected TTS workflows,
  successful multi-stage init, dashboard deployment from template,
  correct metric emission
- **Negative Testing** — Invalid audio inputs, malformed requests,
  init stage failures (corrupt/missing model), broken pod health
  reporting, unsupported model with `--omni` flag, 1-GPU deployment
  attempt (requires 2x GPU minimum), partial stage failure (valid LLM
  stage with corrupt TTS artifact on PVC)
- **Boundary Testing** — 50-turn voice sessions, 10-minute dialogue
  duration, GPU memory limits (15% threshold), single-word prompts
  (vllm-omni#5659 regression guard), p95 latency at minute 10 vs
  minute 1
- **Regression Testing** — Existing vLLM CUDA/ROCm/Gaudi/CPU/Spyre
  templates remain unaffected, base OpenAI API compatibility
  preserved across standard endpoints

### 2.3 Test Priorities

- **P0 (Critical)** — Core functionality that gates Tech Preview
  shipment: ServingRuntime template dashboard discovery, multi-stage
  init completion and `/health` endpoint fidelity, OpenAI API
  conformance, RELATED_IMAGE reference in operator CSV for
  disconnected deployment, disconnected end-to-end inference
  (TC-E2E-003, elevated from P1), biometric PII ship gate confirmation
- **P1 (High)** — Performance and stability requirements for
  voice-agent-grade quality: TTFB p95 <= 350 ms and E2E p95 <= 1.2 s
  for TTS models, 50-turn session stability, 10-minute dialogue
  stability with GPU memory growth < 15%, Prometheus metrics emission
  (17 `vllm_omni:*` + 32 `vllm:*` families), Qwen3-Omni stability
  validation (stability only, without TTFB/E2E thresholds), RBAC
  enforcement per role, biometric PII non-retention at all log levels
  (DEBUG/INFO/WARN/ERROR), partial stage failure detection, egress
  NetworkPolicy enforcement (TC-E2E-003 moved to P0; P1 count reduced
  by 1)
- **P2 (Medium)** — Capability matrix documentation accuracy, blind
  listening evaluation for timbre drift (MANUAL — explicit evaluation
  criteria required), additional tuning flag validation, regression
  testing against existing vLLM templates, soak test parameterization
  via `OMNI_SOAK_DURATION` env var

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- **OpenShift**: TBD -- pin to a specific version once RHOAI EA1
  compatibility matrix is published (the strategy does not specify a
  minimum OpenShift version; "4.14+" is a placeholder based on current
  RHOAI support)
- **RHOAI**: TBD -- pin to the specific EA1 build version once the
  vLLM-Omni ServingRuntime template is included in a release candidate
  (the strategy targets EA1 but does not name a version number)
- **GPU Hardware**: At least 1 node with 2x GPUs (reference hardware:
  NVIDIA H100 80GB for performance baselines; functional tests are
  accelerator-agnostic)
- **Container Image**: `registry.redhat.io/rhaii/vllm-omni-cuda-rhel9` (GA)
  or `registry.redhat.io/rhaii-early-access/vllm-omni-cuda-rhel9` (EA),
  with SHA256 digest pin. Registry namespace is release-channel-dependent;
  AIPCC pushes to both registries separately. Tests must NOT hardcode the
  registry path — use the `RELATED_IMAGE` value from the operator CSV
- **Base Image**: RHEL 9.6 CUDA (AIPCC base)
- **Model Storage**: S3-compatible storage (AWS S3 or in-cluster MinIO) with all
  5 model weights pre-loaded. See Section 3.2 for sizes. The exception is
  TC-PVC-001 which tests PVC-backed storage explicitly.
- **KServe**: Required for InferenceService reconciliation
- **odh-model-controller**: With vLLM-Omni template enabled in
  `config/runtimes/kustomization.yaml`

### 3.2 Test Data Requirements

- **Prompt Corpus**: 50 English prompts (15-word median, 1-20 word range, including
  5 single-word edge cases per vllm-omni#5659). Saved as `prompts.json`. Voice
  discovery: call GET `/v1/audio/voices` before each TTS test suite; use "Vivian"
  if available, else first available voice. Store in class-scoped fixture.
- **Model Weights**: Stored in S3 models bucket; downloaded by KServe storage
  initializer at pod startup. On disconnected clusters, S3 is served by in-cluster
  MinIO with weights pre-loaded. The exception is TC-PVC-001 which tests PVC-backed
  storage explicitly:
  - Qwen3-Omni-30B-A3B (~86 GB at FP16) for multi-stage pipeline testing
  - Qwen3-TTS-12Hz-1.7B-CustomVoice (~4.2 GB) for TTS latency validation
  - Voxtral-4B-TTS-2603 (~7.5 GB) for TTS latency validation
  - OmniVoice-k2-fsa (~4.0 GB) for loading/serving validation and 50-turn
    session stability
  - FLUX.2-klein-4B (~22.1 GB) for loading/serving validation via
    `/v1/images/generations`
- **Sample InferenceService YAML**: Template-generated deployment
  manifest for reference
- **10-Minute Dialogue Script**: Scripted sequential `/v1/audio/speech`
  POST requests for long-session stability testing

### 3.3 Test Users

- **Cluster Admin**: For RHOAI installation, operator CSV updates,
  and cluster-level configuration
- **Data Science Project User**: For InferenceService deployment from
  the RHOAI dashboard, model serving operations
- **Monitoring User**: For Prometheus metrics scraping and dashboard
  access
- **Namespace-Scoped User**: For testing RBAC boundaries on
  ServingRuntime and InferenceService resources

---

## 4. API Endpoints Under Test

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `/health` | GET | Multi-stage readiness check — must return non-200 until LLM, TTS, and Code2Wav stages complete | P0 |
| `/v1/audio/speech` | POST | Text-to-speech inference — primary TP voice workflow endpoint; route timeout boundary assertion: max-length prompt must complete without HTTP 504 | P0 |
| `/v1/audio/voices` | GET | Voice discovery — returns available speaker names for TTS models; used to select voice dynamically (prefer "vivian" if available); called once per test class before TTS inference | P1 |
| `/v1/completions` | POST | Text completion — OpenAI API conformance | P0 |
| `/v1/chat/completions` | POST | Chat completion — OpenAI API conformance | P0 |
| `/v1/models` | GET | List available models — OpenAI API conformance; validates that `--served-model-name={{.Name}}` resolves correctly in the response | P0 |
| Startup probe (httpGet `/health` :8080) | GET | Kubernetes startup gating — `failureThreshold: 40`, `periodSeconds: 30`, max 1200 s startup window; runs before readiness/liveness probes | P0 |
| Readiness probe (httpGet `/health` :8080) | GET | Kubernetes readiness gating — `periodSeconds: 10`, `failureThreshold: 3`; no `initialDelaySeconds` (replaced by startup probe) | P0 |
| Liveness probe (httpGet `/health` :8080) | GET | Kubernetes liveness monitoring — `periodSeconds: 15`, `failureThreshold: 3`; no `initialDelaySeconds` | P1 |
| Prometheus metrics (`/metrics` :8080) | GET | Exposes 17 native `vllm_omni:*` + 32 wrapped `vllm:*` metric families when `--log-stats` is set. Confirmed from template: `prometheus.io/path: '/metrics'` in `spec.annotations`. | P1 |
| Prometheus metric family count validation (17 `vllm_omni:*` + 32 `vllm:*`) | GET | Exact family count assertion via prometheus session fixture | P1 |
| ServingRuntime `opendatahub.io/support-status` annotation (= `"unsupported"`) | Config | Tech Preview badge API-level verification; replaces TC-UI-001/002 browser checks | P0 |
| ServingRuntime dashboard-discovery annotations | Config | API-level discovery verification; replaces TC-UI-001/002 browser checks | P0 |
| AC-2 three-stage init sequence (Qwen3-Omni-30B-A3B) | Config/Runtime | Validates all 3 model stages (LLM, TTS, Code2Wav) complete before readiness | P0 |
| ServingRuntime `supportedModelFormats` | Config | Verify KServe model format match (`name: vLLM` required) | P1 |
| ServingRuntime `runtime-version` annotation | Config | Must be present and correctly valued once RHAII confirms the vLLM-Omni build version | P1 |
| Negative: unsupported model + `--omni` flag | REST/Config | Confirms expected failure mode for model/flag misconfiguration | P1 |
| Negative: single-GPU deployment | Config/Runtime | Confirms expected failure when GPU count is insufficient (requires 2x GPU) | P1 |
| Biometric PII at ALL log levels (DEBUG/INFO/WARN/ERROR) | Runtime/Security | Non-retention verification across all verbosity levels (P0 ship gate per strategy); TC-SEC-001 | P0 |
| `/v1/images/generations` | POST | FLUX.2 image generation — loading/serving validation only; assert HTTP 200 and non-empty image data; no quality or accuracy assertions | P1 |
| `metadata.labels: opendatahub.io/dashboard: 'true'` | Config | Must be in `metadata.labels` (not `metadata.annotations` or `spec.annotations`) | P0 |
| `spec.annotations` (kserve-runtime, Prometheus scrape config) | Config | Entries: `kserve-runtime`, `prometheus.io/path: '/metrics'`, `prometheus.io/port: '8080'`, `monitoring.opendatahub.io/scrape: 'true'` | P1 |
| Container command `["vllm", "serve"]` | Config | Verify container command split from args: `command: ["vllm", "serve"]` with args in separate field | P0 |
| `HF_HOME=/tmp/hf_home` environment variable | Config | Redirects HuggingFace cache to `/tmp/hf_home`; replaces removed `HF_HUB_OFFLINE=1` (not present in actual template) | P1 |
| `securityContext` | Config | Verify: `allowPrivilegeEscalation: false`, `privileged: false`, `runAsNonRoot: true`, `capabilities.drop: [ALL]` | P1 |

> **Remaining open gaps:**
>
> - `--load-format safetensors` flag in TC-TMPL-003 is contingent on RHAII confirming OQ3;
>   hold until resolved
> - SHA256 digest for vllm-omni-cuda-rhel9 not yet available (mitigated by
>   `--vllm-omni-runtime-image` CLI option)
>
> **Resolved gaps:** Prometheus metric families fully enumerated (17 `vllm_omni:*`: 6 pipeline +
> 7 audio + 4 transfer). AC-2 corrected to Qwen3-Omni-30B-A3B. Performance utilities spec'd
> (~110 lines in utils.py). TTS schema confirmed from upstream. See TestPlanGaps.md for full
> resolution details.

---

## 5. Test Cases

> **Note**: Test cases have been updated (v1.6.0-tc-2). See
> [test_cases/INDEX.md](test_cases/INDEX.md) for the complete index (51 test cases: 21 P0, 24 P1,
> 6 P2).

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| TC-TMPL (ServingRuntime Template) | 9 | 5 P0, 3 P1, 1 P2 |
| TC-INIT (Multi-Stage Initialization) | 3 | 1 P0, 2 P1 |
| TC-API (OpenAI API Conformance) | 5 | 5 P0 |
| TC-TTS (Text-to-Speech) | 5 | 2 P0, 3 P1 |
| TC-PERF (Performance) | 1 | 1 P1 |
| TC-STAB (Session Stability) | 4 | 4 P1 |
| TC-METR (Prometheus Metrics) | 3 | 2 P1, 1 P2 |
| TC-SEC (Security) | 3 | 2 P0, 1 P1 |
| TC-DISC (Disconnected/Air-Gapped) | 3 | 3 P0 |
| TC-REG (Regression) | 2 | 2 P2 |
| TC-E2E (End-to-End Scenarios) | 2 | 2 P0 |
| TC-NEG (Negative Scenarios) | 2 | 2 P1 |
| TC-RBAC (RBAC Authorization) | 4 | 4 P1 |
| TC-QUAL (Manual Quality Evaluations) | 1 | 1 P2 |
| TC-IMG (Image Generation) | 1 | 1 P1 |
| TC-PVC (PVC Storage) | 1 | 1 P1 |
| TC-MCAR (Modelcar Storage) | 1 | 1 P2 |
| **Total** | **51** | **21 P0, 24 P1, 6 P2** |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- `TC-TMPL` — ServingRuntime template deployment, annotations, and
  dashboard discovery
- `TC-INIT` — Multi-stage initialization, probe behavior, and
  `/health` endpoint fidelity
- `TC-API` — OpenAI API conformance (completions, chat, models,
  audio/speech)
- `TC-TTS` — Text-to-speech inference via `/v1/audio/speech`
- `TC-PERF` — Latency and performance validation (TTFB, E2E, RTF)
- `TC-STAB` — Session stability (50-turn) and long-session stability
  (10-minute dialogue)
- `TC-METR` — Prometheus metrics exposure and correctness
- `TC-SEC` — Security testing (biometric PII, pickle deserialization,
  egress policy)
- `TC-DISC` — Disconnected/air-gapped deployment validation
- `TC-REG` — Regression testing against existing vLLM templates
- `TC-E2E` — End-to-end user journey scenarios
- `TC-NEG` — Negative scenarios: unsupported model/flag combinations, insufficient
  hardware
- `TC-RBAC` — RBAC authorization testing per defined user role (Cluster Admin, DS
  Project User, Namespace-Scoped User, Monitoring User)
- `TC-QUAL` — Manual quality evaluations requiring human judges (e.g., blind timbre
  drift evaluation)
- `TC-IMG` — Image generation endpoint validation (/v1/images/generations)
- `TC-PVC` — PVC storage feature validation: deploy and serve inference using PVC-mounted
  model weights
- `TC-MCAR` — OCI modelcar storage feature validation: deploy and serve inference using OCI
  modelcar image

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
|----|----------|-------------------|----------|
| TC-E2E-001 | Deploy vLLM-Omni with Qwen3-Omni-30B-A3B and validate end-to-end TTS workflow | `/health`, `/v1/models`, `/v1/audio/speech`, Readiness probe, AC-2 three-stage init | P0 |
| TC-E2E-003 | Disconnected deployment to inference end-to-end | `/health`, `/v1/audio/speech`, Readiness probe | P0 (elevated from P1) |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| `/health` | TC-E2E-001, TC-E2E-003 |
| `/v1/audio/speech` | TC-E2E-001, TC-E2E-003 |
| `/v1/completions` | TC-API-002 |
| `/v1/chat/completions` | TC-API-003 |
| `/v1/models` | TC-E2E-001 |
| Readiness probe | TC-E2E-001, TC-E2E-003 |
| Liveness probe | — |
| Prometheus metrics | — |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

The vLLM-Omni image is consumed via the `RELATED_IMAGE` environment
variable from the OLM ClusterServiceVersion, enabling disconnected
deployment through the standard `relatedImages` mirroring pipeline.
Testing must validate:

- Image mirroring of the vLLM-Omni container (~8.6 GB compressed
  (RHAISTRAT-2493, Image Consumption Model)) to a disconnected registry
- Total air-gapped footprint validation (~95 GB (RHAISTRAT-2493, Image Consumption Model) including
  Qwen3-Omni-30B-A3B model weights at ~86 GB)
- `HF_HOME` redirected to `/tmp/hf_home`; disconnected clusters block
  external access at network level; connected clusters allow HF URI
  model loading by design
- `RELATED_IMAGE` resolution in the ServingRuntime template correctly
  references the mirrored image digest

### 7.2 Upgrade/Migration

This is a new ServingRuntime template with no existing deployments.
The strategy explicitly states "New runtime; no backwards
compatibility concerns." Existing vLLM CUDA/ROCm/Gaudi/CPU/Spyre
templates are unaffected.

PVC-mounted model weights must survive ServingRuntime pod restart
without re-download; PVC mount path `/mnt/models` ensures local
loading; `HF_HOME` redirected to `/tmp/hf_home`.
RBAC permissions are not modified by runtime version changes.
Upgrade path from Tech Preview to GA is out of scope for this test
plan version.

### 7.3 Performance/Scalability

Performance testing targets voice-agent-grade quality on the reference
hardware profile (2x H100 80GB, 1 concurrent user, warm model):

- **TTFB**: p95 <= 350 ms measured by `vllm_omni:audio_ttfp_s` at
  the OpenShift Route. Applies to TTS models (Qwen3-TTS,
  Voxtral-TTS) only; Qwen3-Omni measures stability, not latency.
- **E2E Latency**: p95 <= 1.2 s measured by
  `vllm_omni:e2e_request_latency_s` at the OpenShift Route. Same
  TTS-only applicability.
- **Latency Degradation**: TTFB p95 at minute 10 <= 1.25x TTFB p95
  at minute 1 (route-level measurement includes ~50 ms network
  overhead (RHAISTRAT-2493, NFR Latency)).
- **Session Stability**: 50 consecutive voice turns (15-word median
  prompts) without pod restart or session reset.
- **Long-Session Stability**: 10-minute scripted voice dialogue
  without OOM, pod restart, or GPU memory growth > 15% (measured by
  `vllm:kv_cache_usage_perc{stage,replica}`).
- **Measurement Baseline**: T=0 is when the server reports ready;
  2 warm-up requests (`--num-warmups 2` (RHAISTRAT-2493, Measurement Baseline)) before steady-state
  measurements. Minimum 200 requests (RHAISTRAT-2493, AC-4) for p95 statistical validity.

> **Probe architecture**: The startup probe gates container startup
> with a max 1200 s window (40 × 30 s); the readiness/liveness probes
> activate only after startup succeeds. Measured actual load time is
> ~206 s on 2× H100 80GB (RHAISTRAT-2493, Readiness and Health
> Probes) — well within the 1200 s startup window. No
> `initialDelaySeconds` is needed on readiness/liveness probes because
> the startup probe already enforces the gate.
>
> **Blocking implementation dependency**: Four net-new performance
> utilities must be implemented in `vllm_omni/utils.py` before
> TC-PERF-001/002 and TC-STAB-002 automation can begin: (1) TTFB
> timing wrapper, (2) p95 latency calculator, (3) time-windowed
> latency aggregator (minute-1 vs minute-10), (4) Prometheus
> cross-reference helper. No analogous infrastructure exists in
> opendatahub-tests; the closest analog (`measure_average_latency()`
> in mlserver tests) covers only sequential timing. These utilities
> must be implemented in sprint 1.
>
> **Per-GPU memory distribution**: Validation of per-GPU memory
> allocation (GPU 0: ~60 GB LLM; GPU 1: ~6.6 GB TTS+Code2Wav) is
> deferred to engine-level testing (RHAII scope). Platform-layer
> tests validate aggregate memory growth only via
> `vllm:kv_cache_usage_perc{stage,replica}`.

### 7.4 RBAC/Authorization

The vLLM-Omni ServingRuntime is namespace-scoped, following the same
RBAC model as existing RHOAI serving runtimes. Testing must verify:

- Namespace-scoped ServingRuntime RBAC boundaries (users cannot
  access runtimes in other namespaces)
- InferenceService creation permissions per user role (Data Science
  project user vs. cluster admin)
- Service account permissions for multi-stage model loading from PVC
- Container args are immutable at the template level (users cannot
  inject arbitrary flags like `--log-level DEBUG` via the dashboard)

> **Note**: These RBAC rules apply generically to all RHOAI serving
> runtimes; the TC-RBAC cases specifically confirm that the new
> vLLM-Omni runtime does not break or bypass existing RBAC
> enforcement.

Per-role enforcement (TC-RBAC-001 through TC-RBAC-004):

- **Cluster Admin**: full ServingRuntime and InferenceService control
  across namespaces
- **Data Science Project User**: InferenceService create/delete
  within own project; cannot modify ServingRuntime
- **Namespace-Scoped User**: read-only access to InferenceService
  status; cannot create or delete
- **Monitoring User**: Prometheus metrics read access only; no
  InferenceService or ServingRuntime access

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| RHAII vLLM-Omni image not published to registry.redhat.io in time for EA1 | High | Medium | Coordinate delivery timeline with RHAII by sprint 1; fallback: defer to EA2 with placeholder template |
| `/health` endpoint does not reflect all-stage readiness (returns 200 before TTS/Code2Wav load) | High | Medium | Validate probe fidelity with RHAII in sprint 1; if stage-unaware, escalate as P0 engine defect. AC-8 tests this directly |
| Voice quality regression — latency/stability below thresholds on reference hardware | Medium | Medium | Define quality gates before testing; joint testing cadence with RHAII; accept TP with documented gaps if close. Route-level ~50 ms overhead could push 350 ms threshold |
| Upstream single-word white noise issue (vllm-omni#5659) | Medium | High | AC-3 prompt corpus includes single-word edge cases; monitor upstream fix progress; document known limitation in TP release notes |
| CrashLoopBackOff takes ~10 minutes to surface broken deployments | Medium | Medium | Request per-stage `/health` progress reporting from RHAII; document expected startup time (~206 s (RHAISTRAT-2493, Readiness and Health Probes) on 2x H100 80GB) |
| H100 GPU hardware unavailability for validation | High | Medium | Confirm 2x H100 80GB availability by sprint 1; fallback to shared RHAII hardware or RHAII-provided test results |
| Pickle deserialization attack surface with 3 model artifacts (RISK-001, HIGH) | High | Low | Enforce safetensors-only model format; `HF_HOME=/tmp/hf_home` redirects HuggingFace cache; models pre-loaded via PVC from trusted registries only |
| Stage config opacity — no platform visibility into companion models loaded (RISK-002, MEDIUM) | Medium | Medium | `--log-stats` defaulted in template; sample egress NetworkPolicy in TP guide restricting pod to PVC, K8s API, and Prometheus scrape |
| Biometric PII exposure through voice data logging (RISK-003, MEDIUM) | Medium | Low | Verify no audio logging at INFO level; template must not set DEBUG log level; RHAII confirmation is TP ship gate |
| Composite stability test split — TC-STAB-002, TC-MEM-001, TC-PERF-003 measured in isolation; correlated failures (e.g., GPU memory spike causing latency degradation) undetectable | High | High | Replace isolated TCs with single composite 50-turn/10-min session test that records TTFB, GPU memory, and restart counts simultaneously |
| Qwen3-Omni stability not validated — strategy requires stability testing for Qwen3-Omni but no TC exists for this model | High | High | Add Qwen3-Omni stability test case (no TTFB/E2E thresholds; stability and restart-count only) |
| Missing negative tests: unsupported model + `--omni` flag, 1-GPU deployment | Medium | High | Add TC-NEG-001 (unsupported model + `--omni` flag returns actionable error) and TC-NEG-002 (1-GPU deployment rejected with clear error) |
| RBAC test cases absent — 4 RBAC requirements documented in Section 7.4 with no TC-RBAC category | High | High | Add TC-RBAC-001 through TC-RBAC-004 covering all four defined roles |
| Egress NetworkPolicy not tested — RISK-002 mitigation references network-level enforcement with no corresponding test case | Medium | Medium | Add egress NetworkPolicy enforcement test case in TC-SEC-* suite |
| Partial stage failure not tested — TC-INIT-006 covers empty PVC only; AC-8 requires detection of valid LLM + corrupt TTS artifact | Medium | Medium | Extend TC-INIT-006 or add TC-INIT-007 for partial stage failure scenario |
| Blind listening evaluation (P2) not documented as manual — no test artifact acknowledges this as a human evaluation requirement | Low | Medium | Explicitly mark as MANUAL test with evaluation criteria and evaluator instructions |
| Fast-template rollout and `filterFastResources` behavior not tested — 3 templates expected; auto-hide logic unvalidated | Medium | Medium | Add test for 3-template deployment and `filterFastResources` auto-hide behavior |
| Soak test duration hardcoded in test code — CI systems with different time budgets cannot tune the 10-minute window | Low | High | Parameterize via `OMNI_SOAK_DURATION` env var (default 600 s) and `OMNI_STABILITY_TURNS` (default 50) |
| Biometric PII tested at INFO level only — strategy requires validation at all log levels (DEBUG/INFO/WARN/ERROR) | Medium | High | Expand TC-SEC-001 to cover DEBUG, INFO, WARN, and ERROR log levels |
| TC-DISC tests misclassified as P1 — strategy designates disconnected RELATED_IMAGE resolution as P0 | High | High | Correct TC-DISC-* priority to P0; update pytest marker from tier2 to smoke/tier1 |
| Performance test utility creation is a blocking dependency — TTFB timing wrapper, p95 calculator, time-windowed aggregator, and Prometheus cross-reference helper are net-new; no analogous infrastructure exists in opendatahub-tests | High | Medium | Implement all four utilities in `vllm_omni/utils.py` in sprint 1 before TC-PERF-001/002 and TC-STAB-002 automation begins; closest analog (`measure_average_latency()` in mlserver tests) covers only sequential timing; do not duplicate shared utilities from `tests/model_serving/model_runtime/utils.py` |
| 38 test cases still describe steps using raw CLI (`oc get`, `curl`, `jq`, `grep`) and will fail opendatahub-tests repo standards review | Medium | High | All 38 TCs listed in TEST_PLAN_UPDATE_INSTRUCTIONS.md Section 3 must be rewritten to use `openshift-python-wrapper` / `OpenAIClient` patterns before implementation begins; use TC-TMPL-006, TC-NEG-001, TC-STAB-002, TC-E2E-001 as reference style |
| Prometheus metric family names — all 17 vllm_omni:* families enumerated from upstream; count assertions merged into TC-METR-001 (>=15) and TC-METR-002 (>=30) | Medium | Low | RESOLVED — family counts validated in TC-METR-001/002; individual metric names confirmed from upstream definitions.py |
| Per-GPU memory distribution (GPU 0: ~60 GB LLM; GPU 1: ~6.6 GB TTS+Code2Wav) not validatable at platform layer | Low | Medium | Deferred to engine-level testing (RHAII scope); TC-STAB-002 validates aggregate memory growth only; extend if per-GPU Prometheus labels become available |
| German TTS (ITZ) loading/serving validation has no TC — strategy says "validated for loading/serving only at TP" but no TC exists | Low | Medium | Deferred — added to Section 1.2 Out of Scope; if added later, implement as a parametrized variant of TC-TTS-001 with a German text prompt |
| OmniVoice (k2-fsa, 0.6B) model weights unavailability | Medium | Medium | Coordinate with RHAII; `skip_if_no_multi_gpu` session fixture prevents CI failure when model not available |
| FLUX.2 model weights unavailability | Medium | Medium | Coordinate with RHAII; TC-IMG-001 validates basic loading/serving only; skip if model absent |
| `/v1/images/generations` endpoint behavior unknown | Medium | Medium | TC-IMG-001 validates basic loading/serving only (HTTP 200 + non-empty image response); no quality/accuracy assertions |
| TTS output validation utility missing | Medium | High | Create `validate_tts_output()` in `vllm_omni/utils.py`; current `validate_audio_inference_output()` targets STT not TTS |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- **OpenShift Cluster**: TBD (see Section 3.1) with KServe and RHOAI
  operators installed
- **GPU Nodes**: At least 1 node with 2x GPUs (reference: NVIDIA H100
  80GB for performance baselines; functional tests are
  accelerator-agnostic)
- **Storage**: S3-compatible storage (AWS S3 or in-cluster MinIO) with all 5 model
  weights pre-loaded in the models bucket (Qwen3-Omni-30B-A3B: ~86 GB,
  Qwen3-TTS-12Hz-1.7B-CustomVoice: ~4.2 GB, Voxtral-4B-TTS-2603: ~7.5 GB,
  OmniVoice-k2-fsa: ~4.0 GB, FLUX.2-klein-4B: ~22.1 GB)
- **Container Image**: vLLM-Omni CUDA image from
  `registry.redhat.io/rhaii/vllm-omni-cuda-rhel9` (GA) or
  `registry.redhat.io/rhaii-early-access/vllm-omni-cuda-rhel9` (EA)
  with SHA256 digest pin in operator CSV `relatedImages`. Registry
  namespace is release-channel-dependent; do NOT hardcode
- **odh-model-controller**: With `vllm-omni-cuda-runtime-template`
  (stable + fast-1 + fast-2) enabled in
  `config/runtimes/kustomization.yaml`
- **Operator CSV**: `RELATED_IMAGE` entries for vLLM-Omni variants
- **Monitoring**: Prometheus configured to scrape vLLM-Omni pods for
  `vllm_omni:*` and `vllm:*` metric families
- **Cross-repo setup**: opendatahub-operator `RELATED_IMAGE` env vars
  and Build-Config entries are a release engineering pre-condition;
  TC-TMPL-005 validates the CSV `relatedImages` entry only. This
  cross-repo wiring must be completed before TC-TMPL-005 and TC-DISC
  tests can execute.
- **Runtime image injection**: The vLLM-Omni runtime image URI is
  injected via `--vllm-omni-runtime-image` CLI option or
  `VLLM_OMNI_RUNTIME_IMAGE` env var; `RuntimeTemplates.VLLM_OMNI_CUDA`
  is registered in `utilities/constants.py`.

**pytest marker assignments:**

| Priority | Markers |
|----------|---------|
| P0 (Critical) | `smoke`, `tier1` |
| P1 (High) | `tier2`, `gpu`, `slow` (add `soak` for 10-min session tests) |
| P2 (Medium) | `tier3` |

New markers required in `pytest.ini`: `vllm_omni`, `vllm_omni_nvidia_multi_gpu`,
`vllm_omni_amd_gpu` (future), `vllm_omni_gaudi` (future)

**Accelerator-agnostic design**: Accelerator type is resolved at runtime
via `supported_accelerator_type` session fixture. `OMNI_TEMPLATE_MAP`
maps `AcceleratorType → template name`. Functional tests (template,
init, API, TTS, security, disconnected, RBAC) use
`@pytest.mark.vllm_omni` (accelerator-agnostic). Performance tests
(TC-PERF, TC-STAB) use `@pytest.mark.vllm_omni_nvidia_multi_gpu`
(NVIDIA H100-specific thresholds).

**Deployment class grouping**: Class-scoped fixtures deploy each model
once per test class (~14 total deployments per full run). Destructive
tests (TC-INIT-005/006, TC-NEG-001/002) are isolated to separate test
classes. Soak tests (TC-STAB-002) are in a dedicated class with
extended timeout. Template-only tests (TC-TMPL-*) require no ISVC
deployment.

**Repository file structure:**

```text
tests/model_serving/model_runtime/vllm_omni/
├── conftest.py          # omni_serving_runtime, omni_inference_service,
│                        # omni_pod_resource, skip_if_no_multi_gpu,
│                        # vllm_omni_runtime_image, voice_discovery fixture
├── constant.py          # OMNI_TEMPLATE_MAP, OMNI_SERVING_ARGS,
│                        # OMNI_PREDICT_RESOURCES, OMNI_STARTUP_PROBE,
│                        # OMNI_READINESS_PROBE, OMNI_LIVENESS_PROBE,
│                        # OMNI_ACCELERATOR_IDENTIFIER, OMNI_TTS_QUERY,
│                        # OMNI_IMG_QUERY, OMNI_ISVC_TIMEOUTS,
│                        # model path constants (QWEN3_OMNI_MODEL_PATH, etc.)
├── image_constants.py   # vllm-omni-cuda-rhel9 with @sha256: digest pin
├── utils.py             # TTFB timing wrapper, p95 calculator,
│                        # time-windowed aggregation, Prometheus helper,
│                        # validate_tts_output (TTS-specific variant)
├── test_omni_template.py
├── test_omni_tts.py
├── test_omni_api.py
├── test_omni_image.py   # TC-IMG-001: FLUX.2 /v1/images/generations loading/serving
├── test_omni_metrics.py
├── test_omni_security.py
├── test_omni_disconnected.py
├── test_omni_regression.py
├── probes/
│   ├── conftest.py
│   ├── utils.py
│   └── test_omni_probes.py
├── fast/
│   └── test_omni_stability.py  # TC-STAB-*: 50-turn and 10-min sessions
├── s3/
│   └── test_omni_s3.py         # S3 storage integration (default path)
├── pvc/
│   └── test_omni_pvc.py        # TC-PVC-001: PVC-backed storage
└── modelcar/
    └── test_omni_modelcar.py   # TC-MCAR-001: OCI modelcar storage
```

### 9.2 Configuration

- **Container Args**: `--port=8080 --model=/mnt/models --omni
  --log-stats --served-model-name=<model-name>`
- **Template metadata labels**: `opendatahub.io/dashboard: "true"`,
  `opendatahub.io/ootb: "true"`
- **Template metadata annotations**: `opendatahub.io/support-status: "unsupported"`,
  `opendatahub.io/apiProtocol: 'REST'`
- **ServingRuntime metadata annotations**: `opendatahub.io/recommended-accelerators: '["nvidia.com/gpu"]'`,
  `opendatahub.io/runtime-version: '<version>'`,
  `opendatahub.io/support-status: "unsupported"`
- **ServingRuntime metadata labels**: `opendatahub.io/dashboard: "true"`
- **ServingRuntime spec.annotations**: `opendatahub.io/kserve-runtime: 'vllm-omni'`,
  `prometheus.io/port: '8080'`, `prometheus.io/path: '/metrics'`,
  `monitoring.opendatahub.io/scrape: 'true'`
- **Startup Probe**: `httpGet` on `/health` port 8080,
  `failureThreshold: 40`, `periodSeconds: 30` (max 1200 s startup window)
- **Readiness Probe**: `httpGet` on `/health` port 8080,
  `periodSeconds: 10`, `failureThreshold: 3` (no `initialDelaySeconds`)
- **Liveness Probe**: `httpGet` on `/health` port 8080,
  `periodSeconds: 15`, `failureThreshold: 3` (no `initialDelaySeconds`)
- **HardwareProfile**: Must specify 2+ NVIDIA GPUs (injected by
  HardwareProfile webhook)
- **Environment**: `HF_HOME=/tmp/hf_home` (redirects HuggingFace cache
  to `/tmp/hf_home`; `HF_HUB_OFFLINE=1` is NOT in the actual template)
- **Container Command**: `["vllm", "serve"]` with args in separate field
- **Security Context**: `allowPrivilegeEscalation: false`,
  `privileged: false`, `runAsNonRoot: true`, `capabilities.drop: [ALL]`
- **Model Format**: `supportedModelFormats` declares `name: vLLM`
  only
- **Warm-up**: 2 warm-up requests before steady-state performance measurements.
  `--num-warmups` is a benchmark client flag, not a server flag. Implement warm-up
  as 2 throwaway `OpenAIClient.post()` calls before steady-state measurements.
- **Modalities**: For Qwen3-Omni-30B-A3B text endpoint tests (TC-API-002/003,
  TC-METR-002/003), set `"modalities": ["text"]` in the request body
  to get text-only output. Without this, the response contains audio data in a
  second choice that breaks text validation. Options: `["text"]` (text only),
  `["audio"]` (audio only), `["text", "audio"]` (both). Default (omitted) =
  text + audio for Omni models.

**Per-model ISVC timeout table**:

| Model | Approx. Size | Recommended ISVC Timeout |
|-------|-------------|--------------------------|
| Qwen3-Omni-30B-A3B-Instruct | ~65.7 GB | 2700s (45 min) |
| Qwen3-TTS-12Hz-1.7B-CustomVoice | ~4.2 GB | 900s (default) |
| Voxtral-4B-TTS-2603 | ~7.5 GB | 900s (default) |
| OmniVoice-k2-fsa | ~4.0 GB | 900s (default) |
| FLUX.2-klein-4B | ~22.1 GB | 1200s (conservative) |

**Voice discovery pattern**: Before TTS test suites, call `GET /v1/audio/voices`.
Use "Vivian" if available, else first available voice. Store in class-scoped fixture.

`constant.py` entries required (in `tests/model_serving/model_runtime/vllm_omni/`):

- `OMNI_TEMPLATE_MAP` — dict mapping `AcceleratorType` to `RuntimeTemplates`:
  `{AcceleratorType.NVIDIA: RuntimeTemplates.VLLM_OMNI_CUDA}`; resolved at runtime via
  `supported_accelerator_type` session fixture; extensible to future accelerator types
  (replaces `VLLM_OMNI_TEMPLATE_NAME`)
- `OMNI_SERVING_ARGS` — `["--model=/mnt/models", "--omni", "--log-stats", "--port=8080",`
  `"--served-model-name={{.Name}}"]` (per-model content TBD — verify per model from
  implementation). **The `--omni` flag must always be present in `OMNI_BASE_DEPLOYMENT_CONFIG`.**
- `OMNI_PREDICT_RESOURCES` — 2-GPU resource request/limit spec
- `OMNI_STARTUP_PROBE` — `httpGet /health :8080`, `failureThreshold: 40`, `periodSeconds: 30`
- `OMNI_READINESS_PROBE` — `httpGet /health :8080`, `periodSeconds: 10`, `failureThreshold: 3` (no `initialDelaySeconds`)
- `OMNI_LIVENESS_PROBE` — `httpGet /health :8080`, `periodSeconds: 15`, `failureThreshold: 3` (no `initialDelaySeconds`)
- `OMNI_ACCELERATOR_IDENTIFIER` — defined in `vllm_omni/constant.py` (NOT imported from
  `vllm/constant.py`; self-contained per runtime isolation rule)
- `QWEN3_OMNI_MODEL_PATH` = `"Qwen3-Omni-30B-A3B-Instruct"`
- `QWEN3_TTS_MODEL_PATH` = `"Qwen3-TTS-12Hz-1.7B-CustomVoice"`
- `VOXTRAL_TTS_MODEL_PATH` = `"Voxtral-4B-TTS-2603"`
- `OMNIVOICE_MODEL_PATH` = `"OmniVoice-k2-fsa"`
- `FLUX2_MODEL_PATH` = `"FLUX.2-klein-4B"`
- `OMNI_TTS_QUERY` — TTS audio/speech request body with voice discovery pattern
  (`task_type: "CustomVoice"`, `language: "English"`, `response_format: "wav"`)
- `OMNI_IMG_QUERY` — image generation request body (`model`, `prompt`, `size: "512x512"`, `seed: 42`)
- `OMNI_ISVC_TIMEOUTS` — dict mapping model path to ISVC timeout in seconds
  (e.g., `{"Qwen3-Omni-30B-A3B-Instruct": 2700}`)

**Probe constants comparison** (vllm_omni vs vllm baseline):

| Constant | vllm_omni value | vllm baseline value |
|----------|----------------|---------------------|
| Startup probe `failureThreshold` | 40 | N/A |
| Startup probe `periodSeconds` | 30 | N/A |
| Readiness probe `periodSeconds` | 10 | 10 |
| Readiness probe `failureThreshold` | 3 | 12 |
| Liveness probe `periodSeconds` | 15 | 10 |
| Liveness probe `failureThreshold` | 3 | 12 |
| `initialDelaySeconds` | **Removed** (startup probe used instead) | 120 |

These values must be defined in `vllm_omni/constant.py` (parallel to `vllm/constant.py`).
Probe utilities (`get_probe`, `exec_http_probe`, `resolve_http_get`) must be defined in
`vllm_omni/probes/utils.py` (self-contained; NOT imported from `vllm/probes/utils.py` per
runtime isolation rule).

**Disconnected/S3 test markers**:

- Apply `@pytest.mark.skip_on_disconnected` to any test that requires
  S3 or an external container registry (cannot run in air-gapped
  environments).
- Apply the inverse marker (no `skip_on_disconnected`) to TC-DISC-*
  tests, which are designed to run only in disconnected environments.

**Implementation notes for TC pairs**:

- **Parametrize pattern**: TC-API-002+003, TC-API-004+005,
  TC-METR-001+002, TC-REG-001+002 must use
  `@pytest.mark.parametrize` with `indirect=True` (per
  `vllm/test_vllm_probes.py` reference) and `pytest.param` IDs.
- **pytest.param ID mapping**: Each of the 50 automatable TCs must
  have an explicit `pytest.param` ID entry in the parametrize table
  (see TEST_PLAN_UPDATE_INSTRUCTIONS.md Section 4 for the full
  mapping).
- **GWT docstrings**: All test functions must include a
  Given/When/Then docstring per the AGENTS.md requirement.
- **Markers for specific TCs**: soak tests require `@pytest.mark.soak`;
  10-minute tests require `@pytest.mark.slow`; P2 tests require
  `@pytest.mark.tier3`; TC-DISC-* tests require
  `@pytest.mark.skip_on_disconnected` inverse marker.

`image_constants.py` entry: `vllm-omni-cuda-rhel9` URI with `@sha256:` digest pin (digest TBD
pending image publication by RHAII)

Fixtures in `vllm_omni/conftest.py`:

- `omni_serving_runtime` — class-scoped; `ServingRuntimeFromTemplate` with omni template,
  `--omni` flag, omni probe timings
- `omni_inference_service` — class-scoped; ISVC with 2-GPU resources, PVC storage, `HF_HOME=/tmp/hf_home`
- `omni_pod_resource` — function-scoped; resolves predictor pod via `get_pods_by_isvc_label()`
- `skip_if_no_multi_gpu` — session-scoped; skips if cluster lacks 2x NVIDIA GPUs
- `vllm_omni_runtime_image` — session-scoped; reads `--vllm-omni-runtime-image` CLI option or
  `VLLM_OMNI_RUNTIME_IMAGE` env var

Soak test parameters (env vars):

- `OMNI_SOAK_DURATION` (default: 600 s) — controls 10-minute dialogue duration; CI can override
- `OMNI_STABILITY_TURNS` (default: 50) — controls 50-turn stability test; CI can override

### 9.3 Test Tools

- **Cluster Resource Operations**: `openshift-python-wrapper` (primary
  interface for all K8s/OpenShift interactions in test code):
  `ServingRuntimeFromTemplate` for runtime deployment, `create_isvc()`
  for InferenceService lifecycle, `get_pods_by_isvc_label()` for pod
  resolution, `pod_is_ready()` / `get_restart_counts()` for status
  checks, `pod.execute()` for in-pod commands. Use `oc` CLI only for
  operations outside the wrapper's scope.
- **Inference Requests**: `OpenAIClient` for all HTTP inference calls
  to `/v1/audio/speech`, `/v1/completions`, `/v1/chat/completions`,
  `/v1/models`, `/v1/images/generations` (replaces raw
  `curl`/`httpie`/`requests`)
- **Metrics Validation**: `prometheus` session fixture for Prometheus
  metric queries and cross-reference with `--log-stats` output
- **Performance Testing**: Custom `utils.py` (net-new, to be
  implemented): TTFB timing wrapper, p95 latency calculator,
  time-windowed latency aggregation (minute-1 vs minute-10),
  Prometheus cross-reference helper; Prometheus queries for
  `vllm_omni:audio_ttfp_s` and `vllm_omni:e2e_request_latency_s`
- **GPU Monitoring**: `nvidia-smi` (via `pod.execute()`), Prometheus
  `vllm:kv_cache_usage_perc{stage,replica}` metric
- **Dashboard Verification**: API-level ServingRuntime annotation
  checks (replaces browser-based dashboard; no browser automation)
- **Log Analysis**: `oc logs` / `pod.execute()` for biometric PII
  audit at all log levels (DEBUG/INFO/WARN/ERROR)
- **Shared utility imports**: Import `get_restart_counts`,
  `pod_is_ready`, `validate_audio_inference_output`, and
  `normalize_text_completion_response` from
  `tests/model_serving/model_runtime/utils.py`. Do NOT duplicate
  these in `vllm_omni/utils.py`. Note: `validate_audio_inference_output()`
  targets STT; a TTS-specific variant may be needed (track as open item).
- **Probe utilities**: `get_probe`, `exec_http_probe`, and
  `resolve_http_get` must be defined in `vllm_omni/probes/utils.py`
  (self-contained; NOT imported from `vllm/probes/utils.py` per
  runtime isolation rule). Define `get_kserve_container`,
  `exec_http_probe`, `resolve_http_get`, and `exec_omni_health_check`
  locally in `vllm_omni/probes/utils.py` — do NOT import from `vllm/`.
- **Base image validation**: Use `skopeo inspect` or pod label
  inspection to verify the RHEL 9.6 CUDA base image (AIPCC base)
  for TC-TMPL-008.

> **Open infrastructure gaps (must be resolved before test execution):**
>
> - OCP version not yet specified (TBD — awaiting RHOAI EA1 compatibility matrix)
> - RHOAI operator version not yet specified (TBD — awaiting EA1 build)
> - KServe operator version not yet specified
> - SHA256 digest for `vllm-omni-cuda-rhel9` not yet available (TBD — awaiting RHAII image publication)
> - ~~TTS query constant content~~ — RESOLVED: complete schema confirmed from upstream Speech API
>   docs (model, input, voice=vivian, response_format, speed, task_type, language, stream)
> - ~~`OMNI_SERVING_ARGS` per-model values~~ — RESOLVED: template args are model-agnostic; no
>   per-model overrides needed
> - ~~Prometheus metric names~~ — RESOLVED: all 17 `vllm_omni:*` families enumerated
>   (6 pipeline + 7 audio + 4 transfer)

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| TC-TMPL | 9 | 5 | 3 | 1 |
| TC-INIT | 3 | 1 | 2 | 0 |
| TC-API | 5 | 5 | 0 | 0 |
| TC-TTS | 5 | 2 | 3 | 0 |
| TC-PERF | 1 | 0 | 1 | 0 |
| TC-STAB | 4 | 0 | 4 | 0 |
| TC-METR | 3 | 0 | 2 | 1 |
| TC-SEC | 3 | 2 | 1 | 0 |
| TC-DISC | 3 | 3 | 0 | 0 |
| TC-REG | 2 | 0 | 0 | 2 |
| TC-E2E | 2 | 2 | 0 | 0 |
| TC-NEG | 2 | 0 | 2 | 0 |
| TC-RBAC | 4 | 0 | 4 | 0 |
| TC-QUAL | 1 | 0 | 0 | 1 |
| TC-IMG | 1 | 0 | 1 | 0 |
| TC-PVC | 1 | 0 | 1 | 0 |
| TC-MCAR | 1 | 0 | 0 | 1 |
| **Total** | **51** | **21** | **24** | **6** |

### 10.2 Endpoint Coverage

| Endpoint / Config Item | Test Cases | Coverage |
|------------------------|------------|----------|
| `/health` | TC-INIT-001, TC-INIT-002, TC-E2E-001, TC-E2E-003 | |
| `/v1/audio/speech` | TC-TTS-001, TC-TTS-002, TC-TTS-003, TC-TTS-004, TC-TTS-005, TC-STAB-001, TC-STAB-002, TC-STAB-003, TC-STAB-004, TC-E2E-001, TC-E2E-003 | |
| `/v1/completions` | TC-API-002, TC-API-004 | |
| `/v1/chat/completions` | TC-API-003, TC-API-005 | |
| `/v1/models` | TC-API-001, TC-E2E-001 | |
| `/v1/images/generations` | TC-IMG-001 | |
| `/v1/audio/voices` | TC-TTS-001 (voice discovery step) | |
| Readiness probe (httpGet `/health` :8080) | TC-TMPL-004, TC-E2E-001, TC-E2E-003 | |
| Liveness probe (httpGet `/health` :8080) | TC-TMPL-004, TC-INIT-005 | |
| Prometheus metrics (`/metrics` :8080) | TC-METR-001, TC-METR-002, TC-METR-003 | |
| Prometheus metric family count (17+32) | TC-METR-001 (vllm_omni >=15), TC-METR-002 (vllm >=30) | |
| ServingRuntime `opendatahub.io/support-status` | TC-TMPL-002 | |
| ServingRuntime dashboard-discovery annotations | TC-TMPL-002 | |
| AC-2 three-stage init (Qwen3-Omni-30B-A3B) | TC-INIT-001, TC-E2E-001 | |
| ServingRuntime `supportedModelFormats` | TC-TMPL-006, TC-TMPL-002 | |
| ServingRuntime `runtime-version` annotation | TC-TMPL-007, TC-TMPL-002 | |
| Negative: unsupported model + `--omni` flag | TC-NEG-001 | |
| Negative: single-GPU deployment | TC-NEG-002 | |
| Biometric PII at ALL log levels | TC-SEC-001 | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-06 | Initial test plan |
| 1.1.0 | 2026-08-11 | Updated with TEST_PLAN_REVIEW.md — 8 new Section 4 entries, 11 new risks, Section 9 tooling/structure, TC-DISC priority P1→P0 |
| 1.2.0 | 2026-08-11 | Test case regeneration — 13 new TCs (TC-TMPL-006/007/008, TC-NEG-001/002, TC-RBAC-001–004, TC-STAB-003, TC-SEC-004, TC-QUAL-001, TC-METR-004); rewrote TC-UI-001/002/003 as API-level; consolidated AC-5 into TC-STAB-002 composite; fixed TC-E2E-001 model; expanded TC-SEC-001 to all log levels; extended TC-INIT-006 to partial failure |
| 1.3.0 | 2026-08-11 | Merged TEST_PLAN_UPDATE_INSTRUCTIONS.md findings — added 5 out-of-scope items (OmniVoice, FLUX.2, German TTS, per-GPU distribution, --load-format safetensors); elevated TC-E2E-003 P1→P0; added 6 new risks (perf utilities blocking, 38 CLI TCs, Prometheus path, metric names, per-GPU, German TTS); added probe constants table; added cross-repo pre-condition and runtime image injection notes; added shared imports, base image inspection, parametrize/GWT/marker implementation notes; added inline strategy citations for 6 values; added --served-model-name validation note to objective 2 and /v1/models row; added route timeout assertion to /v1/audio/speech row; added RBAC vLLM-Omni specificity note; added performance utilities blocking dependency and per-GPU deferral notes to NFR |
| 1.3.0-tc | 2026-08-11 | Test case update: deleted TC-MEM-001, TC-PERF-003, TC-UI-001, TC-UI-002; elevated TC-E2E-003 to P0; rewrote 38 TCs from CLI to Python API patterns |
| 1.5.0 | 2026-08-11 | Template alignment: 3-probe design, HF_HOME, securityContext; OmniVoice + FLUX.2 in scope; TC-TMPL-009/TC-TTS-005/TC-STAB-004/TC-IMG-001 added; TC-SEC-003 and TC-UI-003 deleted |
| 1.6.0-tc-2 | 2026-08-11 | Consolidated feedback: TC-PVC-001 and TC-MCAR-001 added; 14 TCs updated PVC→S3; confirmed API schemas (WAV Content-Type, b64_json images, voice discovery); constant.py model paths and schemas added; TC-METR-004 threshold relaxed to >= 15; TC-SEC-004 HF_HUB_OFFLINE replaced with network-level enforcement; recovery steps added to TC-NEG-001/002; TC-STAB-002 notes updated |

---

**End of Test Plan**
