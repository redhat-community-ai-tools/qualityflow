# Test Plan

## **Agent catalog - backend work - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** N/A — no separate enhancement proposal supplied
- **Feature Tracking:** [RHAISTRAT-1740](https://redhat.atlassian.net/browse/RHAISTRAT-1740)
- **Epic Tracking:** [RHOAIENG-70680](https://redhat.atlassian.net/browse/RHOAIENG-70680)
- **Feature Maturity:**
  - DP: 3.5 [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** AI Hub
- **Participating SIGs:** None identified beyond AI Hub

**Document Conventions (if applicable):**

- **Starter kit:** A curated example agent with documentation, model requirements, and configuration requirements.
- **Agent template artifact:** The published starter kit definition available for inspection, without executing the agent.
- **Dev Preview:** Early feature availability with the constraints listed below.

### **Feature Overview**

AI engineers can discover curated agent starter kits, inspect their documentation, and compare their configuration requirements through the catalog API. This provides one place to evaluate available agents before building an application. Administrators configure the sources from which agents are published. This plan covers the browse-only Dev Preview backend.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the backend epic and its 11 children for discovery, published metadata, source administration, artifact access, and documentation.
    - Compared the parent feature with the narrower backend scope; deployment and UI goals belong to the broader feature.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* 
    - Users can evaluate starter kits and their requirements without collecting metadata from multiple repositories.
  - *List the customer use cases identified:*
    - As an AI engineer, I want to find starter kits matching my framework and inspect their requirements.
    - As an administrator, I want to publish curated sources for my organization.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The parent and child issues describe different detail and source routes; the released API contract must resolve this before execution.
    - Remote documentation failure semantics are not specified. Entry criteria require agreement before negative-case execution.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Configured sources publish starter kit metadata and documentation.
    - Users can list, search, filter, page, and inspect agent entries.
    - Users can discover agent-specific sources and available filters.
    - Users can inspect image and template artifacts without executing them.
    - Source updates remove obsolete templates.
    - Installation publishes curated starter kits and supports administrator-configured sources.
    - Documentation explains the API, source configuration, and Dev Preview limits.
  - *Note any gaps or missing criteria:* 
    - No numeric latency, throughput, scale, or remote-fetch recovery targets are supplied.
    - Parent route examples conflict with later child requirements; use the signed-off released contract.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Configuration and template integrity are required across source updates and supported upgrades.
    - No new authorization boundary or telemetry contract is specified for this backend epic.
  - *Note any NFRs not covered and why:*
    - Performance and scale acceptance measurements need agreed targets; see Out of Scope.
    - UI accessibility and deployment telemetry belong to separate delivery scope.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Browse-only Dev Preview excludes agent deployment and execution**
  - *Sign-off:* [Name/Date]

- **Agent versioning and lifecycle management are unavailable**
  - *Sign-off:* [Name/Date]

- **End-user agent registration is unavailable; sources are administrator-configured**
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* 
    - QE kickoff belongs in the design phase, before implementation; no meeting date is supplied.
    - Resolve detail-route differences and remote-fetch failure contracts with development before execution.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Metadata collection, catalog service, and operator integration span three repositories.
    - The pinned source checkout contains shared model/MCP catalog code but no agent plugin; shared config parsing is strict.
    - Parent examples embed artifacts, while later children add a dedicated artifacts endpoint and template persistence.
  - *Impact on testing approach:* 
    - Trace shared integration boundaries and validate the current agent implementation before producing concrete test data.
    - Do not treat model/MCP tests as proof of agent behavior.

- [x] **API Extensions**
  - *List new or modified APIs:* 
    - Agent discovery supports filtering, search, ordering, pagination, and detailed configuration information.
    - Artifact discovery separates image references from downloadable templates.
    - Shared source discovery gains agent-specific selection.
  - *Testing impact:* 
    - Compare responses against the approved release contract and verify both populated and empty collections.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* 
    - Use the configured multi-node OpenShift topology with at least three workers for installation and upgrade checks.
  - *Impact on test design:* 
    - Single API assertions use the installed catalog; full publication and upgrade checks cover cross-component workflows.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate browse-only agent discovery, metadata and documentation publication, artifact access, source updates, installation, and supported configuration preservation for the Dev Preview backend. Validate administrator-configured sources without creating end-user registration workflows.

**Testing Goals**

- **[P0]** As an AI engineer, verify curated agents can be discovered and inspected.
- **[P0]** As an administrator, verify shipped starter kits are available after installation.
- **[P1]** As an AI engineer, verify missing entries and invalid discovery requests have defined outcomes.
- **[P1]** As an administrator, verify source updates preserve metadata integrity and remove obsolete templates.
- **[P1]** As an administrator, verify documentation retrieval failures have a defined outcome and configuration survives supported upgrades.
- **[P2]** As an AI engineer, verify documentation links and preview guidance remain usable.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Frontend and BFF interactions, including catalog telemetry**
  - *Rationale:* The backend epic explicitly delegates these to separate UI work; parent deployment and interaction goals are not backend acceptance criteria.
  - *PM/Lead Agreement:* [Name/Date]

- **Custom source authoring assistant (RHOAIENG-76364)**
  - *Rationale:* This later child adds a separate interactive authoring workflow. This cycle validates administrator source consumption; authoring-assistant acceptance needs a follow-up plan.
  - *PM/Lead Agreement:* [Name/Date]

- **Quantitative performance and scale certification**
  - *Rationale:* No targets are supplied. Add a dedicated acceptance cycle when product and engineering publish thresholds.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Implementation evidence is limited to pinned shared catalog code**
  - GitHub PR data is unreachable and agent-specific implementation is absent from both checkouts. Revalidate candidate scenarios against current implementation before execution.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Agent discovery, details, filters, metadata, artifact inspection, and published documentation; Section III lists feature-specific outcomes.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate API checks and publication workflows using the existing repository conventions; documentation reference accuracy is checked against the release contract.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve existing model and MCP source listing, label validation, configuration parsing, and plugin startup. Shared configuration has callers in both existing loaders. Existing-test duplicate search ran in both pinned checkouts and found no agent-specific assertions. Detached commits are context only until default-branch provenance is confirmed.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — no new packaged self-diagnostic capability is specified.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A for this cycle — no measurable latency or throughput target is supplied; see Out of Scope.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A for this cycle — no published maximum or scale acceptance target is supplied; ordinary pagination remains functional coverage.

- [ ] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* N/A as a separate strategy — no new RBAC or authentication boundary is specified. Existing platform access controls remain prerequisites.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — frontend/BFF validation belongs to the separate AI Hub UI delivery; this plan validates backend metadata and documentation only.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new metrics or alerting acceptance contract is specified in this backend epic; parent interaction telemetry belongs to the UI/deployment scope.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* N/A as a separate cross-version matrix — no agent client or cross-platform matrix is specified. Preserve existing model/MCP behavior under Regression Testing.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Administrator source configuration and persisted template artifacts require preservation across a supported product upgrade.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* AI Hub metadata collection delivery (RHOAIENG-70682, RHOAIENG-76086) must publish the agent data image, and operator delivery (RHOAIENG-70685) must expose its sources for backend end-to-end testing.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Validate curated metadata through installed catalog APIs and verify source updates change published artifacts. No runtime agent execution is included.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — no provider-specific backend behavior is specified; use the configured OpenShift environment.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift with at least three worker nodes, per project configuration; needed for operator installation and upgrade coverage.

- **Platform & Product Version(s):** Product release: 3.5 GA RHOAI RELEASE, copied from Jira. Feature maturity remains Dev Preview per epic description; confirm release-owner interpretation before testing. OpenShift version: release-supported version to be confirmed.

- **CPU Virtualization:** N/A — agent execution is not exercised; virtualization is not required by discovery.

- **Compute Resources:** Release-supported catalog and metadata-processing resources; record actual sizing before publication and upgrade tests.

- **Special Hardware:** No specialized accelerator required for browsing starter kits.

- **Storage:** Catalog database and persisted administrator source configuration; template update tests require retained state.

- **Network:** Repository access for metadata and README retrieval, image registry access for the metadata image, and access to the installed catalog API.

- **Required Operators:** Release-supported model registry operator with agent source support; delivery tracked by RHOAIENG-70685.

- **Platform:** OpenShift; no new provider-specific integration is identified.

- **Special Configurations:** Dev Preview enabled according to the approved release installation instructions; curated and administrator-managed sources, empty sources, multiple frameworks, images, and templates available as controlled test data.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required

- **CI/CD:** Standard tooling — no additional tools required

- **Other Tools:** No additional tools identified

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Development confirms released API paths and error contracts against the implementation.
- [ ] Release owner confirms Dev Preview maturity within 3.5 GA RHOAI RELEASE.
- [ ] Current agent implementation, metadata image, and operator source wiring are available for verification.
- [ ] Development agrees behavior for invalid discovery requests, unavailable README locations, rate limits, and invalid sources.
- [ ] A supported source-to-target upgrade path is identified with retained source and template data.
- [ ] QE owner and sign-off stakeholders are confirmed.

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — No testing deadline or outstanding schedule dependency is specified by the closed epic.

**Test Coverage**

- **Mitigation:** No risk identified beyond acknowledged exclusions — reduced coverage for UI, custom source authoring, and quantitative certification; see Out of Scope.

**Test Environment**

- **Mitigation:** No risk identified — No additional environment uncertainty is identified beyond the implementation-evidence Test Limitation.

**Untestable Aspects**

- **Risk:** Unspecified API error and remote documentation failure contracts may produce incorrect expected results.
  - **Mitigation:** Agree these contracts with development before execution; align negative scenarios to the approved contract.
  - *Alternative validation approach:* Negative response expectations; confirm before test execution
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — No team capacity gap is recorded; confirm allocation at entry.

**Dependencies**

- **Risk:** Metadata image, operator source wiring, and catalog service versions may not be compatible.
  - **Mitigation:** Verify the released component set together before starting installation and upgrade validation.
  - *Dependent teams or components:* AI Hub metadata collection, model registry operator, and catalog service
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHOAIENG-70684]** — As an AI engineer, I want to find relevant starter kits across configured sources
  - *Test Scenario:* **TS-01**: [functional] Verify agents are listed from configured sources
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify search and filters return matching agents
    - *Priority:* P0
  - *Test Scenario:* **TS-03**: [functional] Verify ordered pages contain no missing or duplicate agents
    - *Priority:* P1
  - *Test Scenario:* **TS-04**: [functional] Verify unmatched searches return an empty collection
    - *Priority:* P1
  - *Test Scenario:* **TS-05**: [functional] Verify documented handling of invalid discovery requests
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [functional] Verify filter options reflect available agent metadata
    - *Priority:* P1
  - *Test Scenario:* **TS-07**: [functional] Verify source selection returns only matching agents
    - *Priority:* P1
- **[RHOAIENG-70683]** — As an AI engineer, I want to inspect a selected starter kit
  - *Test Scenario:* **TS-08**: [functional] Verify details expose documentation and configuration requirements
    - *Priority:* P0
  - *Test Scenario:* **TS-09**: [functional] Verify unknown agent identifiers return a not-found response
    - *Priority:* P1
  - *Test Scenario:* **TS-10**: [integration] Verify empty agent sources allow successful catalog startup
    - *Priority:* P1
- **[RHOAIENG-70682]** — As a catalog administrator, I want curated repositories to produce usable agent entries
  - *Test Scenario:* **TS-11**: [integration] Verify indexed starter kits produce complete catalog metadata
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] Verify repository documentation populates agent details
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [integration] Verify documented handling of unavailable repository documentation
    - *Priority:* P1
  - *Test Scenario:* **TS-14**: [integration] Verify generation can explicitly skip documentation retrieval
    - *Priority:* P2
  - *Test Scenario:* **TS-15**: [integration] Verify documented handling of documentation retrieval rate limits
    - *Priority:* P1
- **[RHOAIENG-70685]** — As a catalog administrator, I want default and custom sources available after installation
  - *Test Scenario:* **TS-16**: [e2e] Verify installation exposes default curated agents through the API
    - *Priority:* P0
  - *Test Scenario:* **TS-17**: [e2e] Verify administrator-configured sources expose their agent entries
    - *Priority:* P1
  - *Test Scenario:* **TS-18**: [integration] Verify invalid source configuration reports a diagnosable failure
    - *Priority:* P1
  - *Test Scenario:* **TS-19**: [e2e] Verify source configuration survives a supported product upgrade
    - *Priority:* P1
- **[RHOAIENG-75429]** — As an AI engineer, I want to inspect available agent artifacts
  - *Test Scenario:* **TS-20**: [functional] Verify artifact listings distinguish images and deployment templates
    - *Priority:* P0
  - *Test Scenario:* **TS-21**: [functional] Verify artifact filtering and pagination return the selected subset
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [functional] Verify inline artifacts contain only image references
    - *Priority:* P1
  - *Test Scenario:* **TS-23**: [functional] Verify unknown agents return not-found for artifact requests
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [functional] Verify agents without artifacts return an empty collection
    - *Priority:* P2
- **[RHOAIENG-76111]** — As a catalog administrator, I want source updates to remove obsolete agent templates
  - *Test Scenario:* **TS-25**: [e2e] Verify changed templates replace previously published agent templates
    - *Priority:* P1
  - *Test Scenario:* **TS-26**: [e2e] Verify removing all templates leaves no obsolete artifacts
    - *Priority:* P1
- **[RHOAIENG-76086]** — As an AI engineer, I want starter kit presentation and templates preserved
  - *Test Scenario:* **TS-27**: [integration] Verify published agents preserve source labels and logos
    - *Priority:* P1
  - *Test Scenario:* **TS-28**: [integration] Verify downloaded templates preserve original starter kit content
    - *Priority:* P1
  - *Test Scenario:* **TS-29**: [e2e] Verify the shipped catalog includes agent template data
    - *Priority:* P0
- **[RHOAIENG-76762]** — As a catalog administrator, I want documentation found at supported repository locations
  - *Test Scenario:* **TS-30**: [integration] Verify documentation loads from explicit and default locations
    - *Priority:* P1
  - *Test Scenario:* **TS-31**: [integration] Verify documented handling of unavailable documentation overrides
    - *Priority:* P2
- **[RHOAIENG-76987]** — As an AI engineer, I want readable documentation outside its repository
  - *Test Scenario:* **TS-32**: [functional] Verify relative documentation links resolve to repository content
    - *Priority:* P1
  - *Test Scenario:* **TS-33**: [functional] Verify relative Markdown images retain their alternative text
    - *Priority:* P1
  - *Test Scenario:* **TS-34**: [functional] Verify absolute documentation links remain unchanged
    - *Priority:* P2
- **[RHOAIENG-70686]** — As an AI engineer, I want accurate instructions for the Dev Preview catalog
  - *Test Scenario:* **TS-35**: [functional] Verify documentation describes discovery and administrator source configuration
    - *Priority:* P1
  - *Test Scenario:* **TS-36**: [functional] Verify API reference and preview limitations match released behavior
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
