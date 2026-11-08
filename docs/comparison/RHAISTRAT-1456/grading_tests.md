# RHAISTRAT-1456 run 5 (both tools on GLM 5.3): test grading

Product: `ogx` at e121b2c5 (cited `ogx:<path>:<line>`). Suite: `opendatahub-tests` at 7ffaacc (cited `odh:<path>:<line>`).
The plans and the shipped code are the same as in runs 3 and 4. What shipped is summarized in score-tests/RHAISTRAT-1456.md:
- `WS /v1/responses` with a per-connection cache for `store=false` chains (ogx:src/ogx_api/responses/fastapi_routes.py:229-357).
- Responses compaction.
- No chat-completions sessions, no Memories or Compaction API, and no `[DONE]` terminator on chat SSE.

Loading (mechanical, re-run with `pytest --setup-plan` in each checkout): QF 11/11 load and GEN 27/27 load.

## QualityFlow tests (11, tests/ogx/responses/test_qf_codex_gateway.py)

This is the first QF run that wrote tests for this ticket. All of them drive the shipped WebSocket route through `ogx_test_route` and `ogx_models`, using the `websockets` package locked in uv.lock:3791.

| test | plan case | class | evidence |
|---|---|---|---|
| ::test_websocket_events_arrive_in_order_until_completion | 2 | REAL | The route streams each event as its own frame (fastapi_routes.py:293-294). The test asserts the `sequence_number` order, a single terminal `response.completed` that is the last frame, and non-empty text (test:139-145). "Nothing after completion" goes unchecked, because the reader stops at the first terminal frame (test:46-47). |
| ::test_five_coding_turns_retain_earlier_task_context | 4 | REAL | Five `store=false` turns chained by `previous_response_id` on one socket, each sending only new input. The connection cache rebuilds the context (fastapi_routes.py:262-279, :318-327). The fifth answer must contain the first turn's word and its length (test:189-191). |
| ::test_failed_continuations_cannot_reuse_invalidated_task_context | 5 | REAL | A continuation naming an unknown model raises `ModelNotFoundError`: the router raises it (ogx:src/ogx/core/routers/inference.py:168), the orchestrator re-raises it (streaming.py:519-520), and the handler turns it into an `error` frame (fastapi_routes.py:305-311). That turn evicts its predecessor (:313-317), and reusing the predecessor returns `previous_response_not_found` (:262-275). The test asserts that code (test:232-234). |
| ::test_truncated_responses_remain_available_for_continuation | 6 | WRONG | Sends `max_output_tokens=1`, but `CreateResponseRequest` requires `ge=16` (ogx:src/ogx_api/responses/models.py:224-226). The turn therefore gets a 400 `invalid_request` frame (fastapi_routes.py:280-284), never `response.incomplete`, and the assertion at test:259 fails on a correct product. The behaviour does exist (:296-301, :318-326) with a valid limit. |
| ::test_stored_coding_sessions_resume_after_connection_loss | 7 | REAL | A stored response is written before its terminal event (openai_responses.py:1446-1466). A second socket continues it through the store path (`store` defaults to true, so no cache lookup, fastapi_routes.py:262). The resumed answer must contain the first turn's word (test:303-304). |
| ::test_unstored_sessions_cannot_resume_on_another_connection | 8 | REAL | A new socket starts with an empty cache (fastapi_routes.py:352), so a `store=false` continuation of the first socket's id returns `previous_response_not_found` (:262-275). The test asserts that code (test:338-340). |
| ::test_authorized_users_access_both_transports_consistently | 11 | WEAK | The suite deploys OGX without auth, so there is no "authorized identity". The test sends anonymous requests on both transports and checks only completion and the `model` field (test:369-373). No caller attribution. |
| ::test_both_transports_use_the_selected_self_hosted_model | 14 | WEAK | Asserts only the response `model` field, which echoes the request (`model=self.ctx.model`, streaming.py:412). That is not the backend attribution the plan asks for. |
| ::test_metering_attributes_coding_usage_consistently_across_transports | 15 | WEAK | Asserts only `total_tokens >= 0` on each response (test:420-423). No usage record and no cross-transport comparison: the product has no metering API. |
| ::test_streaming_first_token_latency_stays_below_acceptance_threshold | 17 | WRONG | The timer stops after `_send_ws_turn` returns, which happens only at the terminal frame (test:40-47, :444-451). So it asserts that a whole response finishes in under 200 ms. The plan sets 200 ms for the first generated token, and the route sends deltas as separate frames (fastapi_routes.py:293-294), so that was measurable. Nothing in the product or plan promises full turns in 200 ms. |
| ::test_model_failures_produce_actionable_errors_during_coding | 18 | WEAK | Uses an unknown model, a failure before inference (inference.py:168, sent as `server_error` at fastapi_routes.py:311). The plan wants a mid-response model failure. Only a non-empty message and no completion are checked. |

