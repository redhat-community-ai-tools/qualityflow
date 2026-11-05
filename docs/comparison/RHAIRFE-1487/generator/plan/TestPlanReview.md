---
feature: maas_multi_tenancy
source_key: RHAIRFE-1487
version: 1.1.0
status: Reviewed
last_updated: '2026-05-18'
---
# Test Plan Review — MaaS Multi-Tenancy

## Review Summary

| Criterion | Score | Notes |
| --- | --- | --- |
| Specificity | 2/2 | Test cases reference concrete endpoints, CR kinds, label names, and DB column names |
| Grounding | 2/2 | All Phase 1 scope grounded in S1–S6 Jira stories and Architecture v2 doc |
| Scope Fidelity | 2/2 | In-scope items match S1–S6; BYOIDP, HCP, and per-tenant Gateway explicitly deferred |
| Actionability | 2/2 | 27 test cases generated with steps, test data, and expected results |
| Consistency | 1/2 | Minor: §4.9 references cross-tenant metrics (not in S1–S6); open gaps exist for ValidationResult schema and webhook failure strategy |

**Total: 9/10 — Verdict: Ready**

---

## Criterion Detail

### 1. Specificity (2/2)

The test plan and test cases reference specific and verifiable elements:

- API endpoints: `POST /v1/api-keys`,
  `POST /internal/v1/api-keys/validate`,
  `GET /v1/api-keys`,
  `POST /internal/v1/subscriptions/select`
- Kubernetes label: `maas.opendatahub.io/tenant`
- DB column: `api_keys.tenant`
- CR kinds: `MaaSSubscription`, `MaaSAuthPolicy`, `MaaSModelRef`, `Tenant`
- Kuadrant resources: `AuthPolicy`, `RateLimitPolicy`

### 2. Grounding (2/2)

Every in-scope item traces to a specific source:

- S1 (RHOAIENG-62761): controller reconciliation, namespace label discovery
- S2 (RHOAIENG-62762): MaaSAuthPolicy → Kuadrant AuthPolicy propagation
- S3 (RHOAIENG-62763): DB migration, tenant column backfill
- S4 (RHOAIENG-62764): API key mint/validate/list + ValidationResult
- S5 (RHOAIENG-62765): subscriptions/select + X-MaaS-Tenant header
- S6 (RHOAIENG-62766): admission webhook
- Architecture v2: shared Gateway posture, single maas-api

### 3. Scope Fidelity (2/2)

- Phase 1 boundary correctly excludes: per-tenant Gateway, BYOIDP, HCP, MaaSModelRef tenant binding
- §1.2 Out of Scope is explicit and links to Phase 2 deferral tickets
- S1 note "No new CR for tenant–model binding in Phase 1" is reflected in scope

### 4. Actionability (2/2)

- 27 test cases generated across 9 categories
- Each test case has: objective, preconditions, numbered
  steps, test data (where applicable), expected results
- TC-E2E-001 and TC-E2E-002 cover full user journeys for P0 endpoints
- Test environment requirements (§9) are concrete: OCP 4.19+, RHOAI 3.4+, PostgreSQL, Python 3.11+

### 5. Consistency (1/2)

Minor inconsistencies identified:

- **§4.9** includes "Cross-tenant metrics/usage
  access — DENY" but metrics/billing is not in S1–S6
  scope; this row should be marked deferred or removed
  in a future revision
- **TC-APIKEY-002** and **TC-E2E-001/002** assume a
  specific `ValidationResult` JSON structure that is not
  yet confirmed by dev team (tracked in TestPlanGaps.md)
- **TC-WEBHOOK** cases for fail-open/fail-fast edge
  behavior cannot be fully specified until the webhook
  failure strategy design doc is shared
  (tracked in TestPlanGaps.md)

---

## Revision History

| Cycle | Change |
| --- | --- |
| v1.0.0 | Initial review: Score 6/10. Major gaps: data layer TBD, namespace topology TBD, API key surface undefined, BYOIDP blocking. |
| v1.1.0 | Re-review after update with RHAISTRAT-1741, Architecture v2, S1–S6 stories. Score improved to 9/10. Key resolutions: data layer (PostgreSQL + tenant column), namespace topology (label-selector), API key endpoints (S4), BYOIDP deferred. Remaining gaps: ValidationResult schema, webhook failure strategy, X-MaaS-Tenant header spec. |
