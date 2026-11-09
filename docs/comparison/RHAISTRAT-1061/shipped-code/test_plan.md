# Test Plan

## **Introduce runtime config in LlamaStackDistribution - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** No separate enhancement proposal supplied; scope dependency: [RHAISTRAT-1373](https://redhat.atlassian.net/browse/RHAISTRAT-1373).
- **Feature Tracking:** [RHAISTRAT-1353](https://redhat.atlassian.net/browse/RHAISTRAT-1353)
- **Epic Tracking:** [RHAISTRAT-1061](https://redhat.atlassian.net/browse/RHAISTRAT-1061)
- **Feature Maturity:**
  - DP: N/A
  - TP: 3.5 EA2 RHOAI RELEASE
  - GA: [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** Documentation

**Document Conventions (if applicable):**

- **OGX:** Current project name used by the server API; the ticket retains the former Llama Stack name.
- **Runtime configuration:** Server settings for providers, models, storage, and available APIs.
- **Provider:** A backend that supplies a configured server capability.
- **Praxis mode:** An opt-in deployment mode in which Praxis serves selected APIs and the operator adjusts the generated configuration accordingly.

### **Feature Overview**

Administrators can declare runtime settings alongside their server deployment instead of maintaining a complete configuration template. This reduces version-specific configuration work and makes deployment changes easier to manage. Users can retain a complete custom configuration when needed. This plan covers the Technology Preview in 3.5 EA2 RHOAI RELEASE, including configuration changes, credential protection, and preservation across supported upgrades.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the main ticket description and current release notes.
    - Compared the six direct linked issues for scope changes and delivery dependencies.
    - Distinguished the original API proposal from the renamed release API.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* 
    - Reduces the need to understand and maintain a complete versioned runtime template.
  - *List the customer use cases identified:*
    - As an admin, I want to configure providers and models through deployment settings.
    - As an existing user, I want to retain my runtime settings during migration.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Behaviors are observable through requests, stored data, and reported configuration errors.
    - The main ticket has no explicit acceptance-criteria field; release owners must confirm the description-derived expectations before execution.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Users can deploy supported runtime settings without creating a complete custom template.
    - Omitted settings use compatible distribution defaults.
    - Invalid or contradictory settings produce actionable errors.
    - Changes to runtime settings take effect in the running server.
    - Users retain a complete custom configuration option.
    - Supported upgrades and documented manual migration preserve chosen settings.
    - Published configuration examples produce usable deployments.
  - *Note any gaps or missing criteria:* 
    - Supported source upgrade version and final field coverage require release-owner confirmation.
    - Original automatic-migration wording is superseded by the renamed API migration contract.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Credential confidentiality: generated non-secret configuration must contain no secret values.
    - Persistence: chosen configuration and stored data survive supported restart and upgrade workflows.
  - *Note any NFRs not covered and why:*
    - No latency, throughput, or concurrency target is supplied for this feature.
    - No new metrics, alerts, or UI are specified.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

- **Only the documented runtime-settings subset is supported**
  - Unsupported fields remain available only through a complete custom configuration.
  - *Sign-off:* [Name/Date]
- **Legacy resources require manual migration**
  - The renamed API does not provide automatic conversion or coexistence; users create a new resource and transfer configuration.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* 
    - Design-phase QE kickoff should establish the final schema and migration contract before implementation changes.
    - Kickoff owner/date: [Name/Date].

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Generated configuration must match the selected distribution image and preserve secret references.
    - Older design material describes an API version proposal; the renamed implementation uses a new kind and manual migration.
    - Runtime configuration intersects provider selection, storage, API availability, and rollout behavior.
  - *Impact on testing approach:* 
    - Confirm the release build includes generation before execution.
    - Exercise success and failure paths through server requests and configuration status.
    - Do not assume every capability in the original draft design is implemented.

- [x] **API Extensions**
  - *List new or modified APIs:* 
    - Declarative provider, model, storage, and API selections extend server configuration.
    - Custom configuration remains available as an alternative.
  - *Testing impact:* 
    - Validate safe inputs, error feedback, configuration updates, and manual migration on the release API.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* 
    - Multi-node OpenShift cluster with at least three workers, matching project requirements.
  - *Impact on test design:* 
    - Use isolated namespaces for independent server deployments.
    - Use the same storage and provider endpoints across restart and upgrade comparisons.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate Technology Preview runtime configuration for 3.5 EA2 RHOAI RELEASE: distribution defaults, documented examples, provider and model selection, API availability, persistent storage, protected credentials, configuration updates, custom configuration alternatives, supported upgrades, documented manual migration, and API-version compatibility.

**Testing Goals**

- **[P0]** As an admin, verify declared runtime settings provide a usable server.
- **[P1]** As an admin, verify invalid settings produce actionable errors without replacing a usable configuration.
- **[P1]** As an admin, verify configuration changes and credential rotation take effect reliably.
- **[P1]** As an existing user, verify migration and upgrades preserve chosen settings and stored data.
- **[P1]** As an admin, verify provider credentials remain protected in generated configuration.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Complete API deprecation and demo-repository validation**
  - *Rationale:* Safety/Shields and Evaluation removal are tracked by RHAIRFE-1435 and RHAIRFE-1436; demo maintenance is tracked by RHAISTRAT-1158. This plan covers their effect on runtime configuration, not their independent acceptance criteria.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Controller environment tests were not executable in this run**
  - The operator unit and CLI suites passed, and the Python helper suite passed, but the controller suite requires local control-plane binaries that were unavailable in this environment.
  - Recheck the controller suite in an environment with the required control-plane assets before release.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Validate distribution defaults, declared providers/models, API selections, custom configuration, and negative inputs.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate the listed behaviors using detected repository conventions; reserve human decisions for sign-offs and release-contract confirmation.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve inference, model listing, Responses, and vector-store workflows in the OGX Core regression suite.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* No dedicated self-validation package is specified; configuration failures are checked as functional error feedback.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A: no feature-specific latency or throughput target is provided.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A: no feature-specific production scale target is provided; successive updates test convergence rather than load capacity.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* New secret-to-runtime configuration handling must keep credential values out of generated non-secret configuration; missing and rotated credentials are exercised.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A: no UI is introduced; documented API examples are covered by functional testing.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A: no new metrics or alerts are specified.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Validate the current API, documented examples, and custom-configuration alternative on the release build.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Validate documented manual migration and supported upgrade preservation of chosen settings and stored data.

- [ ] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* No additional team deliverable remains; release-build and source-version confirmation are entry criteria.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Validate OGX Core, wrapper compatibility, documentation examples, and Praxis-mode interaction.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A: no cloud-specific behavior is specified; testing targets OpenShift.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least three worker nodes.

- **Platform & Product Version(s):** Open Data Hub (RHAISTRAT-1061), target 3.5 EA2 RHOAI RELEASE; exact supported OpenShift version: TBD by release owner.

- **CPU Virtualization:** N/A unless a selected provider requires hardware acceleration.

- **Compute Resources:** Sufficient CPU and memory for the OGX server, selected provider backends, and test workloads.

- **Special Hardware:** N/A unless a selected provider requires GPU or other accelerated hardware.

- **Storage:** Default storage class supporting persistent volume claims for restart and upgrade comparisons.

- **Network:** Internal provider endpoints and external access paths required by the selected scenarios.

- **Required Operators:** OGX operator build containing runtime configuration generation; Praxis gateway when Praxis mode is tested.

- **Platform:** OpenShift.

- **Special Configurations:** Namespace-scoped Secrets and ConfigMaps referenced by the server must carry `ogx.io/watch: "true"` and exist in the same namespace as the server.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Existing repository CI.

- **Other Tools:** `configgen` CLI for offline configuration generation and dry-run validation.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Release build containing runtime configuration generation is available
- [ ] Supported source upgrade version and final field coverage are confirmed by the release owner
- [ ] Test automation wrapper supports the release API

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Release-build or upgrade-contract confirmation may delay execution
  - **Mitigation:** Confirm the release build and source-version contract before starting P0 scenarios
  - *Estimated impact on schedule:* 1-2 weeks if confirmation is delayed
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Live server, restart, and upgrade workflows are only partially covered by current unit tests
  - **Mitigation:** Execute the end-to-end scenarios and retain partial-coverage tags until live behavior is verified
  - *Areas with reduced coverage:* Live data persistence, credential rotation, and complete manual migration
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Controller test environment may not be provisioned before release validation
  - **Mitigation:** Provision control-plane binaries and cluster access before executing the controller suite
  - *Missing resources or infrastructure:* Local control-plane binaries and cluster access
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Final field coverage is not confirmed in the source ticket
  - **Mitigation:** Obtain release-owner confirmation before executing field-coverage scenarios
  - *Alternative validation approach:* Compare documented examples with the release CRD schema
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — current QE capacity is sufficient for the planned scenarios.

**Dependencies**

- **Risk:** Wrapper or documentation may lag the release API
  - **Mitigation:** Verify the wrapper and documentation use the release API before starting migration validation
  - *Dependent teams or components:* OGX Core, wrapper/test maintainers, and Documentation
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-1061]** — As an admin, I want to deploy runtime settings without maintaining a complete configuration template
  - *Test Scenario:* **TS-01**: [functional] Verify documented minimal configuration starts a usable server
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] [EXISTING_COVERAGE] Verify omitted settings retain distribution defaults — covered by existing test TestGeneratePraxisDefaultConfigPreservesDefaultConfig
    - *Priority:* P1
  - *Test Scenario:* **TS-03**: [functional] [EXISTING_COVERAGE] Verify malformed and missing base configuration reports clear errors — covered by existing tests TestParseBaseConfig and TestRun
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want to configure providers and their models declaratively
  - *Test Scenario:* **TS-04**: [e2e] Verify declared providers and models serve inference requests
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [functional] [EXISTING_COVERAGE] Verify multiple providers retain distinct model assignments — covered by existing test TestExpandResources_DefaultProviderIsDeterministic
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [functional] [EXISTING_COVERAGE] Verify duplicate and unknown provider references are rejected — covered by existing test TestOGXServerCELValidation
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want to select available server APIs without contradictory settings
  - *Test Scenario:* **TS-07**: [functional] [EXISTING_COVERAGE] Verify disabled APIs are unavailable and conflicting selections are rejected — covered by existing tests TestGenerateConfig_DisabledAPIs and TestOGXServerCELValidation
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want persistent runtime storage and protected provider credentials
  - *Test Scenario:* **TS-08**: [e2e] [PARTIAL_COVERAGE] Verify declared storage preserves data across server restarts
    - *Priority:* P1
  - *Test Scenario:* **TS-09**: [integration] [PARTIAL_COVERAGE] Verify generated configuration never exposes secret values
    - *Priority:* P1
  - *Test Scenario:* **TS-10**: [e2e] Verify credential rotation restores authenticated provider access
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want runtime configuration changes to apply reliably
  - *Test Scenario:* **TS-11**: [e2e] [PARTIAL_COVERAGE] Verify updated runtime settings take effect without unnecessary restarts
    - *Priority:* P1
  - *Test Scenario:* **TS-12**: [functional] [EXISTING_COVERAGE] Verify custom configuration controls the running server and mixed modes are rejected — covered by existing tests TestReconcileGeneratedConfig_SkippedWhenOverrideSet and TestOGXServerCELValidation
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an existing user, I want to migrate and upgrade without losing my runtime settings
  - *Test Scenario:* **TS-13**: [e2e] [PARTIAL_COVERAGE] Verify documented migration and upgrades preserve chosen settings and stored data
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want the current API and base configuration source to be unambiguous
  - *Test Scenario:* **TS-14**: [functional] Verify previous API version is rejected and current API version is accepted
    - *Priority:* P1
  - *Test Scenario:* **TS-15**: [functional] [EXISTING_COVERAGE] Verify base configuration is resolved from OCI image labels — covered by existing tests TestDefaultConfigResolver_OCILabelUsed and TestDefaultConfigResolver_OCILabelMissing
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
