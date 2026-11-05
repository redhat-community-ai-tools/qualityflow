# RHAISTRAT-1246 (remote::anthropic): generated tests scored (run 5, both tools on GLM 5.3)

Product: `ogx` at e121b2c5 (cited as `ogx:<path>:<line>`). Suite: `opendatahub-tests` at 7ffaacc (cited as `odh:<path>:<line>`).

Facts that decide the grades below:
- **The product has remote::anthropic.** It is registered in ogx:src/ogx/providers/registry/inference.py:176-185, and
  the adapter is ogx:src/ogx/providers/remote/inference/anthropic/anthropic.py. Chat goes through the OpenAI mixin
  (:67-91), with `parameters: {}` normalized at :72-77. Models are listed through AsyncAnthropic (:63-65). The per-request
  key field is `anthropic_api_key` (config.py:15-21), and the request key is preferred over the configured one
  (providers/utils/inference/openai_mixin.py:312-321). An upstream 401/403 is passed through as is
  (ogx:src/ogx/core/exceptions/translation.py:43-49).
- **How the shipped distributions configure it.** `provider_id: anthropic` is **unconditional**, and only the key comes
  from `ANTHROPIC_API_KEY` (ogx:src/ogx/distributions/starter/config.yaml:71-74, ci-tests/config.yaml:72-75). An unset key
  leaves the provider present with no models: listing is skipped without a key (openai_mixin.py:581-586), and a failed
  listing is skipped with a warning (core/routing_tables/models.py:121-129).
- **Caveat that applies to both tools.** The suite deploys the downstream distribution `rh`
  (odh:tests/ogx/server_config.py:175), whose config is in neither checkout. For Gemini, that distribution gates the
  provider on `ENABLE_GEMINI` (comment at odh:tests/ogx/server_config.py:106-113). Both tools enable Anthropic by
  injecting `ANTHROPIC_API_KEY` alone, which is how the shipped configs read it. If `rh` gates Anthropic another way,
  both tools' model lookups fail loudly with "registered no LLM model" rather than passing falsely.

## QualityFlow

Run 5 wrote `odh:tests/ogx/inference/test_qf_anthropic.py`: 6 tests in `TestQfAnthropicProvider`. This is the first
run that actually turns the provider on. Run 3 wrote no tests, and run 4's tests chatted with the core vLLM model. The
file builds its own fixtures from the suite's helpers: `build_ogx_server_config` and `create_ogx_server`
(odh:tests/ogx/utils.py:133), a Route like the suite's own (odh:tests/ogx/conftest.py:259,278), and
`wait_for_ogx_client_ready` (utils.py:197). It appends `ANTHROPIC_API_KEY` from a test-owned Secret
(test_qf_anthropic.py:101-108). `anthropic_model_id` picks a model whose `custom_metadata.provider_id` is `anthropic` and
whose type is `llm`, through the client's `Model.provider_id` / `model_type` properties
(ogx_client/types/model.py:31-43, fed by core/routing_tables/models.py:238-241). No suite file was changed. All 6 load
(`--setup-plan`: collected 6, no errors).

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_qf_anthropic.py::TestQfAnthropicProvider::test_native_chat_returns_ack | 1 chat returns ACK without custom auth headers | REAL | Uses a plain client with no extra headers, sends a chat to the Claude model, and asserts `ACK` in the content (:233-240). The request goes through anthropic.py:67-91, authenticated by the configured key |
| ::test_streaming_chat_delivers_ack | 3 assembled stream contains ACK and terminates | REAL | Assembles the deltas, asserts `ACK`, and asserts a `stop` finish_reason (:252-270) |
| ::test_supported_temperatures_return_answers | 4 every supported temperature gives a nonempty answer | REAL | Sends the same prompt at 0.0 and 1.0, the ends of Anthropic's range and inside ogx's `ge=0, le=2` (ogx:src/ogx_api/inference/models.py:1011), and asserts ACK each time (:282-291) |
| ::test_anthropic_model_discovery | 16 Anthropic-format discovery returns accessible ids | REAL | `models.list(anthropic_version=…)` sends the `anthropic-version` header, which routes to `anthropic_list_models` (ogx_api/models/fastapi_routes.py:109,118-123; routing_tables/models.py:249). The test asserts nonempty ids that include the resolved Claude model (:303-309). Caveat: the default page is the first 20 ids in sorted order (routing_tables/models.py:259-262) |
| ::test_responses_create_returns_paris | 18 response text includes Paris | REAL | Responses API on the Claude model; asserts `paris` in `output_text` (:321-331) |
| ::test_streaming_responses_deliver_paris | 19 response stream contains Paris and completes | REAL | Asserts `response.created` and `response.completed` events and assembled text containing Paris (:343-364) |

