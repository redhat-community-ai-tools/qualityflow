# Test Plan

## **Enable remote::gemini provider in OGX (previously Llama Stack) - Quality Engineering Plan**

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
- **Participating SIGs:** AIPCC (wheel delivery), Documentation (Gemini examples)

**Document Conventions (if applicable):**

- **OGX:** The project previously called Llama Stack.
- **Native Gemini provider:** The Gemini-specific backend exposed through the existing OpenAI-compatible client APIs.
- **MCP:** Model Context Protocol, used to connect model workflows to external tools.
- **Provider data:** Request-specific provider credentials that can override deployment credentials.

### **Feature Overview**

Users can connect Gemini models to RHOAI and use chat, embeddings, and external tools through the existing client interfaces. Native Gemini support removes the need for custom authentication workarounds and addresses embedding responses that omit usage statistics. This plan covers the Dev Preview in 3.5 EA2 RHOAI RELEASE, including request-specific credentials and published configuration examples.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the nine original acceptance criteria in RHAISTRAT-1245 and the source RFE.
    - Compared parent onboarding scope and direct platform, integration, and documentation links.
    - Distinguished original requirements from the description's proposed AI-generated strategy.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Customers can use Gemini for chat and embeddings through their existing RHOAI client interface.
  - *List the customer use cases identified:*
    - As an application developer, I want to generate chat answers and embeddings using Gemini.
    - As an application user, I want my requests to use my own credentials.
    - As an application developer, I want Gemini to use external tools to answer questions.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Observable outcomes are available for all original acceptance criteria.
    - Release-specific header compatibility and native Responses tool support require clarification; see Risks.
    - No live API validation or downstream packaging verification was performed during plan preparation.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Native Gemini is available in the downstream distribution.
    - Users configure Gemini without custom authentication headers.
    - Embeddings succeed when the upstream response omits usage statistics.
    - Chat produces responses with streaming and supported temperature settings.
    - Function tools complete through chat completions.
    - Request-specific Gemini credentials override the configured key using the original acceptance criterion's provider-data header.
    - Gemini completes workflows with MCP servers.
    - Published documentation includes usable Gemini configuration examples.
    - The covered functionality is validated against Gemini's OpenAI-compatible endpoint.
  - *Note any gaps or missing criteria:*
    - Exact model selection, release-supported header names and acceptable upstream error categories need release-owner confirmation.
    - No latency, throughput or maximum-concurrency target is specified.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: a request uses only its selected Gemini credential, including when that credential is invalid.
    - Security: returned authentication errors do not expose credential values.
  - *Note any NFRs not covered and why:*
    - Performance and scale targets are unspecified; this cycle makes no latency or capacity claim.
    - No new metrics or alerts are required by the original acceptance criteria.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **The generic OpenAI workaround has documented Gemini compatibility gaps**
  - The ticket reports missing-usage embedding failures, static custom credentials, schema incompatibilities and Responses function-tool rejection with that workaround. Native-provider resolution of every gap is not established by this plan.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Design-phase QE kickoff should establish the acceptance contract before implementation testing.
    - Record the kickoff owner and date: [Name/Date].
    - This retrospective plan does not establish that a kickoff occurred.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Gemini embedding responses omit usage; the adapter supplies usage defaults.
    - Shared chat processing forwards temperature and function tools and normalizes streaming usage.
    - Jira names x-llamastack-provider-data, while the checked source consumes x-ogx-provider-data; both use gemini_api_key.
    - No Gemini-specific schema filter was confirmed in the adapter; tool-schema support must follow the release contract.
    - Upstream provider registration and configuration do not prove downstream image inclusion.
  - *Impact on testing approach:*
    - Validate against the release image and live Gemini endpoint, with controlled missing-usage and invalid-input cases.
    - Treat tests from detached checkouts as context, without suppressing downstream acceptance scenarios.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Existing chat, embeddings and provider discovery APIs gain the Gemini backend.
    - Users can select request-specific Gemini credentials and use MCP tools.
  - *Testing impact:*
    - Verify observable chat, embedding, tool and authentication outcomes through the public client interfaces.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Use the project's multi-node OpenShift topology with at least three worker nodes.
    - Provide outbound access to Gemini and an independently reachable MCP server.
  - *Impact on test design:*
    - Separate remote-service failures from distribution deployment failures.
    - No multi-cloud cluster matrix is required for this API-only backend addition.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate downstream native Gemini availability, chat with streaming and temperature, missing-usage embeddings, chat function tools, per-request authentication, MCP workflows and published examples for the Dev Preview in 3.5 EA2 RHOAI RELEASE. Exercise these capabilities against Gemini's OpenAI-compatible endpoint and verify Gemini configuration across supported deployment lifecycle changes.

