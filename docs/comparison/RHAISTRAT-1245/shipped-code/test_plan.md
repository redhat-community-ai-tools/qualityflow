# Test Plan

## **Enable remote::gemini provider in OGX - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1331](https://redhat.atlassian.net/browse/RHAIRFE-1331)
- **Feature Tracking:** [RHAISTRAT-1350](https://redhat.atlassian.net/browse/RHAISTRAT-1350)
- **Epic Tracking:** [RHAISTRAT-1245](https://redhat.atlassian.net/browse/RHAISTRAT-1245)
- **Feature Maturity:**
  - DP: 3.5 EA2 RHOAI RELEASE
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** N/A

**Document Conventions (if applicable):**

- **OGX:** The downstream distribution formerly known as Llama Stack.
- **remote::gemini:** The native Gemini inference provider type.
- **Provider-data header:** A per-request header used to override provider configuration.
- **MCP:** Model Context Protocol, used to connect models to external tools.

### **Feature Overview**

OGX users can configure Gemini models through a native `remote::gemini` provider instead of a generic OpenAI-compatible workaround. The provider supports Gemini authentication, chat completions, embeddings, tool calling, and per-request API-key overrides. This removes provider-specific compatibility gaps while preserving existing remote providers. The feature is Dev Preview in RHOAI 3.5 EA2.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Include the native Gemini provider in the downstream OGX distribution.
    - Preserve Gemini authentication, embeddings, chat completions, and tool-calling behavior.
    - Support per-request API-key overrides without static network-header workarounds.
    - Preserve behavior of existing remote providers.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Customers can use Gemini models directly with full OGX functionality instead of a limited OpenAI-compatible workaround.
  - *List the customer use cases identified:*
    - As a model consumer, I want to chat with Gemini models through OGX.
    - As an application developer, I want Gemini embeddings without provider-specific failures.
    - As a tenant operator, I want to override the configured Gemini key for a single request.
    - As a platform administrator, I want existing providers to remain available after Gemini is enabled.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - None. The acceptance criteria define observable outcomes.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - The `remote::gemini` provider is available in downstream OGX distributions.
    - Gemini models can be configured using `provider_type: remote::gemini` without network-header workarounds.
    - Gemini embeddings handle missing usage statistics.
    - Gemini chat completions support streaming and temperature parameters.
    - Tool calling works through chat completions.
    - Provider-data headers with `gemini_api_key` override configured keys per request.
    - MCP servers work with Gemini models.
    - Documentation is updated with Gemini configuration examples.
    - All functionality is validated against Gemini's OpenAI-compatible endpoint.
  - *Note any gaps or missing criteria:* No gaps identified.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: Gemini API keys must not appear in pod specs, logs, or API responses.
    - Compatibility: Existing remote providers must continue to work.
    - Availability: The provider activates only when a Gemini credential is configured.
  - *Note any NFRs not covered and why:* Performance and scale targets are not specified in the ticket.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

- **Gemini tool calling is supported through chat completions, not the Responses API**
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* Design review identified provider-specific schema translation, missing embedding usage statistics, and credential isolation as the main test risks.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Gemini and OpenAI-compatible schemas differ for tool definitions.
    - Gemini may omit embedding usage statistics.
    - Provider activation depends on secret injection.
  - *Impact on testing approach:* Tests must exercise real Gemini requests and inspect provider behavior rather than only configuration syntax.

- [x] **API Extensions**
  - *List new or modified APIs:* The user-facing provider list and OpenAI-compatible inference APIs gain a native Gemini provider.
  - *Testing impact:* Verify provider registration, model discovery, chat, embeddings, tools, and per-request authentication.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A standard OGX deployment with a Gemini credential is sufficient; no special cluster topology is required.
  - *Impact on test design:* Tests can run in the existing OGX integration environment.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan covers native Gemini provider registration, deployment activation, chat completions, embeddings, tool calling, per-request authentication, MCP interoperability, security, documentation, and regression against existing providers. It applies to the Dev Preview release in RHOAI 3.5 EA2.

**Testing Goals**

- **[P0]** As a model consumer, verify Gemini provider registration and activation.
- **[P0]** As a model consumer, verify Gemini chat completions and embeddings.
- **[P0]** As an application developer, verify Gemini tool calling.
- **[P1]** As a tenant operator, verify per-request Gemini authentication.
- **[P1]** As a platform administrator, verify existing providers remain available.
- **[P1]** As a security reviewer, verify Gemini credentials remain secret.
- **[P2]** As an integration developer, verify Gemini works with MCP servers.
- **[P2]** As a platform user, verify Gemini configuration documentation is complete.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Gen AI Studio UI**
  - *Rationale:* UI work is owned by the dashboard team.
  - *PM/Lead Agreement:* [Name/Date]

- **Per-user token management in the dashboard**
  - *Rationale:* Planned for a future release.
  - *PM/Lead Agreement:* [Name/Date]

- **Google Vertex AI provider**
  - *Rationale:* Already supported separately.
  - *PM/Lead Agreement:* [Name/Date]

- **Google Interactions API protocol**
  - *Rationale:* Tracked separately in RHAISTRAT-1509.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Live Gemini API access**
  - *Sign-off:* [Name/Date]

- **MCP harness selection**
  - *Sign-off:* [Name/Date]

- **TLS handshake capture**
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Verify provider registration, chat, embeddings, tools, authentication, and MCP behavior.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Existing pytest coverage is present in the OGX integration suite.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Verify existing remote providers remain listed and usable.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Not required for this Dev Preview feature.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* No performance target is specified.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* No scale target is specified.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Verify credential isolation and TLS enforcement.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* No UI changes are in scope.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* No new monitoring requirement is specified.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Verify the provider works with Gemini's OpenAI-compatible endpoint.

- [ ] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* The provider is additive and introduces no persistent state migration.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* Requires a valid Gemini API key and available Gemini models.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Verify MCP interoperability and existing provider coexistence.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* No cloud-specific behavior is introduced.

#### **3. Test Environment**

- **Cluster Topology:** Standard multi-node OpenShift cluster.
- **Platform & Product Version(s):** RHOAI 3.5 EA2, OGX Dev Preview.
- **CPU Virtualization:** Not applicable.
- **Compute Resources:** Standard OGX integration-test worker resources.
- **Special Hardware:** None.
- **Storage:** Standard OGX distribution storage.
- **Network:** Egress to Gemini's OpenAI-compatible endpoint.
- **Required Operators:** OGX distribution operator.
- **Platform:** OpenShift.
- **Special Configurations:** Gemini API key injected from a Kubernetes Secret.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard pytest integration framework.
- **CI/CD:** Existing OGX integration pipeline.
- **Other Tools:** Standard tooling — no additional tools required.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] A valid Gemini API key is available
- [ ] At least one Gemini LLM and embedding model are configured
- [ ] Existing remote providers are available for regression checks

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Gemini API behavior may change between upstream OGX and the RHOAI release.
  - **Mitigation:** Pin the OGX version and monitor upstream Gemini fixes.
  - *Estimated impact on schedule:* 1-2 weeks
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** MCP and TLS checks depend on harnesses that are not yet complete.
  - **Mitigation:** Track the incomplete checks explicitly and complete the harnesses before GA.
  - *Areas with reduced coverage:* MCP interoperability and TLS inspection
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Live Gemini access may be unavailable in some test environments.
  - **Mitigation:** Run the suite only in connected environments with a valid key.
  - *Missing resources or infrastructure:* External Gemini API access
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Responses API tool calling is not supported for Gemini.
  - **Mitigation:** Document chat completions as the supported tool-calling path.
  - *Alternative validation approach:* Verify the documented limitation and supported workflow.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — the feature uses the existing OGX integration environment.

**Dependencies**

- **Risk:** AIPCC wheel availability may block downstream packaging.
  - **Mitigation:** Confirm dependency availability before release.
  - *Dependent teams or components:* AIPCC pipeline
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[REQ-RHAISTRAT-1245-01]** — As a platform administrator, I want Gemini to appear only when a valid credential is configured.
  - *Test Scenario:* **TS-01**: [functional] [EXISTING_COVERAGE] Verify Gemini provider is listed
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts provider visibility)
    - *Downstream required:* yes
    - *Covered by:* `test_gemini_provider_listed`
  - *Test Scenario:* **TS-02**: [functional] [EXISTING_COVERAGE] Verify Gemini works without header workarounds
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts native provider configuration)
    - *Downstream required:* yes
    - *Covered by:* `test_gemini_provider_no_network_headers_workaround`
  - *Test Scenario:* **TS-03**: [functional] [EXISTING_COVERAGE] Verify Gemini activates with configured key
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts activation)
    - *Downstream required:* yes
    - *Covered by:* `test_gemini_conditional_activation_with_key`
  - *Test Scenario:* **TS-04**: [functional] [NEW] Verify provider remains inactive without key
    - *Priority:* P1

