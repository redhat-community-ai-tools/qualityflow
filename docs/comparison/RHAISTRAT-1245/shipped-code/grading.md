# RHAISTRAT-1245 (remote::gemini provider): run 10 grading, QF normal flow on the shipped code (GLM 5.3)

Paths: `ogx:` = `<local>` (e121b2c57), `odh:` = `.../ship/opendatahub-tests/` (7ffaacc, git status clean: QF wrote nothing into it), `O` = `.../qf/outputs/RHAISTRAT-1245/`.

The team's suite `odh:tests/ogx/gemini/` already has 24 Gemini tests (22 runnable, plus two `pytest.fail` placeholders for MCP and TLS). This time QF marks 22 of its 28 scenarios EXISTING_COVERAGE against those tests (O/std/RHAISTRAT-1245_test_description.yaml `covered_by`) and writes no test. The other 6 (4 NEW, 2 PARTIAL_COVERAGE) are `not_implemented` (O/python-tests/summary.yaml, `test_count: 0`, `verification: skipped`). Note: summary.yaml has no `existing_coverage` list, so the 22 claims are the STD's `covered_by` entries. All 22 named tests exist under the claimed names. I checked each one's assertions.

Two facts decide several rows:
- The suite deploys distribution `rh` (`odh:tests/ogx/server_config.py:175`), not the upstream starter. The suite says that distribution gates Gemini on `ENABLE_GEMINI` (`server_config.py:106-121`). The upstream starter lists it unconditionally (`ogx:src/ogx/distributions/starter/config.yaml:75-80`).
- The shipped adapter is a thin OpenAIMixin pass-through to Google's OpenAI-compatible endpoint (`ogx:src/ogx/providers/remote/inference/gemini/gemini.py:21-36`). It adds key/token auth (`:38-70`), streaming-usage coalescing (`:29`) and the embeddings usage fallback (`:108-118`). It has no tool-schema transformation: `exclusiveMaximum`/`propertyNames` stripping is absent from `ogx:src` (grep).

## 1. QF tests (0)

| test | plan case | class | evidence |
|---|---|---|---|
| (none) | - | - | `generated_files: []`, `test_count: 0` (O/python-tests/summary.yaml). Loading: nothing to load (loading/RHAISTRAT-1245.md is empty) |

## 2. not_implemented (6)

| scenario | class | evidence |
|---|---|---|
| 4 provider absent without a key | AVOIDABLE | QF says the suite has "no no-key deployment path". Wrong: `ogx_server` takes indirect params (`odh:tests/ogx/conftest.py:113-131`), and without `enable_gemini` it sets neither `ENABLE_GEMINI` nor `GEMINI_API_KEY` (`server_config.py:114-121`). Every non-Gemini OGX class deploys that way. The autouse fixture checks the runner's env, not the deployment (`gemini/conftest.py:30-41`). A class with default params plus `assert GEMINI_PROVIDER_TYPE not in list_provider_types(...)` (`gemini/utils.py:28-37`) is the test. The team names exactly this as missing (`test_providers.py:85-89`), and run 7's QF wrote it. QF's second reason, the unconditional config, is the upstream starter (`config.yaml:75`), not the `rh` distribution the suite deploys (`server_config.py:175`) |
| 8 unreachable endpoint → actionable error | JUSTIFIED (wrong reason) | QF's reason (no way to make the endpoint unreachable) is false. The suite blocks egress with a scoped `NetworkPolicy` (`odh:tests/model_serving/model_runtime/vllm_omni/s3/test_vllm_omni_tts.py:431-443`), which would cut `generativelanguage.googleapis.com` (`gemini.py:35-36`). But the expected outcome is not shipped. `openai.APIConnectionError` has no `status_code` and is not in `EXCEPTION_MAP` (`ogx:src/ogx/core/exceptions/mapping.py:28-43`, which maps only builtin `ConnectionError`/httpx `ConnectError`). The client therefore gets a generic 500, "Internal server error: An unexpected error occurred." (`translation.py:51-54`, `server/server.py:105-133`), not an actionable connection error. A correct test would fail |
| 15 invalid configured key → auth error | JUSTIFIED | The product path exists. `gemini/model` falls back to the provider even when unregistered (`ogx:src/ogx/core/routers/inference.py:162-191`), and Google's 4xx keeps its status (`translation.py:43-49`). The suite cannot deploy a bad config key, though. The key comes only from the session-wide secret data, filled from env at import (`odh:tests/ogx/constants.py:61,71-79`; `conftest.py:86-107`), and `enable_gemini` always wires that secret key (`server_config.py:114-121`). No param accepts another value. Same call as run 7's conflicting-credentials decline |
| 16 MCP tool via Gemini | JUSTIFIED | No MCP fixture is visible under `odh:tests/ogx`. The team's test is a `pytest.fail` placeholder ("harness TBD", `test_mcp.py:41-50`). MCP deployments exist only in other trees with their own conftests (`odh:tests/rhoai_mcp/conftest.py`, `utilities/resources/mcp_server.py`), so using one would mean new cross-directory infrastructure the team left TBD |
| 23 TLS 1.2+ on egress | JUSTIFIED | Needs handshake capture or a proxy. The suite has neither, and the team's test is a placeholder (`test_security.py:98-102`) |
| 28 docs contain a config example | JUSTIFIED | Published RHOAI docs are in neither checkout. The upstream page has a sample (`ogx:docs/docs/providers/inference/remote_gemini.mdx:44-50`), but a cluster test suite cannot assert product docs |

