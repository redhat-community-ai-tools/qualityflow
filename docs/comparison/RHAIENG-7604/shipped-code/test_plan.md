# Test Plan

## **Update DB Migration CLI for Praxis State Ownership Schema Changes - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** ADR linked in RHAIENG-7604
- **Feature Tracking:** RHAIENG-6598
- **Epic Tracking:** RHAIENG-7604
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** None identified

**Document Conventions (if applicable):**

- **OGX:** The source platform being migrated.
- **Praxis:** The target platform for migrated state.
- **Ownership identity:** The tenant, issuer, and owner values associated with migrated state.
- **Fallback value:** A configured value used when source ownership data is absent.

### **Feature Overview**

Administrators can migrate OGX state to Praxis while preserving the tenant and owner identity associated with each row. When source ownership data is absent, they can configure fallback tenant and owner values so migration can continue without inventing ownership. If required fallback values are missing, the migration reports a clear failure instead of writing incomplete ownership data. The operator-managed workflow also safely retries migration when fallback configuration changes.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Preserve a non-empty source tenant identifier.
    - Use a configured fallback tenant when source tenant data is absent.
    - Preserve a non-empty source owner principal as the target owner subject.
    - Use a configured fallback owner subject when source owner data is absent.
    - Set the production owner issuer on every migrated row.
    - Fail clearly when required fallback values are missing.
    - Propagate fallback configuration through the operator-managed migration Job.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Migrated state remains attributable to the correct tenant and owner after the OGX-to-Praxis transition.
  - *List the customer use cases identified:*
    - As an administrator, I want migrated conversations, responses, and items to remain scoped to their original tenant and owner.
    - As an administrator, I want to supply fallback ownership values for legacy rows that lack tenant or owner data.
    - As an administrator, I want migration to stop with a clear error rather than create rows with incomplete ownership.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - None. The operator-level failure and retry paths need workflow tests in addition to the existing unit coverage.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Source tenant identifiers are preserved when present and non-empty.
    - Configured fallback tenant values are used when source tenant data is absent.
    - Missing tenant data without a fallback produces a clear error.
    - Every target row uses the production owner issuer.
    - Source owner principals are preserved as owner subjects when present and non-empty.
    - Configured fallback owner subjects are used when source owner data is absent.
    - Missing owner data without a fallback produces a clear error.
  - *Note any gaps or missing criteria:* None identified.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Security: fallback values supplied by administrators must be passed to migration commands safely.
  - *Note any NFRs not covered and why:* No performance, scale, usability, or monitoring targets are stated in the ticket.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

None — reviewed and confirmed with [Name/Date] that no feature limitations apply for this release.

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* The linked ADR and merged implementation PRs describe the ownership mapping and operator integration. Workflow-level ownership assertions should be added to the existing operator E2E coverage.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Responses and conversations use globally unique identifiers, while item identifiers and positions are scoped by tenant, issuer, and owner.
    - Fallback values are administrator input and must be safely quoted when passed to migration commands.
    - Fallback changes must create a new migration attempt without duplicating completed rows.
  - *Impact on testing approach:* Tests must validate both direct data mapping and retry/idempotency behavior across the operator workflow.

- [x] **API Extensions**
  - *List new or modified APIs:* The migration Job configuration accepts optional fallback tenant and fallback owner subject values.
  - *Testing impact:* Tests must cover omitted values, individual values, combined values, and invalid values.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A multi-node OpenShift cluster with separate OGX and Praxis PostgreSQL stores.
  - *Impact on test design:* The workflow test must seed legacy ownership gaps, run the operator-managed migration, and inspect the Praxis target rows.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan covers the OGX-to-Praxis ownership mapping, fallback configuration, missing-fallback failure behavior, and operator-managed migration retry behavior. It covers the workflow needed to move persisted state from OGX to Praxis, including the effect of changed fallback values on a new migration attempt.

**Testing Goals**

- **[P0]** As an administrator, verify migrated state preserves tenant and owner identity.
- **[P0]** As an administrator, verify configured fallback ownership is applied by the operator-managed migration.
- **[P1]** As an administrator, verify missing or invalid fallback values produce clear failures.
- **[P1]** As an administrator, verify fallback changes safely retry migration without duplicating data.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Praxis database schema implementation**
  - *Rationale:* Praxis owns and stamps its target schema; this plan validates OGX writes against that schema.
  - *PM/Lead Agreement:* [Name/Date]
- **Kubernetes Job scheduler behavior**
  - *Rationale:* The platform team owns generic Job scheduling and retry mechanics.
  - *PM/Lead Agreement:* [Name/Date]
- **Unrelated OGX data transformations**
  - *Rationale:* This ticket changes ownership mapping and fallback behavior only.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

