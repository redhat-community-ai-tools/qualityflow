# RHAISTRAT-2493 — QualityFlow round 6

Rules and requirement list: `h2h-round2/neutral/part1.md`, ticket section and counting rules. Comparison: `h2h-round4/score-part1.md`. Round 6 contains **29 STD scenarios, all NEW**, with no existing-test mappings. Correctness was checked against the shipped checkout; redundancy against the pre-feature snapshot. No services or tests were executed.

| metric | generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1 Wrong test cases / total | 13/51 | 0/26 | **0/29** |
| 2 Redundant new cases / total | 37/51† | 0/26 | **0/29** |
| 3 Requirements covered / total | 11/12 | 12/12 | **12/12** |
| 4 Runnable now / after own TBDs / total | 2 / not reported / 10 sampled | 2 / 10 / 10 sampled; all checked: 7 / 24 / 26 | **0 / 4 / 10 sampled** |
| 5 Verified real problems raised | 0 | 4 | **1** |

† Generator numbers are the supplied historical scores, unchanged. Its 37 duplicates were against the later suite built from its plan; part1 explicitly says it duplicated nothing on 2026-08-11. Round-6 redundancy uses the snapshot as requested, so the two redundancy columns have different temporal baselines.

**1 — Wrong.** All 29 scenario oracles were reviewed. No confirmed contradiction: `/health`, the preview disclosure, SHA256 image pinning and route-based voice criteria agree with shipped behavior or the ticket. The shipped template is `repos/odh-model-controller/config/runtimes/vllm-omni/vllm-omni-cuda-template.yaml` (health probes at lines 62–78).
Model/endpoint contracts, metric names, probe settings and safetensors enforcement are explicitly TBD; these omissions are not wrong cases. TS-11 does not repeat the generator's unconditional successful `/v1/completions` expectation.
Unverified, not counted: dashboard decline behavior (TS-02), engine-wide metric-family completeness (TS-23), and rejection of untrusted artifacts under the still-unresolved safeguards (TS-26). The template alone cannot establish engine behavior.

**2 — Redundant.** The snapshot's `opendatahub-tests/tests/model_serving/model_runtime/` contains no Omni suite or Omni speech assertions. The only speech text found there is an unrelated audio-file URL in standard-vLLM ModelCar data.
Generic CPU OPT-125M probe tests and Granite PVC inference do not assert Omni multi-stage initialization, speech, or the reference GPU boundary. TS-10's all-stage initialization oracle therefore is not a duplicate of the generic no-restart probe test.
The later shipped `vllm_omni/` tests were not used to penalize new cases. QF's `existing_test_coverage: []` is consistent with the snapshot.

**3 — Covered.** The same 12 requirements are targeted: AC-1 TS-01/02; AC-2 TS-04/08; AC-3 TS-14; AC-4 TS-15; AC-5 TS-16; AC-6 TS-18/19; AC-7a TS-01/21; AC-7b TS-21; AC-8 TS-09.
Blind listening is TS-17; probe/startup behavior is TS-08/10; the fast-1 variant requirement is targeted by TS-03's stable/fast inventory and image-divergence check. Coverage credits the target even when execution details remain TBD.

**4 — Runnable.** Used `random.seed(2493)` and `random.sample(sorted(TS ids), 10)`: TS-06, 20, 03, 11, 29, 17, 23, 24, 16, 28. Results are sampled, not an all-29 execution estimate; no case in this sample runs without lookup now.
After their own TBDs: TS-03 (variant/digest inventory), TS-11 (model-to-endpoint matrix and payload/response schemas), TS-17 (listening protocol and panel), TS-24 (metrics endpoint and rejection contract): **4/10**. Manual dashboard selection and listening are executable procedures once their stated inputs are supplied.
Still blocked: TS-06 lacks a concrete Qwen3 model/storage/request contract; TS-20 lacks an inference request; TS-16's corpus/sampler TBD does not supply its speech request/model contract; TS-23's metric inventory TBD does not supply requests to exercise each stage. TS-28/29 TBD only the release pair, leaving the upgrade procedure/command and inference requests unspecified. A deployed-service precondition is allowed, but does not supply an unspecified request or upgrade command.

**5 — Problems found.** Credit **one test-oracle weakness**, not a demonstrated runtime defect: regression analysis warns, “helper accepts alternate /v1/models success and must not establish Omni all-stage health.”
Verified in both snapshot and shipped `opendatahub-tests/tests/model_serving/model_runtime/vllm/probes/utils.py:128`: `exec_vllm_health_check` tries the configured path and `/health`, `/v1/models`, returning immediately for any HTTP 200. Its callers assert only the returned 200; consequently this helper cannot prove that `/health` itself succeeded.
Other entries are proposed checks, unresolved contracts or general risks. In particular, “do not substitute KV-cache occupancy for total GPU memory” is sound guidance, but round 6 does not identify the shipped soak test's concrete misuse; no additional discovery credit. It also does not raise round 4's relaxed latency constants, metric-prefix disagreement or concrete shipped/proposed probe-timing mismatch.

**LSP and solution exposure.** `stp/RHAISTRAT-2493_regression_analysis.yaml:1` reports `lsp_status: partial`: tests definition/references succeeded; source definitions and references timed out, with text-search fallback. This validates shared infrastructure, not Omni code.
No positive sign of solution-code exposure was found in the STP/STD. The regression analysis says, “No PR diff available and no Omni implementation found,” and `github_analysis.yaml` records PR #906 access failing with “gh: error connecting to api.github.com; web fallback cache miss”. Precise details such as the Limited support badge, two GPUs and 17/32 metric families already appear in the captured Jira description; they are not evidence of leakage. These artifacts support, but cannot independently prove, the access restriction.

SUMMARY | RHAISTRAT-2493 | wrong 0/29 | redundant 0/29 | covered 12/12 | runnable 0/10 | problems 1
