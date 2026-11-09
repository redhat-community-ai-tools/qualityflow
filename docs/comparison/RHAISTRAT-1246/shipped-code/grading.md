# RHAISTRAT-1246 (remote::anthropic in OGX): run 10 grading, QF normal flow on the shipped code (GLM 5.3)

Paths: `ogx:` = `<local>` (e121b2c57), `odh:` = `.../ship/opendatahub-tests/` (7ffaacc), `O` = `.../qf/outputs/RHAISTRAT-1246/`. QF test file `T` = `odh:tests/ogx/anthropic/test_qf_remote_anthropic_provider.py` (10 tests, one class; identical to `O/python-tests/` copy). `git status` in odh shows only that file: no team file changed, no conftest added. There is no `tests/ogx/anthropic/__init__.py`, unlike the sibling dirs; this is cosmetic, since it loads.

The plan is new: 13 scenarios, 0 EXISTING_COVERAGE (std yaml :23). Five are PARTIAL_COVERAGE and still got tests. The duplicate check ran this time (`existing_coverage_check: ran`, O/stp/RHAISTRAT-1246_regression_analysis.yaml:273). QF wrote 10 tests (scenarios 1-4 and 6-11) and declined 3 (5, 12, 13).

Facts the grades rest on:
- **QF now gives the server a configured key.** Run 7 did not. A class-scoped autouse fixture wraps the team's `build_ogx_server_config` to append `ANTHROPIC_API_KEY` from the `ogx-distribution-secret` (`T:34-70`), and it adds `anthropic-api-token` to the shared `OGX_SERVER_SECRET_DATA` dict (`T:43-44`; dict at `odh:tests/ogx/constants.py:71-79`). This works. `ogx_server` is class-scoped and calls the module global `build_ogx_server_config` (`odh:tests/ogx/conftest.py:32, 112-157`). The secret is class-scoped and built from that same dict object (`:88-110`). A class-scoped autouse fixture runs before them. Both `tests/` and `tests/ogx/` are packages, so `import tests.ogx.conftest` is the module pytest loaded. The patch is fragile but legitimate, and it touches no file. Configured-key scenarios now run on the configured path.
- **The provider is shipped.** It is registered with a provider-data validator (`ogx:src/ogx/providers/registry/inference.py:176-185`). The starter config lists it unconditionally with `api_key: ${env.ANTHROPIC_API_KEY:=}` (`ogx:src/ogx/distributions/starter/config.yaml:71-74`). Chat goes to `https://api.anthropic.com/v1` (`anthropic.py:60-61`). Models are discovered with `AsyncAnthropic(...).models.list()` (`anthropic.py:63-65`) and listed with `custom_metadata.provider_id`/`model_type` (`core/routing_tables/models.py:230-246`). A per-request `anthropic_api_key` replaces the config key (`providers/utils/inference/openai_mixin.py:312-321`). Upstream 4xx keep their status (`core/exceptions/translation.py:43-49`).
- Same caveat as run 7: the suite deploys distribution `rh` (`odh:tests/ogx/server_config.py:175`), whose config is in neither checkout. The tests assume `rh` lists the provider as id `anthropic`, keyed on `ANTHROPIC_API_KEY` like starter. I do not count this against them.

## 1. QF tests (10)

