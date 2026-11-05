---
feature: agent_catalog
source_key: RHOAIENG-70680
score: 6
pass: false
verdict: Rework
scores:
  specificity: 2
  grounding: 1
  scope_fidelity: 1
  actionability: 1
  consistency: 1
last_updated: '2026-07-07'
auto_revised: false
before_score: 6
before_scores:
  specificity: 2
  grounding: 1
  scope_fidelity: 1
  actionability: 1
  consistency: 1
error: null
---
# Agent Catalog Test Plan Review

**Feature**: agent_catalog
**Strategy**: [RHOAIENG-70680](https://redhat.atlassian.net/browse/RHOAIENG-70680)
**Test Plan**: [TestPlan.md](TestPlan.md)

---

## Score Table

| Criterion | Score | Max | Evidence | Rationale |
| ----------- | ------- | ----- | ---------- | ----------- |
| Specificity | 2 | 2 | P0 definition names specific agent catalog scenarios (list agents, get detail, plugin health). Risks name GitHub API unavailability, filterQuery complexity, MLMD schema migration. | Swap test passes: replacing "agent catalog" with another catalog feature would break most test objectives and risk entries. |
| Grounding | 1 | 2 | Concepts (list, filter, search, detail, sources) map to strategy deliverables. | Specific REST paths, the filter_options endpoint, artifacts endpoint, filterQuery operators (=, !=, LIKE, ILIKE, IN, AND, OR), ConfigMap names (default-catalog-sources, model-catalog-sources), --catalogs-path, --skip-github-fetch, and make process-agents are not present in the strategy text. These are plausible technical elaborations from child issues but not grounded in the linked strategy. |
| Scope Fidelity | 1 | 2 | All three strategy deliverables (metadata pipeline, API endpoints, operator integration) map to test objectives 1-7. Out-of-scope items (UI, execution, versioning) correctly excluded. | Minor scope creep: the artifacts endpoint (Section 4, row 4) appears with no strategy justification. Custom properties forwarding and sourceLabel resolution are elaborations beyond what the strategy text describes. |
| Actionability | 1 | 2 | ConfigMap names are concrete. Test data specifies counts (7 agents, 15 starter kits). Tools named (oc, curl, pytest, psql, jq). RBAC explicitly marked TBD with rationale. | Missing: no versions for OpenShift, RHOAI, or PostgreSQL. No sample YAML for test data. No cluster sizing or resource requirements. A tester picking this up would need to ask version and environment questions before starting. |
| Consistency | 1 | 2 | Section 10.2 lists all Section 4 endpoints. Priorities align with P0/P1/P2 definitions in Section 2.3. NFRs (disconnected, upgrade, performance) are relevant to feature scope. No contradictions found between sections. | Sections 5, 6, and 10.1 are unpopulated (expected pre-TC generation). E2E coverage cannot be verified yet. Section 7.4 RBAC is TBD which creates an open gap in the consistency picture. |

**Total: 6/10**
**Verdict: Rework**

---

## Grounding Cross-Reference

| Section 4 Entry | Strategy Justification | Verdict |
| ----------------- | ---------------------- | --------- |
| GET /agents | Strategy: "full API support (list, filter, search)" | EXTRAPOLATED -- strategy names the capability but not this specific path |
| GET /agents/{agent_id} | Strategy: "detail" in API support list | EXTRAPOLATED -- strategy implies detail retrieval but does not name this endpoint |
| GET /agents/filter_options | Strategy mentions "filtering" but not a dedicated endpoint for filter metadata | SUSPECTED FABRICATION -- no strategy text supports a separate filter_options endpoint |
| GET /agents/{id}/artifacts | No mention of artifacts in strategy text | SUSPECTED FABRICATION -- this endpoint has no strategy justification |
| GET /sources?assetType=agents | Strategy: "sources" in API support list | EXTRAPOLATED -- strategy names source management but not this specific path or query parameter |
| GET /readyz | Standard Kubernetes health endpoint | EXTRAPOLATED -- reasonable inference from operator deployment context |
| GET /healthz | Standard Kubernetes health endpoint | EXTRAPOLATED -- reasonable inference from operator deployment context |

---

## Section-by-Section Feedback

Feedback is provided only for criteria scoring below 2.

### Grounding (Score: 1/2)

**Section 4 -- API Endpoints Under Test**

The seven endpoints listed are plausible but only partially grounded.
The strategy text describes capabilities (list, filter, search, detail,
sources) without specifying REST paths, API versions, or query parameter
schemas. The test plan presents
`/api/agent_catalog/v1alpha1/agents` as established fact, but the
`v1alpha1` version string, the exact path structure, and the query
parameter set (filterQuery operators, orderBy enum values,
nextPageToken) are not in the strategy.

Two endpoints are suspected fabrications:

- `filter_options` -- The strategy mentions filtering but does not
  describe a metadata endpoint that returns available filter fields
  and values. If this endpoint exists, cite the ADR or
  implementation PR.
- `artifacts` -- The strategy does not mention artifacts at all. If
  agent artifacts (images, templates) are part of the feature, the
  strategy or an ADR should be linked.

**Remediation**: Link to ADR, API specification, or implementation PRs
that define these endpoints. Remove endpoints that cannot be traced to
a requirement document. If the endpoints come from child issues (e.g.,
RHOAIENG-XXXXX), add those as `additional_docs` in the test plan
frontmatter and cite them inline.

**Section 9.2 -- Configuration**

ConfigMap names (`default-catalog-sources`, `model-catalog-sources`),
the `--catalogs-path` argument, and the operator template filename
(`catalog-agent-configmap.yaml.tmpl`) are stated as facts but are not
in the strategy text. These likely come from implementation details or
child issues.

**Remediation**: Add source references for each configuration artifact.
If these names come from the operator codebase, cite the relevant file
or PR.

### Scope Fidelity (Score: 1/2)

**Section 1.2 -- In Scope**

The in-scope list includes items that go beyond the strategy:

- "Artifacts endpoint with type filtering (image-artifact,
  template-artifact)" -- not in strategy
