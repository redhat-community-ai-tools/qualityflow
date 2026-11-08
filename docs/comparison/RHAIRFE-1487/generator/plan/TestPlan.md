---
feature: maas_multi_tenancy
source_key: RHAIRFE-1487
version: 1.1.0
status: Draft
author: RHOAI QE
additional_docs:
  - RHAISTRAT-1741
  - RHOAIENG-62570
last_updated: '2026-05-18'
---
# MaaS Multi-Tenancy Test Plan

## Document Information

- **Feature**: MaaS Multi-Tenancy
- **Epic**: [RHOAIENG-62570](https://redhat.atlassian.net/browse/RHOAIENG-62570)
- **Feature Story**: [RHAIRFE-1487](https://redhat.atlassian.net/browse/RHAIRFE-1487)
- **Strategy**: [RHAISTRAT-1741](https://redhat.atlassian.net/browse/RHAISTRAT-1741)
- **Architecture (v2)**: [MaaS Multi-Tenancy Phase 1 — Working Design](https://docs.google.com/document/d/1Ie0hZFwPlQmVHzZLDtyHxviDXtvwY9wNPjnd1Tw8Gy8/edit?tab=t.0#heading=h.fi2ik433erf1)
- **Team**: Models as a Service
- **Version**: 1.1.0
- **Last Updated**: 2026-05-18

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates the **Phase 1** operator-managed
multi-tenancy capability for MaaS (Models as a Service)
in RHOAI, as scoped by
[RHOAIENG-62570](https://redhat.atlassian.net/browse/RHOAIENG-62570)
and refined in
[RHAISTRAT-1741](https://redhat.atlassian.net/browse/RHAISTRAT-1741)
/ Architecture v2.

Phase 1 delivers **namespace-based tenant isolation**
using a `maas.opendatahub.io/tenant` label. Tenants do
not receive a dedicated Gateway — instead, all tenants
share a single Gateway with tenant identity enforced
through API key scoping, AuthPolicy claim checks, and
a new `tenant` column in the `api_keys` table. The
maas-controller watches multiple namespaces via label
selection and reconciles MaaSSubscription +
MaaSAuthPolicy into the shared Kuadrant policy stack.
A webhook (S6) prevents out-of-namespace resource
creation.

This plan focuses on the engineering stories delivered
under Epic
[RHOAIENG-62570](https://redhat.atlassian.net/browse/RHOAIENG-62570):
[S1/RHOAIENG-62761](https://redhat.atlassian.net/browse/RHOAIENG-62761)
(controller multi-namespace reconciliation),
[S2/RHOAIENG-62762](https://redhat.atlassian.net/browse/RHOAIENG-62762)
(MaaSAuthPolicy policy propagation),
[S3/RHOAIENG-62763](https://redhat.atlassian.net/browse/RHOAIENG-62763)
(DB schema migration for tenant column),
[S4/RHOAIENG-62764](https://redhat.atlassian.net/browse/RHOAIENG-62764)
(API key management endpoints),
[S5/RHOAIENG-62765](https://redhat.atlassian.net/browse/RHOAIENG-62765)
(internal/gateway contract), and
[S6/RHOAIENG-62766](https://redhat.atlassian.net/browse/RHOAIENG-62766)
(admission webhook). Testing must verify that tenant
isolation guarantees hold at the API, data, and policy
layers without per-tenant Gateway instances.

### 1.2 Scope

#### In Scope — Phase 1

- **[S1 / RHOAIENG-62761](https://redhat.atlassian.net/browse/RHOAIENG-62761)
  — Controller: tenant namespaces + reconcile
  subs/auth**: maas-controller label-selector watch,
  namespace discovery via
  `maas.opendatahub.io/tenant` label, Tenant CR
  lifecycle (CREATE/UPDATE/DELETE), reconciliation
  loops for MaaSSubscription + MaaSAuthPolicy
- **[S2 / RHOAIENG-62762](https://redhat.atlassian.net/browse/RHOAIENG-62762)
  — Controller: propagate tenant context into
  policies**: Controller reconciliation of
  MaaSAuthPolicy into Kuadrant AuthPolicy on the
  shared Gateway; AuthPolicy attachment, update,
  and cleanup
- **[S3 / RHOAIENG-62763](https://redhat.atlassian.net/browse/RHOAIENG-62763)
  — maas-api DB migration (tenant on api_keys)**:
  `tenant` column addition to `api_keys` table,
  sentinel/default-tenant backfill for existing rows,
  rollback procedure, zero-downtime migration
  verification
- **[S4 / RHOAIENG-62764](https://redhat.atlassian.net/browse/RHOAIENG-62764)
  — maas-api mint/validate/list + tenant**:
  `POST /v1/api-keys` (create tenant-scoped key),
  `POST /internal/v1/api-keys/validate` (validate
  key and return `ValidationResult` with `tenant`,
  `userID`, `modelRef` fields), key scoping and
  cross-tenant denial
- **[S5 / RHOAIENG-62765](https://redhat.atlassian.net/browse/RHOAIENG-62765)
  — Internal + gateway tenant contract**:
  `POST /internal/v1/subscriptions/select` with
  tenant context, `X-MaaS-Tenant` header propagation
  from gateway (pending Kuadrant/Authorino
  coordination)
- **[S6 / RHOAIENG-62766](https://redhat.atlassian.net/browse/RHOAIENG-62766)
  — Webhook: unsupported namespaces**: Reject
  MaaSSubscription/MaaSAuthPolicy creation in
  namespaces without the
  `maas.opendatahub.io/tenant` label; fail-open vs
  fail-fast behavior per agreed strategy
- Tenant identity isolation — cross-tenant access
  prevention for API keys, subscriptions, and model
  access
- Long-lived API key support (months/years lifetime) — generation, validation, tenant column persistence
- Shared foundation model access (MaaSModelRef) — subscription-based gating per tenant
- Tenant CR deletion and automated resource cleanup
  (namespace, MaaSSubscription, MaaSAuthPolicy,
  generated Kuadrant policies)
- Per-tenant rate limits and quota enforcement via Kuadrant RateLimitPolicy
- Negative testing: cross-tenant API key reuse,
  subscription visibility across tenants, enumeration
  prevention

#### Out of Scope — Phase 1 (Deferred or Other Teams)

- **Per-tenant Gateway instances** — Phase 1 uses a
  shared Gateway; per-tenant Gateway deployment
  deferred to Phase 2 or a future architecture
  decision
- **BYOIDP / External OIDC (AC4 of RHAISTRAT-1741)**
  — deferred to Phase 2; depends on RHAISTRAT-1656;
  tested by its own team when ready
- **Tenant-model restriction (MaaSModelRef binding)**
  — Phase 2 / L1 scope per RHOAIENG-62570;
  `MaaSModelRef` tenant binding not implemented in
  S1–S6
- **Hosted Control Planes (HCP)** — future direction, not Phase 1; no HCP-specific testing in this plan
- External billing system implementation — only integration hooks are in scope
- Foundation model training or fine-tuning per tenant
- MaaS single-tenant functionality (covered by existing test suites)
- RHAISTRAT-1120 (MaaS External OIDC Support) — dependency; tested by its own team
- Operator installation and OLM lifecycle (covered by operator team)

### 1.3 Test Objectives

1. **[S1 / RHOAIENG-62761](https://redhat.atlassian.net/browse/RHOAIENG-62761)**
   Verify that the maas-controller discovers and
   reconciles all namespaces labeled
   `maas.opendatahub.io/tenant`,
   creating/updating/deleting corresponding tenant
   resources on Tenant CR lifecycle events
2. **[S2 / RHOAIENG-62762](https://redhat.atlassian.net/browse/RHOAIENG-62762)**
   Verify that MaaSAuthPolicy changes are propagated
   to Kuadrant AuthPolicy on the shared Gateway with
   correct attachment, update, and deletion behavior
3. **[S3 / RHOAIENG-62763](https://redhat.atlassian.net/browse/RHOAIENG-62763)**
   Verify the `tenant` column DB migration runs
   successfully, backfills existing `api_keys` rows
   with a sentinel/default-tenant value, and is
   rollback-safe
4. **[S4 / RHOAIENG-62764](https://redhat.atlassian.net/browse/RHOAIENG-62764)**
   Verify `POST /v1/api-keys` creates API keys
   persisted with the correct `tenant` value, and
   `POST /internal/v1/api-keys/validate` returns a
   `ValidationResult` including `tenant`, `userID`,
   and `modelRef` fields; cross-tenant API key reuse
   is denied
5. **[S5 / RHOAIENG-62765](https://redhat.atlassian.net/browse/RHOAIENG-62765)**
   Verify `POST /internal/v1/subscriptions/select`
   respects tenant context and that
   `X-MaaS-Tenant` header is forwarded by the
   Gateway for valid requests
6. **[S6 / RHOAIENG-62766](https://redhat.atlassian.net/browse/RHOAIENG-62766)**
   Verify the admission webhook rejects
   MaaSSubscription/MaaSAuthPolicy creation in
   namespaces without the
   `maas.opendatahub.io/tenant` label, following
   the agreed failure strategy
7. Verify that platform admins can expose shared
   foundation models to specific tenants via
   MaaSSubscription, and unauthorized tenants are
   denied access
8. Verify that Tenant CR deletion triggers automatic
   cleanup of all tenant-owned Kubernetes resources
   with no orphaned objects

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — Validate tenant
  provisioning APIs, `POST /v1/api-keys`,
  `POST /internal/v1/api-keys/validate`,
  `POST /internal/v1/subscriptions/select`, and
  admission webhook responses
- **Data Validation Testing** — Verify tenant isolation
  at the DB layer (`api_keys.tenant` column
  correctness, migration backfill), cross-tenant data
  leakage prevention, and `ValidationResult` field
  accuracy
- **Functional Testing** — Test Tenant CR lifecycle
  (create, configure, delete), namespace label
  discovery, MaaSAuthPolicy propagation to Kuadrant,
  and webhook admit/reject decisions

### 2.2 Test Types

- **Positive Testing** — Valid tenant provisioning
  workflows, successful BYOIDP configuration,
  authorized model access within tenant scope, API
  key lifecycle management
- **Negative Testing** — Unauthorized cross-tenant
  access attempts, invalid IDP configurations,
  malformed API keys, tenant resource access after
  deletion, quota violation scenarios
- **Boundary Testing** — Maximum number of tenants per
  cluster, concurrent tenant operations, large model
  catalog filtering per tenant, API key expiration
  edge cases (months/years lifetime)
- **Regression Testing** — Ensure existing
  single-tenant MaaS functionality remains intact,
  verify shared foundation model access patterns
  continue to work, validate existing rate-limit and
  quota mechanisms

### 2.3 Test Priorities

- **P0 (Critical)** — Tenant identity isolation via API
  key `tenant` column (S3/S4), cross-tenant API key
  reuse denial (S4), maas-controller namespace
  reconciliation via label selector (S1), automated
  Tenant CR cleanup, shared model access control via
  MaaSSubscription
- **P1 (High)** — MaaSAuthPolicy propagation to
  Kuadrant AuthPolicy (S2), admission webhook reject
  behavior (S6),
  `POST /internal/v1/subscriptions/select` tenant
  enforcement (S5), `ValidationResult`
  tenant/userID/modelRef fields (S4),
  `X-MaaS-Tenant` header forwarding (S5)
- **P2 (Medium)** — DB migration rollback procedure
  (S3), billing integration hooks, documentation
  coverage for onboarding, edge cases in webhook
  failure strategy

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- **OpenShift** 4.19+
- **RHOAI** 3.4+
- **Database**: PostgreSQL
- **Python** 3.11+ (for pytest tests)

### 3.2 Test Data Requirements

- At least 3 test tenants (e.g., `tenant-a`, `tenant-b`, `tenant-c`)
- Sample Tenant CRs, MaaSSubscription CRs, and MaaSAuthPolicy CRs per tenant
- At least one model deployed and registered as a MaaSModelRef CR (deployed as part of test setup)
- API keys scoped to each tenant (for cross-tenant denial testing)
- Labeled and unlabeled namespaces (for webhook testing)

### 3.3 Test Users

- **Cluster admin** — Creates and manages tenants
  (tenant-a, tenant-b, etc.); provisions Tenant CRs
  and manages maas-controller
- **Tenant user** — Regular user within a tenant
  consuming models via tenant-scoped API keys
- **Cross-tenant attacker** — User with valid
  credentials from Tenant A attempting access to
  Tenant B resources (negative testing)

---

## 4. Interfaces Under Test

### 4.1 Tenant CR Operations

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| Tenant CR (or successor ModelsAsService-like CR) | CREATE | Provision new tenant — triggers operator to create namespace, Gateway, MaaSAuthPolicy, MaaSSubscription, identity configuration, and Kuadrant policies | P0 |
| Tenant CR | DELETE | Remove tenant — triggers automated cleanup of all tenant-owned resources via finalizers | P0 |
| Tenant CR | UPDATE | Modify tenant configuration (gateway references, OIDC config, quota settings) | P1 |
| Tenant CR | GET/LIST | Retrieve tenant status and configuration | P1 |

### 4.2 Per-Tenant Custom Resources

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| MaaSSubscription CR | CREATE | Define which models a tenant can use and under what limits; must be tenant-scoped | P0 |
| MaaSSubscription CR | UPDATE/DELETE | Modify or remove model subscriptions for a tenant | P1 |
| MaaSAuthPolicy CR | CREATE | Define tenant-specific authentication rules, IdP claims, audiences, and policy binding | P0 |
| MaaSAuthPolicy CR | UPDATE/DELETE | Modify or remove tenant auth policies | P1 |
| Kuadrant AuthPolicy (generated) | Verify creation | Confirm gateway-facing auth policy is generated from MaaSAuthPolicy per tenant | P1 |
| Kuadrant RateLimitPolicy (generated) | Verify creation | Confirm gateway-facing rate limit policy is generated per tenant from subscription limits | P1 |

### 4.3 Shared Resources

| Interface | Method | Purpose | Priority |
|-----------|--------|---------|----------|
| MaaSModelRef CR | GET/LIST | Shared model catalog; verify tenant can only see models they are subscribed to | P1 |

### 4.4 Tenant Resource Verification

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| Tenant namespace | Verify creation | Confirm namespace is created with `maas.opendatahub.io/tenant` label and correct RBAC | P0 |
| Shared Gateway | Verify routing | Confirm single shared Gateway routes tenant requests via AuthPolicy claim checks (no per-tenant Gateway) | P0 |
| Tenant identity configuration | Verify | Confirm tenant-scoped claims/audiences are configured in shared IdP (realm-per-tenant deferred to Phase 2) | P1 |

### 4.5 Authentication, Identity, and API Keys (S4)

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| `POST /v1/api-keys` | CREATE | Generate long-lived API key; verify `tenant` field persisted in `api_keys` table | P0 |
| `POST /internal/v1/api-keys/validate` | VALIDATE | Validate API key and return `ValidationResult{tenant, userID, modelRef}`; cross-tenant key returns 401 | P0 |
| `GET /v1/api-keys` | LIST | List API keys scoped to the tenant; verify keys from other tenants are not visible | P1 |

### 4.6 Internal/Gateway Contract (S5)

| Interface | Method | Purpose | Priority |
|-----------|--------|---------|----------|
| `POST /internal/v1/subscriptions/select` | SELECT | Verify tenant context is used to select correct subscription; unauthorized tenant returns 403 | P1 |
| `X-MaaS-Tenant` header | FORWARD | Verify Gateway forwards `X-MaaS-Tenant` header on valid authenticated requests (pending Kuadrant/Authorino coordination) | P1 |

### 4.7 Admission Webhook (S6)

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| MaaSSubscription in unlabeled namespace | REJECT | Webhook rejects CREATE in namespace without `maas.opendatahub.io/tenant` label | P1 |
| MaaSAuthPolicy in unlabeled namespace | REJECT | Webhook rejects CREATE in namespace without `maas.opendatahub.io/tenant` label | P1 |
| MaaSSubscription in labeled namespace | ALLOW | Webhook admits CREATE in correctly labeled tenant namespace | P1 |
| Webhook failure mode | VERIFY | Validate fail-open vs. fail-fast behavior matches agreed strategy from design doc | P2 |

### 4.9 Isolation Enforcement (Negative Testing)

| Interface | Method | Purpose | Priority |
| ----------- | -------- | --------- | ---------- |
| Cross-tenant model access | DENY | Tenant A cannot discover or access Tenant B's models or subscriptions | P0 |
| Cross-tenant API key reuse | DENY | API key from Tenant A cannot authenticate on Tenant B's gateway; no cross-tenant token reuse | P0 |
| Cross-tenant metrics/usage access | DENY | Tenant A cannot view Tenant B's usage data or billing signals | P0 |
| Cross-tenant key/model enumeration | DENY | Tenant users cannot enumerate models, keys, or subscriptions belonging to other tenants | P0 |
| Subscription change isolation | DENY | Subscription changes in Tenant A are invisible to Tenant B | P0 |

---

## 5. Test Cases

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

Test cases are organized by category and stored as individual markdown files in the `test_cases/` directory:

| Category | Test Cases | Priority Distribution |
| ---------- | ------------ | ---------------------- |
| Tenant Provisioning & CR Lifecycle | TC-PROV-001 to TC-PROV-004 | P0: 3, P1: 1 |
| Controller Reconciliation | TC-CTRL-001 to TC-CTRL-003 | P0: 1, P1: 2 |
| AuthPolicy Propagation | TC-POLICY-001 to TC-POLICY-003 | P1: 3 |
| API Key Management | TC-APIKEY-001 to TC-APIKEY-004 | P0: 3, P1: 1 |
| Internal/Gateway Contract | TC-CONTRACT-001 to TC-CONTRACT-002 | P1: 2 |
| Admission Webhook | TC-WEBHOOK-001 to TC-WEBHOOK-003 | P1: 3 |
| Tenant Isolation (Negative) | TC-ISO-001 to TC-ISO-004 | P0: 4 |
| Tenant Cleanup | TC-CLEANUP-001 to TC-CLEANUP-002 | P0: 2 |
| End-to-End Scenarios | TC-E2E-001 to TC-E2E-002 | P0: 2 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- **TC-PROV-xxx** — Tenant provisioning and CR lifecycle (S1)
- **TC-CTRL-xxx** — maas-controller multi-namespace reconciliation (S1)
- **TC-POLICY-xxx** — MaaSAuthPolicy propagation and Kuadrant policy management (S2)
- **TC-APIKEY-xxx** — API key create/validate/list, `ValidationResult` fields, cross-tenant denial (S4)
- **TC-CONTRACT-xxx** — Internal/gateway contract: subscriptions select, X-MaaS-Tenant header (S5)
- **TC-WEBHOOK-xxx** — Admission webhook admit/reject behavior (S6)
- **TC-ISO-xxx** — Tenant isolation and cross-tenant access prevention
- **TC-CLEANUP-xxx** — Tenant deletion and resource cleanup
- **TC-E2E-xxx** — End-to-end tenant lifecycle scenarios

---

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
| ------ | -------- | ------------- | ------------ |
| X-MaaS-Tenant header spec not finalized (S5) | Medium | Medium | Confirm header spec with Kuadrant/Authorino team before writing S5 test cases |
| Webhook failure strategy not documented (S6) | Medium | Medium | Request finalized fail-open vs. fail-fast decision from dev team before writing TC-WEBHOOK cases |
| ValidationResult JSON schema not specified (S4) | Medium | Low | Request OpenAPI spec or example response from dev team |
| Architecture pivot (HCP vs. shared cluster) | High | Low | Test plan is grounded in Architecture v2 and S1–S6; re-scope if HCP re-enters Phase 1 |
| Single shared Gateway — one tenant's misconfigured policy affects others | High | Medium | Add negative tests for cross-tenant policy contamination; coordinate with Kuadrant team |
| Tenant CR deletion — partial cleanup if operator crashes mid-delete | Medium | Medium | Verify cascading deletion via finalizers; assert no orphaned resources post-delete |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- Single OpenShift cluster for Pattern 1 (gateway-per-tenant) testing
- Single maas-controller deployment managing multiple tenants (expanded RBAC required)
- Per-tenant Gateway instances (dedicated ingress paths, separate hostnames/TLS)
- Kuadrant operator for AuthPolicy and RateLimitPolicy generation
- Database infrastructure — decision pending per ADR
  open question 6.1 (shared DB with tenant_id
  partitioning vs separate DB per tenant vs separate
  maas-api per tenant)
- External OIDC provider infrastructure for BYOIDP testing (depends on RHAISTRAT-1120)
- Shared MaaSModelRef catalog accessible to all tenants with subscription-based gating
- Observability backend capable of tenant-labeled metrics and logs

### 9.2 Configuration

- Tenant CR specifications (gateway references, API/OIDC config per tenant)
- RBAC policies for maas-controller to manage multi-tenant resources across namespaces
- MaaSSubscription CRs defining model access limits per tenant
- MaaSAuthPolicy CRs defining authentication rules per tenant
- Kuadrant AuthPolicy generated from MaaSAuthPolicy CRs
- Kuadrant RateLimitPolicy generated per tenant from subscription limits
- OIDC issuer endpoints, JWKS URLs, client secrets per tenant
- Namespace topology configuration — decision pending per ADR open question 6.3
- Metric/log label configuration for per-tenant showback
- Feature flags for multi-tenancy enablement (if applicable)

### 9.3 Test Tools

- **API Testing**: `curl`, `pytest` + `requests`
- **CR Management**: `oc` / `kubectl`
- **Database**: `psql`
- **Log Viewing**: `oc logs`, `kubectl logs`

---

## 10. Appendix

### 10.1 Test Case Summary

> **Note**: To be filled later in the process.

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| | | | | |

### 10.2 Interface Coverage

| Interface | Story | Test Cases | Coverage |
| ----------- | ------- | ------------ | ---------- |
| Tenant CR — CREATE | S1 | | |
| Tenant CR — DELETE | S1 | | |
| Tenant CR — UPDATE | S1 | | |
| Tenant CR — GET/LIST | S1 | | |
| MaaSSubscription CR — CREATE | S1 | | |
| MaaSSubscription CR — UPDATE/DELETE | S1 | | |
| MaaSAuthPolicy CR — CREATE | S2 | | |
| MaaSAuthPolicy CR — UPDATE/DELETE | S2 | | |
| Kuadrant AuthPolicy — Verify creation | S2 | | |
| Kuadrant RateLimitPolicy — Verify creation | S2 | | |
| MaaSModelRef CR — GET/LIST | S1 | | |
| Shared model access grant — CREATE | S1 | | |
| Shared model access grant — DELETE | S1 | | |
| Shared model access grant — GET/LIST | S1 | | |
| Tenant namespace — Verify creation (with label) | S1 | | |
| Shared Gateway — Verify routing | S2 | | |
| Tenant identity configuration — Verify | S1 | | |
| `api_keys.tenant` column — DB migration | S3 | | |
| `api_keys` backfill — sentinel value | S3 | | |
| `POST /v1/api-keys` — CREATE | S4 | | |
| `POST /internal/v1/api-keys/validate` — VALIDATE | S4 | | |
| `ValidationResult` — tenant/userID/modelRef fields | S4 | | |
| `POST /internal/v1/subscriptions/select` — tenant | S5 | | |
| `X-MaaS-Tenant` header — FORWARD | S5 | | |
| Webhook — MaaSSubscription reject (unlabeled ns) | S6 | | |
| Webhook — MaaSAuthPolicy reject (unlabeled ns) | S6 | | |
| Webhook — admit (labeled ns) | S6 | | |
| BYOIDP configuration — CREATE/UPDATE | deferred | N/A — Phase 2 | |
| BYOIDP authentication — AUTH | deferred | N/A — Phase 2 | |
| Per-tenant usage metrics — GET | | | |
| Billing integration hooks — EXPORT | | | |
| Cross-tenant API key reuse — DENY | S4 | | |
| Cross-tenant model access — DENY | S1 | | |
| Cross-tenant metrics/usage — DENY | | | |
| Cross-tenant key/model enumeration — DENY | S4 | | |
| Subscription change isolation — DENY | S1 | | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-05-04 | Initial test plan (based on RHAIRFE-1487 strategy) |
| 1.1.0 | 2026-05-18 | Major update: Incorporated RHAISTRAT-1741, Architecture v2 PDF, and RHOAIENG-62570 (S1–S6 child stories). Shifted scope from per-tenant Gateway to namespace-label / shared-gateway (Phase 1 posture). Added S1 controller reconciliation, S2 AuthPolicy propagation, S3 DB migration, S4 API key endpoints, S5 internal/gateway contract, S6 admission webhook. Deferred BYOIDP, per-tenant Gateway, and MaaSModelRef binding to Phase 2. Resolved data-layer and namespace-topology open questions. Added architecture-divergence, single-gateway blast-radius, and webhook-strategy risks. Updated NFRs, infra config, test tools, and interface coverage table. |

---

**End of Test Plan**
