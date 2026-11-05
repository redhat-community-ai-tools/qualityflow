# RHAISTRAT-1061 — QualityFlow round 6

Scored using `h2h-round2/neutral/part1.md` counting rules and its fixed R1–R11 list. Generator and round-4 numbers are carried forward unchanged. Round 6 has 27 STD scenarios, all NEW, no EXISTING mappings. Correctness was checked against the supplied current-main operator checkout; redundancy against the supplied pre-merge opendatahub-tests snapshot. Paths below are relative to those repositories unless identified as QF output.

| metric | generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1 Wrong cases / total | 35/44 | 0/24 | **0/27** |
| 2 Redundant NEW cases / total | 0/44 | 0/24 | **0/27** |
| 3 Requirements covered / total | 10/11 | 9/11 | **9/11** |
| 4 Runnable now / once TBDs answered / total | sample 0/10 / 0/10 / 10 | sample 6/10 / 6/10 / 10; all checked 12/24 / 12/24 / 24 | **sample 0/10 / 0/10 / 10**; estimated 0/27 |
| 5 Verified real problems raised | 3 | 1 | **0** |

**1 — Wrong.** TS-08/09 match duplicate/unknown provider validation (`api/v1beta1/ogxserver_webhook.go:232,259`); TS-11/23 match provider–disabledAPI and override exclusivity CEL rules (`ogxserver_types.go:539–550`).
TS-19/27's generation-failure preservation matches the early return before Deployment reconciliation (`controllers/ogxserver_controller.go:665–686`); TS-15/16 align with secret references, hashing and watched-secret reconciliation (`pkg/config/secret.go`, controller lines 552–638, 855–863).
The remaining scenarios are broadly phrased without contradictory concrete inputs. Missing-secret feedback in TS-14 is plausible through controller/pod errors; it does not demand a particular condition. Unspecified inputs are runnability failures, not wrong cases; unused source constants are not scored as assertions.

**2 — Redundant.** Snapshot searches found no OGX tests passing declarative providers/storage/baseConfig/disabledAPIs/override_config; the operator image test and `tests/ogx/models/test_models.py::TestOgxModels::test_models_list` do not exercise declarative configuration or its lifecycle.
TS-01/06 require configuration-driven inference, so ordinary inference tests do not duplicate their mechanism. Operator admission/unit tests are outside this metric's opendatahub-tests-only scope. QF explicitly skipped existing-coverage matching; that alone proves neither redundancy nor a coverage gap.

**3 — Covered.** R1 fields: TS-06–13; R2 defaults/validation: TS-02,08,09,11,12,23; R3 generated ConfigMap: TS-15's generated non-secret configuration check; R4 re-render: TS-17–20; R5 upgrade: TS-26/27.
R6 custom ConfigMap: TS-22–24; R7 documentation: TS-05; R10 manual legacy migration: TS-25; R11 provider SecretKeyRef behavior: TS-14–16. Coverage counts targeting independently of executable detail.
Missing R8 (CRD version/deprecation and v1alpha1 rejection) and R9 (OCI-label base configuration). TS-02's generic default check does not test OCI labels, and naming `ogx.io/v1beta1` in metadata does not test rejection of the old version.

**4 — Runnable.** Used `random.seed(1061)` and `random.sample(sorted(TS_ids), 10)` because 27 > 20: TS-01,04,05,11,12,13,18,23,26,27. All ten lack enough executable detail; no runnable-success claim is based on compiling skipped stubs.
TS-01/04/05 omit the actual minimal/example CRs and reference manifests; TS-11/12/23 omit concrete provider objects and unsupported API mutation; TS-13 omits storage setup/data requests; TS-18 omits workload observation/reapply procedure; TS-26/27 omit upgrade procedure and incompatible input.
The STD's repeated input contract asks for “release-approved documented field values” and provides `api_endpoints: []`, rather than supplying those inputs. Answering the STP's platform/source-build TBDs does not fill these gaps. Every Go subtest is a design stub using `t.Skip("Phase 1: Design only - awaiting implementation")`.

**5 — Problems.** No verified concrete product defect or automation gap is raised. The STP lists release/schema confirmation, unavailable review evidence and possible historical wrapper assumptions as risks requiring investigation.
Regression analysis says `existing_coverage_check: "skipped (both checkouts detached; workflow treats tests as context only)"`; its zero mapped tests is not an affirmative finding that the snapshot lacks feature tests. The verified round-4 coverage-gap finding is not inherited as round-6 credit.

`lsp_status: unavailable`. The regression file reports definition/reference requests timing out after 120 seconds, gopls cache/dependency failures, and no lsp_tests server; it claims text tracing rather than a semantic call graph.

**Solution exposure: explicit, despite the pre-merge working tree.** `stp/RHAISTRAT-1061_regression_analysis.yaml` records `historical_evidence.commit: 52fc13773688955226bc6ae82f3ba5f404145574`, title **“Add config generation pipeline (#295)”**, source **“local git object reachable from origin/main; not present at checked-out HEAD”**. It lists generator.go, resolver.go, configmap_reconciler.go and implementation documentation as read files, and says **“Historical code inspected read-only.”** Its text-trace method is **“read definition body from git show”**. I verified that exact commit/title exists in the snapshot's local object database. This is direct evidence of access to the merged solution through local Git history, without successful GitHub access; the result cannot be treated as a clean no-solution-code comparison.

SUMMARY | RHAISTRAT-1061 | wrong 0/27 | redundant 0/27 | covered 9/11 | runnable 0/10 | problems 0
