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
- **Runtime configuration:** Server settings for providers, models, storage and available APIs.
- **Provider:** A backend that supplies a configured server capability.

### **Feature Overview**

Administrators can declare runtime settings alongside their server deployment instead of maintaining a complete configuration template. This reduces version-specific configuration work and makes deployment changes easier to manage. Users can retain a complete custom configuration when needed. This plan covers the Technology Preview in 3.5 EA2 RHOAI RELEASE, including configuration changes and preservation across supported upgrades.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the main ticket description and current release notes.
    - Compared the six direct linked issues for scope changes and delivery dependencies.
    - Distinguished the original API proposal from the renamed release API.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* 
    - Reduces the need to understand a complete versioned runtime template.
  - *List the customer use cases identified:*
    - As an admin, I want to configure providers and models through deployment settings.
    - As an existing user, I want to retain my runtime settings during migration.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Behaviors are observable through requests, stored data and reported configuration errors.
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
    - No latency, throughput or concurrency target is supplied for this feature.
    - No new metrics, alerts or UI are specified.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

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
    - Schema scaffolding in the checkout predates config generation available in later local repository history.
    - Older design material describes v1alpha2 conversion; the renamed implementation uses a new kind and manual migration.
    - Generated config must match the selected distribution image and preserve secret references.
  - *Impact on testing approach:* 
    - Confirm the release build includes generation before execution.
    - Exercise success and failure paths through server requests and configuration status.
    - Do not assume every capability in the original draft design is implemented.

- [x] **API Extensions**
  - *List new or modified APIs:* 
    - Declarative provider, model, storage and API selections extend server configuration.
    - Custom configuration remains available as an alternative.
  - *Testing impact:* 
    - Validate safe inputs, error feedback, configuration updates and manual migration on the release API.

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

Validate Technology Preview runtime configuration for 3.5 EA2 RHOAI RELEASE: distribution defaults, documented examples, provider and model selection, API availability, persistent storage, protected credentials, configuration updates, custom configuration alternatives, supported upgrades and documented manual migration.

**Testing Goals**

- **[P0]** As an admin, verify declared runtime settings provide a usable server.
- **[P1]** As an admin, verify invalid settings produce actionable errors without replacing a usable configuration.
- **[P1]** As an admin, verify configuration changes and credential rotation take effect reliably.
- **[P1]** As an existing user, verify migration and upgrades preserve chosen settings and stored data.
- **[P1]** As an admin, verify provider credentials remain protected in generated configuration.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Complete API deprecation and demo-repository validation**
  - *Rationale:* Safety/Shields and Evaluation removal are tracked by RHAIRFE-1435 and RHAIRFE-1436; demo maintenance is tracked by RHAISTRAT-1158. This plan covers their effect on runtime configuration, not their independent acceptance criteria.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Live PR review and semantic dependency evidence unavailable**
  - GitHub retrieval failed and language-server queries timed out; source inspection and local history provide partial implementation evidence.
  - Recheck against the release build before executing the plan.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Validate distribution defaults, declared providers/models, API selections, custom configuration and negative inputs.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate the listed behaviors using detected repository conventions; reserve human decisions for sign-offs and release-contract confirmation.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve inference, model listing, Responses and vector-store workflows in the OGX Core regression suite. Existing-test duplicate check did not run (both checkouts detached; workflow treats tests as context only); scenarios were not compared against existing tests.

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
  - *Details:* N/A: no new metrics or alerts are in scope; configuration error feedback is covered functionally.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Validate the documented manual migration to the renamed API and continued custom configuration support; automatic conversion is excluded by the product contract.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Stored configuration and application data require preservation. Test explicit settings, compatible new defaults and failed-generation behavior on the release-approved upgrade path.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* OGX Core must deliver the renamed configuration-generation build tracked by RHAISTRAT-1373 and this ticket. RHAIENG-3597 must deliver wrapper/test automation support for the final API; Documentation must supply updated examples under RHAIENG-2702. Closed Jira statuses alone do not verify deliverables.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Documentation examples and manual migration must agree with OGX Core behavior. Demo consumers in RHAISTRAT-1158 should receive the final configuration contract.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A: the runtime configuration contract has no cloud-specific behavior; use the project OpenShift topology.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift, at least three workers; isolate old and new server resources for migration validation.

- **Platform & Product Version(s):** Open Data Hub (RHAISTRAT-1061), target 3.5 EA2 RHOAI RELEASE; exact supported OpenShift version and source upgrade build: TBD by release owner.

- **CPU Virtualization:** No CPU virtualization requirement for runtime configuration.

- **Compute Resources:** Capacity for the server, selected inference backend and a retained deployment during configuration replacement; size to the chosen model.

- **Special Hardware:** No special server hardware required; use the selected inference backend hardware requirements.

- **Storage:** Persistent workload volume and a supported persistent state backend; preserve representative data through restart and upgrade.

- **Network:** Server-to-provider and state-backend connectivity; client access to exercise declared settings.

- **Required Operators:** Target OGX operator with runtime generation and its final schema; a supported legacy installation for manual migration.

- **Platform:** OpenShift; upgrade-path versions must be approved against the target release.

- **Special Configurations:** Provide supported distribution images, valid and invalid configuration inputs, namespace-local referenced objects, watch opt-in labels required by the release API, and disposable test credentials.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required.

- **CI/CD:** Standard tooling — no additional tools required.

