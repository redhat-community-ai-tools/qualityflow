---
feature: update_db_migration_cli_for_praxis_state_ownership_schema_changes
source_key: RHAIENG-7604
source_type: issue
status: In Review
author: OGX Core
components:
- OGX Core
additional_docs: []
last_updated: '2026-09-25'
version: 1.1.0
reviewers: []
---
# update_db_migration_cli_for_praxis_state_ownership_schema_changes Test Plan

**OGX Core** – **E2E/System Testing**

**Strategy**: [RHAIENG-7604](https://redhat.atlassian.net/browse/RHAIENG-7604)

---

## 1. Executive Summary

### 1.1 Purpose

This plan verifies the OGX database migration CLI's end-to-end mapping of source state-ownership
data into the Praxis schema. It covers direct source mappings, CLI-provided fallback values,
the fixed ownership issuer, and clear migration failures when required values and fallbacks are
absent.

### 1.2 Scope

#### In Scope (OGX Core Responsibilities)

- Verify source-to-target `tenant_id` mapping for a present, non-empty source value
  (Objective: #1)
- Verify the `--fallback-tenant` path when source `tenant_id` is absent (Objective: #2)
- Verify the clear error path when `tenant_id` and its fallback are absent (Objective: #3)
- Verify the fixed `owner_issuer` value on every target row (Objective: #4)
- Verify direct `owner_subject` mapping from `owner_principal` (Objective: #5)
- Verify the `--fallback-owner-subject` path when `owner_principal` is absent
  (Objective: #6)
- Verify the clear error path when `owner_principal` and its fallback are absent
  (Objective: #7)

#### Out of Scope (Other Teams)

- None explicitly identified in the supplied strategy.

### 1.3 Test Objectives

1. Verify Praxis `tenant_id` maps to a present, non-empty OGX `tenant_id` through an
   end-to-end migration and target-row inspection (AC: #1 — source tenant mapping).
2. Verify Praxis `tenant_id` uses the CLI-provided `--fallback-tenant` when the source
   `tenant_id` is absent through an end-to-end migration and target-row inspection
   (AC: #2 — fallback tenant mapping).
3. Verify a clear error is displayed and the migration fails when a source row lacks
   `tenant_id` and no fallback tenant is provided through end-to-end CLI execution
   (AC: #3 — missing tenant error without fallback).
4. Verify every migrated target row has `owner_issuer` set to
   `urn:rhoai:ogx:production` through end-to-end migration and target-row inspection
   (AC: #4 — fixed owner issuer).
5. Verify Praxis `owner_subject` maps to a present, non-empty source `owner_principal`
   through an end-to-end migration and target-row inspection
   (AC: #5 — source owner subject mapping).
6. Verify Praxis `owner_subject` uses the CLI-provided `--fallback-owner-subject` when
   source `owner_principal` is absent through an end-to-end migration and target-row
   inspection (AC: #6 — fallback owner subject mapping).
7. Verify a clear error is displayed and the migration fails when a source row lacks
   `owner_principal` and no fallback owner subject is provided through end-to-end CLI
   execution (AC: #7 — missing owner subject error without fallback).

---

## 2. Test Strategy

### 2.1 Test Levels

- **E2E System Testing** — Execute the DB migration CLI against source rows and verify target
  mappings and required error behavior.

### 2.2 Test Types

- **Positive Testing** — Validate direct mappings, fallback mappings, and the fixed
  `owner_issuer` value (AC #1, AC #2, AC #4, AC #5, AC #6).
- **Negative Testing** — Validate clear errors when required source values and their fallbacks
  are absent (AC #3, AC #7).

### 2.3 Test Priorities

- **P0 (Critical)** — Missing required fallback values must produce the specified clear error
  rather than an unverified migration result (Objective: #3) (Objective: #7)
- **P1 (High)** — Required tenant and ownership mappings must produce correct target values
  for direct and fallback paths (Objective: #1) (Objective: #2) (Objective: #4)
  (Objective: #5) (Objective: #6)
- **P2 (Medium)** — No separate P2 behavior is defined by the supplied acceptance criteria;
  any future P2 coverage requires additional scope refinement (Objective: #1)

---

## 3. Test Environment

### 3.1 Infrastructure & Configuration

- A deployed OGX operator environment with the DB migration CLI/Job and its OGX-to-Praxis
  migration path available for execution.
- Source OGX data and target Praxis data must be persistently accessible for before/after
  comparison.
- Migration Job execution output must be observable, including clear errors when required
  fallback values are absent.
- The environment must support exercising CLI-provided fallback tenant and owner-subject
  values.
- OpenShift, RHOAI, OGX operator, dependent-service versions, cluster topology, and resource
  requirements are not specified. TBD — Resolution: confirm supported versions, topology,
  and resource requirements from/with the ADR before environment booking.

### 3.2 Test Data Requirements

- Source OGX rows covering populated and missing or empty `tenant_id` and
  `owner_principal` values.
  - Example: `tenant_id=tenant-A`, `owner_principal=principal-A`.
  - Example: missing or empty `tenant_id` with a populated `owner_principal`.
  - Example: populated `tenant_id` with missing or empty `owner_principal`.
- Fallback-value fixtures for the CLI.
  - Example: `--fallback-tenant=tenant-fallback-A`.
  - Example: `--fallback-owner-subject=subject-fallback-A`.
- Target Praxis rows whose `tenant_id` and `owner_subject` can be compared with source or
  fallback values, and whose `owner_issuer` is checked against
  `urn:rhoai:ogx:production`.
- Failure fixtures in which at least one source row lacks `tenant_id` or
  `owner_principal` while the corresponding fallback is omitted.
- The exact fixture schema, minimum source-row set, and isolation or cleanup requirements are
  not specified. TBD — Resolution: confirm fixture shape, row set, isolation, and cleanup
  from/with the design doc before test data preparation.

### 3.3 Test Users

- Test execution uses a cluster-admin identity with full access to OGX, Praxis, and associated
  objects in all namespaces.

| Role/User | Permissions | Resource | Namespace |
|-----------|-------------|----------|-----------|
| cluster-admin test identity | create, get, list, watch, update, patch, delete | OGX objects; Praxis objects; associated objects | all namespaces |

- The identity can run or trigger the migration Job, observe its output, and inspect the
  resulting source and target data.

### 3.4 Test Tools

- Migration CLI/Job invocation and completion observation.
- Migration-log and error-output collection.
- Source and target datastore inspection.
- The strategy does not identify concrete QE tools or procedures. TBD — Resolution: confirm
  the supported invocation, log collection, datastore query, and cleanup tools from/with the
  feature refinement before test execution.

---

## 4. Interfaces Under Test

| Interface | Type | Purpose |
|-----------|------|---------|
| OGX DB migration CLI | CLI | Executes the OGX-to-Praxis migration, accepts `--fallback-tenant` and `--fallback-owner-subject`, and displays migration errors. |

---

## 5. Test Cases

> **Note**: Test cases have been generated. See the [test case index](test_cases/INDEX.md).

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| TC-E2E | 2 | 2 P1 |
| TC-NEG | 2 | 2 P0 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

Only the following category prefixes are allowed — feature areas go in the
test case name after the prefix, not as a separate category:

| Prefix | Meaning |
|--------|---------|
| TC-E2E | End-to-end user journey flows |
| TC-UI | Browser-based UI interaction flows |
| TC-NEG | Negative and error path journeys |
| TC-NFR | Non-functional requirement validation (performance, disconnected, RBAC) |
| TC-UPG | Upgrade path validation |

Select only the categories relevant to the feature under test.

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Coverage rows may reference one or more `TC-E2E-*` or `TC-UI-*`
test cases generated by `/test-plan-create-cases`.

> **Requirement**: Once populated, the matrix must include every non-pending interface from
> Section 4, and each populated row must contain at least one `TC-E2E-*` or `TC-UI-*`
> reference. The matrix remains empty until `/test-plan-create-cases` runs.

### 6.1 Scenario Summary

| ID | Scenario | Interfaces Covered | Priority |
|----|----------|--------------------|----------|
| TC-E2E-001 | Direct source mappings and fixed ownership issuer | OGX DB migration CLI | P1 |
| TC-E2E-002 | CLI fallbacks for absent source ownership fields | OGX DB migration CLI | P1 |

### 6.2 E2E Coverage Matrix

| Interface (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| OGX DB migration CLI | TC-E2E-001, TC-E2E-002, TC-NEG-001, TC-NEG-002 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification. Concrete testing considerations must end with
`(Objective: #N)`; a **Not Applicable** statement has no grounded
AC/NFR to cite and does not need the marker.

### 7.1 Disconnected/Air-Gapped

**Not Applicable** — The supplied acceptance criteria define database row mappings and
missing-value errors only; they provide no registry, image, catalog, or air-gapped
requirements.

### 7.2 Upgrade/Migration

- Verify the migration workflow for direct mappings, fallback mappings, the fixed ownership
  issuer, and required missing-value errors; backward compatibility, rollback, and upgrade
  path behavior are not specified (Objective: #1) (Objective: #3) (Objective: #4)
  (Objective: #7)

### 7.3 Performance/Scalability

**Not Applicable** — No latency, throughput, dataset-size, concurrency, or resource-consumption
requirement is supplied.

### 7.4 RBAC/Authorization

**Not Applicable** — No roles, permissions, authorization boundaries, or tenant-access controls
are specified.

### 7.5 Security

**Not Applicable** — No authentication, token, transport-security, credential-storage, or
audit-log requirement is supplied.

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Incorrect `tenant_id` mapping for populated or missing source values | High | Medium | Test direct and fallback tenant mappings against AC #1 and AC #2 (Objective: #1) (Objective: #2) |
| Incorrect ownership data, including incomplete application of the fixed issuer or subject mappings | High | Medium | Assert `owner_issuer` on every target row and verify direct and fallback `owner_subject` mappings against AC #4, AC #5, and AC #6 (Objective: #4) (Objective: #5) (Objective: #6) |
| Missing fallback values do not produce the required clear error | High | Medium | Execute missing-tenant and missing-owner-principal cases without fallbacks and verify AC #3 and AC #7 (Objective: #3) (Objective: #7) |
| Explicitly empty values may be handled inconsistently because direct mappings require non-empty values while fallback criteria say “not present” | Medium | Medium | Add explicit empty-value cases and clarify expected behavior using AC #1, AC #2, AC #5, and AC #6 (Objective: #1) (Objective: #2) (Objective: #5) (Objective: #6) |

---

## 9. Appendix

### 9.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| TC-E2E | 2 | 0 | 2 | 0 |
| TC-NEG | 2 | 2 | 0 | 0 |
| **Total** | **4** | **2** | **2** | **0** |

### 9.2 Interface Coverage

| Interface | Test Cases | Coverage |
|-----------|------------|----------|
| OGX DB migration CLI | TC-E2E-001, TC-E2E-002, TC-NEG-001, TC-NEG-002 | |

### 9.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-25 | Initial test plan |

---

## End of Test Plan
