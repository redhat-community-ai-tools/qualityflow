# Test Plan

## **Seamless OGX-to-Praxis Migration for Responses, Conversations, and Embeddings in 3.6 - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-2711](https://redhat.atlassian.net/browse/RHAIRFE-2711)
- **Feature Tracking:** [RHAISTRAT-1073](https://redhat.atlassian.net/browse/RHAISTRAT-1073)
- **Epic Tracking:** [RHAISTRAT-2277](https://redhat.atlassian.net/browse/RHAISTRAT-2277)
- **Feature Maturity:**
  - DP: [Name] [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Agentic API
- **Participating SIGs:** Inference Gateway, OGX Core, Documentation

**Document Conventions (if applicable):**

- **Praxis:** The new public API entrypoint for Responses, Conversations, and Embeddings.
- **OGX:** The existing API service that remains responsible for preserved customer state during migration.
- **RAG:** Retrieval-augmented generation using existing Files and Vector Stores.
- **Greenfield deployment:** A new installation with no pre-existing OGX state.
- **Upgraded deployment:** An existing installation whose OGX state must remain usable after migration.

### **Feature Overview**

Customers can continue using Responses, Conversations, and Embeddings while OGX state is preserved and Praxis becomes the public API entrypoint when explicitly enabled. The migration protects existing Files, Vector Stores, response history, and conversation history so customer applications do not need to change their API calls beyond platform-managed routing. In the current 3.6 implementation, Praxis mode is opt-in and OGX remains the default public path for Responses. Testing therefore covers both the opt-in Praxis topology and the default OGX topology so neither path regresses.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Praxis serves as the public entrypoint for Responses, Conversations, and Embeddings.
    - Upgraded deployments preserve existing Files, Vector Stores, Responses, and Conversations.
    - Public API traffic is authenticated, routed, and policy-enforced by Praxis.
    - Existing OGX state is not dual-written across OGX and Praxis.
    - A documented rollback path can restore OGX routing during the transition window.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Customers can upgrade without losing access to existing state or changing their API clients beyond platform-managed routing.
  - *List the customer use cases identified:*
    - As a customer, I want to keep using my existing Files and Vector Stores after upgrade.
    - As a customer, I want my Responses and Conversations history to remain accessible.
    - As a customer, I want RAG workflows to return correct citations from existing data.
    - As an administrator, I want to revert routing during the transition window.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - No numeric latency, throughput, or rollback-time targets are defined.
    - The greenfield state-ownership decision for Files, Vector Stores, Responses, and Conversations is not finalized.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Praxis serves as the single public entrypoint for Responses, Conversations, and Embeddings in new 3.6 deployments.
    - Upgraded 3.5 deployments preserve existing Files, Vector Stores, Responses, and Conversations state through the transition.
    - Responses with file_search works end-to-end through Praxis, backed by existing OGX-managed data.
    - No dual-write of the same logical resource to both OGX and Praxis state stores.
    - Customer application code does not require changes beyond any platform-managed endpoint reconfiguration.
    - Auth, routing, and policy enforcement are owned by Praxis for all public API traffic.
    - File upload, vector store creation, and file-to-vector-store attachment work through Praxis.
    - A documented rollback path exists to revert routing to OGX during the transition window.
    - Streaming Responses requests work through Praxis.
    - Non-RAG Responses (tool-calling, agentic workflows) work through Praxis.
    - Existing OGX-managed embeddings data remains accessible through the new entrypoint.
  - *Note any gaps or missing criteria:* Performance and scale thresholds are not specified.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Backwards compatibility: Existing file and vector-store IDs remain valid after upgrade.
    - Security: Tenant isolation and ACL enforcement are maintained across the Praxis-to-OGX boundary.
    - State integrity: Each logical resource has exactly one authoritative backend.
    - Availability: Internal backend failures return OpenAI-compatible errors rather than hanging.
  - *Note any NFRs not covered and why:* Latency and throughput targets are not defined in the source ticket.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

- **Praxis mode is opt-in in the current 3.6 implementation**
  - A deployment that does not explicitly enable Praxis keeps OGX as the public path for Responses.
  - *Sign-off:* [Name/Date]
- **The Conversations API is not yet fully disabled at the OGX runtime boundary**
  - The operator removes it from the generated API list, but the OGX runtime can still register the route.
  - *Sign-off:* [Name/Date]
#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* Design review is still needed for the final greenfield state-ownership model and performance targets. QE kickoff should occur before implementation finalization, not after merge.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Preserving state while changing the public entrypoint.
    - Maintaining tenant isolation across the internal Praxis-to-OGX boundary.
    - Ensuring streaming and error behavior remain OpenAI-compatible.
    - Validating rollback without losing state.
  - *Impact on testing approach:* End-to-end and integration scenarios are required because unit tests cannot prove cross-component routing, state parity, or tenant isolation.

- [x] **API Extensions**
  - *List new or modified APIs:* The public Responses, Conversations, and Embeddings APIs remain OpenAI-compatible while their backing implementation changes.
  - *Testing impact:* Contract and compatibility tests must verify that existing client code continues to work.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A multi-node cluster with OGX, Praxis, the Platform Gateway, and persistent storage is required.
  - *Impact on test design:* Upgrade, rollback, RAG, and tenant-isolation scenarios need a production-like topology rather than isolated unit mocks.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Testing covers the opt-in Praxis-fronted topology and the default OGX topology for Responses, Conversations, and Embeddings in 3.6. It validates public API availability, state preservation, RAG continuity, tenant isolation, streaming, error handling, rollback, and the absence of dual-write. The current maturity phase is Dev Preview within the 3.6 GA release.

**Testing Goals**

- **[P0]** As a customer, verify Responses, Conversations, and Embeddings remain available through the public entrypoint.
- **[P0]** As a customer, verify existing Files, Vector Stores, Responses, and Conversations remain usable after upgrade.
- **[P0]** As a customer, verify RAG results and citations come from existing data.
- **[P0]** As a customer, verify unauthorized tenants cannot access my resources.
- **[P0]** As a customer, verify my application code works without changes beyond platform-managed routing.
- **[P0]** As a customer, verify Praxis owns public authentication, routing, and policy enforcement.
- **[P1]** As a customer, verify streaming Responses and OpenAI-compatible errors continue to work.
- **[P1]** As an administrator, verify rollback restores OGX routing without state loss.
- **[P1]** As an administrator, verify migration readiness is observable before cutover.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Full migration to a future Praxis-native state store**
  - *Rationale:* Deferred to a future release; this cycle preserves OGX as the state backend.
  - *PM/Lead Agreement:* [Name/Date]
- **OGX removal or deprecation**
  - *Rationale:* OGX remains deployed as an internal backend for upgraded deployments.
  - *PM/Lead Agreement:* [Name/Date]
- **Non-OpenAI-compatible API support**
  - *Rationale:* Only the OpenAI-compatible APIs listed in the source request are in scope.
  - *PM/Lead Agreement:* [Name/Date]
- **Batch inference API migration**
  - *Rationale:* Not named in the acceptance criteria.
  - *PM/Lead Agreement:* [Name/Date]
- **Multi-cluster or multi-region migration coordination**
  - *Rationale:* Outside the single-cluster transition scope.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **No defined performance thresholds**
  - *Sign-off:* [Name/Date]
- **No external network reachability test in the local kind environment**
  - *Sign-off:* [Name/Date]
- **Upstream Conversations runtime behavior is not yet fully controlled by the operator**
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Public API availability, state preservation, RAG, streaming, and rollback are tested end to end.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Existing Go and pytest suites are extended for migration and topology coverage.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Default OGX topology, Responses availability, and existing OGX API suites must continue to pass.

- [x] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Praxis reachability and migration readiness conditions are included in self-validation.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Not checked because no approved latency or throughput target is defined.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Not checked because no scale threshold is defined; the source ticket mentions 61 customer deployments but does not set a numeric target.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Tenant isolation and authentication across the internal boundary are tested.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Not applicable; this feature has no user-interface change.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Not checked because readiness conditions are covered by self-validation and no new metric or alert is required.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* OpenAI-compatible API behavior is validated across the migration.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Upgraded deployments must preserve existing state and IDs.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* Praxis, Platform Gateway, and OGX operator deliverables are required.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Inference Gateway, OGX Core, and Documentation are affected.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not applicable; no cloud-specific routing or storage behavior is introduced.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with separate OGX and Praxis workloads.

- **Platform & Product Version(s):** OpenShift with RHOAI [Name].

- **CPU Virtualization:** N/A.

- **Compute Resources:** Sufficient for OGX, Praxis, Platform Gateway, and test workloads.

- **Special Hardware:** N/A.

- **Storage:** PostgreSQL-backed OGX state and configured vector-store storage.

- **Network:** Platform Gateway routing with internal-only OGX access in Praxis mode.

- **Required Operators:** OGX K8s Operator and Praxis deployment.

- **Platform:** OpenShift.

- **Special Configurations:** Explicit Praxis mode opt-in and migration-job configuration.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required.

- **CI/CD:** Standard tooling — no additional tools required.

- **Other Tools:** None.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Praxis component is deployed and reachable
- [ ] OGX state and migration job are configured
- [ ] Performance and rollback thresholds are approved

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** The final greenfield state-ownership decision may not be settled before test execution.
  - **Mitigation:** Track the decision as an entry criterion and prioritize the already-implemented opt-in topology.
  - *Estimated impact on schedule:* 1-2 weeks
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Existing tests cover database parity and tenant isolation, but not the full public API path through Praxis.
  - **Mitigation:** Add end-to-end scenarios for public API availability, RAG, streaming, and rollback.
  - *Areas with reduced coverage:* Public API behavior through Praxis.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Mitigation:** No risk identified — downstream OpenShift QE covers packet-level enforcement and external reachability.

**Untestable Aspects**

- **Risk:** Performance and scale targets are not defined.
  - **Mitigation:** Measure latency and throughput once thresholds are approved.
  - *Alternative validation approach:* Record baseline measurements without pass/fail thresholds.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** End-to-end migration tests require a multi-component cluster and may be slower than unit or integration tests.
  - **Mitigation:** Prioritize P0 scenarios and reuse existing fixtures.
  - *Current capacity gaps:* None identified.
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Praxis, Platform Gateway, and OGX operator deliverables may change independently.
  - **Mitigation:** Pin compatible component versions for each test run and track cross-team changes.
  - *Dependent teams or components:* Praxis, Platform Gateway, OGX operator.
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[REQ-RHAISTRAT-2277-01]** — As a customer, I want Responses, Conversations, and Embeddings to remain available through the new public entrypoint.
  - *Test Scenario:* **TS-01**: [e2e] Verify public API availability through Praxis
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-02]** — As a customer, I want my existing Files, Vector Stores, Responses, and Conversations to remain usable after upgrade.
  - *Test Scenario:* **TS-02**: [e2e] [PARTIAL_COVERAGE] Verify migrated state is accessible after upgrade
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-03]** — As a customer, I want file_search to return correct citations from existing vector stores.
  - *Test Scenario:* **TS-03**: [e2e] [PARTIAL_COVERAGE] Verify RAG citations from existing vector stores
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-04]** — As a customer, I want unauthorized tenants to remain unable to access my resources.
  - *Test Scenario:* **TS-04**: [integration] [EXISTING_COVERAGE] Verify tenant isolation across migration boundary — covered by existing test test_e2e_file_upload_and_isolation
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-05]** — As a customer, I want streaming Responses to continue working through the new entrypoint.
  - *Test Scenario:* **TS-05**: [e2e] Verify streaming Responses through Praxis
    - *Priority:* P1