### QualityFlow declines (`not_implemented`: 18)

What the suite already offers once a provider is on: provider-specific patterns in odh:tests/ogx/gemini/. That means
tool calling with a follow-up (test_tool_calling.py:72-104), an invalid per-request key
(test_authentication.py:70-98, helper gemini/utils.py:84), and a key-leak check over the pod spec, logs and responses
(test_security.py:36-83). It also has an upgrade harness (odh:tests/ogx/conftest.py:159;
tests/ogx/inference/upgrade/test_upgrade_chat_completions.py:38,66). QualityFlow's own fixture shows Anthropic can be
deployed, so reasons that amount to "no fixture" no longer hold where these patterns apply.

| plan case | class | evidence |
|---|---|---|
| 5 invalid sampling parameter gives a validation error naming it | AVOIDABLE | ogx validates `temperature` with `ge=0.0, le=2.0` on the chat request (ogx:src/ogx_api/inference/models.py:1011), so for example `temperature=3` is rejected with an error naming the field. The decline says no values are defined, but they are |
| 6 tool call completes through chat and responses | AVOIDABLE | The suite's Gemini tool test is the same flow (odh:tests/ogx/gemini/test_tool_calling.py:72-104). Responses function tools are typed at ogx_api/openai_responses.py:548-561. QF's own fixture supplies the provider |
| 7 tool with empty parameter schema | AVOIDABLE | The product normalizes `parameters: {}` for Anthropic (anthropic.py:72-77). The test is the same as 6 with an empty schema |
| 10 invalid request key does not fall back to the configured key | AVOIDABLE | Pattern at odh:tests/ogx/gemini/test_authentication.py:70-98. `anthropic_api_key` provider data (config.py:15-21) wins over the config key (openai_mixin.py:312-321), and the upstream 401 is returned (translation.py:43-49). The failure itself shows there was no fallback |
| 13 failures do not expose supplied credentials | AVOIDABLE | Pattern at odh:tests/ogx/gemini/test_security.py:36-83, which reads raw pod logs and responses for the key, with an invalid override as in 10 |
| 23 Anthropic access survives a supported upgrade | AVOIDABLE | The suite's pre/post-upgrade harness (odh:tests/ogx/conftest.py:159; tests/ogx/inference/upgrade/test_upgrade_chat_completions.py:38,66) plus QF's own Anthropic fixture |
| 2 missing key gives an actionable error | JUSTIFIED | The message exists (`API key not provided…`, openai_mixin.py:253-261). But with no key, no Claude model is ever registered (openai_mixin.py:581-586), so a chat request fails as an unknown model and never reaches that check |
| 8 invalid tool arguments rejected by tool execution | JUSTIFIED | Function tools are executed by the client. ogx has no server-side argument validation for them to observe, and MCP, the server-side path, has no harness (see 14) |
| 9, 11, 12 override uses account B, concurrent tenants isolated, configured key resumes | JUSTIFIED (3) | Each needs a second Anthropic account and an upstream view of which account authenticated. Neither is in code |
| 14, 15 MCP tool result incorporated / unavailable MCP tool reported | JUSTIFIED (2) | The suite has no MCP harness; its own Gemini MCP test fails on purpose because the harness is TBD (odh:tests/ogx/gemini/test_mcp.py:41-49) |
| 17 invalid credentials fail model discovery | JUSTIFIED | The product does not fail discovery. A failing listing is skipped with a warning (core/routing_tables/models.py:121-129), so the expected authentication error does not exist |
| 20 model unavailable to the account gives an actionable error | JUSTIFIED | Needs a Claude model id the test account cannot access, which code cannot supply |
| 21 published downstream setup works | JUSTIFIED | The downstream guide is not in the product checkout |
| 22 docs: no embeddings, recommend Voyage AI | JUSTIFIED | The guidance is absent; ogx:docs/docs/distributions/self_hosted_distro/starter.md:36 even lists "Voyage embeddings" under Anthropic |
| 24 invalid Anthropic config reported after upgrade | JUSTIFIED | Same as 17: an invalid key only causes a skipped model refresh (routing_tables/models.py:121-129), so there is no report to assert |

