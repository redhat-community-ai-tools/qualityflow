# RHAISTRAT-1245 (remote::gemini): run 5, both tools on GLM 5.3

Product: `ogx` at e121b2c5 (cited as `ogx:`). Suite: `opendatahub-tests` at 7ffaacc (cited as `odh:`).
Both tools parametrize `ogx_server` with `{"enable_gemini": True}`. That injects a valid configured `GEMINI_API_KEY`
from a Secret (odh:tests/ogx/server_config.py:114-121). `GEMINI_API_KEY_SECONDARY` and `_SECONDARY_2` default to ""
(odh:tests/ogx/constants.py:63-64).

Loading is taken from loading/RHAISTRAT-1245.md: QF 17/17 and GEN 24/24 collect.

**Delegation rule (from run 3, applied to both tools).** A test that only delegates to a team test, or re-binds
one, is HOLLOW. A test the tool wrote out itself is graded on its own content. Neither tool delegates this time.

**GEN copied the team's suite.** All 24 GEN tests are bodies copied from the team's existing
`odh:tests/ogx/gemini/` tests (#2187, the same ticket). I compared them by AST after stripping docstrings, and the
similarity is 0.70-1.00 for 23 of them. The 24th, `dep_002`, is the team test with a looser grep. The changes are
renames, removed logging and edited messages. Only `reg_001` (embeddings made mandatory) and `dep_002` change a check.

The generator's own plan already marks every case `automation_status: Complete` and points at the team function
(`genplans/.../TC-*.md` frontmatter). Its run log shows it read all nine team files. Under the rule above the copies
are graded on content. The point remains: **GEN adds no new coverage**, because merging it would give the suite two
identical copies of each test.

QF wrote its own tests in `tests/ogx/inference/`. Two of them lift a team test's body nearly unchanged and are
noted in the table: `012`, from `test_tool_calling_with_unsupported_schema_fields`, and `017`, from
`test_multi_tenant_per_request_keys`.

**GEN conftest.** `tests/remote_gemini_provider/conftest.py:3-6` only lists `pytest_plugins = ["tests.ogx.conftest",
"tests.ogx.gemini.conftest"]`. The fixtures are therefore the team's real ones, not re-implementations. There is a
caveat: pytest 9.1.1 rejects `pytest_plugins` in a conftest that is not loaded as an initial conftest
(`.venv/.../_pytest/config/__init__.py:786-803`). So a whole-suite run such as `pytest tests/` would error on this
file, while the targeted check used for loading passes. Loads stay as given.

## QualityFlow: `odh:tests/ogx/inference/test_qf_remote_gemini.py` (17 tests)

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_qf_remote_gemini.py::TestQfRemoteGemini::test_qf_001_native_gemini_availability | 1 | REAL | Asserts `remote::gemini` is listed (:69), then a chat with no custom headers returns content (:70-76). That is exactly the case's outcome |
| ::test_qf_002_unavailable_provider_error | 2 | WEAK | Gemini is enabled (:48). It sends model `qf-unavailable-provider/qf-model` (:86), which only reaches `ModelNotFoundError` for an unknown provider prefix (ogx:src/ogx/core/routers/inference.py:173-175). remote::gemini is never made unavailable (possible by deploying without `enable_gemini`, odh:tests/ogx/server_config.py:111). No config correction is checked, and `"model"` matches the echoed id, so this repeats case 5 |
| ::test_qf_003_supported_temperatures | 3 | REAL | Temperatures 0.0/0.5/1.0 (valid range 0-2, ogx:src/ogx_api/inference/models.py:1011) each return content (:103-110). The plan does not require exact wording |
| ::test_qf_004_streaming_completion | 4 | REAL | Accumulates deltas within a 2000-chunk bound, then requires non-empty content and finish_reason `stop` (:130-141) |
| ::test_qf_005_unknown_model_error | 5 | REAL | `<gemini-prefix>/qf-unknown-model` passes the router fallback (inference.py:163-191) and goes upstream. The upstream 404 keeps its status (ogx:src/ogx/core/exceptions/translation.py:43-49), and the test asserts 4xx (:158). Its keyword check (:160) is vacuous because the id itself contains "model", but a 4xx on an unknown model is the outcome |
| ::test_qf_007_embeddings_missing_usage | 7 | WEAK | The plan's outcome is usage 0/0 (filled at ogx:src/ogx/providers/remote/inference/gemini/gemini.py:108-118). The test asserts `>= 0` (:178-179) |
| ::test_qf_008_batched_embeddings | 8 | WEAK | The index order check (:198) is guaranteed by the adapter's `enumerate` (gemini.py:100-105). There is no comparison against single-input references and no check of the recorded model dimension, only that the dimensions are equal |
| ::test_qf_009_unsupported_embedding_input | 9 | REAL | `[[104,...]]` validates as `list[list[int]]` (models.py:1037-1040) and reaches `validate_embeddings_input_is_text` (gemini.py:81 → ogx:src/ogx_api/validators.py:38-41). That raises "does not support token arrays… provide text input", which becomes a 400 (ogx:src/ogx/core/exceptions/mapping.py:29). The test asserts 4xx and "input"/"text"/"token" (:217-219) |
| ::test_qf_010_tool_call_roundtrip | 10 | WEAK | The first turn is checked well (finish_reason, name, `location` arg, :251-255) and the tool result is sent back. The final check is only non-empty content (:283). The plan's outcome, an answer that incorporates the result (18°C), is not asserted |
| ::test_qf_011_malformed_tool_definition | 11 | WRONG | The "malformed" tool is `{"name": ...}` with no `parameters` (:299). That is valid in the OpenAI function-tool schema, where parameters are optional. OGX types tools as `list[dict[str, Any]]` (models.py:1013) and forwards them unchanged (ogx:src/ogx/providers/utils/inference/openai_mixin.py:473), so nothing in the shipped code rejects it. The expected 4xx is behaviour the product does not have |
| ::test_qf_012_unsupported_schema_fields | 12 | WEAK | Body lifted from team `test_tool_calling_with_unsupported_schema_fields` (same `lookup_item` tool and prompt, same assertion). One accepted case, no reject case, and `tool_calls or content` (:343) passes on any completion. OGX does no schema filtering (openai_mixin.py:473, no schema-cleaning code in src), so this checks only upstream Gemini. It no longer claims filtering, so it is WEAK rather than WRONG |
| ::test_qf_013_request_credential_override | 13 | WEAK | The plan requires an invalid configured key. The configured key here is valid (server_config.py:114-121), so success with the secondary key (:357-363) does not show the override (openai_mixin.py:312-321) |
| ::test_qf_015_configured_credential_used | 15 | REAL | With no header, only the configured key can authenticate (openai_mixin.py:312-321). The test requires content (:375-380) |
| ::test_qf_016_invalid_override_rejected | 16 | REAL | An invalid override replaces the valid configured key (openai_mixin.py:316-319). The upstream 4xx is kept (translation.py:43-49) and asserted (:398), which shows there was no fallback. The follow-up shows the configured key still works (:400-405) |
| ::test_qf_017_interleaved_user_credentials | 17 | WEAK | Body lifted from team `test_multi_tenant_per_request_keys`: three concurrent requests with valid keys (:421-437). There is no invalid-key control and no attribution, so isolation is not shown. The only check is non-empty content |
| ::test_qf_018_failed_auth_hides_credentials | 18 | WEAK | Asserts only that the configured `GEMINI_API_KEY` is absent (:458). That key is not used for this request, because the override replaces it (openai_mixin.py:316-319, gemini.py:66-68). The supplied credential `invalid-key-12345`, which is the one that could be echoed, is not checked, and neither is "identifies authentication failure" |
| ::test_qf_021_documented_configuration | 21 | WEAK | Uses the suite's `enable_gemini` deployment. The published example (ogx:docs/docs/providers/inference/remote_gemini.mdx) is never applied, and the chat and embedding checks repeat cases 1 and 7 |

### QualityFlow: declines (`not_implemented`)

| plan case | class | evidence |
|---|---|---|
| 6 interrupted stream fails without hanging | JUSTIFIED | Cutting an open upstream stream mid-flight needs a fault harness. The suite has none, and a NetworkPolicy does not reliably sever established connections |
| 14 legacy header overrides an invalid configured key | JUSTIFIED | The product lacks it: only `X-OGX-Provider-Data` / `x-ogx-provider-data` are parsed (ogx:src/ogx/core/request_headers.py:81-86). The suite also cannot set an invalid configured key (server_config.py:114-121) |
| 19 MCP tool result → final answer | JUSTIFIED | No OGX MCP harness. The team's Gemini MCP test is a `pytest.fail` placeholder (odh:tests/ogx/gemini/test_mcp.py:47-50) |
| 20 unavailable MCP tool failure | JUSTIFIED | Same as case 19, plus no MCP fault control |
| 22 missing credentials → "API key not provided" | JUSTIFIED | The message exists (openai_mixin.py:255-261), but `enable_gemini` always injects the key (server_config.py:114-121). An empty override falls back to it (openai_mixin.py:316-318), so the path is unreachable in the suite |
| 23 config survives restart and supported upgrade | AVOIDABLE | Restart: delete the pod from `ogx_gemini_pod` (odh:tests/ogx/gemini/conftest.py:84-95). Upgrade: the suite's pre/post-upgrade harness (odh:tests/ogx/conftest.py:159; odh:tests/ogx/inference/upgrade/test_upgrade_chat_completions.py:37,66) |
| 24 blocked endpoint fails, then recovers | AVOIDABLE | The suite has a scoped egress `NetworkPolicy` context manager (odh:tests/model_serving/model_runtime/vllm_omni/s3/test_vllm_omni_tts.py:431-443). Apply it to `app=ogx` (odh:tests/ogx/constants.py:23), send a request, exit the context, and send it again |

Compared with run 4 (luna): case 2 changed from an AVOIDABLE decline to a WEAK test. Case 14 changed from a WRONG test
to a JUSTIFIED decline. Case 18 dropped from REAL to WEAK, because it now checks the wrong key. Case 12 dropped from
WRONG to WEAK. Case 10 is still WEAK.

## Test Plan Generator: `odh:tests/remote_gemini_provider/` (24 tests, all copies of team tests)

None of the 24 delegates to a team test (each is written out), so each is graded on its content. The "copied from"
column shows the source team test and the AST body similarity.

| test (file::name) | plan case | class | evidence (one line) | copied from (similarity) |
|---|---|---|---|---|
| test_auth_remote_gemini_provider.py::TestGeminiPerRequestAuth::test_tc_auth_001 | TC-AUTH-001 | WEAK | The configured key is valid, so success with the secondary key (:38-45) does not show the override was used (openai_mixin.py:312-321). Same judgment as QF 013 | test_authentication.py::test_per_request_api_key_override (0.97) |
| ::test_tc_auth_002 | TC-AUTH-002 | REAL | An invalid override gives 4xx (translation.py:43-49), the error text names auth/key (:57-63), and the follow-up with the configured key succeeds (:65-71) | test_invalid_per_request_api_key_errors (0.96) |
| test_chat_remote_gemini_provider.py::TestGeminiChatCompletions::test_tc_chat_001 | TC-CHAT-001 | REAL | Checks id, choices, `role == assistant` and non-empty content (:32-36), which is every listed outcome | test_non_streaming_chat_completion (1.00) |
| ::test_tc_chat_002 | TC-CHAT-002 | REAL | Bounded stream, finish_reason `stop`, non-empty concatenated content (:51-63) | test_streaming_chat_completion (0.97) |
| ::test_tc_chat_003 | TC-CHAT-003 | WEAK | The plan expects temperature-0 responses to be identical or near-identical. The test only counts 3+3 non-empty responses (:84-86) and never compares them | test_temperature_controls_variability (0.79) |
| test_dep_remote_gemini_provider.py::TestGeminiDeployment::test_tc_dep_001 | TC-DEP-001 | WRONG | Expects `google.genai` to be importable as the provider's dependency (:31-32). remote::gemini declares `pip_packages=[]` (ogx:src/ogx/providers/registry/inference.py:189-190) and is an `OpenAIMixin` client on the OpenAI-compatible endpoint (gemini.py:21,35-36) | test_build_includes_gemini_and_google_genai (0.85) |
| ::test_tc_dep_002 | TC-DEP-002 | WEAK | The plan's outcome is the `${env.GEMINI_API_KEY:+gemini-inference}` pattern. The test only needs any file containing `remote::gemini` plus either `ENABLE_GEMINI` or `GEMINI_API_KEY` (:47), which is a substring check. (The suite says the real gate is `ENABLE_GEMINI`, server_config.py:105-111) | test_config_conditional_activation_pattern (0.42, grep loosened) |
| ::test_tc_dep_003 | TC-DEP-003 | REAL | `GEMINI_API_KEY` is set in the pod and the provider is listed (:55-56), which is every listed outcome | test_operator_injects_gemini_api_key (0.76) |
| test_e2e_remote_gemini_provider.py::TestGeminiEndToEnd::test_tc_e2e_001 | TC-E2E-001 | REAL | Provider active, a non-streaming chat with content, and a streaming chat whose assembled content is non-empty (:46-67) | test_deploy_and_chat_completion (0.99) |
| ::test_tc_e2e_002 | TC-E2E-002 | WEAK | The first turn is checked (:78-85) and the result is sent back. The final check is only non-empty content (:112), and "incorporating the weather data" is not asserted. Same judgment as QF 010 | test_full_tool_calling_workflow (0.96) |
| ::test_tc_e2e_003 | TC-E2E-003 | REAL | Provider active, short and long embeddings that are finite floats, and equal dimensions (:117-132) | test_embedding_generation_end_to_end (0.98) |
| ::test_tc_e2e_004 | TC-E2E-004 | WEAK | Concurrent requests with valid keys (:139-155). Nothing shows each request authenticated with its own key. Same judgment as QF 017 | test_multi_tenant_per_request_keys (0.91) |
| test_emb_remote_gemini_provider.py::TestGeminiEmbeddings::test_tc_emb_001 | TC-EMB-001 | REAL | Non-empty float vector (:32-38) | test_embedding_generation (1.00) |
| ::test_tc_emb_002 | TC-EMB-002 | REAL | This plan only asks that the request succeed and that usage, if present, is valid. The test checks exactly that (:47-54). The shipped default is gemini.py:108-118 | test_embedding_missing_usage_handled (0.92) |
| test_mcp_remote_gemini_provider.py::TestGeminiMCP::test_tc_mcp_001 | TC-MCP-001 | WEAK | Checks that the provider is active, then always `pytest.fail` (:28-29). The MCP outcome is never exercised | test_mcp_server_connectivity_with_gemini (0.87, placeholder) |
| test_prov_remote_gemini_provider.py::TestGeminiProviders::test_tc_prov_001 | TC-PROV-001 | REAL | `remote::gemini` is in the provider types (:29-32) | test_gemini_provider_listed (0.83) |
| ::test_tc_prov_002 | TC-PROV-002 | REAL | Provider config has no `network.headers` (:37-42), and a chat returns content (:43-49) | test_gemini_provider_no_network_headers_workaround (0.98) |
| ::test_tc_prov_003 | TC-PROV-003 | WEAK | Positive half only (:54-56). The "without key → not listed" half is not tested, although it is deployable by omitting `enable_gemini` (server_config.py:111) | test_gemini_conditional_activation_with_key (0.82) |
| test_reg_remote_gemini_provider.py::TestGeminiRegression::test_tc_reg_001 | TC-REG-001 | REAL | remote::openai chat and embeddings both succeed alongside Gemini (:49-63). It tightens the team test by making embeddings mandatory | test_remote_openai_unaffected (0.70) |
| ::test_tc_reg_002 | TC-REG-002 | REAL | Another provider is listed, and inference through a non-Gemini LLM returns content (:68-82). It does not compare against a "previously configured" list | test_other_providers_unaffected (0.77) |
| test_sec_remote_gemini_provider.py::TestGeminiSecurity::test_tc_sec_001 | TC-SEC-001 | REAL | Env comes from a `secretKeyRef` with no plaintext value. The key is absent from logs, `/v1/providers` and a chat response (:30-49) | test_api_key_not_exposed (0.93) |
| ::test_tc_sec_002 | TC-SEC-002 | WEAK | Checks that the provider is active, then always `pytest.fail` (:54-55). TLS is never observed | test_tls_enforced_for_gemini_egress (0.81, placeholder) |
| test_tool_remote_gemini_provider.py::TestGeminiToolCalling::test_tc_tool_001 | TC-TOOL-001 | REAL | Forced `get_weather` call: type, id, name, arguments as a JSON object, finish_reason `tool_calls` (:70-80) | test_tool_calling (0.99) |
| ::test_tc_tool_002 | TC-TOOL-002 | WRONG | Docstring and plan claim the provider "filters unsupported schema fields before forwarding" (:84). OGX forwards tools unchanged (openai_mixin.py:473) and has no schema-cleaning code in src | test_tool_calling_with_unsupported_schema_fields (0.97) |

### Test Plan Generator: skipped plan cases

None. All 24 plan cases have a test function. The two placeholders (MCP-001, SEC-002) are graded WEAK above, not
as declines.

## Summary

- **QF:** 17 own tests. 7 REAL (cases 1, 3, 4, 5, 9, 15, 16), 9 WEAK, 1 WRONG (case 11, a "malformed" tool that is
  valid). 7 declines: 5 justified, and 2 avoidable (restart/upgrade and endpoint block, both with suite harnesses).
- **GEN:** 14 REAL out of 24, but every one is a copy of the team's existing test for the same case. The generator's
  own plan already marked each case Complete. On content GEN scores higher; in new coverage it adds zero.
  The copied team suite carries its own two WRONG tests (google-genai dependency, schema filtering). GEN's
  conftest would also break a whole-suite `pytest tests/` run (non-top-level `pytest_plugins`).

QF real_and_loads=7
GEN real_and_loads=14

SCORE RHAISTRAT-1245 | QF tests=17 real=7 weak=9 hollow=0 wrong=1 loads=17 declined=7 justified=5 avoidable=2 cases=24 real_cases=7 real_and_loads=7 | GEN tests=24 real=14 weak=8 hollow=0 wrong=2 loads=24 declined=0 justified=0 avoidable=0 cases=24 real_cases=14 real_and_loads=14