| test (T::TestRemoteAnthropicProvider::…) | plan case | class | evidence |
|---|---|---|---|
| test_provider_appears_after_deployment | 1 provider listed | REAL | Asserts `remote::anthropic` in `/v1/providers` (`T:122-126`); registry `inference.py:176-185`, starter `config.yaml:71-74` |
| test_configuration_without_header_workaround | 2 native config, no network.headers | REAL | The provider's `config` has no `network.headers` (`T:137-146`), and a chat on the resolved Claude model returns content (`T:148-154`). It checks both acceptance criteria, through the configured key |
| test_streaming_completion_with_temperature | 3 streaming + temperature | REAL | `stream=True, temperature=0.7`; asserts chunks, `"stop"` in the finish reasons, and non-empty streamed text (`T:165-188`). This is the case's condition exactly |
| test_tool_calls_across_both_apis | 4 tool call on chat and responses | REAL | Chat: `tool_calls[0].function.name == "get_weather"` with JSON args (`T:212-224`). Responses: a `function_call` item named `get_weather` (`T:226-246`). `tool_choice="auto"` leaves a small flake risk, but the content is right |
| test_per_request_credential_override | 6 x-ogx-provider-data key override | WEAK | A baseline chat, then a chat with the secondary key in the header, each returning content (`T:260-273`). The configured key is valid, so this passes even if the header were ignored. Nothing shows the override replaced the configured key. The invalid-override 4xx in the next-but-one test is what proves that path |
| test_concurrent_credential_isolation | 7 concurrent keys isolated | WEAK | Three concurrent chats (config key, secondary, secondary-2) all return content (`T:290-307`). The case's condition, that neither response exposes the other key and each request used its own credential, is never checked. It passes if the headers are ignored or crossed |
| test_anthropic_model_listing_format | 8 Anthropic SDK model-listing format | WEAK | It uses the OpenAI-format `models.list()` and asserts an `anthropic`-provider model with "claude" in the id (`T:314-325`). The case asks for the native Anthropic SDK shape with pagination metadata. OGX serves that only when the request carries `anthropic-version` (`ogx:src/ogx_api/models/fastapi_routes.py:109, 119-124`; `routing_tables/models.py:249-290`), which the test never sends. As a side effect, it does check AC-7's real point: Claude models discovered through `AsyncAnthropic` (`anthropic.py:63-65`) |
| test_authentication_failure_without_credential_leakage | 9 invalid credential → safe 4xx, no leak | WEAK | An invalid per-request key gives 4xx, and the error body does not contain that key (`T:336-348`). That is real (`translation.py:43-49`), but only part of the case. The case's precondition is an invalid *configured* key, and its condition includes "response **and logs** do not contain the key". Logs are never read |
| test_malformed_credential_override_rejection | 10 malformed override → 4xx, config key still works | WRONG | It expects `APIStatusError` 4xx for `x-ogx-provider-data: {not-json}` (`T:359-368`). The shipped server logs "Provider data not encoded as a JSON object!" and drops the header (`ogx:src/ogx/core/request_headers.py:96-100`, called from the middleware at `core/server/server.py:305-310`, `request_headers.py:144-149`). The request then runs on the valid configured key (`openai_mixin.py:312-321`) and returns 200, so `pytest.raises` fails |
| test_unsupported_model_rejection | 11 unknown model → model-not-found | REAL | It asserts 4xx and that the error names the model (`T:386-399`). The router raises `ModelNotFoundError` for an unregistered id with no `provider/` prefix (`core/routers/inference.py:166-168`), which maps to 404 with the model name (`ogx_api/common/errors.py:101-104, 144-148`). A 4xx is enough to rule out the fallback the case worries about. The name check is loose (`… or "model" in error_text`) |

Tally: 10 tests: REAL 5, WEAK 4, HOLLOW 0, WRONG 1.

Loads: 10/10 (loading/RHAISTRAT-1246.md: collected 10, setup-plan clean). Nothing blocks setup. Tests 6 and 7 skip without `OGX_CORE_ANTHROPIC_API_KEY_SECONDARY` (and `_2`), and the class fails fast without a primary key (`T:37-41`), as the team's Gemini suite does (`odh:tests/ogx/gemini/conftest.py:30-41`).

## 2. not_implemented (3)