**Testing Goals**

- **[P0]** As an application developer, verify Gemini chat, embeddings and function tools return usable results.
- **[P0]** As an application user, verify each Gemini request uses only its intended credentials.
- **[P1]** As an application developer, verify invalid inputs and remote-service failures produce actionable errors.
- **[P1]** As an application developer, verify published examples and MCP workflows complete with Gemini.
- **[P1]** As an administrator, verify Gemini configuration remains usable through supported lifecycle changes.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Dashboard-specific Gemini UI and per-user token management**
  - *Rationale:* The ticket assigns these to separate dashboard work or a future release; backend request authentication remains in scope.
  - *PM/Lead Agreement:* [Name/Date]
- **Vertex AI and native Google Interactions protocol support**
  - *Rationale:* These are separate providers or protocol work, outside native Gemini through the OpenAI-compatible endpoint.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Plan preparation could not inspect GitHub PR diffs or the downstream distribution checkout**
  - Acceptance execution must use the release image and confirm packaging and docs before testing; this constraint does not waive any original acceptance criterion.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Cover the Section III native-provider behaviors through the release image and the Gemini OpenAI-compatible endpoint.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Use the established Python test conventions for repeatable provider and workflow checks; documentation examples require an execution-backed check.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve chat, embeddings and tool behavior for existing OpenAI providers. Retain legacy workaround behavior only to its established capability, not native-provider parity. Existing-test search ran on both checkouts; detached revisions were treated as context, so no downstream acceptance scenario was suppressed.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — no new self-test or diagnostic package is specified; provider availability is covered as a functional behavior.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A — no feature-specific latency or throughput target is specified.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A — no feature-specific capacity target is specified. Credential isolation is tested across interleaved requests without claiming production-scale validation.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Verify request credential precedence, invalid-override rejection, user isolation and absence of credentials in authentication errors.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — the backend is API-only; dashboard UI is an explicit scope exclusion.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new Gemini metrics or alerts are required; observable API failures remain functional checks.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Validate Gemini through the OpenAI-compatible API and resolve legacy/current provider-data header compatibility for the target release. Preserve existing provider behavior under Regression Testing.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Gemini connection configuration is persisted in user-managed deployment configuration. Verify it remains usable after a supported upgrade to the target release; the source release and route require release-owner confirmation before execution.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* AIPCC must deliver any required Gemini dependency wheels for the downstream release image; Documentation must deliver Gemini examples. Confirm delivery with the release owner; documentation tracking is RHAIENG-5268 (release note only, not proof that configuration examples exist).

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Validate model inference with MCP tools and deployment configuration supplied through the existing operator-supported workflow. AIPCC and Documentation supply artifacts; OGX Core owns provider acceptance checks.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — Gemini endpoint access is required, but no multi-cloud hosting feature is introduced.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least three worker nodes, per project environment.yaml.

- **Platform & Product Version(s):** Product: 3.5 EA2 RHOAI RELEASE. OpenShift version: release-supported version to be confirmed before execution; project config specifies no version.

- **CPU Virtualization:** N/A — no CPU virtualization capability is exercised.

- **Compute Resources:** Capacity for the distribution service and an MCP tool service; model computation is remote.

- **Special Hardware:** N/A — Gemini inference requires no local accelerator.

- **Storage:** Persist the user deployment configuration and Secret references across restart and the supported upgrade route; no special storage backend is required.

- **Network:** Outbound TLS to Gemini's OpenAI-compatible endpoint and the MCP server, with a controlled means to simulate unavailable endpoints.

- **Required Operators:** The RHOAI-supported distribution operator for the target release, using its existing user-configuration support.

- **Platform:** OpenShift with the release-supported RHOAI distribution image; upstream source is analysis context, not the image under acceptance.

- **Special Configurations:** Distinct valid and invalid Gemini test credentials from protected Secrets; an embedding model and a chat model approved for this release; a safe MCP tool; default and request-specific credential modes.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required.

- **CI/CD:** Standard tooling — no additional tools required.

