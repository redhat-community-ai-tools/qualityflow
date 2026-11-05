# Test Plan

## **Seamless OGX-to-Praxis Migration for Responses, Conversations, and Embeddings in 3.6 - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-2711](https://redhat.atlassian.net/browse/RHAIRFE-2711)
- **Feature Tracking:** [RHAISTRAT-1073](https://redhat.atlassian.net/browse/RHAISTRAT-1073)
- **Epic Tracking:** [RHAISTRAT-2277](https://redhat.atlassian.net/browse/RHAISTRAT-2277)
- **Feature Maturity:**
  - DP: 3.6 [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Agentic API
- **Participating SIGs:** OGX Core, Inference Gateway, Documentation

**Document Conventions (if applicable):**

- **Praxis:** The new customer-facing entrypoint for agentic APIs.
- **OGX:** The existing runtime that continues to provide Files and Vector Stores resource services in 3.6.
- **RAG:** Retrieval-augmented generation, where responses use existing documents as supporting context.
- **Greenfield:** A new deployment with no prior customer state.
- **Authoritative writer:** The single backend permitted to change a resource category.

### **Feature Overview**

Customers can use Responses, Conversations, and Embeddings through one public entrypoint in the 3.6 Dev Preview. This transition aims to keep existing applications and stored history usable when upgrading from 3.5. The plan covers new installations, migration of existing deployments, document-backed responses, and recovery from unsuccessful transitions. Native Files and Vector Stores replacement belongs to a later release.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed RHAIRFE-2711 and the parent strategy's proposed acceptance criteria.
    - Applied RHAIENG-6598's explicit correction: Responses and Conversations state is migrated to the new runtime's schema.
    - Applied RHAIENG-6597's resource integration requirements alongside the source RFE's August scope update.
    - Included public entrypoint, runtime conformance and documentation requirements from RHAIENG-6596, RHAIENG-6599 and RHAIENG-7607.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Protects existing application behavior and customer data while adopting the new entrypoint.
  - *List the customer use cases identified:*
    - As an application developer, I want one entrypoint for responses, conversations and embeddings.
    - As an administrator, I want to upgrade without losing customer history or existing document identifiers.
    - As a tenant, I want my data protected throughout the transition.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Observable contracts are defined, but the approved rollback mechanism and recovery timing remain unresolved in RHAIENG-6598.
    - The original routing-only rollback and five-minute target are proposed parent criteria, not confirmed safe behavior after schema conversion.
    - Numerical latency, throughput and deployment-capacity targets are absent. They require agreement before acceptance benchmarking.
    - Source RFE scope narrows to routing, while child epics require resource passthrough and RAG continuity. Product and engineering must approve this boundary before execution.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Greenfield deployments expose one Responses implementation and serve Conversations and Embeddings through Praxis.
    - Non-RAG, streaming and tool-assisted Responses retain compatible results.
    - Existing Responses and Conversations remain accessible with their original identifiers after upgrade.
    - Existing Files and Vector Stores identifiers remain valid without migrating their native ownership.
    - Applications continue operating without customer code changes after platform-managed cutover.
    - Document-backed Responses return grounded content, real file citations and valid annotation offsets in both response modes.
    - File upload, Vector Store creation and attachment remain available through OGX-backed public operations.
    - Transparent proxy preserves status, headers and body, and streams incrementally.
    - Public policy rejects unauthenticated requests and externally supplied internal-only headers.
    - Tenant and ACL checks remain effective after migration and across delegated operations.
    - Unavailable backends and timeouts produce bounded OpenAI-compatible errors.
    - Each resource category has one authoritative writer throughout transition, including concurrent writes.
    - Upgrade produces an auditable before/after tenant-state inventory.
    - Rollback restores a supported, intact state under the agreed recovery policy.
    - Published deployment and migration instructions let administrators complete and verify the supported workflows.
  - *Note any gaps or missing criteria:*
    - Acceptance criteria in the main description are explicitly proposed; child epics supersede its no-migration model.
    - Confirm deployment profiles, rollback prerequisites, request bounds and performance targets at design review.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: no cross-tenant access or unauthorized operations through either public or delegated paths.
    - Integrity: no missing or duplicate migrated records and no divergent resource writes.
    - Compatibility: preserve supported application contracts and identifiers across 3.5-to-3.6 upgrade.
    - Availability: return a structured service-unavailable error for an unavailable resource backend and terminate requests at the approved timeout.
    - Observability: failed requests have correlated diagnostics across the services involved.
  - *Note any NFRs not covered and why:*
    - Performance acceptance and production capacity qualification lack agreed numeric targets; see Test Limitations.
    - The reported customer-deployment count is business context, not a concurrency or capacity limit.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Native Files and Vector Stores replacement is deferred beyond 3.6**
  - OGX remains authoritative for these resource categories. Passthrough and continuity are covered, as required by RHAIENG-6597.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Schedule a design-phase QE kickoff with development, architecture and product to reconcile the accepted ownership and scope decisions before executing this plan.
    - No kickoff record or approved migration design was supplied.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - The existing operator manages Kubernetes Ingress, so the parent strategy's assumed HTTPRoute cutover must not be treated as implemented.
    - RHAIENG-6598 requires in-place Responses and Conversations schema conversion; OGX keeps Files and Vector Stores ownership.
    - Once Praxis writes converted tables, switching traffic back can expose incompatible data to OGX.
    - Existing operator ingress removal only deletes ingress it owns; other exposure paths need an explicit cutover inventory.
    - Praxis implementation, migration executor and gateway repositories are outside the available checkouts.
  - *Impact on testing approach:*
    - Validate migration and recovery with seeded state and an agreed before/after inventory.
    - Keep required integration coverage distinct from the OGX-only regression baseline.
    - Do not assume a rollback flag, schema name or gateway configuration absent from evidence.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Existing Responses, Conversations and Embeddings capabilities become available through the new public entrypoint.
    - Existing document and Vector Store operations remain available through the same customer-facing entrypoint.
  - *Testing impact:*
    - Compare supported request, result, streaming and failure contracts across the transition.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Use both a fresh 3.6 installation and an independent 3.5 installation populated before upgrade.
    - Include two tenants, external application access, persistent state and an OGX-backed document store.
  - *Impact on test design:*
    - Separate public access checks from authorized internal access.
    - Preserve the pre-upgrade dataset for inventory comparison and recovery validation.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate the 3.6 Dev Preview transition for Responses, Conversations and Embeddings on new and upgraded deployments. Include compatible client behavior, migrated runtime history, OGX-backed resource continuity, tenant protection, bounded failures and the documented recovery path. Files and Vector Stores validation covers passthrough and continuity only, consistent with the child-epic contracts.

**Testing Goals**

- **[P0]** As a customer, verify the new public entrypoint provides compatible agentic APIs.
- **[P0]** As an administrator, verify upgrade preserves history and resource identity with one authoritative writer.
- **[P0]** As a customer, verify document-backed responses preserve grounded results and citations.
- **[P1]** As a tenant, verify unauthorized requests cannot expose or change protected data.
- **[P1]** As an application developer, verify failures and timeouts return bounded compatible errors.
- **[P1]** As an administrator, verify failed or interrupted transitions preserve an auditable inventory.
- **[P1]** As an administrator, verify the published instructions lead to a working, validated transition.
- **[P2]** As an administrator, verify approved rollback restores supported data and rejects unsafe recovery.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Non-OpenAI APIs, Batch inference and unrelated agent resources**
  - *Rationale:* No new dedicated validation is required by this feature's accepted child-epic scope. Transparent proxy coverage remains in scope.
  - *PM/Lead Agreement:* [Name/Date]
- **Multi-cluster migration and cloud-specific qualification**
  - *Rationale:* This cycle covers the supported single-cluster transition; no cross-cluster or cloud-specific feature contract is provided.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Acceptance performance and production capacity qualification lack agreed targets**
  - PM/engineering and PSAP-RHOAI must supply numerical targets and the deployment-profile matrix before this qualification can be added. Functional timeout, iteration-boundary and streaming checks remain in this plan.
  - *Sign-off:* [Name/Date]
- **Available checkouts cover OGX and its tests, without the Praxis implementation**
  - Integration recommendations describe required contracts, not evidence of implemented migration behavior. Obtain the integrated build and implementation references before execution.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Compare public API outcomes for both deployment modes, including streaming, Conversations lifecycle and failure responses.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate Section III contract checks and repeatable migration verification using seeded, non-customer data. Preserve evidence for inventory and access checks.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve the existing direct-OGX Responses generation, embedding dimension/encoding, storage configuration and vector-store RAG behavior as baselines.
    - Existing-test duplicate check ran against both clean main-branch snapshots; OGX-only coverage does not establish Praxis migration behavior.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* No customer self-validation package is specified. Revisit inclusion after the Platform team delivers the supported migration health checks.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Acceptance benchmarking is excluded until PM/engineering and PSAP-RHOAI agree latency and throughput targets; see Test Limitations. Functional streaming and timeout checks remain in scope.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* No supported migration concurrency, volume or capacity boundary is published. Production scale qualification requires the deployment profile matrix and numeric bounds; see Test Limitations. Bounded agent iterations remain functional error checks.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Check public authentication, tenant isolation, ACL enforcement and rejection of client-supplied internal headers across the newly introduced service boundary.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* No UI change is specified. Customer documentation workflows are covered under Functional Testing.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Verify correlated failure diagnostics across the new public entrypoint, OGX and retrieval backend as required by RHAIENG-6597. No metric or alert name is assumed.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Compare supported API behavior and identifiers from the seeded 3.5 client baseline against the 3.6 entrypoint. Confirm the supported deployment matrix before execution.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Exercise 3.5-to-3.6 state conversion, tenant integrity, inventory, interrupted migration and cutover. Validate rollback before and after new writes only once the safe recovery contract is approved.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:*
    - Praxis team must deliver runtime conformance (RHAIENG-6599).
    - Praxis and OGX teams must deliver the resource contract (RHAIENG-6597).
    - Platform team must deliver cutover (RHAIENG-6596) and migration/recovery (RHAIENG-6598).
    - Documentation team must deliver the customer procedure (RHAIENG-7607 and release note RHAIENG-7602).

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:*
    - Agentic API owns Responses, Conversations and Embeddings contract checks.
    - OGX Core owns resource continuity and state evidence.
    - Inference Gateway owns public access/policy and cutover.
    - Documentation owns reproducibility of the published workflow.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Dedicated multi-cloud qualification is excluded: no cloud-specific migration behavior is identified. Execute on the supported platform profile agreed at entry review.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least 3 workers per project environment config; fresh and independently seeded upgrade installations.

- **Platform & Product Version(s):** Target fix version: 3.6 GA RHOAI RELEASE. Feature Release Type: Dev Preview. Source: 3.5. OpenShift version must come from the approved product support matrix before execution.

- **CPU Virtualization:** N/A — the transition does not introduce CPU virtualization requirements.

- **Compute Resources:** Capacity for the existing state backend and the new public entrypoint to coexist during transition, with serving capacity for configured inference and embedding models.

- **Special Hardware:** No new migration-specific hardware. Use the supported model-serving profile agreed for the test environment.

- **Storage:** Persistent OGX state, target Responses/Conversations schema and an independent recoverable snapshot of seeded data; retain file and vector-store content for comparison.

- **Network:** External test client access to the single public endpoint and authorized cluster-internal resource access; independently test direct OGX exposure denial.

- **Required Operators:** OGX K8s Operator and rhods-operator from the target supported release, plus the agreed Praxis deployment mechanism.

- **Platform:** OpenShift; exact supported platform version requires release-owner confirmation.

- **Special Configurations:** Two tenants with separate credentials and ACLs, seeded Responses/Conversations and document identifiers, a configured embedding backend, controllable backend failure/timeout, and approved migration/rollback settings.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI/CD system required.

- **Other Tools:** Feature-specific migration inventory comparison and correlated-request evidence capture; interfaces must be agreed with implementation owners.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Product and engineering reconcile main/RFE scope with RHAIENG-6597 and RHAIENG-6598, including schema ownership and resource passthrough.
- [ ] Release owner confirms the explicit Dev Preview field against GA fix-version naming and the parent Outcome's separate Tech Preview description.
- [ ] Development supplies implementation references and a runnable Praxis-integrated build; the available checkouts establish OGX behavior only.
- [ ] Platform and OGX teams approve migration preflight, data protection, cutover ordering and restart/retry behavior.
- [ ] Platform and product owners approve safe rollback before and after new writes, supported recovery state, transition window and the proposed five-minute target or its replacement.
- [ ] PM/engineering and PSAP-RHOAI agree performance thresholds, timeout/iteration limits and a supported deployment profile matrix.
- [ ] Documentation team supplies the migration procedure and release notes, with the DP documentation scope confirmed.
- [ ] QE assigns owners and verifies seeded state and two-tenant access can be measured without customer data.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Unresolved design and documentation decisions may delay migration validation.
  - **Mitigation:** Review dependencies and P0 execution readiness with the delivery owners before scheduling cutover.
  - *Estimated impact on schedule:* Cannot estimate until the migration and recovery contract is agreed.
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Mitigation:** No risk identified beyond the qualification gaps documented in Test Limitations and Out of Scope; review those boundaries before approval.

**Test Environment**

- **Mitigation:** No risk identified beyond the capabilities and entry gates in Sections II.3 and II.4.

**Untestable Aspects**

- **Risk:** Post-write rollback has no agreed safe schema recovery or timing contract.
  - **Mitigation:** Platform and product owners must approve restoration behavior before rollback execution; retain P2 recovery scenarios until that gate is met.
  - *Alternative validation approach:* Before a runnable recovery build, review the recovery design against a protected seeded-state inventory; this does not replace execution.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — no staffing shortfall is evidenced. Assign named QE and cross-team owners at entry review.

**Dependencies**

- **Risk:** Separately delivered runtime, cutover and migration changes may disagree on ownership or errors.
  - **Mitigation:** Require a common resource contract and an integrated build from the teams listed in Dependencies before running migration coverage.
  - *Dependent teams or components:* Praxis, OGX, Platform and Documentation teams, tracked by the child epics.
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAIENG-6596]** — As a customer, I want one public entrypoint for agentic APIs
  - *Test Scenario:* **TS-01**: [functional] Verify greenfield Responses use the single public entrypoint
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [integration] Verify direct external OGX Responses access is denied
    - *Priority:* P1
  - *Test Scenario:* **TS-03**: [integration] Verify client-supplied internal headers cannot bypass public policy
    - *Priority:* P1

- **[RHAIENG-6599]** — As an application developer, I want compatible Responses behavior
  - *Test Scenario:* **TS-04**: [functional] Verify non-RAG Responses return compatible results through Praxis
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [functional] Verify streaming Responses arrive incrementally before completion
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [e2e] Verify server-side tools complete the full response cycle
    - *Priority:* P1
  - *Test Scenario:* **TS-07**: [integration] Verify iteration limits and timeouts terminate bounded requests
    - *Priority:* P2

- **[RHAIENG-6599]** — As an application developer, I want to manage Conversations through Praxis
  - *Test Scenario:* **TS-08**: [functional] Verify Conversations create, retrieve, update and delete successfully
    - *Priority:* P0
  - *Test Scenario:* **TS-09**: [functional] Verify Conversation items preserve ordering and pagination
    - *Priority:* P1
  - *Test Scenario:* **TS-10**: [functional] Verify missing Conversations return compatible not-found errors
    - *Priority:* P1

- **[RHAIENG-6599]** — As an application developer, I want embeddings from my configured backend
  - *Test Scenario:* **TS-11**: [functional] Verify Praxis embeddings retain configured dimensions and encoding
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] Verify unavailable embedding backends return compatible errors
    - *Priority:* P1

- **[RHAIENG-6598]** — As an administrator, I want existing state preserved through upgrade
  - *Test Scenario:* **TS-13**: [e2e] Verify upgrade preserves Responses and Conversations with original identifiers
    - *Priority:* P0
  - *Test Scenario:* **TS-14**: [e2e] Verify existing Files and Vector Store identifiers remain accessible
    - *Priority:* P0
  - *Test Scenario:* **TS-15**: [e2e] Verify existing applications operate unchanged after traffic cutover
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [e2e] Verify interrupted migration resumes without lost or duplicate records
    - *Priority:* P1

- **[RHAIENG-6598]** — As an administrator, I want one authoritative writer and auditable migration
  - *Test Scenario:* **TS-17**: [e2e] Verify resource writes have one owner throughout migration
    - *Priority:* P0
  - *Test Scenario:* **TS-18**: [e2e] Verify concurrent transition writes never create divergent resources
    - *Priority:* P1
  - *Test Scenario:* **TS-19**: [e2e] Verify before/after upgrade inventories reconcile every tenant resource
    - *Priority:* P1

- **[RHAIENG-6597]** — As a customer, I want Responses to search existing documents through Praxis
  - *Test Scenario:* **TS-20**: [e2e] Verify file search returns grounded content, real file citations and valid annotation byte offsets
    - *Priority:* P0
  - *Test Scenario:* **TS-21**: [e2e] Verify streaming file search preserves incremental content and citations
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [integration] Verify inaccessible search resources return compatible errors
    - *Priority:* P1

- **[RHAIENG-6597]** — As a customer, I want OGX-backed resource operations through the public entrypoint
  - *Test Scenario:* **TS-23**: [e2e] Verify file upload, store creation and attachment through Praxis
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [integration] Verify transparent proxy preserves status, headers and response body
    - *Priority:* P1
  - *Test Scenario:* **TS-25**: [integration] Verify proxied streams arrive without full-response buffering
    - *Priority:* P1

- **[RHAIENG-6597]** — As a tenant, I want my resources protected across the migration
  - *Test Scenario:* **TS-26**: [e2e] Verify authorized resource access succeeds after upgrade
    - *Priority:* P0
  - *Test Scenario:* **TS-27**: [e2e] Verify cross-tenant access and forbidden operations are denied
    - *Priority:* P1
  - *Test Scenario:* **TS-28**: [functional] Verify unauthenticated public API requests are rejected
    - *Priority:* P1

- **[RHAIENG-6597]** — As an application developer, I want understandable failures and correlated diagnostics
  - *Test Scenario:* **TS-29**: [integration] Verify unavailable resource backends return compatible service-unavailable errors
    - *Priority:* P1
  - *Test Scenario:* **TS-30**: [integration] Verify backend timeouts produce bounded compatible error responses
    - *Priority:* P1
  - *Test Scenario:* **TS-31**: [integration] Verify failed requests expose correlated diagnostics across services
    - *Priority:* P1

- **[RHAIENG-6598]** — As an administrator, I want rollback to restore a supported state
  - *Test Scenario:* **TS-32**: [e2e] Verify rollback preserves data before and after new writes
    - *Priority:* P2
  - *Test Scenario:* **TS-33**: [e2e] Verify unsafe rollback is rejected without state corruption
    - *Priority:* P2

- **[RHAIENG-7607]** — As an administrator, I want a complete documented deployment and migration path
  - *Test Scenario:* **TS-34**: [e2e] Verify published greenfield instructions produce a usable public entrypoint
    - *Priority:* P1
  - *Test Scenario:* **TS-35**: [e2e] Verify migration guide covers preflight, protection, migration, cutover, validation and recovery
    - *Priority:* P1

#### Section III.2 — Source Constants

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|:---|:---|:---|:---|
| IngressNameSuffix | `-ingress` | controllers/network_resources.go | 37 |
| Conversation table name (OGX literal) | `openai_conversations` | pkg/config/storage.go | 107 |

These literals describe the current OGX configuration. They do not define the target migration schema.


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
