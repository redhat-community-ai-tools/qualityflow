# RHAISTRAT-1246 — round 6

Applied `h2h-round2/neutral/part1.md` counting rules and its ten requirements. Generator and round-4 numbers are carried forward from the supplied scorecards. Round 6 has 24 STD scenarios: 19 NEW and 5 PARTIAL_COVERAGE, no EXISTING mappings; all 24 count. Correctness checked against shipped `repos/ogx`; redundancy checked against the ticket's snapshot of `opendatahub-tests`.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1 Wrong / total | 2/16 | 1/20 | **1/24** |
| 2 Redundant / total | 0/16 | 0/20 | **0/24** |
| 3 Requirements covered / total | 8/10 | 8/10 | **8/10** |
| 4 Runnable now / once TBDs answered / total | 1 / not reported / 16 | 3 / 18 / 20 (all checked) | **0 / 5 / 10 sampled** (24 total; estimated 0 / 12 / 24) |
| 5 Verified problems found | 0 | 2 | **4** |

**1 — Wrong.** TS-17 specifies `GET /v1/models` and asserts: “Discovery fails with an authentication error and returns no successful model list.” Shipped `src/ogx/core/routing_tables/models.py:121–129,211–225` catches upstream listing exceptions and combines registry models with any successful dynamic results; the endpoint still returns a successful list. The error-contract TBD does not remove this assertion.
TS-02 remains ambiguous rather than counted wrong: an explicitly configured ungated provider can report missing credentials; omitting the key under the shipped activation gate removes the provider instead. TS-05's upstream sampling-error details remain unverified/TBD. No assertion requires the Jira's native outbound header literals, so those metadata literals are not additional wrong cases.

**2 — Redundant.** Text search finds no Anthropic configuration or tests under snapshot `opendatahub-tests/tests/ogx`. Generic chat ACK, responses and model-list tests do not exercise the Anthropic backend or its authentication path; reusing their prompt is not duplicate Anthropic coverage.
The five PARTIAL_COVERAGE scenarios extend generic source-repo credential tests with live Anthropic override, isolation and redaction checks. Source-repo unit tests are outside this metric's specified redundancy corpus.

**3 — Coverage.** All ACs 1–8 are targeted: provider usability/no custom headers (TS-01/02), streaming/sampling (03–05), tools (06–08), request credentials (09–13), MCP (14/15), model discovery (16/17), responses (18–20), and docs (21/22). AC-9 remains the umbrella, as in part1.md; wrong TS-17 does not subtract coverage.
R9, conditional activation by `ANTHROPIC_API_KEY`, has no scenario. R10, SDK inclusion in the image, appears only in common preconditions, dependencies and entry criteria, not a test action/assertion. Thus 8/10, matching round 4.

**4 — Runnable.** Sampled ten from STD scenarios sorted by zero-padded test ID using `random.seed(1246)` and `random.sample(..., 10)`: **06, 02, 17, 05, 19, 10, 23, 08, 21, 13**. None is executable now without lookup: all carry model/authentication or other execution TBDs. This assesses test instructions, not empty Python stubs (`__test__ = False`).
Once the stated TBDs are answered, **06, 05, 19, 08, 21** have executable API/tool/document workflows with the supplied contracts. The five excluded cases are TS-17 (wrong), TS-02 (ungated configuration method unspecified), TS-10 (upstream credential observer has no capture procedure), TS-13 (diagnostic capture/redaction procedure unspecified), and TS-23 (“Execute the supported product upgrade” gives no upgrade procedure; its TBD supplies versions/timeouts). Answering values alone does not supply these missing procedures. Sample estimate: 12/24 after TBDs, not an all-case count.

**5 — Verified problems.** QF itself raises three `source_discrepancies` in the regression YAML, all corroborated in shipped source: legacy `x-llamastack-provider-data` versus parser `x-ogx-provider-data` (`core/request_headers.py:83–86`); chat's AsyncOpenAI path versus the requested native Anthropic wire authentication (`anthropic.py`, `openai_mixin.py:285`); and `AnthropicConfig.sample_run_config` emitting `api_key` while shared configuration/client selection reads `auth_credential` (`anthropic/config.py:29–32`, `openai_mixin.py:140–148`). These are verified contract/configuration discrepancies, not claims of live-service failures.
One additional coverage problem is explicit in the STP regression strategy and regression YAML: generic mocked credential tests and generic OGX tests do not establish live Anthropic authentication or tenant isolation. Snapshot `tests/ogx` has no Anthropic path. Count these as **four distinct findings**, not each missing scenario as another problem; unconfirmed wheel availability and release-contract questions receive no extra credit.

**LSP:** `lsp_status: partial`. Notes say source definitions/references/hover succeeded, no `lsp_tests` server was registered, and no call-hierarchy tool was available; outgoing calls were read from definition bodies.

**Possible solution exposure:** The STP says “Local source is a later merged snapshot” and “Existing-test duplicate check ran on both merged snapshots.” These are suspicious provenance descriptions, but do not establish access to the withheld solution. The regression YAML identifies source commit `3d1bd63f74e94fe197bc8766421b61a9da2e927a`, which matches the permitted snapshot HEAD; its Anthropic adapter, AsyncOpenAI path and `api_key` sample already exist there. `github_data.pr_details` and `file_changes` are empty, with failed PR fetches recorded. No verified solution-only knowledge found.

SUMMARY | RHAISTRAT-1246 | wrong 1/24 | redundant 0/24 | covered 8/10 | runnable 0/10 | problems 4