- **[REQ-RHAISTRAT-1245-02]** — As a model consumer, I want Gemini chat completions to return valid responses.
  - *Test Scenario:* **TS-05**: [functional] [EXISTING_COVERAGE] Verify non-streaming Gemini chat completion
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts response content)
    - *Downstream required:* yes
    - *Covered by:* `test_non_streaming_chat_completion`
  - *Test Scenario:* **TS-06**: [functional] [EXISTING_COVERAGE] Verify streaming Gemini chat completion
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts stream termination)
    - *Downstream required:* yes
    - *Covered by:* `test_streaming_chat_completion`
  - *Test Scenario:* **TS-07**: [functional] [EXISTING_COVERAGE] Verify temperature parameter is accepted
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts parameter acceptance)
    - *Downstream required:* yes
    - *Covered by:* `test_temperature_controls_variability`
  - *Test Scenario:* **TS-08**: [functional] [NEW] Verify unreachable endpoint returns actionable error
    - *Priority:* P1

- **[REQ-RHAISTRAT-1245-03]** — As an application developer, I want Gemini embeddings to work even when usage statistics are absent.
  - *Test Scenario:* **TS-09**: [functional] [EXISTING_COVERAGE] Verify Gemini embedding generation
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts embedding vectors)
    - *Downstream required:* yes
    - *Covered by:* `test_embedding_generation`
  - *Test Scenario:* **TS-10**: [functional] [EXISTING_COVERAGE] Verify missing embedding usage is handled
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts response completion)
    - *Downstream required:* yes
    - *Covered by:* `test_embedding_missing_usage_handled`