Totals: 6 declined, 5 JUSTIFIED, 1 AVOIDABLE (scenario 4).

## 3. existing_coverage (22 `covered_by` claims)

| scenario | named test | class | evidence |
|---|---|---|---|
| 1 provider listed | test_providers.py::test_gemini_provider_listed | VERIFIED | Asserts `remote::gemini` in `/v1/providers` (`test_providers.py:42-46`). Registry `ogx:src/ogx/providers/registry/inference.py:188-194` |
| 2 no network.headers workaround | ::test_gemini_provider_no_network_headers_workaround | VERIFIED | Checks that the provider config has no `network.headers` and that a chat returns content (`:60-75`). `/v1/providers` returns the run-config dict (`ogx:src/ogx/core/providers.py:78`), so a workaround would show |
| 3 activates with configured key | ::test_gemini_conditional_activation_with_key | VERIFIED | Asserts the provider is listed with the key injected (`:91-93`). This is the same assertion as scenario 1; the no-key half is scenario 4 |
| 5 non-streaming chat | test_chat_completions.py::test_non_streaming_chat_completion | VERIFIED | Asserts id, choices, `role == "assistant"` and content (`:49-54`) |
| 6 streaming chat | ::test_streaming_chat_completion | VERIFIED | Asserts chunks > 0, `"stop"` among the finish reasons, and non-empty joined deltas (`:93-95`) |
| 7 temperature accepted | ::test_temperature_controls_variability | VERIFIED | Runs three requests each at 0.0 and 1.0, all valid (`:121-145`). Matches the plan's "two temperature values" |
| 9 embeddings | test_embeddings.py::test_embedding_generation | VERIFIED | Asserts a non-empty list of finite floats (`:50-57`) |
| 10 missing usage handled | ::test_embedding_missing_usage_handled | VERIFIED | Asserts the request succeeds with a vector (`:76-78`). This is the outcome the fallback guarantees (`gemini.py:108-118`). Caveat: it cannot show that usage was actually absent, because the adapter always fills it, so the `usage is None` branch (`:85-86`) never runs |
| 11 tool calling | test_tool_calling.py::test_tool_calling | VERIFIED | Asserts a `get_weather` function call with an id, JSON-object args and `finish_reason == "tool_calls"` (`:90-103`) |
| 12 unsupported schema fields filtered | ::test_tool_calling_with_unsupported_schema_fields | FALSE | The shipped code filters nothing: no schema handling in `gemini.py:21-124` or OpenAIMixin, and no `exclusiveMaximum`/`propertyNames` in `ogx:src`. The test only asserts that a completion came back (`:128-131`). That shows Google tolerated the schema, not that OGX filtered it. If Google rejects these fields, as the Jira says, the test fails on shipped code |
| 13 per-request key override | test_authentication.py::test_per_request_api_key_override | PARTIAL | The header and field are right (`x-ogx-provider-data`, `ogx:src/ogx/core/request_headers.py:83-86`; `gemini_api_key`, `gemini/config.py:18`). The baseline and the override both succeed (`:52-67`). The config key is valid, though, so the test also passes if the header is ignored: nothing shows the secondary key authenticated. It skips without `..._SECONDARY` (`:49-50`) |
| 14 invalid per-request key errors | ::test_invalid_per_request_api_key_errors | VERIFIED | Asserts a 4xx whose message names the key or auth, then a follow-up that succeeds (`:83-107`). Provider data takes precedence (`ogx:src/ogx/providers/utils/inference/openai_mixin.py:312-321`), and the provider's status is preserved (`translation.py:43-49`) |
| 17 image has Gemini + google-genai | test_deployment.py::test_build_includes_gemini_and_google_genai | PARTIAL | The provider half is real (`:58-60`). The `import google.genai` half (`:56-57`) checks a package the Gemini provider does not use: `pip_packages=[]` (`inference.py:190`). google-genai belongs to vertexai (`:200-202`) and is an ogx core dependency (`ogx:pyproject.toml:116`) |
| 18 conditional activation pattern | ::test_config_conditional_activation_pattern | FALSE | Greps the pod for `${env.GEMINI_API_KEY:+gemini-inference}` (`:76,89`). `gemini-inference` appears nowhere in ogx (git grep). The starter has `provider_id: gemini` (`config.yaml:75`), and the suite's own server config documents the gate as `${env.ENABLE_GEMINI:+gemini}` (`server_config.py:106-116`), consistent with `GEMINI_PROVIDER_ID = "gemini"` (`constants.py:56`) |
| 19 operator injects key without exposing it | ::test_operator_injects_gemini_api_key | PARTIAL | Asserts `GEMINI_API_KEY` is set in the pod (via `test -n`, `gemini/utils.py:116-120`) and that the provider is active (`:112-117`). "Without exposing its value" is not asserted here; the secretKeyRef check lives in scenario 22's test |
| 20 remote OpenAI still usable | test_regression.py::test_remote_openai_unaffected | PARTIAL | Correct assertions (`:78-90`), but the suite never injects an OpenAI credential (no `OPENAI` in `server_config.py`/`constants.py`/`conftest.py`). Without a key, OpenAIMixin lists no models (`openai_mixin.py:581-586`). In the suite's own deployment, the test stops at `pytest.fail` (`:75-76`) before checking anything |
| 21 other providers still usable | ::test_other_providers_unaffected | VERIFIED | Asserts Gemini and at least one other provider are listed, and that a chat through a non-Gemini LLM (the vLLM one the suite configures) returns content (`:104-122`) |
| 22 key not exposed | test_security.py::test_api_key_not_exposed | VERIFIED | Asserts secretKeyRef with no plaintext value in the pod spec (`:51-60`), and that the key is absent from every container's logs, the providers dump and a chat response (`:71-82`). Product redaction: `providers.py:78` |
| 24 deploy + chat e2e | test_e2e.py::test_deploy_and_chat_completion | VERIFIED | Asserts the provider is active, non-streaming content and streamed content (`:67-92`) |
| 25 full tool-calling workflow | ::test_full_tool_calling_workflow | VERIFIED | Asserts a tool call with `finish_reason == "tool_calls"`, then a final answer after the tool message (`:115-154`). It checks only for non-empty content, not that the answer uses the tool result |
| 26 embeddings e2e | ::test_embedding_generation_end_to_end | VERIFIED | Short and long inputs: finite float vectors of equal dimension (`:170-190`) |
| 27 multi-tenant per-request keys | ::test_multi_tenant_per_request_keys | PARTIAL | Three concurrent requests (config key, two override keys) all return content (`:213-230`). It passes even if the headers are ignored, so nothing shows that each key authenticated its own request. It skips without both secondary keys (`:207-211`) |

