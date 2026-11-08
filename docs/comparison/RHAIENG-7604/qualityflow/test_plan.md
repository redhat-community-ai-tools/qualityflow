# Test Plan

## **Update DB migration CLI for Praxis state ownership schema changes - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** Ownership mapping ADR linked from [RHAIENG-7604](https://redhat.atlassian.net/browse/RHAIENG-7604)
- **Feature Tracking:** [RHAISTRAT-2277](https://redhat.atlassian.net/browse/RHAISTRAT-2277) — Feature; parent hierarchy through [RHAIENG-6598](https://redhat.atlassian.net/browse/RHAIENG-6598) (Epic)
- **Epic Tracking:** [RHAIENG-6598](https://redhat.atlassian.net/browse/RHAIENG-6598) — story [RHAIENG-7604](https://redhat.atlassian.net/browse/RHAIENG-7604)
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** OGX Core
- **Participating SIGs:** None identified beyond OGX Core

**Document Conventions (if applicable):**

- **Praxis:** Destination for migrated Responses and Conversations history.
- **Fallback identity:** An explicit administrator choice used only when the corresponding source identity is absent or empty.
- **Ownership issuer:** The origin associated with ownership of migrated records.

### **Feature Overview**

Administrators can migrate existing Responses and Conversations history while preserving tenant and owner identities. Explicit fallback choices allow legacy records without these identities to migrate without silently assigning ownership. Migration fails with a clear error when required identity information is unavailable. This plan covers the ownership change; release maturity requires confirmation.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the seven ownership acceptance criteria in RHAIENG-7604.
    - Reviewed the dependent migration-job contract in RHAIENG-7605 and upgrade context in RHAIENG-6598.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Preserves ownership while moving existing history to Praxis.
  - *List the customer use cases identified:*
    - As an administrator, I want existing tenant and owner assignments retained when migrating history.
    - As an administrator, I want explicit fallback choices for legacy records and actionable failure messages.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The seven acceptance criteria have observable data or process-exit outcomes.
    - Whitespace-only identity semantics and the effect of skip-errors on mandatory identity failures require design confirmation.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Migrated records retain their nonempty source tenant identity.
    - Records without a source tenant use the explicitly supplied fallback tenant.
    - A missing source tenant without a fallback causes migration failure with a clear tenant error.
    - Every migrated record has the required OGX production ownership issuer.
    - Migrated records retain their nonempty source owner identity.
    - Records without a source owner use the explicitly supplied fallback owner.
    - A missing source owner without a fallback causes migration failure with a clear owner error.
  - *Note any gaps or missing criteria:*
    - Confirm whitespace-only values and whether mandatory ownership failures may ever be skipped.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Data integrity: retain tenant and owner assignments and use the required issuer on every target record.
    - Security: prevent missing identities from being silently assigned an unrelated tenant or owner.
  - *Note any NFRs not covered and why:*
    - No latency, throughput, concurrency or capacity target is specified for this ownership change.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

None — reviewed and confirmed with [Name/Date] that no additional feature limitations apply to this ownership change.

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - Arrange design-phase review of ownership precedence, fallback failure policy and target schema before implementation changes are accepted; no kickoff date or completed handoff was supplied.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Shared tenant derivation is used by Responses, Conversations, standalone items, legacy inline items and message-only conversations.
    - The available snapshot predates the new fallback and owner fields; the target schema and candidate build must be aligned before execution.
  - *Impact on testing approach:*
    - Exercise each migration path and check persisted ownership, rather than inferring success from process completion.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - No new public service API is specified; the migration interface gains explicit fallback tenant and owner choices.
  - *Testing impact:*
    - Validate source precedence, fallback choices and user-visible errors through migration runs.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Use isolated source and destination databases for migration verification; use the configured multi-node deployment only for the operator-driven workflow.
  - *Impact on test design:*
    - Parameterize source tenancy modes and identity combinations; topology itself is not under test.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate tenant and owner preservation, explicit fallback assignments, the common ownership issuer, and migration failure when required identities cannot be resolved. Cover Responses, Conversations and their items, including legacy inline and message-only history. Include the dependent migration-job handoff; release maturity is unconfirmed.

**Testing Goals**

- **[P0]** As an administrator, verify migrated history retains source or explicitly selected tenant and owner identities.
- **[P0]** As an administrator, verify all migrated history carries the required ownership origin.
- **[P1]** As an administrator, verify unresolved ownership stops migration with an actionable error.
- **[P1]** As an administrator, verify ownership assignments persist through the upgrade migration workflow.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Full epic migration validation beyond ownership**
  - *Rationale:*
    - RHAIENG-6598 also covers RAG identifiers, routing, inventory and rollback. This story validates ownership mapping and the dependent Job handoff; full epic acceptance remains a separate test cycle.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Implementation evidence limited to an older local snapshot**
  - GitHub diffs and review comments could not be retrieved. The linked merged team STP could not be imported. Recheck coverage and source literals against the candidate build before execution.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:*
    - Verify all seven acceptance criteria against target records for Responses, Conversations, standalone items, legacy inline items and message-only conversations. Parameterize absent columns, nulls and empty values where supported by the source schema.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:*
    - Automate database-backed migration checks and the operator-job workflow; use isolated source fixtures and compare target ownership with independently specified expected mappings.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:*
    - Retain response payloads, conversation messages, item ordering, source read-only behavior and rerun idempotency. Existing-test duplicate search ran on both snapshots; old tenant tests do not prove the new ownership contract.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:*
    - Not applicable: no new health check or self-diagnostic package is specified.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:*
    - Not applicable: no performance target or new benchmark is defined in the ticket.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:*
    - Not applicable: no scale limit or capacity change is specified; mixed valid and missing identities are functional data variations.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:*
    - Ownership determines tenant and owner boundaries. Verify that a populated owner cannot substitute for a missing tenant fallback, and vice versa; validate source identities take precedence over administrator fallbacks.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:*
    - Not applicable: no UI is introduced; clear CLI errors are included in functional testing.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:*
    - Not applicable: no new metric or alert is specified; process errors are functional outcomes.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:*
    - Covered as part of Upgrade Testing for legacy 3.5 data and the destination schema; no independent platform compatibility matrix is claimed.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:*
    - Verify migration of seeded 3.5 Responses and Conversations history into the 3.6 target, preserving the requested tenant, owner and issuer assignments.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:*
    - The OGX Core operator delivery RHAIENG-7605 must expose the fallback settings before the migration-job workflow can run; CLI-only checks are independent of that delivery.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:*
    - Verify RHAIENG-7605 passes explicit fallback choices to the CLI and reports failure for unresolved ownership.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:*
    - Not applicable: this ownership mapping has no cloud-specific behavior.

#### **3. Test Environment**

- **Cluster Topology:** Isolated databases for CLI integration; configured multi-node OpenShift deployment with at least three workers for the operator workflow.

- **Platform & Product Version(s):** Open Data Hub candidate containing RHAIENG-7604; exact build and platform versions require confirmation. Parent epic describes 3.5 to 3.6 migration; the story has no fix version.

- **CPU Virtualization:** N/A — no virtualization-specific behavior is involved.

- **Compute Resources:** Capacity sufficient for isolated source/destination databases and a migration Job; record actual allocations before execution.

- **Special Hardware:** N/A — no accelerator or special hardware is required.

- **Storage:** Disposable PostgreSQL source and Praxis-compatible destination with isolated data and backups for destructive migration verification.

- **Network:** Migration process can reach both databases; no network topology changes are under test.

- **Required Operators:** OGX operator candidate containing RHAIENG-7605 for job-level verification.

- **Platform:** OpenShift for operator workflow; local database-backed execution for migration integration checks.

- **Special Configurations:** Source schemas with and without tenant columns; populated, null and empty identities; distinct explicit tenant and owner fallbacks; source snapshot retained for before/after comparison.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI/CD system required.

- **Other Tools:** No additional tools required.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Confirm exact candidate builds, platform version, fix version and release maturity.
- [ ] Provide a build containing the requested ownership mapping and a destination with the matching schema.
- [ ] Confirm whitespace-only identity behavior and skip-errors policy for mandatory identity failures.
- [ ] Confirm operator RHAIENG-7605 fallback settings are available before job-level execution.
- [ ] Prepare independently specified expected ownership mappings and retain source backups.

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — no schedule constraint was supplied; confirm execution dates at kickoff.

**Test Coverage**

- **Mitigation:** No risk identified beyond the explicit boundaries in Out of Scope and Test Limitations; review those boundaries before sign-off.

**Test Environment**

- **Mitigation:** No risk identified — candidate-build alignment is an execution prerequisite in Entry Criteria.

**Untestable Aspects**

- **Risk:** Whitespace-only identities and skip-errors behavior for required ownership failures are not settled by the acceptance criteria
  - **Mitigation:** Obtain a design decision before adding assertions for either behavior; the seven explicit acceptance criteria remain testable.
  - *Alternative validation approach:* Review source and schema with development when the candidate build is selected.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — no special capacity gap is identified for these bounded ownership fixtures.

**Dependencies**

- **Risk:** Operator fallback wiring could diverge from the CLI contract
  - **Mitigation:** Coordinate RHAIENG-7605 and validate the same fallback choices through the Job workflow.
  - *Dependent teams or components:* OGX Core operator migration delivery, RHAIENG-7605.
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAIENG-7604]** — As an administrator, I want to retain the source tenant for migrated data
  - *Test Scenario:* **TS-01**: [integration] Verify migration preserves nonempty source tenant identities
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [integration] Verify source tenants override configured tenant fallback
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to supply a tenant when source tenancy is missing
  - *Test Scenario:* **TS-03**: [integration] Verify missing and empty tenants use configured fallback
    - *Priority:* P0
  - *Test Scenario:* **TS-04**: [integration] Verify mixed tenants preserve source and fallback assignments
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to receive an error when tenant identity cannot be resolved
  - *Test Scenario:* **TS-05**: [integration] Verify missing tenants fail with clear fallback error
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [integration] Verify unauthorized tenant substitution fails without explicit fallback
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to retain the required ownership issuer on all migrated data
  - *Test Scenario:* **TS-07**: [integration] Verify every migrated record has required ownership issuer
    - *Priority:* P0
  - *Test Scenario:* **TS-08**: [integration] Verify fallback records retain the same required issuer
    - *Priority:* P2
- **[RHAIENG-7604]** — As an administrator, I want to retain the source owner for migrated data
  - *Test Scenario:* **TS-09**: [integration] Verify migration preserves nonempty source owner identities
    - *Priority:* P0
  - *Test Scenario:* **TS-10**: [integration] Verify source owners override configured owner fallback
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to supply an owner when source ownership is missing
  - *Test Scenario:* **TS-11**: [integration] Verify missing and empty owners use configured fallback
    - *Priority:* P0
  - *Test Scenario:* **TS-12**: [integration] Verify mixed owners preserve source and fallback assignments
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to receive an error when owner identity cannot be resolved
  - *Test Scenario:* **TS-13**: [integration] Verify missing owners fail with clear fallback error
    - *Priority:* P1
  - *Test Scenario:* **TS-14**: [integration] Verify unauthorized owner substitution fails without explicit fallback
    - *Priority:* P1
- **[RHAIENG-7604]** — As an administrator, I want to migrate legacy data with explicit tenant and owner choices
  - *Test Scenario:* **TS-15**: [e2e] Verify upgraded history retains tenant and owner assignments
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [e2e] Verify migration Job fails without required ownership fallback
    - *Priority:* P1

#### Section III.2 — Source Constants

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|:---------|:------|:------------|:-----|
| VALID_TABLE_RESPONSES | `responses` | src/ogx/cli/migrate/praxis/cmd.py | 51 |
| VALID_TABLE_CONVERSATIONS | `conversations` | src/ogx/cli/migrate/praxis/cmd.py | 51 |
| VALID_TABLE_ITEMS | `items` | src/ogx/cli/migrate/praxis/cmd.py | 51 |
| REQUIRED_OWNER_ISSUER | [NOT FOUND] | src/ogx/cli/migrate/praxis/target.py — older snapshot | — |
| FALLBACK_TENANT_OPTION | [NOT FOUND] | src/ogx/cli/migrate/praxis/cmd.py — older snapshot | — |
| FALLBACK_OWNER_OPTION | [NOT FOUND] | src/ogx/cli/migrate/praxis/cmd.py — older snapshot | — |

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