- "Custom properties forwarding from upstream YAML" -- strategy
  describes metadata extraction but not custom properties specifically
- "sourceLabel-to-sourceID resolution" -- strategy mentions source
  management but not this specific resolution mechanism

**Remediation**: Either (a) link to additional documents that justify
these scope items, or (b) move ungrounded items to a "Tentative
Scope -- Pending ADR" section so reviewers can distinguish between
confirmed and inferred scope.

**Section 1.3 -- Test Objectives**

Objective 5 (artifacts endpoint) has no strategy backing. Objective 3
(sourceLabel resolution) is an implementation detail elevated to a test
objective without strategy justification.

**Remediation**: Rewrite objectives to trace to strategy deliverables.
If artifacts and sourceLabel resolution are confirmed requirements,
cite the source.

### Actionability (Score: 1/2)

**Section 3.1 -- Test Cluster Configuration**

No version requirements are specified for any component:

- OpenShift version (4.x?)
- RHOAI operator version (minimum version with agent catalog support)
- PostgreSQL version
- Model catalog service version

**Remediation**: Add version constraints or state "latest available"
with a minimum version floor.

**Section 3.2 -- Test Data Requirements**

The plan states "7 agents across frameworks" and "15 starter kits" but
provides no sample YAML, no field-level detail on what "varying
completeness" means, and no guidance on how to construct the test data
ConfigMap.

**Remediation**: Include a sample agent entry (3-5 lines of YAML)
showing required vs optional fields. Define what "missing framework"
and "custom properties" look like concretely.

**Section 7.4 -- RBAC/Authorization**

Marked TBD with good rationale, but this creates an actionability gap.
A tester cannot plan RBAC test cases without knowing the permission
model.

**Remediation**: Either (a) clarify that RBAC testing is deferred to a
follow-up test plan, or (b) document the assumed permission model based
on existing catalog patterns and mark it as
"assumed -- pending confirmation."

### Consistency (Score: 1/2)

**Sections 5, 6, 10.1 -- Unpopulated**

These sections are expected to be empty pre-TC generation. No
inconsistency penalty, but they cannot be evaluated for cross-section
alignment.

**Section 10.2 -- Endpoint Coverage**

The endpoint list matches Section 4, which is correct. However,
coverage cannot be verified until test cases populate the table.

**Section 7.4 vs Section 8 -- RBAC Gap**

Section 7.4 marks RBAC as TBD, but Section 8 (Risks) does not include
a risk entry for "RBAC requirements undefined." If RBAC is a known
gap, it should appear as a risk with mitigation (e.g., "follow existing
catalog permission model until ADR clarifies").

**Remediation**: Add a risk entry for undefined RBAC requirements, or
remove the TBD and state that RBAC follows existing patterns.

---

## Revision Guidance

To move from Rework (6/10) to Revise or Ready, address these
priorities:

1. **Grounding (+1)**: Cite ADR or implementation PRs for all seven
   endpoints. Remove or flag endpoints that cannot be traced.
2. **Scope Fidelity (+1)**: Remove artifacts endpoint and custom
   properties from scope unless an additional document justifies them.
   Separate confirmed scope from inferred scope.
3. **Actionability (+1)**: Add version requirements and sample test
   data YAML. Resolve RBAC TBD with an assumed model.
4. **Consistency (+1)**: Add RBAC risk entry to Section 8. Ensure
   Section 7.4 and Section 8 align on the RBAC gap.

---

## Revision History

| Date | Action | Score |
|------|--------|-------|
| 2026-07-07 | Initial assessment | 6/10 |
