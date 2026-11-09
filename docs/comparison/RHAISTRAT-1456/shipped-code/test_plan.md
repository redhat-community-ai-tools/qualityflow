# Test Plan

## **Codex Through the AI Gateway - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1779](https://redhat.atlassian.net/browse/RHAIRFE-1779)
- **Feature Tracking:** [RHAISTRAT-1073](https://redhat.atlassian.net/browse/RHAISTRAT-1073)
- **Epic Tracking:** [RHAISTRAT-1456](https://redhat.atlassian.net/browse/RHAISTRAT-1456)
- **Feature Maturity:**
  - DP: 3.7 GA RHOAI RELEASE [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Inference Gateway
- **Participating SIGs:** Agentic API, Documentation, OGX Core

**Document Conventions (if applicable):**

- **apply_patch:** Codex's built-in file-editing tool
- **AI Gateway:** The governed model-access layer used by Codex
- **Harness support matrix:** The published record of validated coding-agent compatibility

### **Feature Overview**

Developers can run Codex coding sessions against self-hosted models through the AI Gateway. The sessions support multi-turn reasoning, tool calls, streaming, and file edits, including Codex's built-in patch tool. Interactive, headless, and SDK-driven workflows use the standard custom-provider configuration without client modifications. The remaining validation confirms that custom tools are preserved or explicitly rejected and that the nightly workflow publishes the result.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Codex sessions complete multi-turn coding tasks through the AI Gateway
    - File edits use Codex's built-in patch tool when the selected model supports it
    - Unsupported requests produce explicit errors rather than silent tool loss
    - Nightly validation publishes the apply_patch result

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Developers can use a familiar coding agent with self-hosted models while model traffic remains governed by the platform.
  - *List the customer use cases identified:*
    - As a developer, I want to edit files interactively with Codex against a self-hosted model
    - As a platform engineer, I want to run headless Codex review or coding tasks in CI
    - As an application builder, I want to embed Codex workflows through the SDK

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - All acceptance criteria are testable with a deployed gateway, a self-hosted tool-calling model, and the Codex client
    - Support-matrix publication is testable only after the existing reporting destination is available

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - A Codex session completes a multi-turn coding task with file edits
    - Unsupported custom tools return an explicit error
    - The nightly run includes apply_patch and publishes its result
  - *Note any gaps or missing criteria:* No quantified latency, scale, or security target is specified

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Compatibility across supported Responses and Chat Completions backends
    - Streaming integrity for custom-tool events
    - Reliable multi-turn conversation history
  - *Note any NFRs not covered and why:* Performance and scale targets are not defined in the ticket

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

None — reviewed and confirmed with [Name/Date] that no feature limitations apply for this release.

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* QE involvement should occur during design so backend differences, streaming behavior, and tool-history semantics are represented in the test matrix before release.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Grammar-based custom tools must map to backend capabilities that differ by model and API
    - Streaming events must preserve custom-tool deltas and completion markers
    - Multi-turn history must retain custom-tool calls and outputs
  - *Impact on testing approach:* Tests must cover both successful compatibility and explicit rejection paths across supported backends.

- [x] **API Extensions**
  - *List new or modified APIs:* The Responses workflow accepts Codex custom tools and preserves their results across turns.
  - *Testing impact:* Validate successful file edits, multi-turn history, streaming events, and explicit unsupported-tool errors.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* The test path connects Codex to the AI Gateway and a self-hosted model.
  - *Impact on test design:* End-to-end scenarios must use the complete path rather than testing the client in isolation.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan validates Codex coding sessions through the AI Gateway, including multi-turn file edits with apply_patch, custom-tool history, streaming behavior, explicit unsupported-tool errors, compatibility across supported API backends, and publication of the nightly result. It covers the current 3.7 release target.

**Testing Goals**

- **[P0]** As a developer, verify Codex completes a multi-turn coding task with file edits
- **[P0]** As a developer, verify unsupported tools return explicit errors
- **[P1]** As a developer, verify custom-tool history and streaming remain intact
- **[P1]** As a platform operator, verify backend compatibility and nightly result publication

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Authoring and maintaining the complete harness support matrix**
  - *Rationale:* Tracked separately in RHAISTRAT-2769; this plan verifies only that the nightly apply_patch result is published
  - *PM/Lead Agreement:* [Name/Date]
- **The original LlamaStack session-store approach**
  - *Rationale:* Dropped from the current scope; Codex replays conversation history statelessly
  - *PM/Lead Agreement:* [Name/Date]
- **Deploying and operating Codex on OpenShift AI**
  - *Rationale:* Tracked separately in RHAISTRAT-1736
  - *PM/Lead Agreement:* [Name/Date]
- **Running Codex inside an OpenShell sandbox**
  - *Rationale:* Tracked separately in RHAISTRAT-2944
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

None — reviewed and confirmed with [Name/Date] that no test limitations apply for this release.

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Covers multi-turn coding, file edits, custom-tool errors, and supported backend modes.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Add automated integration and end-to-end scenarios to the existing Python test suite and Codex nightly workflow.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Existing Responses API generation must continue to pass; custom-tool compatibility must not alter normal model responses.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — the feature introduces no health-check or self-diagnostic capability.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A — no latency or throughput target is defined.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A — no scale target or concurrent-session requirement is defined.

- [ ] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* N/A — no new authorization boundary is introduced; gateway authentication is covered by existing platform tests.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — no user-interface change is in scope.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new metric or alert requirement is defined.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Validate the workflow across supported Responses and Chat Completions backends.

- [ ] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* N/A — Codex replays session state per request and no persistent state migration is introduced.

- [ ] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* N/A — the merged gateway change, test environment, and reporting destination are entry criteria rather than another team's pending delivery.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Codex, the AI Gateway, self-hosted model serving, and nightly reporting operate as one workflow.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — the behavior is cloud-independent.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster

- **Platform & Product Version(s):** Open Data Hub 3.7 GA RHOAI RELEASE [confirm release phase]

- **CPU Virtualization:** N/A

- **Compute Resources:** Sufficient for the AI Gateway and the selected self-hosted model

- **Special Hardware:** N/A

- **Storage:** Standard cluster storage for test repositories and generated files

- **Network:** Connectivity from Codex to the AI Gateway and from the gateway to the model endpoint

- **Required Operators:** Open Data Hub operator and configured model-serving stack

- **Platform:** OpenShift

- **Special Configurations:** Codex custom-provider profile, a self-hosted tool-calling model, and the apply_patch-enabled gateway configuration

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required

- **CI/CD:** Existing Codex nightly workflow

- **Other Tools:** Codex CLI and Codex SDK

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] The gateway build containing custom-tool compatibility is deployed
- [ ] A self-hosted model that supports tool calling is available
- [ ] The Codex custom-provider profile points to the AI Gateway
- [ ] The nightly reporting destination can receive the apply_patch result

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — the implementation PR is merged and the remaining work is validation-focused.

**Test Coverage**

- **Risk:** The complete support-matrix publication workflow is owned separately, which could hide a failure to publish the nightly result
  - **Mitigation:** Verify the nightly result reaches the existing reporting destination and escalate publication failures to the owning team
  - *Areas with reduced coverage:* Complete matrix authoring and version pinning
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** A selected model may not support the required custom-tool behavior
  - **Mitigation:** Use a known tool-calling model for P0 scenarios and retain an explicit-rejection test for unsupported backends
  - *Missing resources or infrastructure:* A compatible self-hosted model endpoint
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Mitigation:** No risk identified — every acceptance criterion has an observable pass or fail condition.

**Resource Constraints**

- **Mitigation:** No risk identified — the existing Python suite and nightly workflow can host the required scenarios.

**Dependencies**

- **Mitigation:** No risk identified — required components are already available or represented as entry criteria.

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-1456]** — As a developer, I want Codex to complete a multi-turn coding task with file edits through the AI Gateway
  - *Test Scenario:* **TS-01**: [e2e] Verify multi-turn Codex session edits files
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify explicit error unsupported custom tool
    - *Priority:* P0
  - *Test Scenario:* **TS-03**: [integration] Verify custom tool history across turns
    - *Priority:* P0

- **[RHAIENG-7794]** — As a developer, I want grammar-based custom tools to be accepted or explicitly rejected end to end
  - *Test Scenario:* **TS-04**: [integration] Verify streamed custom tool events intact
    - *Priority:* P1
  - *Test Scenario:* **TS-05**: [functional] Verify explicit error malformed tool grammar
    - *Priority:* P1

- **[RHAISTRAT-1810]** — As a developer, I want supported API backends to preserve Codex tool behavior
  - *Test Scenario:* **TS-06**: [functional] Verify file edits across API backends
    - *Priority:* P1

- **[REQ-RHAISTRAT-1456-01]** — As a platform operator, I want nightly validation to publish the apply_patch result
  - *Test Scenario:* **TS-07**: [e2e] Verify nightly result published support matrix
    - *Priority:* P1

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name]
