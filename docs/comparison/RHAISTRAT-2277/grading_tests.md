# RHAISTRAT-2277: run 5 (both tools on GLM 5.3), test grading

Shipped code: `ogx-k8s-operator` at 2f5096a (Praxis-fronted mode, migration Job). Suite: `opendatahub-tests` at 7ffaacc.
The Praxis gateway itself is in neither checkout. The suite deploys its own test Praxis
(`tests/ogx/praxis/server_config.py`) behind the `praxis_gateway_route` fixture (`tests/ogx/praxis/conftest.py:220-245`).
That config serves `/v1/responses` (translated to chat completions on vLLM) and the Conversations/Responses stores
(`server_config.py:79-143`). It has no tool step, no file_search step and no route for Files, Vector Stores or Embeddings.
In Praxis mode the operator turns off `responses` and `conversations` in OGX (`pkg/config/generator.go:35`, `:68-72`),
deletes OGX's Ingress (`controllers/network_resources.go:113-148`) and creates no Route or HTTPRoute (`:119-122`).

## QualityFlow tests (tests/ogx/praxis/qf_rhaistrat_2277/test_qf_ogx_praxis_migration.py)

The class fixture `praxis_context` seeds OGX through `ogx_client`, runs the real `praxis_migration_runner`, reads both
databases, and builds an `OgxClient` on the suite's `praxis_gateway_route`. The tests then drive the migrated Praxis
route. One caveat applies to all five route tests. The client is built without the suite's `verify=OGX_CLIENT_VERIFY_SSL`
(`tests/ogx/constants.py:21-22`; the suite's own clients pass it, e.g. `tests/ogx/conftest.py:318`). On a cluster with
self-signed router certificates, every request would fail the TLS handshake. This does not change the classes.

| test (file::name) | plan case | class | evidence |
|---|---|---|---|
| TestQfOgxPraxisMigration::test_non_rag_responses_through_praxis | 4: non-RAG Responses give compatible results through Praxis | REAL | It POSTs `/v1/responses` through `praxis_gateway_route`, the suite's Responses route (`server_config.py:83-121`). It asserts an id and the deterministic answer word (`:146-158`) |
| TestQfOgxPraxisMigration::test_streaming_responses_arrive_incrementally | 5: streaming content arrives before completion and reconstructs the response | WEAK | It checks for non-empty `response.output_text.delta` events before `response.completed` (`:181-192`). It never compares the joined deltas with the completed `output_text`, so the "reconstructs the completed response" half is unchecked |
| TestQfOgxPraxisMigration::test_conversations_crud_through_praxis | 8: Conversation create, retrieve, update, delete | REAL | It runs create, retrieve (id), update (metadata equals the new value) and delete, then expects 404 on retrieve (`:201-217`). This goes through the gateway's `openai_conversations` filter (`server_config.py:89-94`). Minor gap: the updated metadata is read from the update response, not from a later retrieve |
| TestQfOgxPraxisMigration::test_conversation_items_order_and_pagination | 9: pages concatenate to the recorded item sequence in order | WEAK | It creates three items, pages with `limit=2` and `after`, and checks page sizes and no overlap (`:226-254`). It discards the ids `items.create` returns and never compares against the recorded order ("first", "second", "third"). Instead it asserts the ids are lexically sorted (`:255`), an ordering rule nothing in the checkouts defines |
| TestQfOgxPraxisMigration::test_missing_conversation_not_found | 10: absent Conversation gets the not-found status **and** the OpenAI error envelope, disclosing nothing | WEAK | Only `status_code == 404` (`:266-270`). The error envelope and the non-disclosure check are missing |
| TestQfOgxPraxisMigration::test_migrated_identifiers_preserved | 13: every seeded record is retrieved **through Praxis** with its id, content and tenant ownership | WEAK | The migration is real, but this is a database parity check (id/created_at/model, conversation created_at/metadata; `:273-301`). Nothing is retrieved through Praxis, and content and ownership are unchecked. It repeats the suite's existing tests/ogx/praxis/test_db_migration.py:70-147 almost line for line |

Loads: 6/6. I re-ran `pytest --setup-plan` on the checkout and every fixture resolved. The test sits in tests/ogx/praxis/, so
`ogx_postgres_pod` (conftest.py:46) and the other praxis fixtures are in scope. The only other file it adds is its own
conftest.py, which registers the `qf_test_id` marker. No team file is edited.

## QualityFlow declines (`not_implemented`, 29)

This run implemented 4, 5, 8, 9 and 10, five of the ten cases runs 3 and 4 had declined as AVOIDABLE. The other five are
still declined, and the reasons given for them do not hold:

| plan case | class | evidence |
|---|---|---|
| 1 greenfield Responses through the single public entrypoint, and exactly one external implementation | AVOIDABLE | The Responses call is test 4's call on `praxis_gateway_route`. For the inventory half: in Praxis mode the operator deletes OGX's Ingress (network_resources.go:113-148) and turns off OGX's `responses` (generator.go:35, :68-72), and the test can check both. The reason ("no Python-test interface enumerates the exposure inventory") is beside the point: admin_client can list Ingresses and Routes |
| 2 direct external OGX Responses access denied | AVOIDABLE | After `praxis_migration_runner`, OGX's generated config no longer serves `responses` (generator.go:35, :68-72), and the suite's `ogx_test_route` / `ogx_client` reaches OGX directly. A POST `/v1/responses` there must be denied. OGX is internal-only behind the Praxis NetworkPolicy peer (controllers/ogxserver_controller.go:1983-2022) |
| 14 existing Files and Vector Store ids stay accessible in the OGX-backed service | AVOIDABLE | The AC names the OGX-backed service, not Praxis, so the reason ("no Files or Vector Store target schema or route in Praxis") does not apply. Seed with `ogx_client`, run `praxis_migration_runner` (praxis/conftest.py:249-267), then read the ids back as tests/ogx/praxis/test_praxis_tenant_isolation.py:117-127 does |
| 26 authorized resource access works after the upgrade | AVOIDABLE | Tenant clients (`_build_tenant_client`, test_praxis_tenant_isolation.py:17-46) after `praxis_migration_runner`. Praxis mode sets the `x-user-id`/`x-tenant-id` owner policy (generator.go:353-377) |
| 27 cross-tenant and forbidden operations denied | AVOIDABLE | The suite already tests cross-tenant and cross-user denial (test_praxis_tenant_isolation.py:79-140) against that owner policy (generator.go:353-377). The AC does not require the Praxis route, so "no ACL matrix wired through the migrated Praxis route" does not block it |
| 3 client `x-praxis-ai-*` headers cannot bypass policy | JUSTIFIED | `x-praxis-ai` appears in neither checkout (grep) |
| 6 server-side tool cycle | JUSTIFIED | The suite's Praxis has one inference step and no tool step (server_config.py:101-143) |
| 7 iteration and timeout bounds | JUSTIFIED | The config hard-codes `max_iterations: 1` and `timeout_ms: 300000` (server_config.py:104-105). The approved bounds belong to Praxis, which is outside the checkouts |
| 11, 12 embeddings through Praxis; unavailable embedding backend | JUSTIFIED (2) | Praxis serves only Responses and Conversations (generator.go:35), and the suite's Praxis has no embeddings route |
| 15 apps unchanged after cutover | JUSTIFIED | Cutover is platform-managed. The operator creates no Route or HTTPRoute (network_resources.go:119-122) |
| 16 interrupted migration resumes | JUSTIFIED | The Job only retries (`migrationJobBackoffLimit` 2, migration_job.go:51, :818). There is no interruption or resume procedure |
| 17, 18 one write owner; concurrent writes never diverge | JUSTIFIED (2) | No write-audit evidence and no concurrent-writer harness exist in the checkouts |
| 19 before/after inventory reconciliation | JUSTIFIED | No inventory export exists in code |
| 20, 21, 22 file-search citations, streaming file search, inaccessible search resources | JUSTIFIED (3) | The suite's Praxis has no file_search step (server_config.py:101-143). `file_citation` carries `index`, not byte offsets (ogx_client/types/response_object.py:128-139) |
| 23 upload, store and attach through Praxis | JUSTIFIED | The suite's Praxis routes only to the vLLM upstream (server_config.py:119-122) |
| 24, 25 transparent proxy; stream passthrough | JUSTIFIED (2) | There is no Praxis proxy route to OGX in the checkouts |
| 28 unauthenticated public requests rejected | JUSTIFIED | Public authentication belongs to the external gateway, which is not in the checkouts |
| 29, 30, 31 503 envelope, bounded timeout, correlated diagnostics | JUSTIFIED (3) | Praxis error mapping and diagnostics are outside the checkouts |
| 32, 33 rollback preserves data; unsafe rollback rejected | JUSTIFIED (2) | The rollback is soft: the webhook only warns, never rejects, and says data loss is possible (api/v1beta1/ogxserver_webhook.go:62-72) |
| 34, 35 published instructions; migration guide | JUSTIFIED (2) | These are documentation procedures, not code |

Totals: 5 AVOIDABLE, 24 JUSTIFIED.

## Test Plan Generator tests (tests/ogx_to_praxis_migration/)

Rule applied, the same as in run 3. Every test except TC-NEG-001 calls `_api_token()`, which skips unless
`OGX_PRAXIS_TOKEN` is set. Nothing in the suite sets it, and the suite has a `current_client_token` fixture
(tests/conftest.py:106). Those tests therefore always skip in the team's suite, and none can be REAL. This run's tests are
better than run 3's: they find the topology from the cluster through `admin_client` (HTTPRoute, Service, Deployment)
instead of reading env-var URLs and evidence files. The HTTPRoute they require is platform-made; the operator creates none
(network_resources.go:119-122). Their OGX log checks read pods in the Praxis Service's namespace, but Praxis runs in
`praxis-standalone` by default (api/v1beta1/ogxserver_types.go:47-57), apart from OGX, so the "absent from OGX logs"
checks pass vacuously.

| test (file::name) | plan case | class | evidence |
|---|---|---|---|
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_001 | TC-E2E-001 one Praxis `/v1/responses`, no competing implementation | WEAK | The assertions fit the TC: exactly one HTTPRoute selecting Praxis, 200 with `id`/`output`, the request id in Praxis logs, no OGX route (`:262-291`). It needs the env token, though (rule above), and the OGX log check is vacuous |
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_002 | TC-E2E-002 embeddings through Praxis | WEAK | The assertions fit (dimension, model, batch indexes, `prompt_tokens`; `:311-342`), but it needs the env token and an env-recorded dimension |
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_003 | TC-E2E-003 file and vector-store ids survive the upgrade | WEAK | It now writes its own pre-upgrade baseline to a ConfigMap and compares the TC's fields (`:363-416`), but it needs the env token. The pre-upgrade phase also requires a `/v1/responses` HTTPRoute that selects Praxis (`:359`, `_praxis_route` `:112-115`), which a 3.5 cluster does not have, so the baseline cannot be captured where the TC says |
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_004 | TC-E2E-004 one authoritative backend per write | WRONG | It asserts that the File and Vector Store ids appear in Praxis logs and **not** in OGX logs (`:469-471`). The TC itself expects File and Vector Store ids to live in OGX's store, and in the shipped topology OGX still serves files and vector stores: Praxis takes only `responses` and `conversations` (generator.go:32-35). The other checks are non-empty ids only |
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_005 | TC-E2E-005 file_search citations with byte offsets | WRONG | It now reads annotations from `output[].content[]` correctly, but asserts `annotation.start_index`/`end_index` on `file_citation` (`:517-526`). The shipped `file_citation` has `file_id`, `filename` and `index` only (ogx_client/types/response_object.py:128-139); `start_index`/`end_index` exist only on `container_file_citation` (:158-173) |
| test_e2e_ogx_to_praxis_migration.py::test_tc_e2e_006 | TC-E2E-006 rollback to OGX within 5 min, state intact | WEAK | It never triggers a rollback or compares state; it only checks that the route selects OGX and returns 200. It also cannot run: `:545` uses an undefined name `client` (the parameter is `admin_client`), so it raises NameError before any request |
| test_neg_ogx_to_praxis_migration.py::test_tc_neg_001 | TC-NEG-001 OGX port unreachable from outside, unauthenticated calls get 401 | WEAK | No env token here. The 401 checks for no token and a bad token, plus the no-leak check, fit (`:187-203`). The port-8321 probe targets the public gateway hostname, not OGX's address, and the TC's NetworkPolicy checks (non-Praxis pod denied, Praxis pod allowed) are missing |
| test_neg_ogx_to_praxis_migration.py::test_tc_neg_002 | TC-NEG-002 503 envelope when OGX is unreachable | WEAK | It now really scales OGX to 0 and checks for 503, the error fields, no leaks, and recovery (`:225-272`). But it needs the env token, the "file read" is a POST to `/v1/files/{id}` (`:231-236`), it looks for OGX in the HTTPRoute's namespace (`:225`), and the bounded-time check is missing |
| test_neg_ogx_to_praxis_migration.py::test_tc_neg_003 | TC-NEG-003 tenant isolation through delegation | WEAK | The cross-tenant reads expecting 403/404 fit, but both "tenants" share the one env token and differ only by client-sent `x-user-id`/`x-tenant-id` headers (`:287-292`), the very headers a public gateway is supposed to own. The file_search probe sends no tenant headers at all (`:323-332`), and the OGX log identity check is missing |
| test_upg_ogx_to_praxis_migration.py::test_tc_upg_001 | TC-UPG-001 switchover follows readiness, no black hole, state preserved | WRONG | The inventory GETs `/v1/conversations` and expects 200 with `data` (`:121-133`). The shipped Conversations API has no list operation: create is the only call on `/v1/conversations` (ogx_client/resources/conversations/conversations.py:62-91; the resource has create/retrieve/update/delete only). The readiness ordering and continuous probe are not tested (docstring `:151-152`) |

Loads: 10/10. The loading file reports "collected 5; 5 deselected" because the suite deselects upgrade-marked tests by
default. With `--pre-upgrade` and `--post-upgrade`, `--setup-plan` resolves all five upgrade-phase tests too. TC-E2E-006's
NameError surfaces only at run time.

## Test Plan Generator skips

None. Each of the 10 plan cases has a test function.

SCORE RHAISTRAT-2277 | QF tests=6 real=2 weak=4 hollow=0 wrong=0 loads=6 declined=29 justified=24 avoidable=5 cases=35 real_cases=2 | GEN tests=10 real=0 weak=7 hollow=0 wrong=3 loads=10 declined=0 justified=0 avoidable=0 cases=10 real_cases=0
