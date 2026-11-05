# Test Plan

## **[TP] MaaS Multi-Tenancy — Per-Tenant Gateway Provisioning, Identity Isolation, and Model Sharing - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-1487](https://redhat.atlassian.net/browse/RHAIRFE-1487)
- **Feature Tracking:** [RHAISTRAT-1513](https://redhat.atlassian.net/browse/RHAISTRAT-1513)
- **Epic Tracking:** [RHAIRFE-1487](https://redhat.atlassian.net/browse/RHAIRFE-1487)
- **Feature Maturity:**
  - DP: N/A
  - TP: 3.6 EA2 RHOAI RELEASE [confirm]
  - GA: [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** Model as a Service
- **Participating SIGs:** Identity integration and platform observability contributors (team ownership to confirm)

**Document Conventions (if applicable):**

- **MaaS:** Models-as-a-Service, shared model access with managed authorization and quotas.
- **BYOIDP:** Bring Your Own Identity Provider, an external tenant identity service.
- **OIDC:** OpenID Connect, identity authentication used with external providers.
- **Access grant:** Permission exposing a shared model to selected tenants.
- **Tenant:** An organizational identity and policy boundary within a shared cluster.

### **Feature Overview**

Platform administrators can manage separate organizational tenants while sharing selected foundation models. Tenant users receive private identities, keys and model access so organizations can use the same cluster without exposing one another’s data. This plan covers the requested Tech Preview scope, including external identity integration and tenant-attributed observability. Provisioning and deletion boundaries require release-owner agreement before execution.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed all eight main acceptance criteria and the May 10 scope clarification.
    - Compared the linked OIDC feature and cloned multi-tenancy feature against the main request.
    - Identified unresolved differences in gateway creation and namespace deletion.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Organizational tenants share model capacity while retaining private access and policy controls.
  - *List the customer use cases identified:*
    - As a platform admin, I want to onboard and remove tenants without altering another tenant.
    - As a tenant user, I want private keys and access only to models shared with my organization.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The current sources disagree on which resources onboarding creates and deletion removes.
    - The checked-out implementation is a configuration singleton; it does not establish all requested multi-tenant capabilities.
    - Release acceptance must be resolved before these planned scenarios become executable acceptance tests.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Admin onboarding automatically prepares tenant namespace, gateway, identity and policies (provisioning boundary unresolved).
    - Users cannot discover or access another tenant’s models, keys or usage.
    - Long-lived keys remain scoped to tenant identity.
    - Tenants can configure an external identity provider.
    - Selected tenants can consume shared foundation models through separate gateways.
    - Tenant removal cleans all owned resources (namespace ownership unresolved).
    - Metrics, dashboards and logs attribute usage to tenants and allow admin filtering.
    - Documentation covers onboarding, external identity and shared model governance.
  - *Note any gaps or missing criteria:*
    - Tenant count, latency targets, cleanup deadlines, accepted key lifetimes and log/metric attribution contracts need agreement.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: no cross-tenant disclosure or unauthorized inference.
    - Quotas: each tenant remains limited by its own configured allowance.
    - Monitoring: tenant filtering includes only activity belonging to the selected tenant.
  - *Note any NFRs not covered and why:*
    - No latency or throughput SLA is specified; formal performance acceptance is excluded with agreement below.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Namespace-level isolation boundary**
  - Control-plane isolation, multi-cluster disaster recovery and tenant-admin self-service are separate features per the main request.
  - *Sign-off:* [Name/Date]

- **Existing gateway and identity services are required by the current implementation**
  - RHAISTRAT-1741 comment 17803252 identifies gateway and identity provider creation as external prerequisites. Main AC1 requests automatic provisioning, so release acceptance remains unresolved.
  - *Sign-off:* [Name/Date]

- **Current deletion preserves tenant namespace and user data**
  - The same linked clarification limits automatic deletion to managed resources. Main AC6 requires a confirmed ownership boundary before this retained set can be accepted.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Arrange the design-phase QE kickoff before further implementation decisions are accepted.
    - Review RHAISTRAT-1741 comment 17803252 with the main ticket owner to settle provisioning and cleanup.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Gateway validation currently requires an existing Gateway rather than creating one.
    - Tenant is enforced as a namespaced singleton; per-tenant deployment and database isolation require confirmation.
    - Resource ownership spans namespaces and cluster-scoped policies.
    - OIDC issuer/audience scoping must remain consistent with API key authorization.
  - *Impact on testing approach:*
    - Use distinct issuers and overlapping usernames, subscriptions and model names to expose scope collisions.
    - Treat current source as architecture evidence, not proof that requested acceptance criteria are implemented.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Tenant management exposes identity, gateway, key policy and telemetry configuration.
  - *Testing impact:*
    - Validate lifecycle, authorization and policy boundaries through observable tenant behavior.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Shared cluster with two isolated tenant services, distinct gateways, identity providers and a shared model.
  - *Impact on test design:*
    - Compare authorized and denied access from both tenants throughout sharing and deletion.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Plan Tech Preview verification of tenant onboarding with prepared gateways, isolated identity and model visibility, long-lived keys, external identity configuration, selective shared-model access, independent quotas, safe removal, tenant observability and documented workflows. Preserve tenant configuration across supported upgrades. The unresolved automatic-provisioning and complete-cleanup acceptance criteria remain release decisions; this plan does not certify them as covered.

**Testing Goals**

- **[P0]** As a platform admin, verify tenant lifecycle preserves other tenants and rejects unauthorized changes.
- **[P0]** As a tenant user, verify private identity, keys and model data remain inaccessible to other tenants.
- **[P0]** As a tenant admin, verify authorized external users obtain durable model access and foreign identities are denied.
- **[P0]** As a platform admin, verify shared-model grants allow selected tenants and deny ungranted tenants independently of quotas.
- **[P0]** As a platform admin, verify tenant usage is attributable and excludes other tenant activity when filtered.
- **[P1]** As a platform admin, verify documented workflows and supported upgrades preserve tenant boundaries.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Billing and financial metering integration**
  - *Rationale:* Main May 10 clarification removes billing; tenant observability remains in scope.
  - *PM/Lead Agreement:* [Name/Date]
- **Formal latency and maximum-tenant-count certification**
  - *Rationale:* No approved SLA or tenant-count target is supplied; quota boundaries and concurrent tenants remain in scope.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Live environment verification unavailable in this planning run**
  - Static repository and Jira analysis establish test intent, not passing runtime results. Execution begins when Section II.4 criteria are met.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:*
    - Cover tenant lifecycle, identity, catalog visibility, key lifetime, grants and quota isolation.
    - Include denial, collision, recovery and boundary conditions.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:*
    - Automate API assertions and cross-tenant inference comparisons in the existing MaaS suite.
    - Documentation workflow checks compare published instructions with observable results.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:*
    - Existing-test duplicate search ran on both clean merged snapshots.
    - Existing single-endpoint OIDC key isolation and expiration-limit checks do not establish independent tenant isolation.
    - Preserve current API-key create/list/revoke, invalid-token rejection, subscription enforcement and default-tenant health behavior.

- [x] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:*
    - Include tenant readiness and denied foreign-identity access as short health checks after onboarding.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:*
    - Not selected: no provisioning latency, inference throughput or cleanup SLA is specified.

- [x] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:*
    - Exercise concurrent onboarding and same-named subscriptions across tenants.
    - At configured per-tenant quota boundaries, verify one exhausted allowance cannot affect another.
    - Production tenant-count scale acceptance awaits a documented target.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:*
    - New tenant isolation boundaries require issuer, audience, key ownership, model authorization and private usage checks.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:*
    - Not selected: this request defines administrative configuration rather than a new UI component.
    - Documentation workflows are covered functionally.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:*
    - Compare generated traffic with tenant-attributed Prometheus metrics, Perses dashboards and Loki logs.
    - Verify tenant filtering and concurrent gateway attribution.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:*
    - Not selected as a separate matrix: supported platform versions must be supplied before execution.
    - State preservation across a supported release transition is covered under Upgrade Testing.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:*
    - Persistent identity configuration, keys, grants and tenant policy must survive a supported upgrade.
    - Verify both authorized access and cross-tenant denials after the transition.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:*
    - Identity integration delivery and per-tenant support from the external OIDC work (RHAISTRAT-1120).
    - Main description names OIDC as a dependency, although the stored Jira blocks link points in the opposite direction.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:*
    - Coordinate identity and observability contributors on per-tenant behavior across separate gateways.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:*
    - Not selected: no cloud-specific feature contract is identified for shared-cluster tenant isolation.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node cluster with at least three workers, two independent tenant services and a shared model endpoint.

- **Platform & Product Version(s):** OpenShift version: confirm the supported matrix. Product fix version: 3.6 EA2 RHOAI RELEASE; target version: 3.6 GA RHOAI RELEASE.

- **CPU Virtualization:** N/A — no virtualization-specific capability is introduced.

- **Compute Resources:** Capacity for two tenant services, gateways, identity services and lightweight inference traffic; approve a higher tenant-count target separately.

- **Special Hardware:** No special hardware required for tenant isolation; use a supported lightweight model backend.

- **Storage:** Persistent API-key and identity backing stores appropriate to the supported tenant deployment model.

- **Network:** Separate reachable tenant gateways, external identity discovery endpoints and cross-namespace routes to shared models.

- **Required Operators:** Supported MaaS deployment with its model-serving, gateway and policy operators; observability collectors and dashboards installed.

- **Platform:** OpenShift shared-cluster deployment per project environment configuration.

- **Special Configurations:** Distinct tenant identities with overlapping usernames, same-named subscriptions, private and shared models, separate quotas and synthetic usage records.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required.

- **CI/CD:** Standard tooling — no additional tools required.

- **Other Tools:** Controllable identity-session expiry and synthetic traffic correlation for long-lived key and observability validation.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Release owner resolves TP title, 3.6 EA2 fix version, 3.6 GA target version and historical 3.5 linked-feature scope.
- [ ] Feature owner settles automatic Gateway/identity creation versus the external prerequisites stated in RHAISTRAT-1741 comment 17803252.
- [ ] Feature owner defines tenant-owned resources and confirms namespace preservation versus complete cleanup.
- [ ] Development supplies the supported multi-tenant build and deployment model; existing singleton configuration alone is not sufficient.
- [ ] Identity team confirms supported per-tenant external provider patterns despite the older single-provider restriction in RHAISTRAT-1120.
- [ ] Observability contributors supply tenant attribution/filtering contract and synthetic records for comparison.
- [ ] Agree accepted key lifetime, clock-control method and supported source/target upgrade pair.
- [ ] Assign QE owner, reviewers and release decisions before execution.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Release scope differs across the main and cloned feature
  - **Mitigation:** Resolve the release boundary with the main owner before scheduling P0 execution
  - *Estimated impact on schedule:* Unestimated until ownership decisions are recorded
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Mitigation:** No risk identified — reduced coverage for formal SLA, tenant-count certification and billing, see Out of Scope

**Test Environment**

- **Mitigation:** No risk identified — execution prerequisites are documented in the execution prerequisites in Section II.4

**Untestable Aspects**

- **Risk:** Provisioning and cleanup acceptance outcomes conflict with implementation evidence
  - **Mitigation:** Do not substitute prepared gateways or retained namespaces for the main criteria; obtain the accepted contract before execution
  - *Alternative validation approach:* Review current ownership behavior and planned acceptance separately; neither constitutes acceptance of automatic provisioning
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — no capacity shortfall measured for the representative tenant load

**Dependencies**

- **Risk:** Older OIDC scope may not deliver independent identity providers per tenant
  - **Mitigation:** Identity contributors must confirm supported tenant issuer/audience scoping before the multi-tenant identity cases execute
  - *Dependent teams or components:* External OIDC integration owners; RHAISTRAT-1120
  - *Sign-off:* [Name/Date]


---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAIRFE-1487]** — As a platform admin, I want to onboard independent tenants with prepared gateways
  - *Test Scenario:* **TS-01**: [functional] Verify tenant onboarding creates an isolated usable service
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify unauthorized tenant provisioning is denied
    - *Priority:* P1
  - *Test Scenario:* **TS-03**: [functional] Verify missing gateways prevent successful tenant activation
    - *Priority:* P1
  - *Test Scenario:* **TS-04**: [integration] Verify concurrent tenant onboarding keeps tenant settings separate
    - *Priority:* P2

- **[RHAIRFE-1487]** — As a tenant user, I want my identity restricted to my own tenant
  - *Test Scenario:* **TS-05**: [integration] Verify identical usernames remain isolated across tenant identity providers
    - *Priority:* P0
  - *Test Scenario:* **TS-06**: [integration] Verify foreign tenant identity tokens are rejected
    - *Priority:* P1
  - *Test Scenario:* **TS-07**: [integration] Verify forged tenant identity cannot expand model access
    - *Priority:* P1

- **[RHAIRFE-1487]** — As a tenant user, I want private models and usage hidden from other tenants
  - *Test Scenario:* **TS-08**: [functional] Verify model discovery lists only tenant-authorized models
    - *Priority:* P0
  - *Test Scenario:* **TS-09**: [integration] Verify private model access from another tenant is denied
    - *Priority:* P1
  - *Test Scenario:* **TS-10**: [functional] Verify another tenant cannot read private usage data
    - *Priority:* P1

- **[RHAIRFE-1487]** — As a tenant user, I want long-lived API keys bound to my tenant
  - *Test Scenario:* **TS-11**: [e2e] Verify long-lived tenant keys continue inference after login expires
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] Verify cross-tenant key discovery and management are denied
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [functional] Verify tenant key lifetime accepts its limit and rejects excess
    - *Priority:* P1
  - *Test Scenario:* **TS-14**: [integration] Verify revoked tenant keys cannot access shared models
    - *Priority:* P1

- **[RHAIRFE-1487]** — As a tenant admin, I want to configure my external identity provider
  - *Test Scenario:* **TS-15**: [e2e] Verify external tenant users obtain keys and consume models
    - *Priority:* P0
  - *Test Scenario:* **TS-16**: [integration] Verify wrong issuer or audience cannot authenticate tenants
    - *Priority:* P1
  - *Test Scenario:* **TS-17**: [integration] Verify changing one identity provider leaves other tenants usable
    - *Priority:* P2

- **[RHAIRFE-1487]** — As a platform admin, I want to share models only with selected tenants
  - *Test Scenario:* **TS-18**: [e2e] Verify granted tenants consume shared models through separate gateways
    - *Priority:* P0
  - *Test Scenario:* **TS-19**: [integration] Verify ungranted tenants cannot discover or invoke shared models
    - *Priority:* P1
  - *Test Scenario:* **TS-20**: [integration] Verify grant removal ends shared model access
    - *Priority:* P1

- **[RHAIRFE-1487]** — As a tenant admin, I want quotas enforced independently for each tenant
  - *Test Scenario:* **TS-21**: [integration] Verify tenant quotas independently limit shared model consumption
    - *Priority:* P0
  - *Test Scenario:* **TS-22**: [integration] Verify exhausting one tenant quota preserves another tenant allowance
    - *Priority:* P1
  - *Test Scenario:* **TS-23**: [integration] Verify same-named tenant subscriptions retain distinct quota allowances
    - *Priority:* P2

- **[RHAIRFE-1487]** — As a platform admin, I want tenant removal to preserve unrelated data
  - *Test Scenario:* **TS-24**: [e2e] Verify tenant removal cleans managed resources and preserves user data
    - *Priority:* P0
  - *Test Scenario:* **TS-25**: [integration] Verify tenant deletion leaves other tenants serving models
    - *Priority:* P1
  - *Test Scenario:* **TS-26**: [integration] Verify interrupted tenant deletion resumes without deleting shared resources
    - *Priority:* P2

- **[RHAIRFE-1487]** — As a platform admin, I want observability attributed and filtered by tenant
  - *Test Scenario:* **TS-27**: [e2e] Verify tenant metrics dashboards and logs show attributable usage
    - *Priority:* P0
  - *Test Scenario:* **TS-28**: [functional] Verify tenant filtering excludes other tenant activity
    - *Priority:* P1
  - *Test Scenario:* **TS-29**: [integration] Verify simultaneous gateway traffic retains distinct tenant usage totals
    - *Priority:* P2

- **[RHAIRFE-1487]** — As a platform admin, I want documented tenant management workflows
  - *Test Scenario:* **TS-30**: [e2e] Verify documented onboarding identity and sharing workflows succeed
    - *Priority:* P0
  - *Test Scenario:* **TS-31**: [functional] Verify documentation explains denied sharing and retained tenant data
    - *Priority:* P1

- **[RHAIRFE-1487]** — As a platform admin, I want tenant configuration preserved during supported upgrades
  - *Test Scenario:* **TS-32**: [e2e] Verify supported upgrades preserve tenant identities keys and grants
    - *Priority:* P1
  - *Test Scenario:* **TS-33**: [integration] Verify upgrade preserves cross-tenant access restrictions
    - *Priority:* P2

#### **2. Source Constants**

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|:---|:---|:---|:---|
| TenantKind | `Tenant` | maas-controller/api/maas/v1alpha1/tenant_types.go | 25 |
| TenantInstanceName | `default-tenant` | maas-controller/api/maas/v1alpha1/tenant_types.go | 27 |
| tenantFinalizer | `maas.opendatahub.io/tenant-finalizer` | maas-controller/pkg/controller/maas/tenant_reconcile.go | 48 |

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - [Name]: [Name / @github-handle]