## Test Plan Generator

The generator wrote `odh:tests/remote_anthropic_provider/` with 4 files and 19 tests: 15 collected by default, plus 4
upgrade cases (`test_tc_upg_00{1,2}[pre|post]`) that are deselected unless `--pre-upgrade` / `--post-upgrade` is passed.
This run it also added the switch it was missing in run 3. `enable_anthropic` in odh:tests/ogx/server_config.py injects
`ANTHROPIC_API_KEY` from `ogx-distribution-secret`, and `ANTHROPIC_*` constants were added to tests/ogx/constants.py. It
changed no conftest. Loading: 0 load. The directory is outside `tests/ogx/`, so `fixture 'distribution_name' not found`
for all 15, and the 4 upgrade cases hit the same error when selected. Importing `ogx_client, ogx_server` from
tests.ogx.conftest does not bring in their dependencies.

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_e2e_remote_anthropic_provider.py::TestAnthropicEndToEnd::test_tc_e2e_001[anthropic] | TC-E2E-001 native inference | REAL | Asserts `remote::anthropic` is in /v1/providers and a chat returns choices with content (:99-103, :71-78). The plan's "x-api-key, not Bearer" line cannot be checked and does not hold for the OpenAI-compatible path anyway |
| ::test_tc_e2e_002[anthropic] | TC-E2E-002 streaming + low-temperature consistency | WEAK | Checks only that some chunk has a finish_reason (:116-123). It never compares repeated temperature-0 outputs and never assembles the content |
| ::test_tc_e2e_003[anthropic] | TC-E2E-003 per-request key override | WEAK | Both calls succeed (:135-140), but that would also happen if the override were ignored, as its own comment admits (:141-143). There is no check that the config key still works after the override |
| ::test_tc_e2e_004[anthropic] | TC-E2E-004 Anthropic-format model listing | WEAK | Uses the default OpenAI-format list and filters by provider (:148-156). The plan's point, an Anthropic-schema listing, is available through the `anthropic-version` header (ogx_api/models/fastapi_routes.py:118-123) and is never requested |
| ::test_tc_e2e_005[anthropic] | TC-E2E-005 provider listed and active | REAL | Asserts a `remote::anthropic` entry with `provider_id == "anthropic"` (shipped id, starter/config.yaml:71) and health metadata (ProviderInfo.health, ogx_api/admin/models.py:72) |
| ::test_tc_e2e_006[anthropic] | TC-E2E-006 chat tool call + follow-up | REAL | Asserts a `get_weather` tool_call with `location`, then sends the tool result back and asserts a final completion (:171-215). This is the same flow as the suite's Gemini tool test |
| ::test_tc_e2e_007[anthropic] | TC-E2E-007 Responses tool call + follow-up | WRONG | Passes the chat-style nested `{"function": {...}}` tool to the Responses API (:224, tool at :23-34). Responses function tools need a top-level `name` (`OpenAIResponseInputToolFunction`, ogx:src/ogx_api/openai_responses.py:548-561), so the request is rejected before any tool call |
| ::test_tc_e2e_008[anthropic] | TC-E2E-008 MCP integration | WEAK | Checks that the provider is listed, then calls `pytest.fail` as a placeholder (:262-266). No MCP is involved |
| TestAnthropicActivation::test_tc_e2e_009[enabled] | TC-E2E-009 activation (key set) | REAL | Provider present and a chat succeeds (:294-304) |
| TestAnthropicActivation::test_tc_e2e_009[disabled] | TC-E2E-009 activation (key unset) | WRONG | Expects `remote::anthropic` to be absent without the key (:295). The shipped configs keep `provider_id: anthropic` unconditionally (starter/config.yaml:71-74, ci-tests/config.yaml:72-75), and only an empty or `__disabled__` id drops a provider (core/resolver.py:246). Its own constants comment claims `${env.ANTHROPIC_API_KEY:+anthropic-inference}`, which contradicts the `anthropic` id every other test uses |
| test_neg_remote_anthropic_provider.py::TestAnthropicInvalidConfigKey::test_tc_neg_001[invalid-config-key] | TC-NEG-001 invalid configured key gives 401/403 | WRONG | With an invalid configured key, model listing fails and is skipped (core/routing_tables/models.py:121-129), so no Claude model exists and the expected 401/403 cannot be reached. `_anthropic_model_id` fails first. It also needs the shared `ANTHROPIC_API_KEY` to be invalid, the same value every positive test needs to be valid |
| TestAnthropicInvalidOverride::test_tc_neg_002[invalid-override] | TC-NEG-002 invalid per-request key | REAL | An invalid `anthropic_api_key` override (config.py:15-21) is preferred over the config key (openai_mixin.py:312-321), and the upstream 401 comes back (translation.py:43-49). The test asserts 401/403, that the key is not echoed, and that a follow-up without the override succeeds (:89-110) |
| TestAnthropicMissingKey::test_tc_neg_003[unset-key] | TC-NEG-003 missing key prevents activation | WRONG | Asserts `remote::anthropic` is absent (:131-134). The shipped config keeps the provider without a key (starter/config.yaml:71-74) and only lists no models (openai_mixin.py:581-586) |
| test_nfr_remote_anthropic_provider.py::TestAnthropicSecurity::test_tc_nfr_001[anthropic] | TC-NFR-001 keys not leaked | REAL | Checks the pod env uses `secretKeyRef`, sends a successful chat, sends an invalid override, then checks that neither key appears in the error body, any container's logs, or /v1/providers (:78-119). This mirrors the suite's Gemini check (gemini/test_security.py:36-83). Operator logs are not read, but the operator never sees the value |
| ::test_tc_nfr_002[anthropic] | TC-NFR-002 TLS 1.2+ egress | WEAK | Checks that the provider is listed, then calls `pytest.fail` as a placeholder (:124-129) |
| test_upg_remote_anthropic_provider.py::TestAnthropicUpgrade::test_tc_upg_001[pre-anthropic-upgrade] | TC-UPG-001 openai workaround survives upgrade | WEAK | Checks that `remote::anthropic` is listed, then calls `pytest.fail` (:47-52). No `remote::openai` workaround is ever configured |
| ::test_tc_upg_001[post-anthropic-upgrade] | TC-UPG-001 | WEAK | Same body |
| ::test_tc_upg_002[pre-anthropic-upgrade] | TC-UPG-002 migration to native provider | WEAK | Provider listed, then `pytest.fail` (:63-68). No migration happens |
| ::test_tc_upg_002[post-anthropic-upgrade] | TC-UPG-002 | WEAK | Same body |

### Generator skips

None. All 16 plan cases have a test function.

SCORE RHAISTRAT-1246 | QF tests=6 real=6 weak=0 hollow=0 wrong=0 loads=6 declined=18 justified=12 avoidable=6 cases=24 real_cases=6 | GEN tests=19 real=6 weak=9 hollow=0 wrong=4 loads=0 declined=0 justified=0 avoidable=0 cases=16 real_cases=6