## QualityFlow declines (`not_implemented`, 11)

| plan case | class | evidence |
|---|---|---|
| 1, 3, 9, 10, 22 (Codex CLI default-transport repair, HTTP fallback, six-tool coding task, invalid tool args not executed, Codex version matrix) | JUSTIFIED (5) | Each outcome is a Codex-client run in a disposable repo with an acceptance test or an action count. The suite has no Codex CLI and no repo harness. Codex is even configured `supports_websockets = false` (ogx:src/ogx/cli/connect/codex.py:303) |
| 12, 13 (unauthenticated and forbidden callers denied) | JUSTIFIED (2) | The deployed spec has no auth option (odh:tests/ogx/server_config.py:174-203), so no deny path can be configured |
| 16 (policy blocks a disallowed coding request) | JUSTIFIED | No policy configuration in the suite, and the repo baseline needs the harness |
| 19, 20 (task at the context boundary, oversized context) | JUSTIFIED (2) | The supported context boundary cannot be known from code (`ModelInfo` has no context window), and the acceptance and baseline parts need the harness |
| 21 (stored work usable after upgrade) | JUSTIFIED | The evidence (completed edit, unchanged action count) needs the coding harness. Pre/post-upgrade fixtures do exist (odh:tests/ogx/conftest.py:159-170), so QF's reason is only partly accurate |

Totals: 11 JUSTIFIED, 0 AVOIDABLE. The four cases that runs 3 and 4 declined avoidably (2, 5, 6 and 8) are now written. Three of them are REAL. Case 6 is WRONG because of an invalid parameter value.

## Test Plan Generator tests (27, tests/ogx_codex_sdk/)

The plan is built on chat-completions `session_id` sessions, a PostgreSQL session store and Memories/Compaction providers. The product has none of these:
- The chat request takes no session field (ogx:src/ogx_api/inference/models.py:982-1028). `session_id` is only forwarded upstream as extra_body (ogx:src/ogx/providers/utils/inference/openai_mixin.py:482-483).
- The Api enum has no memory or compaction API (ogx:src/ogx_api/datatypes.py:113-136).

