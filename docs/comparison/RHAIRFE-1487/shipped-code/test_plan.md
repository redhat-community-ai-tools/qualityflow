# Test Plan

## **MaaS Multi-Tenancy: Per-Tenant Gateways, Identity Isolation, and Model Sharing - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAISTRAT-1741](https://redhat.atlassian.net/browse/RHAISTRAT-1741)
- **Feature Tracking:** [RHAISTRAT-1513](https://redhat.atlassian.net/browse/RHAISTRAT-1513)
- **Epic Tracking:** [RHAIRFE-1487](https://redhat.atlassian.net/browse/RHAIRFE-1487)
- **Feature Maturity:**
  - DP: N/A
  - TP: 3.6 EA2 RHOAI RELEASE
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** Model as a Service
- **Participating SIGs:** AI Core Platform Security

**Document Conventions (if applicable):**

- **BYOIDP:** Bring Your Own Identity Provider, an external identity provider configured for a tenant.
- **Tenant:** An isolated organizational scope with its own gateway, identity configuration, policies, and visible models.
- **Shared foundation model:** A model made available to selected tenants through an access grant.

### **Feature Overview**

Models-as-a-Service can provision isolated tenants on a shared OpenShift cluster. A platform administrator creates a tenant once, and the platform prepares the tenant namespace, per-tenant gateway, identity configuration, API service, and policies. Tenant users can use long-lived API keys and an external identity provider while models, keys, and usage data remain isolated by tenant. The platform administrator can selectively expose shared foundation models and can view usage separated by tenant. Deleting a tenant removes the resources the platform owns while preserving the tenant namespace to protect user data.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - A platform administrator provisions a tenant with one request and receives an isolated tenant environment.
    - Tenant users cannot discover or access models, API keys, or usage data from another tenant.
    - Tenant-scoped API keys support a long lifetime.
    - A tenant can use an external identity provider.
    - Selected tenants can access shared foundation models.
    - Tenant deletion removes platform-owned resources.
    - Existing metrics, dashboards, and logs attribute usage by tenant.
    - Documentation covers onboarding, external identity, and shared model governance.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Multi-department enterprises and AI service providers can serve independent organizations from one managed deployment without manually duplicating infrastructure.
  - *List the customer use cases identified:*
    - As a platform administrator, I want to onboard an isolated tenant without deploying a separate cluster.
    - As a tenant user, I want to authenticate with my organization's identity provider and use a durable API key.
    - As a platform administrator, I want to share selected foundation models only with approved tenants.
    - As a platform administrator, I want to filter usage by tenant across all tenant gateways.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The requested long-lived key lifetime is expressed as months or years; an exact supported boundary must be confirmed before the lifetime test is finalized.
    - The external identity provider test needs a representative provider configuration and tenant credentials.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Tenant provisioning creates the namespace, gateway, identity configuration, and policies automatically.
    - Tenant users cannot discover or access another tenant's models, API keys, or usage data.
    - Long-lived API keys are scoped to tenant identity.
    - A tenant can configure an external identity provider.
    - A platform administrator can expose shared foundation models to selected tenants.
    - Tenant deletion cleans up tenant-owned resources.
    - Existing observability attributes and filters data per tenant.
    - Documentation covers tenant onboarding, external identity configuration, and shared model governance.
  - *Note any gaps or missing criteria:* No explicit latency, scale, or rate-limit thresholds are specified.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: cross-tenant data and inference isolation; denial of missing, invalid, or forged credentials.
    - Observability: per-tenant metrics, dashboards, and logs.
    - Capacity: independent per-tenant quotas and rate limits.
  - *Note any NFRs not covered and why:* Performance and scale targets are not defined in the ticket.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

- **Tenant namespaces are preserved after tenant deletion**
  - The platform removes the resources it owns but preserves the namespace to protect user data.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* QE kickoff should occur during design, before implementation changes merge. The linked architecture and external OIDC dependency must be reviewed with development before the BYOIDP workflow is automated.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Tenant isolation spans gateway routing, authentication, API-key storage, model visibility, and telemetry.
    - Shared model access must preserve tenant boundaries across separate gateways.
    - Long-lived credential testing cannot wait for a multi-year wall clock.
  - *Impact on testing approach:* Use end-to-end isolation tests, a configurable lifetime boundary for key-lifetime validation, and explicit granted and ungranted tenant cases for shared models.

- [x] **API Extensions**
  - *List new or modified APIs:* A tenant request exposes provisioning, identity, gateway, and shared-model governance controls.
  - *Testing impact:* Validate positive and negative tenant access, malformed or unauthorized requests, and cleanup after deletion.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A shared OpenShift cluster with at least two isolated tenants, separate per-tenant gateways, an external identity provider, and a shared foundation model.
  - *Impact on test design:* Cross-tenant cases must exercise both tenant gateways and verify that only the intended tenant can access a shared model.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan covers tenant provisioning, per-tenant gateway and identity isolation, long-lived API keys, external identity provider configuration, controlled shared model access, cleanup, per-tenant observability, and documentation validation for the Technology Preview release.

**Testing Goals**

- **[P0]** As a platform administrator, verify tenant provisioning creates an isolated usable tenant.
- **[P0]** As a tenant user, verify models, API keys, and usage data remain isolated by tenant.
- **[P0]** As a platform administrator, verify shared model access is granted only to approved tenants.
- **[P1]** As a tenant user, verify long-lived API keys remain valid and scoped to my tenant.
- **[P1]** As a tenant user, verify authentication through an external identity provider.
- **[P1]** As a platform administrator, verify usage data can be filtered by tenant.
- **[P1]** As a platform administrator, verify tenant isolation survives a platform upgrade.
- **[P2]** As a platform administrator, verify documentation describes the supported tenant workflows.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Control-plane-level tenant isolation**
  - *Rationale:* Covered by a separate control-plane isolation request.
  - *PM/Lead Agreement:* [Name/Date]
- **Multi-cluster high availability and disaster recovery**
  - *Rationale:* RHAIRFE-1608 covers cross-cluster HA and failover.
  - *PM/Lead Agreement:* [Name/Date]
- **Tenant administrator self-service**
  - *Rationale:* RHAIRFE-1915 covers tenant-admin group and usage management.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **No multi-year wall-clock credential test**
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Cover tenant provisioning, credentials, shared models, cleanup, observability, and documentation.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Extend the existing pytest multitenancy suites; use automated API and cluster assertions.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Existing tenant bootstrap, isolation, inference, cleanup, and negative-security suites must continue to pass.

- [x] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Include the shared-model grant and tenant observability scenarios in the self-validation package.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Not applicable because the ticket defines no latency or throughput target.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Not applicable because no tenant-count or concurrency target is specified.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Verify missing, invalid, forged, and cross-tenant credentials are rejected.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Not applicable because this ticket does not introduce a tenant-facing UI workflow.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Verify per-tenant usage attribution and filtering across metrics, dashboards, and logs.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Verify behavior across two tenant gateways and an external identity provider.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Verify persistent tenant state and cross-tenant isolation after a platform upgrade.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* RHAISTRAT-1120 must provide the supported external OIDC integration.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Gateway routing, model serving, observability, and identity integration require joint validation.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not applicable because the ticket does not define cloud-specific behavior.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least three worker nodes.

- **Platform & Product Version(s):** OpenShift with Open Data Hub 3.6 EA2 RHOAI RELEASE.

- **CPU Virtualization:** Standard cluster virtualization; no special nested virtualization requirement.

- **Compute Resources:** Sufficient capacity for two tenants, two gateways, tenant API services, and a shared foundation model.

- **Special Hardware:** GPU is not required when a CPU-capable shared foundation model is used.

- **Storage:** Object storage for the shared foundation model and persistent storage for tenant data.

- **Network:** External routes for both tenant gateways and reachable identity and observability endpoints.

- **Required Operators:** Open Data Hub operator, Gateway API implementation, and MaaS controllers.

- **Platform:** OpenShift.

- **Special Configurations:** A representative external identity provider, two isolated tenants, a shared foundation model, and per-tenant rate-limit settings.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** N/A

- **CI/CD:** N/A

- **Other Tools:** Representative external identity provider and tenant-filterable observability query interface.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Supported long-lived API-key lifetime boundary is confirmed
- [ ] Representative external identity provider configuration and test credentials are available
- [ ] A shared foundation model and two tenant access grants are available

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** External identity provider support may not be available in the test environment before the release gate.
  - **Mitigation:** Start environment preparation now and use the RHAISTRAT-1120 integration as the dependency owner.
  - *Estimated impact on schedule:* 1 to 2 weeks
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Shared-model governance may be tested only for tenant-local models, leaving cross-gateway grant behavior uncovered.
  - **Mitigation:** Require both granted and ungranted tenant cases in the end-to-end scenario.
  - *Areas with reduced coverage:* Shared foundation model access
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Mitigation:** No risk identified — the environment uses supported OpenShift, Gateway API, and Open Data Hub components.

**Untestable Aspects**

- **Mitigation:** No risk identified — all in-scope requirements have observable outcomes once entry criteria are met.

**Resource Constraints**

- **Mitigation:** No risk identified — the required topology can use existing shared test infrastructure.

**Dependencies**

- **Mitigation:** No risk identified — the external OIDC dependency is explicitly tracked in the test strategy.

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[REQ-RHAIRFE-1487-01]** — As a platform administrator, I want to provision an isolated tenant with one request
  - *Test Scenario:* **TS-001**: [integration] [EXISTING_COVERAGE] Verify tenant provisioning creates isolated environment
    - *Priority:* P0
    - *Upstream coverage:* full (verifies tenant readiness, namespace, gateway, and controller-created children)
    - *Downstream required:* no
    - *Covered by:* `test_aitenant_bootstrap_creates_tenant_environment`

- **[REQ-RHAIRFE-1487-02]** — As a tenant user, I want models, API keys, and usage data isolated by tenant
  - *Test Scenario:* **TS-002**: [integration] [EXISTING_COVERAGE] Verify API keys stay tenant isolated
    - *Priority:* P0
    - *Upstream coverage:* full (verifies direct and search isolation for active API keys)
    - *Downstream required:* no
    - *Covered by:* `test_get_api_key_from_other_tenant_gateway_not_found`, `test_search_in_tenant_does_not_return_other_tenant_keys`
  - *Test Scenario:* **TS-003**: [integration] [EXISTING_COVERAGE] Verify cross-tenant inference is rejected
    - *Priority:* P0
    - *Upstream coverage:* full (verifies a tenant key is rejected by another tenant gateway)
    - *Downstream required:* no
    - *Covered by:* `test_tenant_a_key_on_tenant_b_gateway_rejected`

- **[REQ-RHAIRFE-1487-03]** — As a tenant user, I want a long-lived API key scoped to my tenant
  - *Test Scenario:* **TS-004**: [functional] [PARTIAL_COVERAGE] Verify API key remains valid at lifetime boundary
    - *Priority:* P1
    - *Downstream required:* yes

- **[REQ-RHAIRFE-1487-04]** — As a tenant user, I want to authenticate through an external identity provider
  - *Test Scenario:* **TS-005**: [e2e] [PARTIAL_COVERAGE] Verify external identity provider login and key creation
    - *Priority:* P1
    - *Upstream coverage:* partial (verifies OIDC configuration retention, not login)
    - *Downstream required:* yes
    - *Covered by:* `test_aitenant_oidc_stays_in_aitenant_spec`

- **[REQ-RHAIRFE-1487-05]** — As a platform administrator, I want shared models available only to granted tenants
  - *Test Scenario:* **TS-006**: [e2e] [PARTIAL_COVERAGE] Verify shared model access follows grant
    - *Priority:* P0
    - *Downstream required:* yes
  - *Test Scenario:* **TS-007**: [e2e] [PARTIAL_COVERAGE] Verify ungranted tenant cannot discover shared model
    - *Priority:* P0
    - *Downstream required:* yes

- **[REQ-RHAIRFE-1487-06]** — As a platform administrator, I want tenant deletion to remove platform-owned resources
  - *Test Scenario:* **TS-008**: [integration] [EXISTING_COVERAGE] Verify tenant cleanup preserves user namespace
    - *Priority:* P1
    - *Upstream coverage:* full (verifies child cleanup, namespace preservation, and metadata removal)
    - *Downstream required:* no
    - *Covered by:* `test_aitenant_deletion_cleans_up_children_and_preserves_namespace`

- **[REQ-RHAIRFE-1487-07]** — As a tenant user, I want invalid or forged credentials rejected
  - *Test Scenario:* **TS-009**: [integration] [EXISTING_COVERAGE] Verify invalid tenant credentials are denied
    - *Priority:* P1
    - *Upstream coverage:* full (verifies missing, invalid, and forged identity-header denial on both gateways)
    - *Downstream required:* no
    - *Covered by:* `test_missing_api_key_denied_on_each_tenant_gateway`, `test_invalid_api_key_denied_on_each_tenant_gateway`, `test_forged_identity_header_denied_on_tenant_gateway`

- **[REQ-RHAIRFE-1487-08]** — As a platform administrator, I want usage data attributed and filterable by tenant
  - *Test Scenario:* **TS-010**: [functional] Verify tenant usage monitoring filters isolate data
    - *Priority:* P1

- **[REQ-RHAIRFE-1487-09]** — As a platform administrator, I want tenant rate limits enforced independently
  - *Test Scenario:* **TS-011**: [integration] Verify independent tenant rate limit enforcement
    - *Priority:* P1

- **[REQ-RHAIRFE-1487-10]** — As a platform administrator, I want documentation that matches supported tenant workflows
  - *Test Scenario:* **TS-012**: [functional] Verify documentation covers tenant workflows
    - *Priority:* P2

- **[REQ-RHAIRFE-1487-11]** — As a platform administrator, I want tenant isolation preserved after a platform upgrade
  - *Test Scenario:* **TS-013**: [e2e] Verify tenant isolation after platform upgrade
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
