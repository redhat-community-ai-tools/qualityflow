---
feature: ogx_to_praxis_migration
source_key: RHAISTRAT-2277
score: 8
pass: true
verdict: Ready
scores:
  specificity: 2
  grounding: 2
  scope_fidelity: 1
  actionability: 1
  consistency: 2
last_updated: '2026-08-11'
auto_revised: true
before_score: 7
before_scores:
  specificity: 2
  grounding: 2
  scope_fidelity: 1
  actionability: 1
  consistency: 1
error: null
---
# Test Plan Review — OGX to Praxis Migration

## Rubric Scores

| Criterion | Score | Notes |
|-----------|-------|-------|
| Specificity | 2/2 | Risks name Praxis's absence from the 3.5-ea.2 architecture inventory, the nonexistent delegation protocol, the two-phase switchover ordering, and the 39-of-61 regulated deployments. Priorities name `file_search` RAG against pre-existing OGX data and `file-*`/`vs_*` ID continuity. Swap test passes on every risk row. |
| Grounding | 2/2 | All 11 Section 4 entries trace to verbatim strategy sentences; zero suspected fabrications. Versions, table names, and auth variables are sourced. TBDs carry an inline reason and a resolving document type. The plan declines to specify Praxis's deployment mechanism rather than inventing it. |
| Scope Fidelity | 1/2 | Both citation gates pass — all 8 ACs covered, all 4 NFR categories cited, no invalid citations — and every out-of-scope item is absent from interfaces and test levels. Four in-scope High Level Requirements still map to no objective because the strategy states them without acceptance criteria. |
| Actionability | 1/2 | Two cluster shapes, four user roles, named PostgreSQL tables, real ID formats, and per-purpose tooling are specified. The unresolved Praxis deployment mechanism blocks provisioning the primary component under test, and five or more questions remain. |
| Consistency | 2/2 | All seven cross-checks pass. Section 4 is now a subset of Section 1.2; Section 9.2 enumerates all 11 interfaces; every NFR category is addressed with 7.1 the sole justified Not Applicable; placeholders correct pre-create-cases. |

**Total: 8/10 — Verdict: Ready**

## Grounding Cross-Reference

| Section 4 Entry | Source Match | Status |
|-----------------|-------------|--------|
| `POST /v1/responses` | "Given a new RHOAI 3.6 deployment, when a customer sends a POST /v1/responses request, then the request is served by Praxis..." | Grounded |
| `POST /v1/embeddings` | "Given a new 3.6 deployment, when a customer sends POST /v1/embeddings, then the request is routed by Praxis to the configured embedding backend..." | Grounded |
| `GET /v1/files/{id}` | "measured by: GET /v1/files/{existing_id} and GET /v1/vector_stores/{existing_id} return the same data as pre-upgrade." | Grounded |
| `GET /v1/vector_stores/{id}` | Same sentence as above. | Grounded |
| `POST /v1/files` | "File upload (/v1/files), vector store creation (/v1/vector-stores), and file-to-vector-store attachment must also route through the new entrypoint." | Grounded |
| `POST /v1/vector-stores` | Same sentence as above. | Grounded |
| `/v1/conversations` | "Praxis becomes the sole publicly reachable implementation of /v1/responses, /v1/conversations, and /v1/embeddings in RHOAI 3.6." | Grounded |
| OGX internal delegation on port 8321 | "Praxis delegates state-dependent operations to OGX via internal HTTP calls on port 8321 (the standard OGX server port, cluster-internal only)." | Grounded |
| Platform Gateway HTTPRoute | "External ingress: Platform Gateway (Envoy) routes external traffic to Praxis via Gateway API HTTPRoutes." | Grounded |
| OGXServer | "The OGX K8s Operator (OGXServer CRD) continues to manage the OGX server lifecycle for upgraded deployments." | Grounded |
| DataScienceCluster | "e.g., a flag on the DataScienceCluster CR or OGXServer CR that re-enables direct OGX routing" — plan preserves the hedge as "Candidate location ... mechanism not yet confirmed" | Grounded |

No entry required a suspected-fabrication mark.

## Section-by-Section Feedback

### Scope Fidelity (1/2)

Four in-scope High Level Requirements have no test objective: file upload, vector store creation,
and file-to-vector-store attachment (P1); streaming Responses (P1); non-RAG Responses covering
tool-calling and agentic workflows (P2); and continued accessibility of existing OGX-managed
embeddings data (P2). The strategy lists all four as requirements but writes no acceptance
criterion for any of them.

The plan keeps these in Section 1.2 scope and Section 2.3 priorities, keeps their interfaces in
Sections 4 and 9.2, discloses the omission in Section 1.3, and files it in TestPlanGaps.md as a
request for acceptance criteria. That is the correct handling — fabricating AC numbers to satisfy
the coverage gate would be strictly worse.

Remediation is upstream: PM and Engineering add acceptance criteria to RHAISTRAT-2277, then re-run
`/test-plan-update`. The plan must not invent citations to close this.

### Actionability (1/2)

Open questions a platform engineer would still raise: which OpenShift z-stream and which RHOAI 3.5
and 3.6 builds, how Praxis is deployed at all, which vector I/O provider backs the RAG fixture,
which of the 61 deployment profiles to build, which tool proves port 8321 is unreachable, and what
the request and response payload shapes are.

Every one is recorded in TestPlanGaps.md with the document type that would resolve it, and none is
answerable from the strategy — Praxis is not in the architecture inventory and no ADR exists. This
score is bounded by the source material rather than by the writing, and should improve once Praxis
architecture onboarding or an ADR lands. Do not invent values to raise it.

## Revision History

Initial assessment scored 7/10 (Specificity 2, Grounding 2, Scope Fidelity 1, Actionability 1,
Consistency 1) with a verdict of Revise.

One revision cycle applied:

- Removed `/v1/chat/completions` and `/v1/messages` from Sections 4 and 9.2. Both appeared in the
  strategy's technical approach but in neither its acceptance criteria nor its scope statements,
  and `/v1/messages` was excluded by Section 1.2's Out of Scope entry for Anthropic Messages,
  restating the strategy's own exclusion. The removal and the open question behind it are recorded
  in TestPlanGaps.md.
- Added a Section 1.3 note disclosing the four in-scope requirements that carry no acceptance
  criterion, and filed the corresponding gap.

Consistency rose 1 to 2 as Section 4 became a subset of Section 1.2. Scope Fidelity and
Actionability are unchanged and are bounded by the source strategy.