- **[REQ-RHAISTRAT-1245-04]** — As an application developer, I want Gemini tool calls to use compatible schemas.
  - *Test Scenario:* **TS-11**: [functional] [EXISTING_COVERAGE] Verify Gemini tool calling
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts tool-call output)
    - *Downstream required:* yes
    - *Covered by:* `test_tool_calling`
  - *Test Scenario:* **TS-12**: [functional] [EXISTING_COVERAGE] Verify unsupported schema fields are filtered
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts successful completion)
    - *Downstream required:* yes
    - *Covered by:* `test_tool_calling_with_unsupported_schema_fields`

- **[REQ-RHAISTRAT-1245-05]** — As a tenant operator, I want to override the configured Gemini key for one request.
  - *Test Scenario:* **TS-13**: [functional] [EXISTING_COVERAGE] Verify per-request key override
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts successful authentication)
    - *Downstream required:* yes
    - *Covered by:* `test_per_request_api_key_override`
  - *Test Scenario:* **TS-14**: [functional] [EXISTING_COVERAGE] Verify invalid per-request key errors
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts 4xx rejection)
    - *Downstream required:* yes
    - *Covered by:* `test_invalid_per_request_api_key_errors`
  - *Test Scenario:* **TS-15**: [functional] [NEW] Verify invalid configured key returns auth error
    - *Priority:* P1

