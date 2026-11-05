# RHAISTRAT-2418 — round 6 score

Same counting rules and nine requirements as `h2h-round2/neutral/part2.md`; comparison numbers retained from that file and `h2h-round4/score-part2.md`. Counted all 24 STD `scenarios[]` entries, all NEW. STD references below mean `h2h-round6/qf/RHAISTRAT-2418/std/RHAISTRAT-2418_test_description.yaml`.

Reference caveat: the supplied current models-as-a-service checkout is `2d4ad1e`, and this feature is **not shipped there**. Read-only `gh pr view 1363` on 2026-10-26 confirms OPEN, `mergedAt: null`, head `930b7ab2b0c056a3ad246c79ab22c2de6af0c79b`, labels `approved` and `do-not-merge/hold`. As in rounds 2/4, apply the method's unshipped-feature exception: ticket requirements are authoritative; use the saved implementation diff at `scratchpad/h2h/score/_pr1363.diff` to check implementation details. Do not describe this PR as shipped code.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1. Wrong / total | 0/27 | 0/26 | **3/24** |
| 2. Redundant new cases / total | 0/27 | 0/26 | **0/24** |
| 3. Requirements covered / total | 9/9 | 9/9 | **9/9** |
| 4. Runnable as written / after TBDs / sampled | 10/10 sampled; after-TBD count not separately reported | 2/2/10 sampled | **0/3/10 sampled** |
| 5. Verified real problems found | 0 | 1 | **0** |

Metric 1 evidence: TS-03, TS-04 and TS-06 supply literal `namespace: synthetic-namespace-a` (and TS-04 also `synthetic-namespace-b`), yet expect nonempty decision rates, ratios and a zero-denial result (STD:469–520, 612–675, 873–897). The rule selectors accept only `rh-connectivity-link|kuadrant-system` (`_pr1363.diff`:15, 23–32); these fixtures yield no matching output. The same namespace restriction is explicit in the ticket's Namespace portability risk.
These are concrete invalid inputs, not TBDs: the fixture note permits replacing synthetic **policy identifiers** with hashes for cluster tests, but does not remap namespaces. Merely answering the rule-expression TBD does not repair them. No other verified contradiction counted; in particular, unrendered dashboard no-NaN expectations remain ticket-aligned caveats, as in round 4.

Metric 2 evidence: searched the snapshot opendatahub-tests checkout `f034344348803e3804cc3e7238fb74d0d98b3537` under `snap/RHAISTRAT-2418/opendatahub-tests/tests` for `auth_server_`, `MaaSHighAuthDenyRate`, `auth_decisions`, `auth_deny_ratio`, `auth-decisions`, `auth_latency_p95` and `authconfig`: no hits.
There are no EXISTING mappings. Rule-unit coverage reported in Jira belongs to the product PR, not opendatahub-tests; overlap with it is excluded from this redundancy metric.

Metric 3 evidence: same AC mapping: (1) counter/labels TS-01; (2) per-policy Perses views TS-07/08; (3) >10% for 10m alert TS-14/19; (4) promtool rule tests TS-03–06 and TS-14–17.
(5) catalog TS-23/24; (6) zero traffic TS-10/11; (7) scrape recovery/no spurious warnings TS-02/18; (8) resets/no negative spikes TS-12; (9) privacy TS-20. Conditional PM approval does not erase the alert mapping; incorrect fixtures still count toward coverage under the specified rules.

Metric 4 evidence: 24 > 20, so sampled 10 over sorted test IDs with `random.seed(2418); random.sample(range(1,25),10)`: **008, 009, 010, 013, 015, 016, 017, 019, 020, 024**. None runs as written: the three unit cases await the intended rule/alert expression, identifiers and evaluation interval; the other seven have prose-only traffic, interruption, upgrade, UI or catalog-query steps.
After those implementation TBDs are answered, TS-15/16/17 have mechanically constructible promtool inputs: ratios 0.09/0.10/0.11 at 1 rps for 11m; 20% for 9m then zero denials for 11m; and 0/0.0005/0.001/0.002 rps with a 20% qualifying control (STD:1664–1690, 1772–1794, 1879–1909). Their expected firing states are concrete. Apply the same mechanically constructible-fixture allowance used in round 4.
The remaining seven still need executable requests, commands or queries after their listed TBDs are answered. Thus **0 as written, 3 after TBDs, denominator 10 sampled**, not 24. Generator's historical 10/10 retains the missing-host grpcurl caveat: potentially 3/10 if that issue is confirmed.

Metric 5 evidence: QF flags unavailable implementation/test evidence and asks to reconcile the intended build; it does not identify the verified held/open PR, declined dashboard PR, or standalone-versus-deployed-rule test drift. Snapshot absence alone is not a discovered shipped-code defect.
Its datasource, zero-total NaN and Loki-feasibility concerns repeat the ticket or request confirmation; no independently verified defect or specific untested shipped behavior is established. Neither proposed tests nor unanswered questions earn problem-finding credit.

`lsp_status: partial` (`stp/RHAISTRAT-2418_regression_analysis.yaml:1`). It reports tests-repo helper definitions/references/hover, but explicitly says: “Test helpers are patterns only, not LSP validation of the missing feature.” No production call graph was validated.

Solution exposure: **no affirmative sign found**. The STP says “Jira reports new rate, deny-ratio and P95 rules, but the local snapshot lacks these additions and the standalone rule tests” and “PR-derived FILE_PATH rows are omitted because no PR file list or diff was retrievable.” The STD marks the new names/thresholds `ticket-only; reconcile with intended implementation before code generation`; those names, the nine-test claim, thresholds and fallback discussion are present in the saved Jira input and do not demonstrate access to the solution. The supplied source snapshot is `cdf545fd`, tests snapshot `f0343443`.

SUMMARY | RHAISTRAT-2418 | wrong 3/24 | redundant 0/24 | covered 9/9 | runnable 0/10 | problems 0
