---
feature: ogx_to_praxis_migration
source_key: RHAISTRAT-2277
status: Open
gap_count: 32
last_updated: '2026-08-11'
---
# Gaps — OGX to Praxis Migration

Every gap below traces to something the strategy itself leaves open. The strategy names the root
cause directly: Praxis is not in the RHOAI 3.5-ea.2 architecture inventory, and its architecture,
CRDs, operator model, and capabilities are unknown to the architecture context.

## Scope & Endpoints

- Praxis's internal architecture, CRDs, and operator model are undocumented — resolved by an ADR or
  Praxis architecture onboarding document.
- The Praxis-to-OGX delegation protocol, including request and response schema and tenant context
  propagation, does not exist yet — resolved by an ADR or API spec.
- The concrete rollback mechanism is unconfirmed. The strategy proposes "a flag on the
  DataScienceCluster CR or OGXServer CR" as a possibility, not a decision — resolved by an ADR or
  design doc.
- Greenfield state ownership is undetermined. The strategy's own ownership table lists Files, Vector
  Stores, Responses history, and Conversations history as "Praxis or OGX (TBD)" for greenfield —
  resolved by an ADR or architecture doc.
- No performance or latency targets exist for the delegation path, so no performance objective could
  be grounded — resolved by PM and Engineering input captured in an ADR or performance requirements
  doc.
- No explicit CLI commands or CRD field-level test hooks are named for verifying OGX's internal-only
  exposure, such as the exact NetworkPolicy spec or HTTPRoute naming — resolved by a design doc or
  ADR.
- Four in-scope High Level Requirements have no acceptance criterion, so no AC-traceable test
  objective can be written for them: file upload, vector store creation, and file-to-vector-store
  attachment through the new entrypoint (P1); streaming Responses requests through Praxis (P1);
  non-RAG Responses covering tool-calling and agentic workflows (P2); and continued accessibility of
  existing OGX-managed embeddings data (P2) — resolved by PM and Engineering adding acceptance
  criteria to the strategy.
- Contract parity for `/v1/chat/completions` and `/v1/messages` is asserted in the strategy's
  technical approach but appears in neither its acceptance criteria nor its scope statements, and
  `/v1/messages` is arguably excluded by the Out-of-Scope entry for Anthropic Messages. Both were
  removed from Section 4 pending clarification — resolved by PM confirming whether OpenAI-compatible
  contract parity for these two endpoints is in scope for 3.6 QE.

## Test Strategy & Risks

- Praxis's internal architecture is entirely undocumented; the strategy flags this as a critical gap
  blocking sprint 1 — resolved by an ADR or architecture doc.
- No ADR exists for this strategy. The strategy lists its ADR as "To be created if needed" —
  resolved by an ADR.
- No performance or latency targets are defined for the Praxis-to-OGX delegation path, so Section
  7.3 can describe what to measure but not what constitutes a pass — resolved by a design doc or PM
  input.
- The exact delegation protocol contract, including tenant context propagation, is undefined —
  resolved by an API spec or ADR.
- Greenfield state ownership for Files, Vector Stores, Responses, and Conversations is marked TBD in
  the strategy — resolved by an ADR or architecture doc.
- The concrete operator-level rollback mechanism, meaning a specific CR field or flag, is not yet
  defined — resolved by a design doc or ADR.
- How Praxis is deployed — standalone operator, module, or integrated component — is unresolved,
  which affects the scope of rhods-operator integration testing — resolved by a design doc.

## Environment & Infrastructure

- Praxis's architecture, deployment model, and CRDs are undocumented, so QE cannot determine how to
  deploy or configure Praxis in the test environment — resolved by an architecture doc or
  component-architecture.json produced by Praxis onboarding.
- The Praxis-to-OGX delegation protocol does not exist, which affects the internal auth and service
  account setup, error-handling paths, and network configuration QE needs to exercise — resolved by
  an ADR or design doc defining the delegation API contract.
- The rollback mechanism implementation is undefined, so rollback test setup cannot be scripted —
  resolved by an ADR or design doc.
- Greenfield state ownership is TBD, which determines what backend and test data must be
  provisioned for greenfield scenarios — resolved by a design doc or architecture onboarding.
- No OpenShift or RHOAI version pins are specified for either the 3.5 upgrade source or the 3.6
  target — resolved by release documentation or an ADR.
- The vector DB provider is unspecified; the strategy names pgvector, Milvus, and FAISS as
  possibilities without selecting one, and RAG continuity tests need the correct backend
  provisioned — resolved by architecture context (ogx-distribution.md) or a design doc.
- No performance or latency targets exist for the delegation path, so no performance test
  environment or thresholds can be defined — resolved by PM and Engineering input captured in an ADR
  or NFR doc.
- The migration and audit report format is undefined, and it is needed to write assertions for the
  regulated-customer audit evidence requirement — resolved by a design doc.
- The characteristics of the 61 customer deployment profiles are not enumerated, so there is no
  configuration matrix for QE to sample from — resolved by the OGX to Praxis 3.6 Migration Plan
  document or PM input.
- No ADR is available for this strategy, and most infrastructure specifics above depend on decisions
  not yet made — resolved by an ADR once created.

## Test Case Coverage Gaps

Recorded when test cases were generated. Interface coverage, objective traceability, TC counts, and
category scope all validated clean; the items below are what the generated suite cannot yet cover.

- All 11 interfaces from Section 4 have E2E coverage and all 12 test objectives map to at least one
  test case. No uncovered interface or orphan objective remains.
- No performance test case was generated for the Praxis-to-OGX delegation latency described in
  Section 7.3. The strategy sets no latency or throughput target, so any pass or fail threshold
  would be invented — resolved by PM and Engineering setting delegation performance targets, after
  which a TC-NFR case can be added.
- TC-UPG-001 measures the upgrade traffic gap but asserts no maximum. No acceptable upgrade
  disruption window is defined anywhere in the strategy, so the case records the observed gap as a
  baseline for sign-off instead — resolved by PM defining an acceptable disruption window.
- The four in-scope requirements listed above that carry no acceptance criterion have no test cases,
  because a test case must trace to a Section 1.3 objective and no objective could be written for
  them — resolved by the same acceptance criteria request.
- `AUTH_ISSUER` and `AUTH_JWKS_URI` are named in Section 3.1 but no test case exercises a
  non-default value for either. TC-NEG-001 and TC-NEG-003 verify that authentication is enforced and
  not bypassed, not that alternate issuer configurations behave correctly — resolved by confirming
  whether alternate OIDC issuer configurations are in scope for 3.6 QE.
- TC-E2E-004 targets the upgraded topology only. Greenfield write ownership is listed as "Praxis or
  OGX (TBD)" in the strategy, so no greenfield dual-write case could be specified — resolved by the
  greenfield state ownership decision.
- TC-E2E-006 does not name a concrete rollback trigger. The step records whichever mechanism ships,
  since the strategy proposes a DataScienceCluster or OGXServer CR flag without deciding — resolved
  by the rollback mechanism decision.
