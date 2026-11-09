# Test Plan

## **Remote Anthropic Provider - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1332](https://redhat.atlassian.net/browse/RHAIRFE-1332)
- **Feature Tracking:** [RHAISTRAT-1350](https://redhat.atlassian.net/browse/RHAISTRAT-1350)
- **Epic Tracking:** [RHAISTRAT-1246](https://redhat.atlassian.net/browse/RHAISTRAT-1246)
- **Feature Maturity:**
  - DP: 3.5 EA2 RHOAI RELEASE
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** Documentation

**Document Conventions (if applicable):**

- **OGX:** Open-source AI application server and library, formerly Llama Stack.
- **Dev Preview:** A pre-release feature phase used before Tech Preview and general availability.
- **MCP:** Model Context Protocol, a protocol for connecting models to external tools and resources.
- **AIPCC:** The internal Python wheel build pipeline used for downstream distribution images.

### **Feature Overview**

The native Anthropic provider lets users configure and use Claude models directly with OGX. It removes the need to emulate Anthropic through the OpenAI-compatible provider with custom authentication headers. Users can list Anthropic models, stream chat responses, use tools, connect MCP servers, and supply a different Anthropic credential for an individual request. The provider, its Python SDK dependency, configuration examples, and deployment guidance are included for the RHOAI 3.5 EA2 Dev Preview distribution.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Include the native Anthropic provider in the downstream RHOAI OGX distribution.
    - Configure Anthropic models without the OpenAI-compatible provider and custom-header workaround.
    - Support streaming chat completions and temperature or sampling parameters.
    - Support tool calling through chat completions and responses APIs.
    - Support per-request Anthropic credential override.
    - Support MCP servers with Anthropic models.
    - List Anthropic models using Anthropic's native response format.
    - Update configuration and embedding-model guidance.
    - Validate all functionality against the Anthropic API.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Customers can use one of the most requested model providers directly, with correct authentication, per-request credentials, and a supported migration path from the prior workaround.
  - *List the customer use cases identified:*
    - As an administrator, I want to add Claude models to an OGX deployment without provider-specific header workarounds.
    - As an application developer, I want streaming and tool-based Claude interactions to work through the standard OGX APIs.
    - As an administrator, I want different users or requests to use their own Anthropic credentials against the same provider endpoint.
    - As an administrator, I want existing OpenAI-compatible provider configurations to keep working while I migrate to the native provider.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - No requirement is untestable. Streaming, tool calling, and live validation need explicit pass criteria and representative test data.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - The native provider is available in downstream RHOAI OGX distributions.
    - Anthropic models can be configured without custom network headers.
    - Chat completions work with streaming and temperature parameters.
    - Tool calling works through chat completions and responses APIs.
    - Per-request Anthropic credentials override configured credentials.
    - MCP servers work with Anthropic models.
    - Model listing uses Anthropic's native format.
    - Documentation includes configuration examples and embedding-model guidance.
    - Functionality is validated against the Anthropic API.
  - *Note any gaps or missing criteria:* The ticket does not define a performance threshold, an exact error-response contract, or the set of models to pre-register.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: store configured Anthropic credentials in Kubernetes Secrets, enforce TLS 1.2 or higher, and prevent credential leakage.
    - Backward compatibility: existing OpenAI-compatible configurations continue to work.
    - Multi-tenant behavior: concurrent requests with different per-request credentials remain isolated.
  - *Note any NFRs not covered and why:* No performance, monitoring, or accessibility target is specified; those areas are not checked as dedicated strategies.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Anthropic inference requires external API access**
  - The provider cannot operate in a fully disconnected environment because it calls the Anthropic service in real time.
  - *Sign-off:* [Name/Date]

- **Legacy text completions are not supported**
  - The Anthropic provider supports chat completions, messages, and responses workflows, but not the legacy text-completions endpoint.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* A design-phase handoff is reflected by the refinement document and strategy. The feature is an additive provider inclusion backed by an upstream implementation; QE should validate native authentication, model discovery, tool and MCP integration, and downstream packaging rather than operator framework behavior.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Anthropic uses a different authentication header scheme and model-listing response format from OpenAI-compatible providers.
    - Per-request credentials must override configured credentials without leaking values or crossing concurrent requests.
    - The downstream image must include the Anthropic SDK through the AIPCC wheel pipeline.
    - Optional MCP integration requires an external tool server and representative tool payload.
  - *Impact on testing approach:* Tests need at least two valid Anthropic credentials, live egress, an MCP test server, and clear assertions for streaming events, tool calls, model shape, and safe failures.

- [x] **API Extensions**
  - *List new or modified APIs:* The feature adds a native Anthropic provider selection and per-request credential override. Existing model, provider, chat, messages, responses, and tool interfaces remain the user-facing surfaces.
  - *Testing impact:* Validate each user-facing surface with the native provider and confirm that existing interfaces remain compatible.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A multi-node OpenShift cluster runs the OGX distribution and operator, with egress to the Anthropic service and, for MCP coverage, a reachable test MCP server.
  - *Impact on test design:* Provider activation, inference, model listing, and MCP workflows should run against the deployed distribution rather than only isolated provider code.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan covers native Anthropic provider packaging, activation, configuration, authentication, model listing, streaming inference, tool calling, MCP integration, per-request credential override, safe failure behavior, and compatibility with existing provider configurations for the RHOAI 3.5 EA2 Dev Preview release.

**Testing Goals**

- **[P0]** As an administrator, verify the native Anthropic provider is available in the deployed distribution.
- **[P0]** As an administrator, verify Claude models can be configured without the OpenAI-compatible workaround.
- **[P0]** As an application developer, verify streaming responses preserve temperature and sampling behavior.
- **[P0]** As an application developer, verify tool calls work through chat and responses workflows.
- **[P0]** As an application developer, verify missing or invalid Anthropic credentials fail safely.
- **[P1]** As an application developer, verify per-request credentials remain isolated across concurrent requests.
- **[P1]** As an application developer, verify Anthropic models are listed in the native response format.
- **[P1]** As an application developer, verify MCP tools work with Anthropic models.
- **[P1]** As an administrator, verify existing provider configurations remain usable after migration or upgrade.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Anthropic-specific Gen AI Studio UI**
  - *Rationale:* The dashboard team owns the user-interface work separately.
  - *PM/Lead Agreement:* [Name/Date]

- **Dashboard per-user API token management**
  - *Rationale:* Dashboard-managed token lifecycle is planned for a future release.
  - *PM/Lead Agreement:* [Name/Date]

- **Anthropic embedding models**
  - *Rationale:* Anthropic does not provide embedding models; documentation points users to a separate embedding provider.
  - *PM/Lead Agreement:* [Name/Date]

- **Claude thinking and reasoning feature validation**
  - *Rationale:* The native provider passes supported request fields through; no additional reasoning-feature strategy is part of this ticket.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Live Anthropic credentials and egress required**
  - End-to-end scenarios require valid credentials and network egress to the external Anthropic service.
  - *Sign-off:* [Name/Date]

- **No defined performance threshold**
  - Comparative response time can be observed, but pass or fail cannot be judged without a product-approved latency or throughput target.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Cover provider availability, configuration, authentication, model listing, inference, tool calling, MCP, and safe failure paths.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Use pytest for provider-level, integration, and deployed-distribution scenarios; retain mocked transport tests for deterministic error and header checks.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Existing-test duplicate check ran against the configured OGX and Open Data Hub test repositories; retain partial upstream coverage and generate only the identified live-deployment gaps.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Not applicable; no self-validation or readiness package is defined for this provider.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Not applicable; no latency, throughput, or resource-use target is defined.

- [x] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Validate concurrent requests that use distinct per-request credentials to detect cross-request credential leakage or authentication failures.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Validate Secret-backed credentials, TLS 1.2 or higher, credential override behavior, safe errors, and absence of credential leakage.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Not applicable; this feature is exposed through APIs and configuration rather than a new user interface.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Not applicable; no new metric or alert is required by the ticket.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Confirm the native provider and existing OpenAI-compatible provider configurations operate side by side.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Verify an existing provider configuration survives upgrade and can migrate to the native provider without losing inference capability.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* The AIPCC team must provide the Anthropic SDK wheel in the downstream build pipeline; the deployed image and operator configuration must expose the provider.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Validate OGX operator configuration and MCP tool integration with Anthropic models; Gen AI Studio UI integration remains out of scope.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not applicable; the provider is cloud-agnostic and requires standard OpenShift egress to the Anthropic service.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least three worker nodes.

- **Platform & Product Version(s):** RHOAI 3.5 EA2 with the OpenShift version supported by that release [confirm].

- **CPU Virtualization:** N/A; the provider has no special CPU virtualization requirement.

- **Compute Resources:** Standard RHOAI worker capacity sufficient to run the OGX distribution and test workloads.

- **Special Hardware:** N/A; no special hardware is required.

- **Storage:** Standard cluster storage; the Anthropic provider has no dedicated storage requirement.

- **Network:** Egress to the Anthropic service with TLS 1.2 or higher; proxy and certificate configuration must follow the deployment's standard network policy.

- **Required Operators:** OGX Kubernetes operator configured for the RHOAI 3.5 EA2 distribution.

- **Platform:** OpenShift.

- **Special Configurations:** Anthropic credential stored in a Kubernetes Secret, native provider activated in the distribution, at least two valid Anthropic credentials for override testing, and an optional MCP test server.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI/CD tool required.

- **Other Tools:** TLS inspection utility for transport validation and a controlled MCP test server for tool integration.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] The downstream distribution image contains the native Anthropic provider and Anthropic SDK
- [ ] At least two valid Anthropic credentials are available for per-request override testing
- [ ] Egress to the Anthropic service is available and uses TLS 1.2 or higher
- [ ] A controlled MCP test server is available for MCP scenarios

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — the ticket has a released 3.5 EA2 fix version and the provider is present in the current source and distribution configuration.

**Test Coverage**

- **Risk:** Mocked transport tests do not prove live Anthropic authentication, tool completion, or MCP interaction.
  - **Mitigation:** Run deployed-distribution scenarios with valid credentials and retain partial-coverage tags until live gaps are exercised.
  - *Areas with reduced coverage:* Live authentication, responses-API tool calling, and MCP integration.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Anthropic service availability, rate limits, or credential restrictions may block end-to-end execution.
  - **Mitigation:** Keep deterministic provider-level tests in CI and schedule live scenarios with retry windows and controlled request volume.
  - *Missing resources or infrastructure:* Valid live credentials and reliable external API egress.
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Mitigation:** No risk identified — all in-scope requirements have observable API, configuration, or deployment outcomes.

**Resource Constraints**

- **Mitigation:** No risk identified — existing QE automation capacity is sufficient; live API usage is bounded by the scenario set.

**Dependencies**

- **Mitigation:** No risk identified — the current source includes the provider and SDK dependency, while the downstream image and AIPCC wheel availability remain entry criteria.

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[REQ-RHAISTRAT-1246-01]** — As an administrator, I want the deployed distribution to include the native Anthropic provider.
  - *Test Scenario:* **TS-01**: [functional] Verify provider appears after deployment
    - *Priority:* P0

- **[REQ-RHAISTRAT-1246-02]** — As an administrator, I want to configure Claude models without the OpenAI-compatible workaround.
  - *Test Scenario:* **TS-02**: [functional] Verify configuration without header workaround
    - *Priority:* P0

- **[REQ-RHAISTRAT-1246-03]** — As an application developer, I want streaming responses to preserve temperature and sampling controls.
  - *Test Scenario:* **TS-03**: [integration] [PARTIAL_COVERAGE] Verify streaming completion with temperature
    - *Priority:* P0
    - *Upstream coverage:* partial (existing tests verify streaming and temperature separately against a configured server)
    - *Downstream required:* yes
    - *Covered by:* `test_messages_streaming_basic`, `test_messages_non_streaming_with_temperature`

- **[REQ-RHAISTRAT-1246-04]** — As an application developer, I want tool calls to work through both chat and responses workflows.
  - *Test Scenario:* **TS-04**: [e2e] [PARTIAL_COVERAGE] Verify tool calls across both APIs
    - *Priority:* P0
    - *Upstream coverage:* partial (existing tests cover message tool use and tool-schema normalization, not a complete responses workflow)
    - *Downstream required:* yes
    - *Covered by:* `test_messages_with_tool_definitions`, `test_empty_tool_parameters_normalized`

- **[REQ-RHAISTRAT-1246-05]** — As an application developer, I want MCP tools to work with Anthropic models.
  - *Test Scenario:* **TS-05**: [e2e] Verify MCP tool use with Anthropic model
    - *Priority:* P1

- **[REQ-RHAISTRAT-1246-06]** — As an application developer, I want each request to use its own Anthropic credential.
  - *Test Scenario:* **TS-06**: [functional] [PARTIAL_COVERAGE] Verify per-request credential override
    - *Priority:* P1
    - *Upstream coverage:* partial (existing test verifies the selected credential on a mocked request)
    - *Downstream required:* yes
    - *Covered by:* `test_provider_data_api_key_overrides_config`
  - *Test Scenario:* **TS-07**: [e2e] Verify concurrent credential isolation
    - *Priority:* P1

- **[REQ-RHAISTRAT-1246-07]** — As an application developer, I want to discover available Anthropic models.
  - *Test Scenario:* **TS-08**: [functional] [PARTIAL_COVERAGE] Verify Anthropic model listing format
    - *Priority:* P1
    - *Upstream coverage:* partial (existing test verifies native response shape; deployed provider visibility remains uncovered)
    - *Downstream required:* yes
    - *Covered by:* `test_models_list_anthropic_sdk_response_shape`

- **[REQ-RHAISTRAT-1246-08]** — As an application developer, I want credential and model errors to fail safely.
  - *Test Scenario:* **TS-09**: [functional] [PARTIAL_COVERAGE] Verify authentication failure without credential leakage
    - *Priority:* P1
    - *Upstream coverage:* partial (existing test verifies failure before an upstream request)
    - *Downstream required:* yes
    - *Covered by:* `test_missing_api_key_fails_with_a_hint_and_sends_nothing`
  - *Test Scenario:* **TS-10**: [functional] Verify malformed credential override rejection
    - *Priority:* P1
  - *Test Scenario:* **TS-11**: [functional] Verify unsupported model rejection
    - *Priority:* P2

- **[REQ-RHAISTRAT-1246-09]** — As an administrator, I want existing provider configurations to remain usable after migration or upgrade.
  - *Test Scenario:* **TS-12**: [e2e] Verify migration preserves provider configuration
    - *Priority:* P1

- **[REQ-RHAISTRAT-1246-10]** — As an administrator, I want current guidance for Anthropic configuration and embeddings.
  - *Test Scenario:* **TS-13**: [functional] Verify configuration and embedding guidance
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
  - Product Manager: [Name / @github-handle]
