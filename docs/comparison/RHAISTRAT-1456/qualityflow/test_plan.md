# Test Plan

## **AI Gateway Support for OpenAI Codex Agent SDK - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1779](https://redhat.atlassian.net/browse/RHAIRFE-1779)
- **Feature Tracking:** [RHAISTRAT-1073](https://redhat.atlassian.net/browse/RHAISTRAT-1073)
- **Epic Tracking:** [RHAISTRAT-1456](https://redhat.atlassian.net/browse/RHAISTRAT-1456)
- **Feature Maturity:**
  - DP: 3.6 GA RHOAI RELEASE [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Inference Gateway
- **Participating SIGs:** Agentic API, OGX Core, Documentation

**Document Conventions (if applicable):**

- **Codex:** the coding CLI harness under test.
- **Praxis:** the AI Gateway entrypoint identified by the current Jira child epic.
- **TTFT:** time from request submission to the first generated token.
- **Stored session:** coding history retained for continuation after a connection closes.

### **Feature Overview**

Developers can use Codex with self-hosted models through the AI Gateway for multi-turn coding tasks. This gives platform teams one governed entrypoint for coding traffic. The plan covers default client connectivity, task continuity and consistent access decisions. Release maturity and the transition from the original LlamaStack scope require confirmation before execution.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the original five acceptance criteria in [RHAISTRAT-1456](https://redhat.atlassian.net/browse/RHAISTRAT-1456).
    - Reviewed the current WebSockets child epic [RHAIENG-7793](https://redhat.atlassian.net/browse/RHAIENG-7793) and parent scope.
    - Kept grammar tools separate per [RHAIENG-7794](https://redhat.atlassian.net/browse/RHAIENG-7794).

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Developers can retain coding context while platform teams govern model access.
  - *List the customer use cases identified:*
    - As a developer, I want to repair a failing test using a self-hosted model without changing coding harnesses.
    - As a platform administrator, I want the same coding traffic policies regardless of transport.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The current child epic is specific; the historical session identifier, memory and compaction assumptions need design reconciliation.
    - Latency is measurable once the hardware, model, load and percentile are agreed. See Untestable Aspects risk; no delivery or performance result is asserted.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Codex completes a five-turn coding task without resending full conversation history.
    - The six originally named coding tools (bash, read_file, write_file, edit_file, grep_search, glob_search) return schema-valid JSON arguments.
    - Streaming TTFT remains under 200ms on the agreed configuration.
    - Stored coding work resumes after disconnect without repeating completed actions.
    - At least one originally listed OSS model reads a failing test, navigates a repository, writes a patch and passes the test.
    - Codex completes multi-turn tool calling using its default WebSockets transport through the AI Gateway.
    - Authentication, metering and policy decisions match the HTTP path.
    - The Codex nightly run exercises WebSockets; this is release evidence required by Entry Criteria, not a feature scenario.
  - *Note any gaps or missing criteria:*
    - Current Jira retargeting does not settle which historical session, tool and latency criteria remain binding. Preserve their validation targets until PM and engineering reconcile them.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Performance: original TTFT under 200ms target; proposed p95 over 100 requests requires owner confirmation.
    - Security: no unauthenticated or forbidden model access on either transport.
    - Compatibility: supported Codex versions and product upgrades retain usable stored work.
    - Observability: usage attribution and metering are equivalent across transports.
  - *Note any NFRs not covered and why:*
    - No invented concurrent-session quota or general cloud matrix: advertised model context boundary is tested; see Out of Scope for broad scale certification.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Unstored history is limited to the current connection in the checked OGX baseline**
  - A fresh connection has no unstored predecessor history; the gateway recovery contract must distinguish stored from unstored work.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Schedule the QE kickoff during design, before implementation; collect [Name/Date].
    - Reconcile legacy acceptance criteria with the current child epic and obtain the gateway delivery contract.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - The OGX baseline has a Responses WebSocket route and auth middleware, but its generated Codex profile disables WebSockets.
    - Connection-local unstored history disappears on disconnect; persisted Responses history is a different contract.
    - Only the tests checkout has an LSP server; source tracing used text search. No AI Gateway checkout was provided.
  - *Impact on testing approach:*
    - Treat real gateway tool workflows, metering parity and reconnect behavior as integration targets; baseline unit assertions do not prove them.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Responses gains a persistent client connection for streamed coding events on the gateway.
  - *Testing impact:*
    - Compare observable completion, errors and access decisions across both supported transports.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Codex reaches a multi-node OpenShift deployment through the gateway, with a self-hosted model backend and a persistent history store.
  - *Impact on test design:*
    - Exercise route refusal, disconnect and product update at the product boundary; no platform scheduler or network-plugin certification.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate Codex coding workflows through the AI Gateway at the release maturity confirmed in Entry Criteria. Cover default WebSockets connectivity, ordered streaming, tool interoperability, five-turn task context, stored-session recovery, HTTP fallback, authentication, policy, routing, metering, latency, context boundaries and stored-work compatibility. Historical criteria remain explicit validation targets until reconciled; this plan does not assert they already work.

**Testing Goals**

- **[P0]** As a developer, verify multi-turn coding completes with retained context and valid tool results.
- **[P0]** As a platform administrator, verify unauthorized or disallowed coding requests cannot reach models.
- **[P1]** As a developer, verify connection loss and transport refusal recover without duplicate actions or misleading success.
- **[P1]** As a platform administrator, verify model selection and usage attribution remain consistent across transports.
- **[P1]** As a developer, verify agreed latency and context limits produce usable results or actionable failures.
- **[P1]** As a developer, verify supported client and product updates preserve usable stored work.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Grammar custom tools and apply_patch acceptance**
  - *Rationale:* Separate [RHAIENG-7794](https://redhat.atlassian.net/browse/RHAIENG-7794) / [RHAISTRAT-1810](https://redhat.atlassian.net/browse/RHAISTRAT-1810) owns grammar compatibility; transport tests include ordinary file edits through supported coding tools. Grammar-specific acceptance is owned by that separate epic.
  - *PM/Lead Agreement:* [Name/Date]

- **Realtime voice semantics and sandbox governance**
  - *Rationale:* Voice and OpenShell composition have separate ownership in RHAIRFE-3620 and [RHAIRFE-3645](https://redhat.atlassian.net/browse/RHAIRFE-3645); only coding transport is covered here.
  - *PM/Lead Agreement:* [Name/Date]

- **Broad platform and concurrent-load certification**
  - *Rationale:* No cloud, OS or concurrent-session support matrix is specified. Validate the agreed coding configuration and context boundary; scope sign-off is required.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Static evidence only in this planning run**
  - No deployed gateway, model workload or nightly execution was run; product behavior remains to be validated in the agreed environment.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Default connection, ordered completion, multi-turn context, tool arguments, reconnect and explicit errors; no claim that mocks prove gateway delivery.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate the feature scenarios with existing Python test conventions; require the real Codex WebSockets nightly evidence before release approval.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Existing-test duplicate check ran across both clean default-branch snapshots. Retain OGX malformed-request, missing predecessor, provider error, streaming, basic Responses and HTTP-only no-tools CLI smoke baselines. New gateway workflows are gaps rather than repeats of those narrow assertions.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Not selected: this ticket adds no product self-diagnostic or readiness capability.

**Non-Functional**

- [x] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Original criterion: TTFT under 200ms. Confirm hardware, model, request size, warm-up and whether p95 across 100 consecutive requests applies before execution; report observed measurements, never infer compliance.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Not selected for broad load certification; validate the advertised model context boundary under Functional Testing. No concurrent-session or quota value is established.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* The WebSocket handshake and per-session requests must preserve HTTP access denials and policy decisions, including unauthenticated and forbidden callers.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Not selected: API and CLI workflow only, no UI component or accessibility changes in current scope.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Validate equivalent coding usage attribution and metering at the gateway, including model and caller identity; no metric names are invented.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Run the supported Codex client versions against the agreed product/backend matrix; accept at least one model from the original OSS candidate list.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Stored coding history must remain usable across the supported product update path; use the release pair agreed in Entry Criteria.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* AI Gateway engineering must deliver WebSockets upgrade, fallback and governance parity in [RHAIENG-7793](https://redhat.atlassian.net/browse/RHAIENG-7793). Historical Memories/Compaction delivery is not assumed; require it only if the reconciled design uses it.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Inference Gateway and Agentic API own transport/governance integration; OGX Core supplies the Responses compatibility baseline; Documentation owns the supported setup and limitations. Validate with a real self-hosted model.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not selected: no cloud-specific behavior is identified; broad platform certification is excluded below.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift deployment with at least 3 worker nodes per project configuration; expose the gateway-to-model path.

- **Platform & Product Version(s):** Jira versions: 3.6 GA RHOAI RELEASE; target: 3.7 GA RHOAI RELEASE. Release owner must select the execution build. OpenShift version is not specified; use the supported platform matrix.

- **CPU Virtualization:** N/A — no virtualization behavior introduced by this coding API feature.

- **Compute Resources:** CPU and memory for gateway/history services plus accelerator capacity for the selected self-hosted model; record requests and limits for latency reproducibility.

- **Special Hardware:** Model-compatible accelerator hardware; original strategy mentions A100-80/H100 as hypotheses, not confirmed lab allocation or a proven SLA.

- **Storage:** Persistent Responses history storage for reconnect and upgrade checks, plus a disposable coding repository. Unstored connections are tested separately.

- **Network:** Codex-to-gateway route accepting secure WebSocket upgrades and HTTP streaming; controllable disconnect and upgrade refusal.

- **Required Operators:** Supported OpenShift AI and serving operators for the selected build; record installed versions during execution.

- **Platform:** OpenShift with the agreed RHOAI build and a self-hosted model from Qwen 3.5, Mistral Small 4, Llama 3.3 70B, Nemotron 3 Super or GPT-oss; validate at least one, without claiming all are supported.

- **Special Configurations:** Pin Codex client and model versions, enable the actual default WebSockets profile, configure authenticated permitted/forbidden users, and record history retention and model context limits.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI/CD tool required.

- **Other Tools:** Real Codex CLI harness, a controlled connection-interruption facility and first-token timing capture for the feature-specific checks.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] PM and engineering reconcile original LlamaStack/session criteria with current gateway scope and confirm a supported recovery identifier.
- [ ] Release owner resolves 3.6 fix version versus 3.7 target and explicit Dev Preview versus parent GA intent.
- [ ] AI Gateway WebSockets, fallback and governance delivery is available; the default Codex profile actually uses WebSockets.
- [ ] Model, hardware, latency method and supported context limit are recorded; no fabricated thresholds.
- [ ] Supported client versions and the product upgrade source/target pair are agreed.
- [ ] The Codex nightly run publishes evidence that it exercised WebSockets and multi-turn tool calling; the existing HTTP-only no-tools smoke is insufficient.
- [ ] QE owner and environment allocation are confirmed.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Legacy acceptance criteria and current transport scope may diverge
  - **Mitigation:** Resolve the scope contract at design kickoff before test implementation
  - *Estimated impact on schedule:* Execution start depends on owner reconciliation; no duration asserted.
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Baseline smoke may hide default-transport and real tool-workflow gaps
  - **Mitigation:** Require the default WebSockets nightly evidence and the new gateway scenarios
  - *Areas with reduced coverage:* See Out of Scope for separately owned grammar tools, voice and sandbox composition.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Mitigation:** No risk identified — No resource shortage has been established; environment requirements are specified in II.3.

**Untestable Aspects**

- **Risk:** The latency and recovery contracts are not reproducible until the design is settled
  - **Mitigation:** Confirm the measurement configuration and supported stored-session identifier before execution; retain these as P1 targets
  - *Alternative validation approach:* Use pinned configuration measurements and connection interruption checks once Entry Criteria is met; no performance or recovery pass is claimed.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** Historical Jira comments report insufficient QE capacity beyond preview
  - **Mitigation:** Assign a QE owner and prioritize the core workflow and access-denial checks at kickoff
  - *Current capacity gaps:* Current QE allocation is unconfirmed; historical comments are not proof of present capacity.
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Gateway delivery may lag the original backend compatibility work
  - **Mitigation:** Track RHAIENG-7793 and validate the delivered gateway; do not treat the baseline OGX implementation as gateway completion
  - *Dependent teams or components:* Inference Gateway and Agentic API; grammar-tool delivery is owned separately as noted in Out of Scope.
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAIENG-7793]** — As a developer, I want Codex to complete coding tasks using its default transport
  - *Test Scenario:* **TS-01**: [e2e] Verify Codex repairs failing tests through default WebSockets
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [integration] [PARTIAL_COVERAGE] Verify WebSocket events arrive in order until completion
    - *Priority:* P0
  - *Test Scenario:* **TS-03**: [integration] Verify unsupported WebSockets fall back without duplicate actions
    - *Priority:* P1

- **[RHAISTRAT-1456]** — As a developer, I want coding context retained across successive turns
  - *Test Scenario:* **TS-04**: [e2e] Verify five coding turns retain earlier task context
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [integration] Verify failed continuations cannot reuse invalidated task context
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [integration] Verify truncated responses remain available for continuation
    - *Priority:* P1

- **[RHAISTRAT-1456]** — As a developer, I want interrupted work to resume without repeating completed actions
  - *Test Scenario:* **TS-07**: [e2e] Verify stored coding sessions resume after connection loss
    - *Priority:* P1
  - *Test Scenario:* **TS-08**: [integration] Verify unstored sessions cannot resume on another connection
    - *Priority:* P1

- **[RHAISTRAT-1456]** — As a developer, I want coding tools to receive valid arguments and return usable results
  - *Test Scenario:* **TS-09**: [e2e] Verify supported coding tools complete with valid arguments
    - *Priority:* P0
  - *Test Scenario:* **TS-10**: [integration] Verify invalid tool arguments fail without executing actions
    - *Priority:* P1

- **[RHAIENG-7793]** — As a platform administrator, I want the same access decisions for both transports
  - *Test Scenario:* **TS-11**: [integration] Verify authorized users access both transports consistently
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] Verify unauthenticated connections are denied before model access
    - *Priority:* P0
  - *Test Scenario:* **TS-13**: [integration] Verify forbidden users cannot access coding sessions
    - *Priority:* P0

- **[RHAIENG-7793]** — As a platform administrator, I want coding traffic governed consistently across transports
  - *Test Scenario:* **TS-14**: [e2e] Verify both transports use the selected self-hosted model
    - *Priority:* P1
  - *Test Scenario:* **TS-15**: [e2e] Verify metering attributes coding usage consistently across transports
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [e2e] Verify disallowed coding requests are blocked across transports
    - *Priority:* P0

- **[RHAISTRAT-1456]** — As a developer, I want interactive coding responses within the agreed latency target
  - *Test Scenario:* **TS-17**: [e2e] Verify streaming first-token latency stays below the acceptance threshold
    - *Priority:* P1
  - *Test Scenario:* **TS-18**: [integration] Verify model failures produce actionable errors during coding
    - *Priority:* P1

- **[RHAISTRAT-1456]** — As a developer, I want coding sessions to handle model context limits safely
  - *Test Scenario:* **TS-19**: [integration] Verify coding tasks complete at the supported context boundary
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [integration] Verify oversized coding context fails without corrupting prior work
    - *Priority:* P1

- **[RHAISTRAT-1456]** — As a developer, I want supported client and product updates to preserve stored coding work
  - *Test Scenario:* **TS-21**: [e2e] Verify stored coding work remains usable after upgrade
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [e2e] Verify supported Codex versions complete the same coding workflow
    - *Priority:* P1

#### Section III.2 — Source Constants

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|:---|:---|:---|:---|
| _WS_STRIPPED_FIELDS | `("type", "stream", "stream_options", "background")` | src/ogx_api/responses/fastapi_routes.py | 220 |
| WS_UNKNOWN_PREDECESSOR | `previous_response_not_found` | src/ogx_api/responses/fastapi_routes.py | 300 |
| WS_AUTH_DENIAL_CODE | `4401` | src/ogx/core/server/auth.py | 188 |
| BASELINE_CODEX_WEBSOCKETS_SETTING | `supports_websockets = false` | src/ogx/cli/connect/codex.py | 297 |


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
