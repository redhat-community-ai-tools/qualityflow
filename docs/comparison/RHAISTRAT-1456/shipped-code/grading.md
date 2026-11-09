# RHAISTRAT-1456 (Codex through the AI Gateway, incl. apply_patch): run 10 grading, QF normal flow on the shipped code (GLM 5.3)

Paths: `ogx:` = `<local>` (e121b2c57), `odh:` = `.../ship/opendatahub-tests/` (7ffaacc), `O` = `.../qf/outputs/RHAISTRAT-1456/`.

Context. The Jira is about the AI Gateway (praxis-proxy/ai). The delivered items all link praxis-proxy/ai issues. The only remaining scope is Codex's grammar-based `apply_patch` custom tool (RHAIENG-7794, upstream #1834). The Jira puts "The LlamaStack approach" (now OGX) out of scope (O/stp/RHAISTRAT-1456_jira_data.yaml, description). The gateway code is in neither checkout. The suite deploys a Praxis gateway only for the OGX→Praxis migration tests (`odh:tests/ogx/praxis/conftest.py:179-247`). The suite has no Codex client: `codex`, `apply_patch` and `custom_tool` appear only in QF's own new file (git grep). Plan: 7 scenarios, all NEW, `existing_coverage_count: 0`. QF wrote one test plus a marker-only conftest (`odh:tests/ogx/qf/conftest.py`, registers `qf_test_id`), and declined 6.

## 1. QF tests (1)

| test | plan case | class | evidence |
|---|---|---|---|
| tests/ogx/qf/test_qf_codex_ai_gateway.py::TestQFCodexAiGateway::test_unsupported_custom_tool_returns_explicit_error | 2 (explicit error for an unsupported custom tool) | WRONG | Tests a different product and feature. It sends `ogx_client.responses.create(tools=[{"type": "custom", ...}])` (`:37-49`) straight to OGX (`ogx_client` → OGX route, `odh:tests/ogx/conftest.py:313-324`), not through the AI Gateway the scenario and the Jira name. OGX's 400 is generic schema validation: its Responses tools union has no `custom` member (`ogx:src/ogx_api/openai_responses.py:634-640`, discriminator `type`). The `RequestValidationError` becomes a 400 (`ogx:src/ogx/core/server/server.py:569`, `core/exceptions/translation.py:20-34`), and that is why `"custom"` appears in the message (`:51-52`). Every custom tool is rejected the same way, the supported `apply_patch` grammar included, so the test cannot tell "unsupported grammar" from "OGX has no custom tools". It would pass on shipped OGX, but it checks pre-existing OGX request validation that the Jira puts out of scope, not the gateway's no-silent-drop behaviour. Loads: collected 1, no setup error (loading/RHAISTRAT-1456.md) |

Totals: 1 test: 0 REAL, 0 WEAK, 0 HOLLOW, 1 WRONG. 1 loads.

## 2. not_implemented (6)

| scenario | class | evidence |
|---|---|---|
| 1 multi-turn Codex session edits files | JUSTIFIED | The gateway is not checked out, and the suite has no Codex harness (git grep). ogx's generated Codex catalog disables the tool (`"apply_patch_tool_type": None`, `ogx:src/ogx/cli/connect/codex.py:191`). QF's reason is accurate |
| 3 custom-tool history across turns | JUSTIFIED | ogx Responses accepts only web_search/file_search/function/mcp input tools (`openai_responses.py:634-640`), so there is no custom-tool call or output to replay. The gateway is not checked out |
| 4 streamed custom-tool events intact | JUSTIFIED | Same cause: a custom tool cannot be declared on ogx Responses (`openai_responses.py:634-640`), so no custom-tool stream can be produced. ogx has chat-completion custom tool calls (`ogx:src/ogx/providers/inline/responses/builtin/responses/streaming.py:1600`), but not on this path |
| 5 malformed grammar → explicit error | JUSTIFIED | ogx has no grammar validation and rejects the `custom` type at schema level first (`openai_responses.py:634-640`). A test here would repeat the WRONG above. The gateway's grammar handling is not checked out |
| 6 file edits on native and translated backends | JUSTIFIED | Needs Codex `apply_patch` on both paths. Disabled in ogx (`codex.py:191`), no Codex in the suite, gateway not checked out |
| 7 nightly apply_patch result published | JUSTIFIED | ogx's only Codex workflow is manual (`workflow_dispatch`, `ogx:.github/workflows/integration-tests-codex-cli.yml:5-7`) and has no apply_patch task. The support matrix is RHAISTRAT-2769, which the Jira lists as out of scope |

Totals: 6 declined, 6 JUSTIFIED, 0 AVOIDABLE. Groups: 1/6 (no Codex harness, apply_patch disabled in ogx); 3/4/5 (no custom tools on ogx Responses; the gateway is not checked out); 7 (CI and the out-of-scope matrix).

## 3. existing_coverage

None: the STD has `existing_coverage_count: 0` and every scenario is NEW. summary.yaml has no `existing_coverage` entries.

| entry | class | evidence |
|---|---|---|
| (none) | - | - |

## 4. The plan

The plan follows the Jira closely: gateway, Codex, apply_patch, an explicit error for an unservable custom tool, both backends, the nightly run. It also excludes the old LlamaStack approach (O/stp/RHAISTRAT-1456_test_plan.md:120-122). Only ogx is checked out. Against ogx, four scenarios expect behaviour it lacks:
- **1** and **6**: apply_patch file edits, disabled in ogx (`codex.py:191`), and there is no `apply_patch` in `ogx:src` (git grep);
- **3**: custom-tool call/output history;
- **4**: streamed custom-tool events (custom tools cannot be declared on Responses, `openai_responses.py:634-640`).

All four are gateway behaviour (praxis #1834/#1854), so this counts "not in the shipped code available", not a misreading of the Jira. Scenarios 2 and 5 hold trivially on ogx (any custom tool gets a 400), which is not what they mean.

Misses:
- no regression scenario for the delivered work the Jira lists, e.g. the WebSocket transport. ogx ships `WS /v1/responses` (`ogx:src/ogx_api/responses/fastapi_routes.py:229-250`), and the generated Codex profile pins HTTP (`codex.py:303`);
- nothing on silent drops it could see in ogx: a custom `tool_choice` that names no declared tool is logged and dropped (`streaming.py:2094-2097`), and unknown allowed-tool types are skipped (`:2081-2083`).

Test Limitations "None" (`test_plan.md:130-132`) is an over-claim: the plan needs a deployed gateway build and a Codex client that the suite does not have.

## 5. Acceptance criteria (O/stp/RHAISTRAT-1456_jira_data.yaml, 3 bullets)

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | Codex completes a multi-turn coding task through the gateway, incl. apply_patch edits | COVERED | TS-01 (+ TS-06) |
| AC-2 | no layer silently drops a custom tool; unservable request → explicit error | COVERED | TS-02 (+ TS-05) |
| AC-3 | nightly run includes apply_patch, result in the harness support matrix | COVERED | TS-07 (matrix authoring stated out of scope, publication tested) |

SCORE RHAISTRAT-1456 | QF tests=1 real=0 weak=0 hollow=0 wrong=1 loads=1 declined=6 justified=6 avoidable=0 cases=7 real_cases=0 covered=0 verified=0 partial=0 false=0 plan_wrong=4 acs=3 ac_covered=3 ac_out_of_scope=0 ac_missed=0