| test | plan case | class | evidence |
|---|---|---|---|
| test_compact_ogx_codex_sdk.py::test_tc_compact_001 | TC-COMPACT-001 | WRONG | Asserts a `compaction` provider type and server-side recall of `session_id` turns. Neither exists (datatypes.py:113-136, inference/models.py:982-1028) |
| ::test_tc_compact_002 | TC-COMPACT-002 | WRONG | Same: a compaction provider plus recall of facts across `session_id` turns, each sent as a separate one-message request |
| ::test_tc_compact_003 | TC-COMPACT-003 | WRONG | Same, with two concurrent "sessions" |
| test_e2e_ogx_codex_sdk.py::test_tc_e2e_001 | TC-E2E-001 | WRONG | The final summary must recall five earlier one-message requests through `session_id` (test:53-62). There is no server-side chat session |
| ::test_tc_e2e_002 | TC-E2E-002 | WRONG | Deletes the OGX pod, then expects the `session_id` context to survive. No session store exists |
| ::test_tc_e2e_003 | TC-E2E-003 | WRONG | The per-tool argument checks are real, but the test ends by requiring the model to recall all six tools through `session_id` (test:151-160), which cannot happen |
| ::test_tc_e2e_004 | TC-E2E-004 | WRONG | Isolation and recall across `session_id` sessions; no sessions exist |
| test_infra_ogx_codex_sdk.py::test_tc_infra_001 | TC-INFRA-001 | WEAK | Checks that deployments, pods, the port and health exist, and that `psql \dt` returns something (test:69-73). No CR status and no session tables (none exist) |
| ::test_tc_infra_002 | TC-INFRA-002 | WRONG | Expects `memory` and `compaction` provider types and log lines. There is no such API (datatypes.py:113-136) |
| ::test_tc_infra_003 | TC-INFRA-003 | WEAK | Checks that some NetworkPolicy exists and that `pg_isready` from the OGX pod reaches PostgreSQL. The plan's deny paths (test pod to vLLM and to PostgreSQL) are never tried |
| test_perf_ogx_codex_sdk.py::test_tc_perf_001 | TC-PERF-001 | REAL | Times from request to first streamed chunk, 100 samples each for a plain prompt and a tool prompt, and asserts P95 within a configurable budget (test:29-49, :81-83). This matches the plan's own measurement (first `data:` line, configured baseline) |
| ::test_tc_perf_002 | TC-PERF-002 | WRONG | Sends the OGX model id to direct vLLM. OGX ids are `<provider_id>/<model>` (ogx:src/ogx/core/routing_tables/models.py:184), a name vLLM does not serve, so the direct leg fails. It also skips unless the made-up env `OGX_CODEX_VLLM_BASE_URL` is set, although the suite has `OGX_CORE_VLLM_URL` (odh:tests/ogx/constants.py:33) |
| ::test_tc_perf_003 | TC-PERF-003 | WRONG | Measures "PostgreSQL session retrieval" under 100 `session_id` sessions. There is no session store, only plain chat latency |
| test_regr_ogx_codex_sdk.py::test_tc_regr_001 | TC-REGR-001 | REAL | A standard OpenAI SDK client, non-streaming and streaming, gets ACK, and no `session_id` field leaks (test:31-54). It checks only that the SDK parses the reply, not the plan's explicit schema fields |
| ::test_tc_regr_002 | TC-REGR-002 | WRONG | Requires an HPA and a PDB in the namespace. The deployed spec configures neither (odh:tests/ogx/server_config.py:174-203), and no load is generated |
| test_sess_ogx_codex_sdk.py::test_tc_sess_001 | TC-SESS-001 | WRONG | Server-side recall across `session_id` requests (test:52-61); no chat sessions |
| ::test_tc_sess_002 | TC-SESS-002 | WRONG | Session survival across a pod restart; no session store |
| ::test_tc_sess_003 | TC-SESS-003 | WRONG | Per-session recall of the file name; no sessions |
| ::test_tc_sess_004 | TC-SESS-004 | WRONG | Expects 404/422 for an unknown or other-owner `session_id`. The field is ignored and forwarded (openai_mixin.py:482-483), so the request succeeds and `pytest.fail` fires (test:208) |
| test_stream_ogx_codex_sdk.py::test_tc_stream_001 | TC-STREAM-001 | WRONG | `collect_raw_sse` requires a `data: [DONE]` event (utils.py:183-192). OGX chat SSE never sends one: `sse_stream` only formats items (ogx:src/ogx_api/utils.py:43-62, used at ogx:src/ogx_api/inference/fastapi_routes.py:135-136), and `[DONE]` appears nowhere in ogx/src. So it fails on the shipped product |
| ::test_tc_stream_002 | TC-STREAM-002 | REAL | Streams through the SDK, then asserts at least two tool calls on contiguous indexes 0..n with distinct names and per-index arguments that parse (test:76-94). Unique call ids are not checked |
| ::test_tc_stream_003 | TC-STREAM-003 | WEAK | Closes the stream from the client and checks that a follow-up request returns choices. The plan's server-side kill and the client's error handling are not exercised |
| ::test_tc_stream_004 | TC-STREAM-004 | REAL | A non-streaming forced `bash` call. Asserts the JSON content type, `object`, the tool name, parseable arguments with `command`, and `finish_reason == "tool_calls"` (test:161-176): every bullet of the plan |
| test_tool_ogx_codex_sdk.py::test_tc_tool_001 | TC-TOOL-001 | REAL | One forced call per tool (six tools), each with JSON arguments holding the required fields (test:36-48). The forced `tool_choice` makes the name check trivial, and the plan's "no extraneous parameters" is not asserted |
| ::test_tc_tool_002 | TC-TOOL-002 | WEAK | Each prompt states the answer ("The first result is calculator.py"), and no tool output is fed back. Three independent forced calls, so nothing is chained |
| ::test_tc_tool_003 | TC-TOOL-003 | WRONG | Expects 400/422 for a tool with no `parameters`. OGX takes `tools: list[dict[str, Any]]` without validating them (ogx:src/ogx_api/inference/models.py:1013), and `parameters` is optional in the OpenAI schema. The plan case is Codex rejecting malformed call arguments, a different behaviour |
| ::test_tc_tool_004 | TC-TOOL-004 | WEAK | Passes if any of up to three listed models makes one forced `bash` call (test:158-174). No parser-mode matrix |

## Test Plan Generator skipped plan cases

None: all 27 plan cases have a test function.

SCORE RHAISTRAT-1456 | QF tests=11 real=5 weak=4 hollow=0 wrong=2 loads=11 declined=11 justified=11 avoidable=0 cases=22 real_cases=5 | GEN tests=27 real=5 weak=5 hollow=0 wrong=17 loads=27 declined=0 justified=0 avoidable=0 cases=27 real_cases=5
