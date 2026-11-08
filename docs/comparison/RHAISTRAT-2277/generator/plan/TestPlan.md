---
feature: ogx_to_praxis_migration
source_key: RHAISTRAT-2277
source_type: strat
status: In Review
author: OGX QE
components:
- Inference Gateway
- OGX Core
additional_docs: []
last_updated: '2026-08-11'
version: 1.0.0
reviewers: []
---
# ogx_to_praxis_migration Test Plan

_OGX QE – End-to-end migration, RAG continuity, and state integrity testing_

**Strategy**: [RHAISTRAT-2277](https://redhat.atlassian.net/browse/RHAISTRAT-2277)

---

## 1. Executive Summary

### 1.1 Purpose

This plan validates the migration of the Responses, Conversations, and RAG (file_search and Vector
Store) APIs from OGX to Praxis as the sole customer-facing entrypoint in RHOAI 3.6. Praxis becomes
the public implementation of `/v1/responses`, `/v1/conversations`, and `/v1/embeddings`, while OGX
is retained as an internal, cluster-only state backend reached by delegation on port 8321.

The business driver is twofold. New customers must not encounter two competing implementations of
the same OpenAI-compatible API, and the 61 existing OGX deployments — 39 of them in regulated
industries — must cross the 3.5-to-3.6 release boundary without state loss or application code
changes. Testing therefore concentrates on what the customer can observe: that greenfield
deployments expose only Praxis, that upgraded deployments continue to resolve pre-existing file and
vector store IDs, that RAG retrieval still returns correct citations from data written under 3.5,
that no resource is dual-written, that tenant isolation survives the new internal boundary, and
that routing can be rolled back to OGX inside the transition window.

### 1.2 Scope

#### In Scope (OGX QE Responsibilities)

- Praxis as the single public entrypoint for `/v1/responses`, `/v1/conversations`, and
  `/v1/embeddings` in greenfield 3.6 deployments
- Verification that OGX port 8321 is not reachable from outside the cluster
- Upgrade path validation: Files, Vector Stores, Responses history, and Conversations history
  remain intact and reachable through Praxis after a 3.5-to-3.6 upgrade
- Continuity of existing file IDs (`file-*`) and vector store IDs (`vs_*`) post-upgrade
- End-to-end RAG continuity: `/v1/responses` with the `file_search` tool returning correct
  citations and annotations sourced from pre-existing OGX-managed data
- Error behaviour when Praxis cannot reach OGX for a state-dependent operation
- State ownership and dual-write prevention across Files, Vector Stores, Responses, Conversations
- Tenant isolation across the Praxis-to-OGX internal delegation boundary
- Rollback: reverting external routing from Praxis to OGX during the transition window
- File upload, vector store creation, and file-to-vector-store attachment through the new entrypoint
- Streaming Responses requests through Praxis

#### Out of Scope (Other Teams)

- Full data migration from OGX PostgreSQL to a Praxis-native state store, deferred to a future
  release
- OGX removal or deprecation; OGX remains deployed as an internal backend in upgraded deployments
- Praxis support for non-OpenAI-compatible APIs such as Llama Stack native and Anthropic Messages
- Changes to OGX's internal provider architecture, covering inference providers, vector DB
  providers, and file processors
- Batch inference API (`/v1/batches`) migration
- Multi-cluster and multi-region migration coordination
- Changes to the OGX Distribution container image or its dependency chain

### 1.3 Test Objectives

1. Verify Praxis is the sole publicly reachable implementation of `/v1/responses` in a new 3.6
   deployment, with no competing OGX endpoint externally exposed, via an e2e API test plus a
   network reachability scan (AC: #1 — only one Service/HTTPRoute exposes /v1/responses externally
   and OGX port 8321 is not externally reachable).
2. Verify `POST /v1/embeddings` on a greenfield 3.6 deployment is routed by Praxis to the
   configured embedding backend and returns a valid embedding response, asserting correct vector
   dimensions (AC: #2 — successful embedding response with correct vector dimensions).
3. Verify existing file IDs (`file-*`) and vector store IDs (`vs_*`) remain accessible with
   identical data through Praxis after a 3.5-to-3.6 upgrade, comparing `GET /v1/files/{id}` and
   `GET /v1/vector_stores/{id}` responses before and after (AC: #3 — existing file and vector_store
   IDs accessible through Praxis post-upgrade without customer code changes).
4. Verify triggering the rollback procedure on an upgraded deployment reverts external routing to
   OGX and restores service, asserting `POST /v1/responses` succeeds through OGX within five
   minutes of rollback initiation (AC: #4 — rollback restores OGX-served responses within 5
   minutes with state intact).
5. Verify `POST /v1/responses` with the `file_search` tool on an upgraded deployment returns
   correct citations and annotations referencing pre-upgrade file IDs, validating citation file IDs
   and annotation byte offsets (AC: #5 — citations reference pre-upgrade file IDs with valid
   annotation byte offsets).
6. Verify Praxis returns an OpenAI-compatible error response when OGX is unavailable for a
   state-dependent operation, simulating OGX unavailability and asserting HTTP 503 with a
   structured error body (AC: #6 — error response matches the OpenAI API error schema with type,
   message, and code fields).
7. Verify no logical resource — File, Vector Store, Response, or Conversation — is dual-written to
   both OGX and Praxis state stores, via audit log analysis of write operations during integration
   testing (AC: #7 — each resource ID written to exactly one backend).
8. Verify tenant isolation is maintained across the Praxis-to-OGX internal delegation boundary,
   asserting that tenant A credentials cannot reach tenant B resources through the delegation path
   (AC: #8 — cross-tenant access is denied through the delegation path).
9. Verify representative existing OGX customer deployment profiles upgrade to 3.6 without state
   loss or required application code changes, and that existing file and vector store IDs remain
   valid post-upgrade (NFR: Backwards Compatibility — deployments upgrade without state loss or app
   code changes and IDs remain valid).
10. Verify Praxis enforces authentication at the public boundary using platform-standard mechanisms
    and that OGX's existing OAuth2/OIDC authentication is not bypassed by the internal delegation
    path (NFR: Security — tenant isolation and ACL enforcement maintained, public-boundary auth
    enforced without bypassing OGX auth).
11. Verify each resource type has exactly one authoritative backend with no dual-write, and that
    unavailable-backend errors are OpenAI-compatible, combining write-path audit with error schema
    validation (NFR: State Integrity — single authoritative backend per resource type and
    OpenAI-compatible errors for unavailable backends).
12. Verify that when OGX is unavailable Praxis returns correct OpenAI-compatible error responses
    rather than hanging or surfacing platform-internal errors (NFR: Availability — correct
    OpenAI-compatible errors on OGX unavailability with no hangs or internal errors).

Four in-scope requirements carry no objective above because the strategy states them as High Level
Requirements without a matching acceptance criterion: file upload, vector store creation, and
file-to-vector-store attachment through the new entrypoint (P1); streaming Responses requests (P1);
non-RAG Responses covering tool-calling and agentic workflows (P2); and continued accessibility of
existing OGX-managed embeddings data (P2). Objectives for these cannot cite an AC that does not
exist, so they are recorded in TestPlanGaps.md as a request for PM and Engineering to add
acceptance criteria. They remain in scope and will gain objectives once those criteria land.

---

## 2. Test Strategy

### 2.1 Test Levels

- **E2E System Testing** — End-to-end exercise of the Praxis-fronted API surface through the
  deployed Platform Gateway, across both greenfield and upgraded topologies, including the
  3.5-to-3.6 upgrade transition itself, rollback by route reversion, and OGX-unavailable failure
  handling. Verified through external interfaces: HTTP API responses, network reachability of OGX
  port 8321, and audit logs.

The strategy describes no dashboard or browser-facing surface for this feature, so no UI test level
is defined. If a migration status or rollback control is later exposed in the dashboard, a UI level
must be added.

### 2.2 Test Types

- **Positive Testing** — Valid greenfield requests served solely by Praxis; upgraded-deployment
  requests against pre-existing file and vector store IDs; successful embeddings with correct
  vector dimensions; successful file_search RAG responses with correct citations and annotations;
  rollback completing inside the five-minute window.
- **Negative Testing** — Requests against an unavailable OGX backend expecting an OpenAI-compatible
  503; cross-tenant access attempts across the delegation boundary; attempts to reach OGX port 8321
  directly from outside the cluster; dual-write detection through audit log analysis.

### 2.3 Test Priorities

- **P0 (Critical)** - Praxis is the sole reachable `/v1/responses`, `/v1/conversations`, and
  `/v1/embeddings` entrypoint in greenfield 3.6; upgraded deployments preserve Files, Vector
  Stores, Responses, and Conversations state; file_search RAG works end to end against
  pre-existing OGX data; no dual-write of any logical resource; no customer code changes required;
  auth, routing, and policy enforcement owned by Praxis.
- **P1 (High)** - File upload, vector store creation, and file-to-vector-store attachment work
  through the new entrypoint; a documented, operator-supported rollback path reverts routing to OGX
  with state intact; streaming Responses requests work through Praxis.
- **P2 (Medium)** - Non-RAG Responses covering tool-calling and agentic workflows work through
  Praxis; existing OGX-managed embeddings data remains accessible through the new entrypoint.

---

## 3. Test Environment

### 3.1 Infrastructure & Configuration

Two cluster shapes are required for every migration-facing objective:

- **Greenfield 3.6 cluster** — fresh install with Praxis as the sole public entrypoint and OGX
  either absent or not externally exposed.
- **Upgraded cluster** — provisioned at 3.5 GA with pre-existing OGX state, then upgraded to 3.6
  to exercise the routing switchover. The same cluster must support triggering the rollback
  procedure and observing OGX regain public routing.

Cluster-side requirements:

- OpenShift and RHOAI version pins for both the 3.5 source and 3.6 target are TBD.
- Components present: Praxis (deployment mechanism TBD), OGX Distribution v1.1.2 or later, OGX K8s
  Operator with the OGXServer CRD, rhods-operator, odh-model-controller, and the Platform Gateway
  with Gateway API and Kuadrant/Authorino.
- Gateway API HTTPRoutes directing external traffic to Praxis, and a NetworkPolicy restricting OGX
  port 8321 to accept traffic only from Praxis. The environment must permit an external network
  scan against port 8321.
- Kuadrant AuthPolicy enforcing API key or OpenShift token auth at the Praxis boundary, with OGX's
  OAuth2/OIDC configuration (`AUTH_ISSUER`, `AUTH_JWKS_URI`) intact.
- A reachable vLLM embedding endpoint, or OGX's embedding provider, for `/v1/embeddings` routing.
- OGX's configured vector I/O provider for RAG. The strategy names pgvector, Milvus, and FAISS as
  possibilities without selecting one; the provider must match the pre-existing state under test.
- At least two tenants with distinct credentials, to exercise isolation across the boundary.
- A means of making OGX unreachable — scale to zero or network partition — to drive the
  unavailable-backend paths.
- Write-operation audit logging enabled and collectible, to support the dual-write objective.

### 3.2 Test Data Requirements

- **Pre-upgrade OGX state fixture** — Files with `file-*` IDs, Vector Stores with `vs_*` IDs, and
  Responses and Conversations history seeded in OGX PostgreSQL before the upgrade, so post-upgrade
  and post-rollback assertions can compare against a known baseline.
- **Vector store content for RAG** — at least one vector store with attached files whose content
  supports file_search retrieval, so citation correctness and annotation byte offsets can be
  validated against known source text.
- **OpenAI-compatible request payloads** — request and response shapes for `/v1/responses`
  including a file_search tool invocation, `/v1/embeddings`, `/v1/files`, `/v1/vector-stores`, and
  file-to-vector-store attachment. Exact schemas depend on Praxis's undocumented API.
- **Multi-tenant data** — files, vector stores, and conversations owned by at least two distinct
  tenants.
- **Deployment profile variations** — the strategy cites 61 existing deployments without
  enumerating their configuration parameters, so the sampling matrix is TBD.
- **Migration report baseline** — the expected shape of the before-and-after state inventory report
  produced during upgrade, required to assert on the regulated-customer audit evidence. Format TBD.

### 3.3 Test Users

- **Cluster administrator** — able to trigger the upgrade, initiate rollback, and reconfigure
  Gateway HTTPRoutes.
- **Two authenticated API consumers** — representing separate tenants, using API key or OpenShift
  token auth through Kuadrant AuthPolicy, exercising Responses, Conversations, Embeddings, and RAG.
- **Unauthenticated user** — to confirm OGX port 8321 and the internal delegation path are not
  externally reachable and that unauthenticated public API calls are rejected at the Praxis
  boundary.
- **Internal delegation identity** — whatever identity Praxis presents when calling OGX. The
  mechanism is undefined because the delegation protocol does not yet exist.

### 3.4 Test Tools

- `oc` and `kubectl` for inspecting Service, HTTPRoute, and NetworkPolicy state, driving the
  upgrade, reading the OGXServer and DataScienceCluster CRs, and executing rollback.
- `curl` for exercising the OpenAI-compatible endpoints and validating error response schemas.
- A network scanning tool capable of confirming port 8321 is unreachable from outside the cluster.
  The strategy states the requirement without naming a tool.
- `psql` for inspecting the OGX state tables `files_metadata`, `vector_store_metadata`, and
  `ogx_kvstore` before and after upgrade and rollback.
- Log and audit collection tooling for write-operation analysis.
- pytest as the automation harness for the generated e2e suites.

---

## 4. Interfaces Under Test

| Interface | Type | Purpose |
|-----------|------|---------|
| `POST /v1/responses` | REST | Customer-facing responses API served by Praxis, including the file_search RAG flow |
| `POST /v1/embeddings` | REST | Customer-facing embeddings API routed by Praxis to the configured backend |
| `GET /v1/files/{id}` | REST | Retrieve pre-existing file metadata through Praxis after upgrade |
| `GET /v1/vector_stores/{id}` | REST | Retrieve pre-existing vector store data through Praxis after upgrade |
| `POST /v1/files` | REST | File upload routed through the new entrypoint |
| `POST /v1/vector-stores` | REST | Vector store creation routed through the new entrypoint |
| `/v1/conversations` | REST | Customer-facing conversations API served by Praxis |
| OGX internal delegation on port 8321 | REST | Praxis-to-OGX calls for stateful operations; verified negatively as not externally reachable |
| Platform Gateway HTTPRoute | CRD | External routing target repointed to Praxis during upgrade and reverted on rollback |
| OGXServer | CRD | OGX server lifecycle under the OGX K8s Operator, including any internal-only mode |
| DataScienceCluster | CRD | Candidate location for the rollback flag; mechanism not yet confirmed |

---

## 5. Test Cases

Ten test case specifications have been generated. See the index for the full list.

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| TC-E2E | 6 | P0: 5, P1: 1 |
| TC-NEG | 3 | P0: 3 |
| TC-UPG | 1 | P0: 1 |

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
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each interface in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Interfaces Covered | Priority |
|----|----------|-------------------|----------|
| TC-E2E-001 | Greenfield serves /v1/responses from Praxis, no competing implementation | `POST /v1/responses`, Platform Gateway HTTPRoute, OGXServer | P0 |
| TC-E2E-002 | Greenfield routes /v1/embeddings to the configured backend | `POST /v1/embeddings` | P0 |
| TC-E2E-003 | Pre-existing file and vector store IDs resolve identically after upgrade | `GET /v1/files/{id}`, `GET /v1/vector_stores/{id}` | P0 |
| TC-E2E-004 | Write path routes each resource to exactly one backend | `POST /v1/files`, `POST /v1/vector-stores`, `/v1/conversations` | P0 |
| TC-E2E-005 | RAG file_search returns citations from pre-upgrade OGX data | `POST /v1/responses`, OGX internal delegation on port 8321 | P0 |
| TC-E2E-006 | Rollback reverts routing to OGX within five minutes, state intact | Platform Gateway HTTPRoute, DataScienceCluster, OGXServer | P1 |

### 6.2 E2E Coverage Matrix

| Interface (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| `POST /v1/responses` | TC-E2E-001, TC-E2E-005 |
| `POST /v1/embeddings` | TC-E2E-002 |
| `GET /v1/files/{id}` | TC-E2E-003 |
| `GET /v1/vector_stores/{id}` | TC-E2E-003 |
| `POST /v1/files` | TC-E2E-004 |
| `POST /v1/vector-stores` | TC-E2E-004 |
| `/v1/conversations` | TC-E2E-004 |
| OGX internal delegation on port 8321 | TC-E2E-005 |
| Platform Gateway HTTPRoute | TC-E2E-001, TC-E2E-006 |
| OGXServer | TC-E2E-001, TC-E2E-006 |
| DataScienceCluster | TC-E2E-006 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

**Not Applicable** — the strategy describes no runtime image pulls, external registry dependencies,
or catalog source configuration introduced by this migration. Praxis platform onboarding and the
OGX K8s Operator install model are referenced but not described as changing in a way that affects
disconnected or air-gapped operation.

### 7.2 Upgrade/Migration

This is the central concern of the feature. Testing must confirm that the 3.5-to-3.6 upgrade
preserves Files, Vector Stores, Responses, and Conversations without loss; that pre-existing
`file-*` and `vs_*` IDs return identical data through Praxis afterwards; that the two-phase
switchover — Praxis healthy first, HTTPRoutes repointed second — never opens a traffic black hole;
that rollback during the transition window leaves state intact; and that no logical resource is
dual-written at any point in the transition.

### 7.3 Performance/Scalability

The Praxis-to-OGX delegation hop adds latency to RAG workflows, which involve an embedding query,
vector retrieval, and context assembly. The delegation path must be benchmarked against direct OGX
access, and unavailable-backend behaviour must be exercised under load so that failures surface as
errors rather than hangs. No pass or fail threshold can be set yet: the strategy's own open
questions record that no performance targets exist in the RFE or architecture context and that PM
input is needed.

### 7.4 RBAC/Authorization

Testing must confirm tenant isolation across the Praxis-to-OGX internal boundary, so that tenant A
credentials cannot reach tenant B resources through the delegation path; that the NetworkPolicy
restricting OGX port 8321 to Praxis-only traffic holds against an external scan; and that Praxis
owns authorization enforcement for all public traffic.

### 7.5 Security

Testing must confirm that OGX's existing OAuth2/OIDC authentication is not bypassed by the internal
delegation path, and that Praxis enforces authentication at the public boundary using
platform-standard mechanisms — Kuadrant AuthPolicy or kube-auth-proxy. This covers the
authentication mechanism itself, as distinct from the per-tenant access boundaries in 7.4.

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Praxis architecture is unknown; its CRDs, operator model, and internal architecture are undocumented, and divergent API contracts would break the transparent migration | High | High | Require Praxis architecture onboarding before sprint 1; validate contract compatibility with automated conformance tests against OGX's existing suite |
| The Praxis-to-OGX delegation protocol does not yet exist, leaving the contract for Files, Vector Stores, file_search, Conversations, and tenant context propagation undefined | High | High | Treat protocol definition as a blocking dependency for test design; delegation-path test cases cannot be specified in detail until it is documented |
| Delegation latency degrades RAG performance, as the internal hop adds cost to embedding query, vector retrieval, and context assembly | Medium | Medium | Benchmark the delegation path against direct OGX access; collocate Praxis and OGX pods by affinity if latency exceeds thresholds once they are set |
| Upgrade ordering dependencies; the switchover must follow Praxis health but precede OGX losing ingress, and the wrong order creates a traffic black hole | High | Medium | Two-phase switchover with rhods-operator reconciliation enforcing the ordering; test the failure mode explicitly |
| Regulated customer audit requirements; 39 of 61 deployments need auditable evidence of state integrity through the migration | High | Medium | Generate a migration report during upgrade recording state inventory counts before and after, and assert against it |
| State migration complexity in future releases, since OGX-as-state-backend is a transitional architecture | Low | Medium | Design the delegation protocol behind a clean interface replaceable by native Praxis state access without API changes |

---

## 9. Appendix

### 9.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| TC-E2E | 6 | 5 | 1 | 0 |
| TC-NEG | 3 | 3 | 0 | 0 |
| TC-UPG | 1 | 1 | 0 | 0 |
| **Total** | **10** | **9** | **1** | **0** |

### 9.2 Interface Coverage

| Interface | Test Cases | Coverage |
|-----------|------------|----------|
| `POST /v1/responses` | TC-E2E-001, TC-E2E-005, TC-E2E-006, TC-NEG-002 | |
| `POST /v1/embeddings` | TC-E2E-002 | |
| `GET /v1/files/{id}` | TC-E2E-003, TC-NEG-002, TC-NEG-003 | |
| `GET /v1/vector_stores/{id}` | TC-E2E-003, TC-NEG-003 | |
| `POST /v1/files` | TC-E2E-004 | |
| `POST /v1/vector-stores` | TC-E2E-004 | |
| `/v1/conversations` | TC-E2E-004 | |
| OGX internal delegation on port 8321 | TC-E2E-005, TC-NEG-001, TC-NEG-002, TC-NEG-003 | |
| Platform Gateway HTTPRoute | TC-E2E-001, TC-E2E-006, TC-UPG-001 | |
| OGXServer | TC-E2E-001, TC-E2E-006, TC-NEG-001 | |
| DataScienceCluster | TC-E2E-006 | |

### 9.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-11 | Initial test plan |

---

## End of Test Plan
