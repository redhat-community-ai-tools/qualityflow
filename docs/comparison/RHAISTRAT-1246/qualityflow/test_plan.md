# Test Plan

## **Enable remote::anthropic provider in OGX (previously Llama Stack) [3.5] - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1332](https://redhat.atlassian.net/browse/RHAIRFE-1332)
- **Feature Tracking:** [RHAISTRAT-1350](https://redhat.atlassian.net/browse/RHAISTRAT-1350)
- **Epic Tracking:** [RHAISTRAT-1246](https://redhat.atlassian.net/browse/RHAISTRAT-1246)
- **Feature Maturity:**
  - DP: 3.5 EA2 RHOAI RELEASE
  - TP: [confirm]
  - GA: [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** Documentation

**Document Conventions (if applicable):**

- **OGX:** Current name of Llama Stack, providing a common application interface across model providers.
- **MCP:** Model Context Protocol, used to discover and invoke external tools.
- **Provider data:** Request-scoped credentials supplied for an inference provider.
- **Native provider:** The dedicated Anthropic provider selected by users, distinct from a generic-provider configuration workaround.

### **Feature Overview**

Users can connect Claude models to their RHOAI applications through the dedicated Anthropic provider. This removes the need for custom authentication configuration and enables independent credentials for each user's requests. The Dev Preview target is 3.5 EA2, covering chat, streaming, tool conversations, external tools and model discovery. This plan defines release validation targets and does not record successful execution.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the feature's nine acceptance criteria against the cloned RFE and parent provider-onboarding scope.
    - Reviewed documentation obligations from RHAIENG-3828 and the consumer relationship to OSPRH-29653.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Users can select Claude without maintaining a provider-specific authentication workaround.
  - *List the customer use cases identified:*
    - As an application developer, I want to use Claude for chat and tool-assisted answers.
    - As a tenant, I want my own credentials applied only to my requests.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Failure responses and supported model identifiers need release-owner confirmation before execution.
    - The original header name and the current source name differ; see Entry Criteria.
    - No feature behavior is declared untestable; the release image and API credentials are execution prerequisites.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Dedicated Anthropic provider is usable in the downstream release.
    - Claude inference succeeds without custom authentication headers.
    - Chat supports streamed output and supported temperature settings.
    - Chat and responses support complete tool-call conversations.
    - Request-scoped Anthropic credentials override configured credentials.
    - Claude tasks can discover and invoke MCP tools.
    - Accessible Anthropic models are returned through model discovery.
    - Published configuration and embedding guidance are accurate.
    - All in-scope behaviors are exercised against the real Anthropic service.
  - *Note any gaps or missing criteria:*
    - The strategy block is explicitly proposed, not approved acceptance criteria.
    - Header naming, authentication transport and release configuration are unresolved execution contracts.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: tenant requests use their own credentials without fallback after an invalid override or leakage to another request.
    - Compatibility: existing stored provider configuration and usable model access remain valid across a supported upgrade.
  - *Note any NFRs not covered and why:*
    - No performance SLA, production load target, new metrics or accessibility requirement is specified; see Out of Scope.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Anthropic embedding generation is not provided**
  - Use a separate embedding provider; documentation must explain the recommended alternative.
  - *Sign-off:* [Name/Date]

- **Legacy text completion is not supported by Anthropic**
  - Use chat completions for Claude text generation.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Design-phase kickoff evidence is not supplied by Jira.
    - Design walkthrough and agreement on the release contract: [Name/Date].

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Anthropic model listing uses AsyncAnthropic, while the current chat adapter inherits an AsyncOpenAI path. Native x-api-key and anthropic-version behavior must be established on the target release.
    - The snapshot accepts x-ogx-provider-data; the original acceptance criteria specify x-llamastack-provider-data. Both refer to anthropic_api_key for override.
    - The sample config uses api_key while shared configuration reads auth_credential; confirm the supported release configuration.
    - Distribution inclusion and the anthropic SDK wheel supply are not established by this source checkout.
  - *Impact on testing approach:*
    - Inspect the release configuration and upstream requests in a controlled test account before claiming authentication parity.
    - Use the actual supported header and document the legacy-header behavior after release-owner confirmation.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Existing chat, responses, model listing and tool workflows gain an additional backend provider.
    - The parent scope keeps the application interface OpenAI-compatible.
  - *Testing impact:*
    - Cover complete and streaming results, supported sampling, tool arguments, invalid credentials and inaccessible models.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Use the configured OpenShift multi-node environment with at least three worker nodes.
  - *Impact on test design:*
    - Exercise parallel tenants against one provider and externally reachable MCP tools; no topology matrix is introduced.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate the Dev Preview Anthropic provider in the downstream 3.5 EA2 release: configuration without custom headers, chat and responses in complete and streamed modes, supported sampling, tool conversations, request credentials, MCP tool workflows, model discovery and usable documentation. Preserve configured access over the supported upgrade path. Live-service checks use approved test accounts and supported Claude models.

**Testing Goals**

- **[P0]** As an application developer, verify Claude answers and tool workflows succeed through the dedicated provider.
- **[P0]** As a tenant, verify concurrent requests use only their intended credentials.
- **[P0]** As an application developer, verify invalid credentials and unavailable services cannot produce successful authenticated results.
- **[P1]** As an administrator, verify discoverable models and published setup guidance support a usable configuration.
- **[P1]** As an administrator, verify configured Anthropic access remains usable across a supported upgrade.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Dashboard provider selection and per-user token UI**
  - *Rationale:* Separate Dashboard-team delivery; this feature validates backend request credentials.
  - *PM/Lead Agreement:* [Name/Date]

- **Native Anthropic frontend protocols and extended reasoning**
  - *Rationale:* Parent scope separates frontend protocol support; proposed strategy excludes thinking/reasoning validation.
  - *PM/Lead Agreement:* [Name/Date]

- **Production performance, scale and new observability targets**
  - *Rationale:* No approved SLA, load envelope, metric or alert is specified.
  - *PM/Lead Agreement:* [Name/Date]

- **Gemini and the OpenStack consumer operator**
  - *Rationale:* OSPRH-29653 belongs to the consumer operator team; only its dependency on this provider is recorded here.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Release-specific implementation evidence is incomplete**
  - The PRs could not be fetched and the downstream distribution checkout is unavailable. Local source is a later merged snapshot, so release-image behavior must be established before execution.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Exercise each in-scope capability and its failure paths against an approved Claude model. Successful inference requires nonempty relevant answer content; streams require content events and a completed terminal outcome.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate provider-specific functional and integration assertions, including invalid-key and tenant-isolation cases. Documentation setup is an executable workflow; embedding guidance is checked for the documented limitation and alternative.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Retain the existing generic chat, responses and model-listing suites for other configured providers. Preserve existing OpenAI-workaround authentication behavior without changing its configuration. Existing-test duplicate check ran on both merged snapshots; generic credential-selection coverage does not establish Anthropic wire authentication or tenant isolation.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — no new self-diagnostic capability or self-validation package is specified.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A — no latency or throughput acceptance target is defined; see Out of Scope.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A — no production load target is defined. Concurrent tenant isolation is a security check, not a scale benchmark; see Out of Scope.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Check valid and invalid request overrides, fallback only when no override is supplied, concurrent credential isolation and reset after an override. Upstream failures must not expose secret values.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — the backend provider adds no UI. API configuration documentation is covered as a user workflow; see Out of Scope for Dashboard validation.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new metric or alert is specified; see Out of Scope.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Validate the existing application-facing chat and responses contracts with the Anthropic backend, including streaming termination and tool-result continuation. Existing-provider compatibility remains in regression checks.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Stored provider settings and model access must survive a supported product upgrade. Confirm source/target versions and verify usable inference after upgrade.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* AIPCC must supply the anthropic SDK wheels used by the downstream image. Documentation must deliver the RHAIENG-3828 configuration and embedding guidance before documentation validation.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Exercise Claude conversations with MCP tools and tool-result continuation. Coordinate documentation validation with Documentation; the unrelated consumer operator is covered by its owning team.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — Anthropic is a remote service, with no cloud-specific platform behavior or multi-cloud requirement in this feature.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift with at least three workers, per project configuration; one deployed downstream inference service.

- **Platform & Product Version(s):** RHOAI 3.5 EA2 RHOAI RELEASE, Dev Preview. Exact OpenShift support version and supported upgrade source: [confirm] with the release owner.

- **CPU Virtualization:** No CPU virtualization feature is required for this remote inference provider.

- **Compute Resources:** Standard capacity for the deployed service and two concurrent tenant clients; no local model-serving accelerator is required.

- **Special Hardware:** No special hardware for the remote provider.

- **Storage:** Existing persistent configuration and response storage required by the deployed service; retain the same settings across upgrade checks.

- **Network:** TLS egress to the real Anthropic service and the controlled MCP service. Approved quotas and access are required before execution.

- **Required Operators:** Supported OGX deployment operator for the target release; existing environment/Secret injection is used.

- **Platform:** OpenShift, using the project's supported deployment configuration.

- **Special Configurations:** Dedicated Anthropic provider, supported Claude model and two independent test-account keys supplied through Secrets. No key values in reports. Configure the supported request header only after confirming the release contract.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI system required.

- **Other Tools:** Controlled MCP service returning a deterministic tool result and a redacting request observer for authentication validation.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Release owner confirms header contract: x-llamastack-provider-data versus x-ogx-provider-data, including intended legacy-header compatibility.
- [ ] Development confirms native authentication behavior and supported api_key/auth_credential configuration on the release image.
- [ ] Downstream image includes the provider and required AIPCC wheels.
- [ ] Approved accounts provide distinct valid keys, invalid-key controls, supported models and sufficient quota.
- [ ] Documentation is delivered and the design walkthrough and human sign-offs are collected.
- [ ] Release owner confirms OpenShift version, upgrade source/target and TP/GA maturity dates.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Historical closure does not establish current validation completion.
  - **Mitigation:** Reconcile the release validation record with Development before scheduling this plan.
  - *Estimated impact on schedule:* To be confirmed at test kickoff
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Release-specific authentication may differ from the inspected source snapshot.
  - **Mitigation:** Resolve the release contract and retain real upstream authentication checks as release blockers.
  - *Areas with reduced coverage:* Wire authentication evidence until release-image validation
  - *Sign-off:* [Name/Date]
  - **Mitigation:** Reduced coverage for excluded areas, see Out of Scope.

**Test Environment**

- **Risk:** External API faults or throttling may make live runs intermittent.
  - **Mitigation:** Use isolated test accounts, capture redacted provider errors and retry only transient failures.
  - *Missing resources or infrastructure:* None identified; service availability is externally controlled
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Mitigation:** No risk identified — No behavior is declared untestable; all execution prerequisites are listed in Entry Criteria.

**Resource Constraints**

- **Mitigation:** No risk identified — No capacity gap is established by Jira; confirm test-account quotas before execution.

**Dependencies**

- **Risk:** The release image may not contain the required anthropic SDK wheels.
  - **Mitigation:** Obtain AIPCC build evidence and verify provider usability in the released image.
  - *Dependent teams or components:* AIPCC and OGX Core
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-1246]** — As an administrator, I want to use Anthropic models in the downstream distribution
  - *Test Scenario:* **TS-01**: [functional] Verify Anthropic inference returns answers without custom headers
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify missing Anthropic credentials produce actionable errors
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an application developer, I want to receive streamed Claude answers with supported sampling
  - *Test Scenario:* **TS-03**: [functional] Verify Claude streaming delivers content and completion events
    - *Priority:* P0
  - *Test Scenario:* **TS-04**: [functional] Verify supported temperatures yield successful Claude chat responses
    - *Priority:* P1
  - *Test Scenario:* **TS-05**: [functional] Verify invalid sampling parameters produce validation errors
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an application developer, I want to complete Claude tool conversations
  - *Test Scenario:* **TS-06**: [integration] Verify Claude tool calls complete through chat and responses
    - *Priority:* P0
  - *Test Scenario:* **TS-07**: [functional] Verify Claude handles tools with empty parameter schemas
    - *Priority:* P2
  - *Test Scenario:* **TS-08**: [integration] Verify invalid tool arguments produce actionable failures
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As a tenant, I want to authenticate each request with my own Anthropic key
  - *Test Scenario:* **TS-09**: [integration] [PARTIAL_COVERAGE] Verify request credentials override configured Anthropic credentials
    - *Priority:* P0
  - *Test Scenario:* **TS-10**: [integration] [PARTIAL_COVERAGE] Verify invalid request credentials cannot use configured credentials
    - *Priority:* P1
  - *Test Scenario:* **TS-11**: [integration] [PARTIAL_COVERAGE] Verify concurrent tenants retain isolated Anthropic credentials
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] [PARTIAL_COVERAGE] Verify configured credentials resume after request override
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [integration] [PARTIAL_COVERAGE] Verify Anthropic failures redact supplied credential values
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an application developer, I want to complete Claude tasks using MCP tools
  - *Test Scenario:* **TS-14**: [e2e] Verify Claude answers incorporate MCP tool results
    - *Priority:* P0
  - *Test Scenario:* **TS-15**: [e2e] Verify unavailable MCP tools report actionable failures
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an application developer, I want to discover accessible Anthropic models
  - *Test Scenario:* **TS-16**: [functional] Verify Anthropic model discovery returns accessible model identifiers
    - *Priority:* P0
  - *Test Scenario:* **TS-17**: [functional] Verify invalid credentials fail Anthropic model discovery
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an application developer, I want to receive Claude responses in supported modes
  - *Test Scenario:* **TS-18**: [functional] Verify Claude responses return requested answer content
    - *Priority:* P0
  - *Test Scenario:* **TS-19**: [functional] Verify streaming Claude responses deliver content and completion
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [functional] Verify unavailable Claude models produce actionable response errors
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an administrator, I want to configure Anthropic using published guidance
  - *Test Scenario:* **TS-21**: [e2e] Verify documented Anthropic setup produces successful inference
    - *Priority:* P0
  - *Test Scenario:* **TS-22**: [functional] Verify documentation identifies unsupported embeddings and alternatives
    - *Priority:* P1

- **[RHAISTRAT-1246]** — As an administrator, I want to preserve configured Anthropic access during upgrades
  - *Test Scenario:* **TS-23**: [e2e] Verify configured Anthropic access survives supported upgrades
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [e2e] Verify invalid Anthropic configuration reports errors after upgrade
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
