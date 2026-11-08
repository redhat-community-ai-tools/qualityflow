# RHAISTRAT-1245 — round 6 score

Same units and counting rules as `h2h-round2/neutral/part1.md`; generator and round-4 figures are copied from the supplied scorecards. Round 6 has 24 STD scenarios, all NEW. Correctness is against shipped code; redundancy is against the pre-merge tests snapshot. No live service tests were run.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1 Wrong / total | 5/24 | 0/24 | **1/24** |
| 2 Redundant / total | 21/24† | 0/24 | **0/24** |
| 3 Requirements covered / total | 7/8 | 8/8 | **8/8** |
| 4 Runnable now / after TBD / total | sample 0 / not reported / 10 | sample 5 / 6 / 10; all checked 12 / 16 / 24 | **sample 0 / 7 / 10** |
| 5 Verified problems raised | 0 | 7 | **1** |

**1 — Wrong.** TS-14 explicitly expects successful authentication with `x-llamastack-provider-data` despite an invalid configured key. Shipped `repos/ogx/src/ogx/core/request_headers.py:83-96` recognizes only the two capitalizations of `x-ogx-provider-data`, so that override is ignored.
Its compatibility-disposition TBD does not erase the concrete success assertion. Other model, status and schema-contract TBDs are not errors; TS-07's zero usage defaults and TS-09's token-array rejection match shipped `gemini.py:81,108-118`. TS-11's upstream malformed-tool error remains unverified, not counted wrong.

**2 — Redundant.** The snapshot `snap/RHAISTRAT-1245/opendatahub-tests` has no Gemini suite or Gemini provider configuration; searching its tests and utilities finds only an unrelated Gemini AI disclaimer.
Generic chat and embedding tests exercise the default deployment, not these native-Gemini acceptance oracles. Product-repo unit overlap, including credential caching, is outside this metric. † The generator's historical 21/24 is retained with the original caveat: the later Gemini suite was automated from that plan; it is not the round-6 snapshot baseline.

**3 — Coverage.** Using the same eight ACs: downstream availability TS-01; configuration without custom authentication TS-01/21; absent-usage embeddings TS-07; chat/streaming/temperature TS-03/04; function tools TS-10; request credentials TS-13/14/16/17; MCP TS-19/20; documentation TS-21.
AC-9 remains an umbrella and does not increase the denominator. Documentation is explicitly tested by executing published examples; the wrong legacy-header case still targets its requirement under the supplied coverage rule.

**4 — Runnable.** Sampled 10 of 24 sorted scenario IDs with `random.seed(1245)`: TS-02, 03, 05, 06, 11, 12, 15, 17, 18, 20. Every sampled case contains execution-input TBDs, so none is runnable now.
After those TBDs: TS-03, 05, 11, 12, 15, 17 and 18 have public request paths, request data and behavioral oracles; TS-17 explicitly TBDs its attribution mechanism. This assumes supplied schema/error contracts are verified, rather than treating unknown upstream behavior as a confirmed contradiction.
TS-02 still needs an unspecified configuration/application procedure to make the provider unavailable; TS-06 needs an unspecified connection-interruption control; TS-20 needs an unspecified MCP fault setup. Their TBDs cover data, errors and deadlines, not those missing procedures. Result: 0/10 now, 7/10 after TBDs; no all-case runnable extrapolation claimed.

**5 — Problems found.** One verified discrepancy: STP Technology Challenges says, “Jira names x-llamastack-provider-data, while the checked source consumes x-ogx-provider-data; both use gemini_api_key.” Shipped `request_headers.py:83-96` confirms this.
Schema filtering and native Responses support are explicitly unresolved, not verified defects. The unavailable downstream checkout and release-documentation questions are limitations, not product problems; round-4 placeholder-test findings cannot be credited to this output.

`lsp_status: unavailable` in `stp/RHAISTRAT-1245_regression_analysis.yaml`: “LSP tool not registered; no lsp_* MCP servers exposed. Python checkouts analyzed by rg and source-body reads.”

**Solution visibility.** There is evidence it saw an upstream implementation: the STP says “Gemini embedding responses omit usage; the adapter supplies usage defaults,” and the regression analysis names `GeminiInferenceAdapter.openai_embeddings`. However, that adapter already exists in the allowed snapshot (`snap/RHAISTRAT-1245/ogx/src/ogx/providers/remote/inference/gemini/gemini.py:75-123`, including zero usage defaults at 115-117). This is not evidence of access to the withheld downstream solution. The output states “Plan preparation could not inspect GitHub PR diffs or the downstream distribution checkout”; it gives no shipped `ENABLE_GEMINI` gate or downstream config location. No affirmative evidence of access beyond the supplied snapshot was found.

SUMMARY | RHAISTRAT-1245 | wrong 1/24 | redundant 0/24 | covered 8/8 | runnable 0/10 | problems 1
