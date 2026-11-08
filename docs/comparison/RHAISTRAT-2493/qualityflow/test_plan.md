# Test Plan

## **Tech Preview vLLM-Omni Serving on RHOAI with Voice-Agent-Grade Quality - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-3014](https://redhat.atlassian.net/browse/RHAIRFE-3014)
- **Feature Tracking:** [RHAISTRAT-2757](https://redhat.atlassian.net/browse/RHAISTRAT-2757)
- **Epic Tracking:** [RHAISTRAT-2493](https://redhat.atlassian.net/browse/RHAISTRAT-2493)
- **Feature Maturity:**
  - DP: N/A
  - TP: 3.6 EA1 RHOAI RELEASE
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Model Runtimes
- **Participating SIGs:** RHAII / OCTO Runtimes, Release Engineering, Documentation

**Document Conventions (if applicable):**

- **Omni:** A runtime that combines several model stages for multimodal output.
- **TTFB:** Time to first response byte measured at the external serving route.
- **RTF:** Audio generation time divided by generated audio duration.

### **Feature Overview**

Operators can deploy vLLM-Omni models from the model-serving dashboard without writing configuration files. This provides an integrated path for voice applications that otherwise require separately managed serving services. This plan covers Technology Preview deployment and English speech workflows with model-specific quality expectations.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Dashboard discovery and deployment, readiness gating, published images and TP documentation reviewed against the main feature.
    - Voice quality and long-session criteria compared with the source RFE.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* 
    - Integrated model deployment reduces the operational burden of assembling voice serving services.
  - *List the customer use cases identified:*
    - As an operator, I want to deploy voice models through the dashboard.
    - As an application developer, I want responsive speech across a long conversation.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Main criteria are proposed and require PM/Engineering validation before execution.
    - Unsupported-model diagnostics, exact shipped runtime version, safetensors flag support and performance harness ownership need answers.
    - September release-note comments include realtime and image endpoints while the main strategy excludes them; resolve scope before accepting documentation.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - AC-1: Runtime appears in the dashboard with preview support disclosure.
    - AC-2: Dashboard deployment reaches readiness only after multi-stage initialization.
    - AC-3: Fifty consecutive speech turns complete without HTTP errors, session reset or pod restart.
    - AC-4: Warm TTS route TTFB p95 is at most 350 ms and E2E p95 at most 1.2 s.
    - AC-5: Ten-minute dialogue has no OOM/restart and meets latency-drift and memory limits.
    - AC-6: Published runtime image is pinned by SHA256 in the release image inventory.
    - AC-7: Preview labeling and capability documentation agree with the supported release.
    - AC-8: Failed model stages keep readiness false and health unsuccessful.
  - *Note any gaps or missing criteria:* 
    - See Testability for unresolved source conflicts and product decisions.
    - The source RFE additionally requires blind listening with at most one of five raters reporting drift.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - English prompts, one concurrent user, two H100 80GB GPUs and two warm-up requests before measurements.
    - TTS latency targets apply to Qwen3-TTS and Voxtral-TTS over at least 200 requests per model.
    - T=0 is serving readiness, not pod start. Compare minute 1 with minute 10.
    - Minute-10 TTFB p95 must be at most 1.25 times minute-1 p95.
    - GPU-memory growth must remain within 15%; report the source KV-cache proxy separately from actual GPU memory.
    - Fifty-turn corpus has a 15-word median, ordinary prompts of 10–20 words and single-word edge cases.
    - Qwen3-Omni is evaluated for stability, not the TTS latency thresholds.
    - Voice must not be logged, cached or persisted; verify authorized metrics access and trusted offline model loading.
  - *Note any NFRs not covered and why:*
    - Broader capacity and language claims are excluded in II.1.
    - No additional throughput or RTF threshold is invented; confirm the RFE applicability before adding one.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **English-only quality acceptance**
  - TP quality thresholds apply to English. Other languages have no quality claim in this plan.
  - *Sign-off:* [Name/Date]

- **Realtime voice is outside the current TP strategy**
  - Full-duplex realtime support is described as upstream work in progress. Later release-note comments require reconciliation at entry review.
  - *Sign-off:* [Name/Date]

- **Reference-model hardware floor**
  - The Qwen3-Omni reference model requires at least two H100 80GB GPUs; one GPU does not fit the stated reference weights.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* 
    - Conduct the QE kickoff during design, before implementation decisions become fixed.
    - No kickoff date is evidenced by the collected data; record the human decision at entry review.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - The available checkout has standard vLLM templates but no Omni implementation; PR details were inaccessible.
    - Health checks must observe all model stages rather than merely an accepting HTTP listener.
    - The proposed readiness/liveness values are initial delay 250 s, period 30 s and failure threshold 12. Readiness failure removes traffic eligibility; liveness failure can restart a container.
    - Dashboard discovery uses existing annotations, vLLM model-format matching and the unsupported support-status value.
    - Stable and fast variants require coordinated image inventory, overlays and digest-based visibility.
    - Engine metrics alone omit route overhead, and KV-cache occupancy is not total GPU-memory usage.
  - *Impact on testing approach:* 
    - Treat checkout examples as patterns only and validate actual release settings before execution.
    - Observe the whole startup interval and collect both route timings and engine telemetry.

- [x] **API Extensions**
  - *List new or modified APIs:* 
    - Speech synthesis returns streamed audio through the external serving endpoint.
    - Validate supported model listing, health and text-generation capabilities for each model that implements them.
  - *Testing impact:* 
    - Check supported request/response contracts and malformed input rejection.
    - Do not require text-generation endpoints from a TTS-only model.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* 
    - Use the configured multi-node cluster with at least three workers and the reference two-GPU model allocation.
  - *Impact on test design:* 
    - Separate cold startup, warm latency, sustained session and disconnected deployment observations.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate Technology Preview dashboard selection, supported model deployment, complete-stage readiness, external inference, voice quality, release images, documentation, privacy, monitoring and deployment preservation across a supported product upgrade. Joint RHAII validation supplies engine quality and privacy evidence; Model Runtimes validates platform integration.

**Testing Goals**

- **[P0]** As an operator, verify preview deployment becomes usable only when every model stage is ready and stays unavailable on initialization failure.
- **[P0]** As an application developer, verify supported voice requests succeed without session failures or persistence of voice content.
- **[P0]** As an operator, verify published runtime images identify the approved release and missing images cannot yield successful serving.
- **[P1]** As an application developer, verify sustained speech meets model-specific responsiveness and stability expectations.
- **[P1]** As an operator, verify secure monitoring and deployment continuity across supported lifecycle changes.
- **[P2]** As an operator, verify preview guidance accurately describes capabilities and deployment restrictions.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Playground UX, dedicated model-format selection and disaggregated serving**
  - *Rationale:* Separate follow-up features; this cycle uses existing dashboard discovery.
  - *PM/Lead Agreement:* [Name/Date]

- **Image generation, video, broader engine certification and OmniVoice quality thresholds**
  - *Rationale:* Engine-only work belongs to RHAII; this plan retains joint voice gates and platform integration evidence.
  - *PM/Lead Agreement:* [Name/Date]

- **Non-reference accelerators, platforms, languages and multi-user capacity**
  - *Rationale:* This TP cycle validates the reference profile only; it makes no broader quality or scale claim.
  - *PM/Lead Agreement:* [Name/Date]

- **KEDA autoscaling and GA support certification**
  - *Rationale:* Separate work or later maturity; no GA SLA is claimed.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Unavailable implementation diff and unverified checkout lineage**
  - Network access prevented PR inspection. Clean detached checkouts provide patterns, not proof of merged Omni implementation or coverage. Re-run implementation comparison when access is restored.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Dashboard selection, complete-stage health, inference and failure paths in Section III.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate repeatable platform, metrics and route checks. Archive listening clips and ratings as human evaluation evidence; do not synthesize ratings.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve standard vLLM CUDA, ROCm, Gaudi, CPU and Spyre runtime selection and inference. Reuse standard vLLM probe, fast-runtime and PVC inference suites as patterns. Text search found no ticket-specific or Omni assertions in either checkout. Both checkouts are detached and their default-branch lineage was not verified, so no existing tests suppress new scenarios.

- [x] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Include complete-stage readiness and failed-stage health checks in the self-validation package once release-image behavior is confirmed.

**Non-Functional**

- [x] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Apply the I.1 measurement profile and model-specific targets. Observe latency and memory during the dialogue, not only its final state.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Extended capacity testing is excluded in II.1. Exercise the minimum reference GPU allocation boundary in Section III; do not claim multi-user scalability.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Voice privacy is a ship gate. Validate trusted model loading, offline behavior, restricted egress and protected metrics; these are feature-specific risks beyond generic RBAC.

- [x] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Check the existing dashboard discovery, limited-support badge, consent modal and deployment workflow without requiring dashboard code changes.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Verify the required 17 native and 32 wrapped metric families against the shipped engine contract, including stage/replica dimensions and successful request observations. Confirm metric names and counts before execution.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* N/A as a separate cross-platform matrix; only the release and reference hardware in II.3 are claimed. Broader platform certification is excluded in II.1.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Serving configuration is persistent. Validate preservation and serving after a supported N-to-N+1 product upgrade where Omni exists on both sides; select the release pair at entry review.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* RHAII must provide the productized image, all-stage health contract and voice-privacy confirmation. Release Engineering supplies mirrored digest inventory. Documentation resolves capability claims. These are team deliveries, not cluster prerequisites.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Joint evidence covers engine voice quality, release-image consumption and documentation correctness. The dashboard uses existing discovery behavior.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — no cloud-specific capability is introduced; the reference cluster is sufficient for this TP cycle.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster, at least three workers, with serving and metrics access.

- **Platform & Product Version(s):** Open Data Hub / RHOAI target: 3.6 EA1 RHOAI RELEASE. Exact OpenShift version and upgrade pair require release-owner confirmation.

- **CPU Virtualization:** N/A — the serving workload uses GPU acceleration; no CPU virtualization feature is introduced.

- **Compute Resources:** One serving replica and one concurrent user for the reference voice measurements; size host memory from the actual image/model requirements.

- **Special Hardware:** Two H100 80GB GPUs for the Qwen3-Omni reference model. Smaller-model single-GPU reports do not change that requirement.

- **Storage:** Trusted safetensors models provisioned on PVC. Budget approximately 95 GB total image-plus-model footprint as a planning estimate and verify actual capacity.

- **Network:** External OpenShift Route for latency and inference measurements, metrics scraping and a restricted-egress test namespace. Use sequential speech POSTs with the standard 30-second route timeout.

- **Required Operators:** Installed model-serving platform, KServe, GPU enablement and release image inventory matching the target release.

- **Platform:** OpenShift on the configured reference cluster; exact platform release confirmed before test execution.

- **Special Configurations:** HardwareProfile selects the required GPUs. Start with the shipped runtime settings and no DEBUG logging; confirm offline model loading and metric collection.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI/CD system required.

- **Other Tools:** Feature-specific route latency harness and fixed English prompt corpus; GPU-memory sampler; archived blind-listening clips and five-rater protocol.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] PM/Engineering approve the proposed criteria and resolve realtime/image endpoint and documentation scope conflicts.
- [ ] Confirm supported models, runtime version, image digests, exact platform version and supported upgrade pair.
- [ ] RHAII delivers the image and all-stage health behavior; book reference hardware before execution.
- [ ] Agree privacy evidence across supported log levels and obtain engine-team confirmation before release approval.
- [ ] Resolve safetensors flag support, unsupported-model diagnostics and metrics contract against the shipped build.
- [ ] Assign performance harness/corpus ownership and reserve five listening raters.
- [ ] Confirm actual GPU-memory instrumentation; do not substitute KV-cache occupancy for total GPU memory.
- [ ] Reconcile published release notes with RHOAIENG-82083 and RHOAIENG-95229 before documentation acceptance.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Image and validation evidence may miss release readiness
  - **Mitigation:** Track RHAII and Release Engineering delivery with the release owner; hold release approval until required evidence is available.
  - *Estimated impact on schedule:* Requires release-owner assessment before execution
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Planned evidence may overstate release support
  - **Mitigation:** Compare Section III with the approved model/endpoint matrix; reduced coverage for excluded areas is documented in Out of Scope.
  - *Areas with reduced coverage:* No realtime or extended-capacity acceptance claim
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Route timing and memory measurements may be misleading
  - **Mitigation:** Record route latency independently and correlate actual GPU-memory use with the source KV-cache proxy.
  - *Missing resources or infrastructure:* A validated GPU-memory sampler and route timing harness
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Unsupported-model diagnostics and safetensors flag behavior remain undefined
  - **Mitigation:** Obtain the shipped engine contract during entry review; add contract-specific assertions before executing those conditions. Privacy remains testable jointly with RHAII and is not waived.
  - *Alternative validation approach:* Inspect the shipped build and obtain engine-owner confirmation before entry approval
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** Listening evaluation and long-session runs may lack assigned capacity
  - **Mitigation:** Reserve five raters and schedule reference-hardware runs before entry approval.
  - *Current capacity gaps:* Rater booking and benchmark ownership are unconfirmed
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Engine and documentation deliverables may disagree with platform scope
  - **Mitigation:** Resolve endpoint scope and RN-only versus additional-guide decisions with owners; require documented agreement before acceptance.
  - *Dependent teams or components:* RHAII / OCTO Runtimes, Release Engineering and Documentation
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-2493]** — As an operator, I want to discover and choose the Tech Preview runtime
  - *Test Scenario:* **TS-01**: [e2e] Verify dashboard discovery and preview acceptance workflow
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify declining preview acceptance prevents runtime enablement
    - *Priority:* P1
  - *Test Scenario:* **TS-03**: [integration] Verify available runtime variants follow image divergence
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to deploy supported models without authoring configuration files
  - *Test Scenario:* **TS-04**: [e2e] Verify dashboard deployment serves supported Omni models
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [integration] Verify missing model storage prevents successful serving
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [integration] Verify undersized GPU allocation cannot falsely report readiness
    - *Priority:* P1
  - *Test Scenario:* **TS-07**: [functional] Verify minimum reference GPU allocation serves the model
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to receive traffic only after every model stage is ready
  - *Test Scenario:* **TS-08**: [integration] Verify readiness remains blocked throughout partial initialization
    - *Priority:* P0
  - *Test Scenario:* **TS-09**: [integration] Verify failed model stages keep serving unavailable
    - *Priority:* P0
  - *Test Scenario:* **TS-10**: [integration] Verify normal initialization avoids premature liveness restarts
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to receive valid speech and supported text responses
  - *Test Scenario:* **TS-11**: [functional] Verify speech streaming and supported text API conformance
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [functional] Verify malformed speech requests return client errors
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [functional] Verify single-word speech avoids white noise output
    - *Priority:* P2