- **[REQ-RHAISTRAT-1245-06]** — As an integration developer, I want Gemini models to work with MCP servers.
  - *Test Scenario:* **TS-16**: [integration] [PARTIAL_COVERAGE] Verify Gemini MCP server connectivity
    - *Priority:* P2
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts prerequisite only)
    - *Downstream required:* yes

- **[REQ-RHAISTRAT-1245-07]** — As a platform administrator, I want the distribution to package and activate Gemini correctly.
  - *Test Scenario:* **TS-17**: [functional] [EXISTING_COVERAGE] Verify image includes Gemini and google-genai
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts package and provider)
    - *Downstream required:* yes
    - *Covered by:* `test_build_includes_gemini_and_google_genai`
  - *Test Scenario:* **TS-18**: [functional] [EXISTING_COVERAGE] Verify conditional activation pattern
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts configuration)
    - *Downstream required:* yes
    - *Covered by:* `test_config_conditional_activation_pattern`
  - *Test Scenario:* **TS-19**: [functional] [EXISTING_COVERAGE] Verify operator injects Gemini key
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts secret injection)
    - *Downstream required:* yes
    - *Covered by:* `test_operator_injects_gemini_api_key`

- **[REQ-RHAISTRAT-1245-08]** — As a platform administrator, I want existing providers to remain available after Gemini is enabled.
  - *Test Scenario:* **TS-20**: [functional] [EXISTING_COVERAGE] Verify remote OpenAI remains usable
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts coexistence)
    - *Downstream required:* yes
    - *Covered by:* `test_remote_openai_unaffected`
  - *Test Scenario:* **TS-21**: [functional] [EXISTING_COVERAGE] Verify other providers remain usable
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts non-Gemini inference)
    - *Downstream required:* yes
    - *Covered by:* `test_other_providers_unaffected`

- **[REQ-RHAISTRAT-1245-09]** — As a security reviewer, I want Gemini credentials to remain protected.
  - *Test Scenario:* **TS-22**: [functional] [EXISTING_COVERAGE] Verify API key is not exposed
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts logs and responses)
    - *Downstream required:* yes
    - *Covered by:* `test_api_key_not_exposed`
  - *Test Scenario:* **TS-23**: [functional] [PARTIAL_COVERAGE] Verify TLS is enforced for egress
    - *Priority:* P2
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts prerequisite only)
    - *Downstream required:* yes

- **[REQ-RHAISTRAT-1245-10]** — As a model consumer, I want complete Gemini workflows to work end to end.
  - *Test Scenario:* **TS-24**: [e2e] [EXISTING_COVERAGE] Verify deployment and chat completion workflow
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts provider and response)
    - *Downstream required:* yes
    - *Covered by:* `test_deploy_and_chat_completion`
  - *Test Scenario:* **TS-25**: [e2e] [EXISTING_COVERAGE] Verify full tool-calling workflow
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts tool result)
    - *Downstream required:* yes
    - *Covered by:* `test_full_tool_calling_workflow`
  - *Test Scenario:* **TS-26**: [e2e] [EXISTING_COVERAGE] Verify embedding generation end to end
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts embedding consistency)
    - *Downstream required:* yes
    - *Covered by:* `test_embedding_generation_end_to_end`
  - *Test Scenario:* **TS-27**: [e2e] [EXISTING_COVERAGE] Verify multi-tenant per-request keys
    - *Priority:* P2
    - *Upstream coverage:* opendatahub-io/opendatahub-tests#2187 — partial (asserts distinct key use)
    - *Downstream required:* yes
    - *Covered by:* `test_multi_tenant_per_request_keys`

- **[REQ-RHAISTRAT-1245-11]** — As a platform user, I want complete Gemini configuration documentation.
  - *Test Scenario:* **TS-28**: [functional] [NEW] Verify documentation includes Gemini configuration examples
    - *Priority:* P2

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name] / @[handle]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name]