- **Other Tools:** Standard tooling — no additional tools required.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] OGX Core confirms the target build contains runtime generation and the final supported field set.
- [ ] Release owner confirms description-derived acceptance expectations and the supported source upgrade build.
- [ ] Use the ticket release-type field (Technology Preview) rather than historical GA comments; release owner confirms final maturity.
- [ ] Migration contract is resolved: manual creation of the renamed resource, no automatic conversion; rollback procedure agreed.
- [ ] Wrapper automation supports the final release API rather than obsolete v1alpha2-only assumptions.
- [ ] Documentation examples and declared storage/provider dependencies are available.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Release build and schema confirmation may delay execution
  - **Mitigation:** Obtain the release artifact and final field inventory before scheduling the cycle
  - *Estimated impact on schedule:* Unquantified until build confirmation
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Detached snapshots may hide already-covered behaviors
  - **Mitigation:** Repeat coverage matching on the approved default-branch release checkout; reduced coverage for independent work, see Out of Scope
  - *Areas with reduced coverage:* Cross-repository duplicate detection and related-ticket independent acceptance
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Mitigation:** No risk identified — environment requirements are explicitly listed in II.3.

**Untestable Aspects**

- **Risk:** Unavailable live review evidence may conceal behavioral constraints
  - **Mitigation:** Re-fetch PR reviews and confirm the final contract with OGX Core before execution
  - *Alternative validation approach:* Read-only local source/history inspection and release-owner contract review
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — no planning capacity gap identified; execution sizing depends on the chosen model in II.3.

**Dependencies**

- **Risk:** Historical API assumptions may persist in consumer automation
  - **Mitigation:** Verify the wrapper and documentation use the release API before starting migration validation
  - *Dependent teams or components:* OGX Core, wrapper/test maintainers and Documentation
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-1061]** — As an admin, I want to deploy runtime settings without maintaining a complete configuration template
  - *Test Scenario:* **TS-01**: [functional] Verify documented minimal configuration starts a usable server
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify omitted settings retain distribution defaults
    - *Priority:* P1
  - *Test Scenario:* **TS-03**: [functional] Verify malformed base configuration reports a clear error
    - *Priority:* P1
  - *Test Scenario:* **TS-04**: [functional] Verify missing base configuration reports a clear error
    - *Priority:* P1
  - *Test Scenario:* **TS-05**: [functional] Verify documented runtime fields match accepted configuration options
    - *Priority:* P2

- **[RHAISTRAT-1061]** — As an admin, I want to configure providers and their models declaratively
  - *Test Scenario:* **TS-06**: [e2e] Verify declared providers and models serve inference requests
    - *Priority:* P0
  - *Test Scenario:* **TS-07**: [functional] Verify multiple providers retain distinct model assignments
    - *Priority:* P1
  - *Test Scenario:* **TS-08**: [functional] Verify duplicate provider identifiers are rejected
    - *Priority:* P1
  - *Test Scenario:* **TS-09**: [functional] Verify models referencing unknown providers are rejected
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want to select available server APIs without contradictory settings
  - *Test Scenario:* **TS-10**: [functional] Verify disabled APIs are unavailable to clients
    - *Priority:* P1
  - *Test Scenario:* **TS-11**: [functional] Verify conflicting provider and disabled API selections fail
    - *Priority:* P1
  - *Test Scenario:* **TS-12**: [functional] Verify unsupported API selections are rejected
    - *Priority:* P2

- **[RHAISTRAT-1061]** — As an admin, I want persistent runtime storage and protected provider credentials
  - *Test Scenario:* **TS-13**: [e2e] Verify declared storage preserves data across server restarts
    - *Priority:* P1
  - *Test Scenario:* **TS-14**: [functional] Verify missing credentials report an actionable configuration error
    - *Priority:* P1
  - *Test Scenario:* **TS-15**: [integration] Verify generated configuration never exposes secret values
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [e2e] Verify credential rotation restores authenticated provider access
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want runtime configuration changes to apply reliably
  - *Test Scenario:* **TS-17**: [e2e] Verify updated runtime settings take effect in requests
    - *Priority:* P1
  - *Test Scenario:* **TS-18**: [functional] Verify unchanged settings avoid unnecessary server restarts
    - *Priority:* P2
  - *Test Scenario:* **TS-19**: [e2e] Verify invalid updates preserve the last usable configuration
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [e2e] Verify successive updates converge on the latest settings
    - *Priority:* P2
  - *Test Scenario:* **TS-21**: [e2e] Verify configured settings survive an operator restart
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an admin, I want to retain control through a complete custom configuration
  - *Test Scenario:* **TS-22**: [e2e] Verify custom configuration controls the running server
    - *Priority:* P1
  - *Test Scenario:* **TS-23**: [functional] Verify mixed custom and declarative configurations are rejected
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [functional] Verify missing custom configuration reports an actionable error
    - *Priority:* P1

- **[RHAISTRAT-1061]** — As an existing user, I want to migrate and upgrade without losing my runtime settings
  - *Test Scenario:* **TS-25**: [e2e] Verify documented manual migration preserves chosen runtime settings
    - *Priority:* P1
  - *Test Scenario:* **TS-26**: [e2e] Verify upgrades preserve customizations and compatible new defaults
    - *Priority:* P1
  - *Test Scenario:* **TS-27**: [e2e] Verify incompatible upgrade configuration preserves the running deployment
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
