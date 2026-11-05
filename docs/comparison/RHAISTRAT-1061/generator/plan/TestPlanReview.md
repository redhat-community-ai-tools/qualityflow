---
feature: runtime_config_in_crd
strat_key: RHAISTRAT-1061
score: 10
pass: true
verdict: Ready
scores:
  specificity: 2
  grounding: 2
  scope_fidelity: 2
  actionability: 2
  consistency: 2
before_score: 8
before_scores:
  specificity: 2
  grounding: 1
  scope_fidelity: 2
  actionability: 1
  consistency: 2
last_updated: '2026-06-16'
auto_revised: false
error: null
---
# Test Plan Review

## Rubric Scores

| Criterion | Score | Notes |
| --- | --- | --- |
| Specificity | 2/2 | Priorities, risks, test levels, and categories are all feature-specific. No boilerplate. |
| Grounding | 1/2 | 3 of 20 Section 4 entries not traceable to source: config caching by digest, ConfigMap cleanup, configgen stdin input. |
| Scope Fidelity | 2/2 | Every strategy item maps to test objectives. No scope creep, no gaps. |
| Actionability | 1/2 | Tools and test data categories listed, but no specific versions, no sample YAML, test case sections empty. |
| Consistency | 2/2 | All cross-references align: Section 4 to 10.2, priorities to definitions, test levels to interface types. |

**Total: 8/10 — Verdict: Ready**

## Grounding Cross-Reference

| Section 4 Entry | Source Citation | Verdict |
| --- | --- | --- |
| OGXServer CRD (`spec.providers`) | PR #289: "distribution, providers, resources, state storage, network, workload, externalProviders, overrideConfig" | Grounded |
| OGXServer CRD (`spec.resources`) | PR #289: "distribution, providers, resources, state storage" | Grounded |
| OGXServer CRD (`spec.storage`) | PR #295: "generates config.yaml from spec.providers, spec.resources, spec.storage, spec.disabledAPIs" | Grounded |
| OGXServer CRD (`spec.disabledAPIs`) | PR #295: "spec.disabledAPIs" | Grounded |
| OGXServer CRD (`spec.overrideConfig`) | PR #289 + PR #295: "spec.overrideConfig continues to override declarative generation" | Grounded |
| OGXServer CRD (`spec.network.networkPolicy`) | PR #290: "NetworkPolicy is per-CR toggle via spec.network.networkPolicy.enabled" | Grounded |
| Validating admission webhook | PR #122: "Validating admission webhook with cert-manager and OpenShift webhook support confirmed" | Grounded |
| Operator: config generation pipeline | PR #295: "generates config.yaml from spec.providers, spec.resources, spec.storage, spec.disabledAPIs" | Grounded |
| Operator: OCI label loading | PR #295: "Uses OCI label com.ogx.distribution.configs as primary base config source" | Grounded |
| Operator: merge config | RHAIENG-5697: "MergeProviders whole-API-type replacement" | Grounded |
| Operator: immutable ConfigMap creation | PR #295: "Creates immutable ConfigMaps (`<name>-config-<hash>`)" | Grounded |
| Operator: pod rollout trigger | Reasonable inference from immutable ConfigMap hash naming, but not explicitly stated | Extrapolated |
| Operator: embedded config fallback | PR #295: "with embedded config fallback" | Grounded |
| Operator: config caching by digest | No source material mentions caching by image digest | Suspected Fabrication |
| Operator: ConfigMap cleanup | No source explicitly describes cleanup of old immutable ConfigMaps | Suspected Fabrication |
| Operator: legacy adoption | PR #292: "annotation-driven adoption of LLSD PVC/Service/Ingress" | Grounded |
| Operator: PVC orphaning | PR #292: "PVCs orphaned (not deleted)" | Grounded |
| Operator: adoption status conditions | PR #292: "Adoption status conditions tracked" | Grounded |
| Migration: LlamaStackDistribution to OGXServer | PR #289 + RHAIENG-2705 | Grounded |
| configgen CLI (OCI label resolution) | RHAIENG-5698: "no configgen CLI tests" | Grounded |
| configgen CLI (stdin input mode) | RHAIENG-5698 mentions CLI but not stdin mode | Suspected Fabrication |

## Section-by-Section Feedback

### Grounding (scored 1/2)

Three Section 4 entries are not traceable to source material:

1. **"Operator: config caching by digest"** — No PR or Jira issue mentions caching configs by image
   digest. The earlier RHAIENG-4220 description mentioned caching, but that was from the pre-rename
   LlamaStackDistribution era and hasn't been confirmed in the OGXServer implementation. **Fix:**
   Mark as TBD pending code verification, or remove if not implemented.

2. **"Operator: ConfigMap cleanup"** — Immutable ConfigMaps (`<name>-config-<hash>`) will accumulate
   with each config change. No source describes cleanup behavior. **Fix:** Mark as TBD pending code
   verification, or remove.

3. **"`configgen` CLI (stdin input mode)"** — RHAIENG-5698 mentions missing CLI tests but does not
   describe a stdin input mode. **Fix:** Remove this entry or verify against source code.

Additionally, "Operator: pod rollout trigger" is a reasonable inference from immutable ConfigMap
hash naming but should cite the specific mechanism
(new ConfigMap name → Deployment spec change → rolling update).

### Actionability (scored 1/2)

The test plan would benefit from:

1. **Pinning specific versions** (or explicit TBD with rationale) for OpenShift, RHOAI operator, and
   OGX operator image tag.
2. **Adding at least one sample OGXServer CR YAML** in the test data section so a QE engineer can
   start without creating CRs from scratch.
3. **Providing Postgres setup instructions** or referencing a shared test fixture.
4. **Noting the openshift-python-wrapper PR #2647 dependency** as a blocker with a fallback plan
   (e.g., use raw `oc` commands until wrapper is merged).

## Revision History

Initial assessment (v1.1.0 of TestPlan.md, post CRD rename to OGXServer/v1beta1).