- **[REQ-RHAISTRAT-2277-06]** — As a customer, I want clear OpenAI-compatible errors when an internal backend is unavailable.
  - *Test Scenario:* **TS-06**: [integration] Verify OpenAI-compatible errors during backend failure
    - *Priority:* P1

- **[REQ-RHAISTRAT-2277-07]** — As an administrator, I want to revert routing to OGX during the transition window.
  - *Test Scenario:* **TS-07**: [e2e] Verify rollback restores OGX routing
    - *Priority:* P1

- **[REQ-RHAISTRAT-2277-08]** — As a customer, I want no dual-write of the same logical resource across OGX and Praxis.
  - *Test Scenario:* **TS-08**: [integration] Verify single-writer state ownership
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-09]** — As a customer, I want OGX to be unreachable from outside the cluster in Praxis-fronted mode.
  - *Test Scenario:* **TS-09**: [integration] [EXISTING_COVERAGE] Verify OGX is internal-only in Praxis mode — covered by existing test TestPraxisOptIn_CreatesNoExternalExposurePrimitive
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-10]** — As a customer, I want file upload, vector store creation, and attachment to work through Praxis.
  - *Test Scenario:* **TS-10**: [e2e] [PARTIAL_COVERAGE] Verify file and vector store lifecycle through Praxis
    - *Priority:* P1

- **[REQ-RHAISTRAT-2277-11]** — As a customer, I want existing embeddings data to remain accessible through the new entrypoint.
  - *Test Scenario:* **TS-11**: [e2e] Verify embeddings through new entrypoint
    - *Priority:* P1

- **[REQ-RHAISTRAT-2277-12]** — As a customer, I want non-RAG Responses with tool calling to continue working.
  - *Test Scenario:* **TS-12**: [e2e] Verify non-RAG tool calling through Praxis
    - *Priority:* P2

- **[REQ-RHAISTRAT-2277-13]** — As a customer, I want my application code to continue working without changes beyond platform-managed routing.
  - *Test Scenario:* **TS-13**: [e2e] Verify customer code compatibility across migration
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-14]** — As a customer, I want Praxis to own public authentication, routing, and policy enforcement.
  - *Test Scenario:* **TS-14**: [integration] Verify Praxis owns public auth and policy
    - *Priority:* P0

- **[REQ-RHAISTRAT-2277-15]** — As an administrator, I want migration readiness to be observable before cutover.
  - *Test Scenario:* **TS-15**: [integration] Verify migration readiness conditions
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
  - [Name]: [Name]