- **Other Tools:** No additional tool requirement identified.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Confirm release-image inclusion of the Gemini provider and required AIPCC wheels.
- [ ] Confirm the target release's provider-data header contract, including the original x-llamastack-provider-data acceptance criterion and current x-ogx-provider-data naming.
- [ ] Confirm supported models, temperature range, schema-field restrictions and upstream error categories.
- [ ] Provide two distinct test credentials and a safe MCP service without recording credential values.
- [ ] Confirm the supported OpenShift version, upgrade source release and configuration-preservation route.
- [ ] Locate the published downstream configuration examples; a release note alone is insufficient.
- [ ] Obtain human review of the risks, limitations and scope exclusions.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** The closed feature and later automation records may refer to different release baselines
  - **Mitigation:** Confirm the image digest and supported lifecycle route with the delivery owner before scheduling execution
  - *Estimated impact on schedule:* Baseline confirmation needed before execution; duration requires owner agreement
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Header naming and schema handling may differ between Jira and the target release
  - **Mitigation:** Keep legacy-header and schema-contract checks in scope; resolve discrepancies with the release owner before acceptance
  - *Areas with reduced coverage:* Native Responses function-tool support remains an open question, not an asserted supported capability
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Live Gemini service behavior may change between validation runs
  - **Mitigation:** Pin the approved model and record endpoint errors and service version information without secrets
  - *Missing resources or infrastructure:* No missing resource is asserted; external service stability is uncertain
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Mitigation:** No risk identified — all original acceptance criteria have observable checks once entry criteria are met. For the additional native Responses question, see the Test Coverage risk.

**Resource Constraints**

- **Risk:** Credential ownership or API quota may interrupt repeated validation
  - **Mitigation:** Reserve protected test credentials and agree a bounded request budget before running the suite
  - *Current capacity gaps:* No measured capacity shortfall; quota and credential availability require confirmation
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Required downstream wheels or configuration examples may not match the release image
  - **Mitigation:** Confirm dependency delivery with AIPCC and example delivery with Documentation before entry criteria are accepted
  - *Dependent teams or components:* AIPCC, Documentation, OGX Core
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-1245]** — As a user, I want to use native Gemini models in the downstream distribution
  - *Test Scenario:* **TS-01**: [functional] Verify native Gemini availability in downstream deployments
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify unavailable provider produces an actionable error
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to receive Gemini chat responses with supported generation options
  - *Test Scenario:* **TS-03**: [functional] Verify Gemini chat completes with supported temperature settings
    - *Priority:* P0
  - *Test Scenario:* **TS-04**: [functional] Verify Gemini streaming delivers content through completion
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [functional] Verify unknown Gemini models return a descriptive error
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [functional] Verify interrupted Gemini streams report failure without hanging
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to generate Gemini embeddings even without usage statistics
  - *Test Scenario:* **TS-07**: [functional] Verify embeddings succeed when usage statistics are absent
    - *Priority:* P0
  - *Test Scenario:* **TS-08**: [functional] Verify batched embeddings preserve input ordering and dimensions
    - *Priority:* P1
  - *Test Scenario:* **TS-09**: [functional] Verify unsupported embedding inputs are rejected clearly
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to use Gemini function tools through chat completions
  - *Test Scenario:* **TS-10**: [integration] Verify Gemini tool calls complete a function roundtrip
    - *Priority:* P0
  - *Test Scenario:* **TS-11**: [functional] Verify malformed Gemini tool definitions return clear errors
    - *Priority:* P1
  - *Test Scenario:* **TS-12**: [integration] Verify tool schemas follow supported Gemini field restrictions
    - *Priority:* P2

- **[RHAISTRAT-1245]** — As a user, I want to authenticate each Gemini request with the intended credentials
  - *Test Scenario:* **TS-13**: [integration] Verify request credentials override configured Gemini credentials
    - *Priority:* P0
  - *Test Scenario:* **TS-14**: [integration] Verify legacy provider headers override configured Gemini credentials
    - *Priority:* P1
  - *Test Scenario:* **TS-15**: [functional] Verify omitted overrides use configured Gemini credentials
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [integration] Verify invalid overrides cannot use valid configured credentials
    - *Priority:* P1
  - *Test Scenario:* **TS-17**: [integration] Verify interleaved users retain separate Gemini request credentials
    - *Priority:* P0
  - *Test Scenario:* **TS-18**: [functional] Verify failed authentication reveals no Gemini credentials
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to complete Gemini workflows with MCP server tools
  - *Test Scenario:* **TS-19**: [e2e] Verify Gemini MCP tool results produce final answers
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [integration] Verify unavailable MCP tools produce an observable failure
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to configure Gemini from published examples without custom authentication workarounds
  - *Test Scenario:* **TS-21**: [e2e] Verify documented Gemini configuration enables chat and embeddings
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [functional] Verify missing Gemini credentials produce an actionable error
    - *Priority:* P1

- **[RHAISTRAT-1245]** — As a user, I want to retain Gemini configuration across supported deployment lifecycle changes
  - *Test Scenario:* **TS-23**: [e2e] Verify Gemini configuration survives restart and supported upgrade
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [integration] Verify unavailable Gemini endpoint fails then recovers
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
