# RHAISTRAT-1456 — QualityFlow round 6

Method: `h2h-round2/neutral/part2.md`, same 13 requirements and counting rules; comparison numbers from `h2h-round4/score-part2.md`. All 22 STD scenarios checked for correctness, redundancy and coverage (21 NEW, 1 PARTIAL_COVERAGE). A TBD/open question is not wrong. No product tests executed.

| metric | generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1. Wrong / total | 19/27 | 1/27 | **1/22** |
| 2. Redundant / total | 0/27 | 0/27 | **0/22** |
| 3. Requirements covered / total | 10/13 | 11/13 | **7/13** |
| 4. Runnable as written / once TBDs answered / sampled total | 3 / not separately reported / 10 | 1/1/10 | **0/0/10** |
| 5. Verified real problems found | 0 | 2 | **2** |

**1. Wrong:** TS-09 explicitly says “invokes bash, read_file, write_file, edit_file, grep_search and glob_search” (STD TEST-01); these are not the shipped Codex tools, as verified in part2.md and round-2 score evidence for `rust-v0.118.0`. Its reconciliation question does not remove the asserted names.
TS-05, TS-06 and TS-08 match shipped OGX `src/ogx_api/responses/fastapi_routes.py`: failed unstored continuation evicts its predecessor, incomplete responses remain continuable, and a fresh connection has no unstored cache. Unverified model/policy/fallback expectations are not counted wrong; inherited source constants alone do not make other TCs wrong.

**2. Redundant:** Compared against snapshot opendatahub-tests `c88d2d1`, not today's tests. `tests/ogx/responses/test_responses.py:27` covers basic response text; inference, file-search and upgrade tests do not assert these coding/WebSocket workflows.
TS-02 overlaps OGX's mocked `test_websocket_streams_events_until_terminal` only partly and adds real gateway transport assertions. That test is in the product repository, outside the redundancy denominator; there are no EXISTING mappings among these 22 cases.

**3. Coverage:** R2 five-turn context → TS-04; R3 OSS E2E → TS-01 plus STP II.3 OSS-model configuration; R4 JSON tool arguments → TS-09/10; R5 resume → TS-07; R7 model routing → TS-14 (two distinguishable choices and selected-model attribution); R8 TTFT → TS-17; R9 gateway connection → TS-01. Wrong cases still count toward coverage.
Missing: R1 tool-call deltas (TS-02 checks general output event order, with no tool-delta reconstruction); R6 compaction; R10 zero invalid calls across a ten-task suite; R11 chat back-compat; R12 cross-user session isolation; R13 HPA/PDB/state surviving service restart. Model-access denial in TS-13 does not test another user's stored history; connection loss and product upgrade do not explicitly exercise service restart.

**4. Runnable:** 22 > 20, so sampled with Python `random.seed(1456); random.sample(range(1,23),10)` over sorted test IDs: **001, 003, 004, 005, 006, 010, 014, 015, 016, 019**. None is runnable as written or merely after answering its open questions.
Examples: TS-01 supplies no repository, failing test or Codex command; TS-05 no request or failure-injection command; TS-06 no output-limit request; TS-14/15/16 no model-selection, metering or policy request. Every sampled case has prose actions and `api_endpoints: []`; answering the design questions still leaves inputs and commands to author. Full scan likewise finds 0/22 runnable, with no executable EXISTING mapping.

**5. Problems found:** (1) Historical session contract conflicts with Responses: STD `HISTORICAL_RECOVERY_IDENTIFIER` marks `session_id` as `conflict: true`, and TS-07 says it “is not assumed equivalent to previous_response_id.” Shipped `src/ogx_api/responses/models.py:151,160` exposes `previous_response_id`/`conversation`, with no session_id request field. Counted once as a ticket-versus-code contradiction.
(2) Missing real default-WebSocket/tool-workflow coverage: STP I.3 flags that the generated Codex profile disables WebSockets, and II.4 calls the existing “HTTP-only no-tools smoke” insufficient. Verified in snapshot `src/ogx/cli/connect/codex.py:297` (`supports_websockets = false`) and shipped `tests/integration/responses/test_codex_cli_smoke.py:63` (prompt says “Do not use tools”); the five snapshot WebSocket tests use mocks. Counted once as an untested shipped transport/workflow gap, not as proof the gateway fails.
Release-target reconciliation, latency unknowns and PR #5327's unavailable status earn no credit. Merely scoping out grammar/apply_patch does not identify the shipped tool-union defect credited in round 4.

`lsp_status: partial` — regression YAML lines 1–3: “LSP unavailable (source repo has no registered lsp_source server; tests repo traced with lsp_tests) — used text search.”

Solution-access check: no positive evidence found. Apparently implementation-specific statements include “routes 345-349 evicts failed predecessor” and “routes 328-336,350-359 terminal incomplete branch” (regression YAML); both are already present in the supplied pre-feature OGX snapshot. Regression metadata records OGX `fd895ae25952dcf1387ac3e217420a76d7f606f8` and tests `c88d2d1a09116df9634838d28b927b130538fcf6`; GitHub data records “gh: error connecting to api.github.com” and no retrieved implementation diff. Detailed baseline knowledge is therefore consistent with the authorized snapshot, not evidence of seeing the solution.

Verification paths: shipped OGX = `<local>` (`f27e1991`); snapshots = sibling `h2h/snap/RHAISTRAT-1456/{ogx,opendatahub-tests}`. QF evidence is in `h2h-round6/qf/RHAISTRAT-1456/{stp,std}/`.

SUMMARY | RHAISTRAT-1456 | wrong 1/22 | redundant 0/22 | covered 7/13 | runnable 0/10 | problems 2