- **[RHAISTRAT-2493]** — As an operator, I want to sustain voice sessions within the published quality thresholds
  - *Test Scenario:* **TS-14**: [e2e] Verify consecutive voice turns complete without session failures
    - *Priority:* P0
  - *Test Scenario:* **TS-15**: [e2e] Verify warm TTS route latency meets percentile targets
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [e2e] Verify continuous dialogue maintains latency and memory stability
    - *Priority:* P1
  - *Test Scenario:* **TS-17**: [e2e] Verify blinded listening meets timbre stability expectations
    - *Priority:* P2

- **[RHAISTRAT-2493]** — As an operator, I want to deploy the published runtime in disconnected environments
  - *Test Scenario:* **TS-18**: [integration] Verify published runtime images match approved release digests
    - *Priority:* P0
  - *Test Scenario:* **TS-19**: [e2e] Verify mirrored runtime serves locally provisioned model weights
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [integration] Verify unavailable mirrored images prevent successful serving
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to understand preview capabilities and deployment restrictions
  - *Test Scenario:* **TS-21**: [functional] Verify preview documentation matches available serving capabilities
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [functional] Verify deployment guidance discloses security and storage requirements
    - *Priority:* P2

- **[RHAISTRAT-2493]** — As an operator, I want to observe pipeline health and performance securely
  - *Test Scenario:* **TS-23**: [integration] Verify pipeline metrics expose required stage dimensions
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [integration] Verify unauthorized clients cannot read runtime metrics
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to keep voice data private while using trusted models
  - *Test Scenario:* **TS-25**: [e2e] Verify voice content remains absent from persistent artifacts
    - *Priority:* P0
  - *Test Scenario:* **TS-26**: [integration] Verify untrusted model artifacts cannot bypass deployment safeguards
    - *Priority:* P1
  - *Test Scenario:* **TS-27**: [integration] Verify restricted egress permits local model serving
    - *Priority:* P1

- **[RHAISTRAT-2493]** — As an operator, I want to retain deployed model configuration through a product upgrade
  - *Test Scenario:* **TS-28**: [e2e] Verify Omni serving configuration survives supported product upgrade
    - *Priority:* P1
  - *Test Scenario:* **TS-29**: [integration] Verify invalid post-upgrade deployments remain visibly unhealthy
    - *Priority:* P2

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name / @github-handle]