Totals: 22 claims: 15 VERIFIED, 5 PARTIAL (13, 17, 19, 20, 27), 2 FALSE (12, 18).

## 4. The plan

28 scenarios, 22 of them the team's tests renamed. Section III tags each of those EXISTING_COVERAGE while its own note says "Upstream coverage: ... partial" (O/stp/RHAISTRAT-1245_test_plan.md, every TS-01..27 entry), so the labels contradict the text. Two scenarios expect behaviour the shipped code lacks. **8**: an actionable connection error, where shipped code returns a generic 500 (`mapping.py:28-43`, `translation.py:51-54`). **12**: unsupported schema fields are filtered, but no filtering exists (`gemini.py:21-124`). Scenario 17 attributes google-genai to Gemini (`inference.py:190`). Scenario 4 holds only on a gated distribution: the upstream starter is unconditional (`config.yaml:75`); I follow the suite's `ENABLE_GEMINI` gate and do not count it. Shipped behaviour the plan misses:
- the OAuth path: `access_token` + `project`, their mutual-exclusion and required-pairing errors (`gemini/config.py:36-58`), and the `x-goog-user-project` header (`gemini.py:49-53`);
- streaming-usage coalescing (`gemini.py:27-29`, `openai_mixin.py:107-111`);
- rejection of token-array embeddings input (`gemini.py:81`);
- `provider/model` fallback routing to an unregistered Gemini model (`inference.py:162-191`).

## 5. Acceptance criteria (O/stp/RHAISTRAT-1245_jira_data.yaml, 9 bullets)

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | remote::gemini available in downstream distributions | COVERED | TS-01, TS-17 |
| AC-2 | configured as remote::gemini without network.headers | COVERED | TS-02 |
| AC-3 | embeddings work, missing usage handled | COVERED | TS-09, TS-10 |
| AC-4 | chat with streaming and temperature | COVERED | TS-05, TS-06, TS-07 |
| AC-5 | tool calling via /v1/chat/completions | COVERED | TS-11, TS-25 |
| AC-6 | provider-data `gemini_api_key` overrides config key | COVERED | TS-13, TS-14, TS-27 (shipped header is `x-ogx-provider-data`) |
| AC-7 | MCP servers work with Gemini | COVERED | TS-16 (declined) |
| AC-8 | docs updated with Gemini config examples | COVERED | TS-28 (declined) |
| AC-9 | validated against Gemini's OpenAI-compatible endpoint | COVERED | TS-05..TS-27 run live against it (`gemini.py:35-36`); Section II Compatibility Testing |

SCORE RHAISTRAT-1245 | QF tests=0 real=0 weak=0 hollow=0 wrong=0 loads=0 declined=6 justified=5 avoidable=1 cases=28 real_cases=0 covered=22 verified=15 partial=5 false=2 plan_wrong=2 acs=9 ac_covered=9 ac_out_of_scope=0 ac_missed=0