| scenario | class | evidence |
|---|---|---|
| 5 MCP tool use with Claude | JUSTIFIED | Nothing under `odh:tests/ogx` deploys an MCP server. The team's own Gemini MCP test is a `pytest.fail` placeholder ("MCP harness … is TBD", `odh:tests/ogx/gemini/test_mcp.py:33-50`). Only a generated `MCPServer` wrapper exists (`odh:utilities/resources/mcp_server.py`), with no fixture. This matches the run-10 RHAISTRAT-1245 call |
| 12 legacy remote::openai config survives upgrade | AVOIDABLE | QF says there is "no pre-upgrade OGX deployment … harness". There is one. `odh:tests/ogx/inference/upgrade/test_upgrade_chat_completions.py:26-80` has pre_upgrade/post_upgrade classes for an OGX chat, and `ogx_server` reuses the pre-upgrade OgxServer in a post-upgrade run (`odh:tests/ogx/conftest.py:63-67, 159-168`). The legacy provider is reachable two ways. The distribution's `remote::openai` takes its base_url and key from env (`ogx:…/starter/config.yaml:66-70`), which QF's own wrapper (`T:46-62`) can set. The OgxServer CR also takes a `providers` section (`odh:utilities/resources/ogx_server.py:61-62`) |
| 13 docs: native config + embedding guidance | JUSTIFIED | The case names the RHOAI 3.5 EA2 product docs, which are in neither checkout. The upstream page has the config table and sample but no embedding guidance (`ogx:docs/docs/providers/inference/remote_anthropic.mdx:1-46`; embeddings are only a commented TODO, `anthropic.py:48-58`). A correct test would fail on the upstream page and cannot reach the downstream one |

## 3. existing_coverage (0)

None: the STD has `existing_coverage_count: 0` (std yaml :23), and summary.yaml lists none. covered=0. Not counted, from the PARTIAL_COVERAGE scenarios: all 7 named tests exist. They are `tests/integration/messages/test_messages.py:107, 161, 194`, `tests/unit/providers/inference/test_remote_anthropic.py:160, 170, 454` and `tests/integration/models/test_models.py:21`. The messages and models ones exercise the generic Anthropic-format API surface (`/v1/messages`, Anthropic-format listing), not specifically the `remote::anthropic` provider.

## 4. The plan

13 scenarios cover the 9 ACs plus negative cases and a migration case.

**One scenario expects behaviour the shipped code lacks.** Scenario 10 expects a 4xx for a malformed `x-ogx-provider-data`. The shipped code logs and ignores it, then falls back to the configured key (`request_headers.py:96-100`).

Other weak spots:
- Scenario 8 reads AC-7 (the provider uses `AsyncAnthropic` to list Anthropic's models, `anthropic.py:63-65`) as "OGX returns the Anthropic SDK listing shape". That shape is a generic OGX route for any model (`fastapi_routes.py:119-124`).
- Scenario 13 wants embedding guidance that the shipped page does not have (`remote_anthropic.mdx:1-46`).

Shipped behaviour the plan misses:
- The native `/v1/messages` passthrough with extended thinking, and `count_tokens` (`anthropic.py:34-41`).
- Explicit rejection of `/v1/completions` (`anthropic.py:93-100`).
- `parameters: {}` normalization and the strict json_schema default (`anthropic.py:71-90`).
- The missing-key error with its header hint (`openai_mixin.py:253-263`).

## 5. Acceptance criteria (O/stp/RHAISTRAT-1246_jira_data.yaml, 9 bullets)

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | remote::anthropic in downstream distributions | COVERED | TS-01 |
| AC-2 | configured as remote::anthropic without network.headers | COVERED | TS-02 |
| AC-3 | chat completions with streaming and temperature | COVERED | TS-03 |
| AC-4 | tool calling via chat completions and responses | COVERED | TS-04 |
| AC-5 | provider-data `anthropic_api_key` overrides config key | COVERED | TS-06, TS-07 (shipped header is `x-ogx-provider-data`, not the AC's `x-llamastack-provider-data`) |
| AC-6 | MCP servers work with Anthropic models | COVERED | TS-05 (declined) |
| AC-7 | model listing works (AsyncAnthropic handles /v1/models format) | COVERED | TS-08 (misread as the OGX Anthropic-format listing, see 4) |
| AC-8 | docs: Anthropic config examples + embedding guidance | COVERED | TS-13 (declined) |
| AC-9 | validated against Anthropic's API | COVERED | TS-01..TS-11 run live against `api.anthropic.com` (`anthropic.py:60-61`) |

SCORE RHAISTRAT-1246 | QF tests=10 real=5 weak=4 hollow=0 wrong=1 loads=10 declined=3 justified=2 avoidable=1 cases=13 real_cases=5 covered=0 verified=0 partial=0 false=0 plan_wrong=1 acs=9 ac_covered=9 ac_out_of_scope=0 ac_missed=0