None — reviewed and confirmed that no test limitations apply for this release.

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Covers direct ownership mapping, fallback use, fixed issuer behavior, and operator command construction.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Existing unit, integration, and controller tests are automated; workflow scenarios will extend the tier2 suite.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Existing-test duplicate check ran. Existing migration, golden, writer, and controller suites cover direct mapping, schema conflicts, and command construction.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — no health-check or self-diagnostic capability is introduced.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A — no performance target is specified.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A — no scale target or ownership-specific capacity limit is specified.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Fallback values are administrator input and must be safely quoted before use in migration commands.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — no user interface is introduced.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new metric or alert requirement is specified.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* N/A — no cross-version compatibility requirement is specified beyond this migration path.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Migration moves persisted OGX state into the Praxis target and must remain idempotent.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* The OGX CLI and OGX operator changes must both be present in the tested build.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* The workflow integrates OGX, the OGX operator, and the Praxis target schema.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — no cloud-specific behavior is introduced.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster with at least three worker nodes.
- **Platform & Product Version(s):** OpenShift; OGX and Praxis product versions TBD because RHAIENG-7604 has no fix version.
- **CPU Virtualization:** N/A.
- **Compute Resources:** Sufficient for OGX, the OGX operator, Praxis, and two PostgreSQL databases.
- **Special Hardware:** N/A.
- **Storage:** Separate PostgreSQL-backed OGX source and Praxis target stores.
- **Network:** Standard in-cluster networking between the operator, migration Job, and databases.
- **Required Operators:** OGX operator and a Praxis deployment compatible with the target schema.
- **Platform:** OpenShift.
- **Special Configurations:** Migration Job fallback tenant and fallback owner subject values; source rows with present and absent ownership values.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.
- **CI/CD:** Standard tooling — no additional CI/CD tool required.
- **Other Tools:** Standard tooling — no additional tools required.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] OGX source data includes rows with and without tenant and owner values
- [ ] Migration fallback values and no-fallback cases are available

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — the implementation PRs are merged and the ticket is closed.

**Test Coverage**

- **Risk:** The existing tier2 migration workflow does not assert tenant, issuer, or owner columns.
  - **Mitigation:** Extend the workflow test to query ownership columns and compare them with configured source and fallback values.
  - *Areas with reduced coverage:* Operator-managed ownership mapping until the workflow assertion is added.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** A live OGX-to-Praxis environment may not be available in every test cycle.
  - **Mitigation:** Use the source repository's real Postgres and Praxis integration workflow for schema-level validation and run the operator workflow when the cluster environment is available.
  - *Missing resources or infrastructure:* Cluster environment with OGX, Praxis, and PostgreSQL.
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Mitigation:** No risk identified — all acceptance criteria have observable data, status, or command behavior.

**Resource Constraints**

- **Mitigation:** No risk identified — existing automated suites cover most direct behavior and only workflow-level gaps remain.

**Dependencies**

- **Mitigation:** No risk identified — the linked CLI and operator changes are merged.

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAIENG-7604]** — As an administrator, I want migrated state to preserve tenant and owner identity.
  - *Test Scenario:* **TS-01**: [functional] [EXISTING_COVERAGE] Verify source tenant and owner mappings
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/ogx#262 — full (verifies direct mapping, whitespace handling, and missing-fallback errors)
    - *Downstream required:* no
    - *Covered by:* `test_tenant_id_column_takes_precedence_when_present`, `test_source_owner_principal_takes_precedence`
  - *Test Scenario:* **TS-02**: [functional] [EXISTING_COVERAGE] Verify fixed owner issuer on rows
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/ogx#262 — full (verifies the production default, custom issuer propagation, and invalid URN rejection)
    - *Downstream required:* no
    - *Covered by:* `test_default_owner_issuer_is_a_valid_urn`, `test_custom_owner_issuer_is_copied_to_every_target_row`
  - *Test Scenario:* **TS-03**: [integration] [PARTIAL_COVERAGE] Verify operator migration applies fallback ownership
    - *Priority:* P0
    - *Upstream coverage:* opendatahub-io/opendatahub-tests — partial (verifies migration parity but does not query ownership columns)
    - *Downstream required:* yes
  - *Test Scenario:* **TS-04**: [integration] Verify migration failure reports missing fallback
    - *Priority:* P1
  - *Test Scenario:* **TS-05**: [functional] [EXISTING_COVERAGE] Verify invalid fallback values are rejected
    - *Priority:* P1
    - *Upstream coverage:* opendatahub-io/ogx#262 — full (verifies invalid tenant and blank owner fallback rejection)
    - *Downstream required:* no
    - *Covered by:* `test_invalid_fallback_tenant_rejected`, `test_missing_or_blank_fallback_is_rejected`

- **[RHAIENG-7605]** — As an administrator, I want fallback configuration changes to produce a safe migration retry.
  - *Test Scenario:* **TS-06**: [e2e] [PARTIAL_COVERAGE] Verify migration reruns after fallback change
    - *Priority:* P1
    - *Upstream coverage:* ogx-ai/ogx-k8s-operator#381 — partial (verifies attempt-key changes but not end-to-end data idempotency)
    - *Downstream required:* yes
  - *Test Scenario:* **TS-07**: [functional] [EXISTING_COVERAGE] Verify fallback security quoting prevents injection
    - *Priority:* P1
    - *Upstream coverage:* ogx-ai/ogx-k8s-operator#381 — full (verifies omitted, individual, combined, and shell-metacharacter fallback values)
    - *Downstream required:* no
    - *Covered by:* `TestReconcileMigration_FallbackArguments`

#### **2. Source Constants**

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|----------|-------|------------|------|
| DEFAULT_OWNER_ISSUER | `urn:rhoai:ogx:production` | src/ogx/cli/migrate/praxis/target.py | 54 |

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
