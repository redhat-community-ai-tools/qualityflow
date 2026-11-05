---
feature: maas_multi_tenancy
source_key: RHAIRFE-1487
version: 1.1.0
status: Open
gap_count: 9
last_updated: '2026-05-18'
---
# Gaps — MaaS Multi-Tenancy

> Updated for v1.1.0 — incorporates RHAISTRAT-1741, Architecture v2, RHOAIENG-62570 (S1–S6).
> Items marked **[RESOLVED]** were open questions in
> v1.0.0 that are now answered by Phase 1 stories or
> Architecture v2.

---

## Resolved (from v1.0.0)

- **[RESOLVED — S3]** Data layer topology — Shared
  PostgreSQL with `tenant` column on `api_keys` table
  confirmed by Architecture v2 and S3.
- **[RESOLVED — S1]** Namespace topology — One labeled
  namespace per tenant via
  `maas.opendatahub.io/tenant` label confirmed by S1.
- **[RESOLVED — S4]** API key management API surface —
  `POST /v1/api-keys`,
  `POST /internal/v1/api-keys/validate`,
  `GET /v1/api-keys` specified in S4.
- **[RESOLVED — Phase 2 deferral]** Identity realm
  topology — BYOIDP / realm-per-tenant explicitly
  deferred to Phase 2 (depends on RHAISTRAT-1656).

---

## Open Gaps — Scope & Endpoints

- **`ValidationResult` JSON schema** — S4 names the
  three fields (`tenant`, `userID`, `modelRef`) but does
  not provide the exact JSON structure, field types, or
  error-case responses for
  `POST /internal/v1/api-keys/validate`. Test cases
  TC-APIKEY-002 and TC-E2E-001/002 are blocked until
  this is confirmed. **Resolved by**: OpenAPI spec or
  example response from dev team.

- **X-MaaS-Tenant header specification** — S5 describes
  the header as "optional, coordinate with
  Kuadrant/Authorino owners." It is unclear whether the
  header is injected by the Gateway, Authorino, or
  maas-api, and what behavior is expected if absent or
  mismatched. TC-CONTRACT-001/002 are partially blocked.
  **Resolved by**: Finalized header spec from
  Kuadrant/Authorino team.

- **Webhook failure strategy** — S6 states "follow
  agreed strategy from design doc" for fail-open vs.
  fail-fast behavior. The design document has not been
  shared with QE. TC-WEBHOOK cases for edge behavior
  cannot be written until this is resolved.
  **Resolved by**: Link to finalized design doc or
  explicit policy statement from dev team.

- **Shared model access grant mechanism** — Not
  addressed in S1–S6. How platform admins grant tenant
  access to specific MaaSModelRef resources is undefined
  for Phase 1. **Resolved by**: API spec or design doc
  (likely Phase 2 scope; confirm with dev team).

---

## Open Gaps — Test Strategy

- **Architecture divergence (HCP vs. shared cluster)**
  — RHAISTRAT-1741 auto-generated TL;DR references an
  HCP pattern inconsistent with Architecture v2 and
  S1–S6. If the architectural direction changes,
  significant test coverage would need to be rescoped.
  **Resolved by**: Architectural decision record (ADR) or
  explicit statement from Staff Engineer confirming
  shared-cluster Phase 1 posture.

- **Negative isolation test acceptance criteria** —
  High-level verification themes (cross-tenant token
  reuse, enumeration, subscription visibility) lack
  detailed acceptance criteria with exact expected HTTP
  responses and error codes. TC-ISO test cases use
  inferred expected results. **Resolved by**: Feature
  refinement or security test plan addendum.

---

## Open Gaps — Environment & Infrastructure

- **OpenShift and RHOAI version requirements** —
  Versions 4.19+ and 3.4+ are specified in the test plan
  but not confirmed by any Phase 1 story.
  **Resolved by**: Feature release targeting a specific
  OCP/RHOAI version.

- **MaaSSubscription and MaaSAuthPolicy CR schemas** —
  Field definitions not provided in detail. S1 and S2
  reference these CRs but do not supply a CRD schema.
  Test data in TC files uses inferred field names.
  **Resolved by**: CRD YAML from repository.

- **Kuadrant operator version** — Not specified in any
  Phase 1 story. **Resolved by**: Implementation plan
  pinning Kuadrant version.
