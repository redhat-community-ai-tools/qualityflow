# RHAISTRAT-2277 run 10 (QualityFlow main 3b7ffa3 on the shipped code, GLM 5.3): test grading

Paths: R = `<local>`, O = `R/qf/outputs/RHAISTRAT-2277`.
Shipped code: `R/ship/ogx-k8s-operator` at 2f5096a, cited `OP:<path>:<line>`. Suite: `R/ship/opendatahub-tests` at 7ffaacc, cited `ODH:<path>:<line>`.
QF test file: `T` = `ODH:tests/ogx/praxis/test_qf_ogx_praxis_migration.py`. It has 5 tests in one class that share a class-scoped namespace and OGXServer (T:38-56). `git status` in the suite shows only this file as added, so no team file was edited. The file in O/python-tests is identical to it.

Context: the Praxis gateway is in neither checkout. The suite deploys its own test Praxis, configured in ODH:tests/ogx/praxis/server_config.py:
- one single-tenant `state_owner` (:88)
- Conversations and Responses stores on the Praxis database (:89-100)
- an inference step that rewrites `/v1/responses` to chat completions and sends every path to vLLM (:101-143; catch-all route :119-122)

OGX is never on this Praxis's request path. In Praxis mode the operator turns off `responses` and `conversations` in OGX (OP:pkg/config/generator.go:32-35, :71).

## 1. QualityFlow tests (5)

| test (T::TestQualityFlowOgxPraxisMigration::…) | plan case | class | evidence |
|---|---|---|---|
| test_qf_streaming_responses_through_praxis | 5 streaming Responses through Praxis | WEAK | The test streams a Responses request through the Praxis route and asserts only that the chunk list is non-empty (T:73-83). The plan asks that the stream "terminates with a completed response". The SDK has a `response.completed` event type (ogx_client/types/response_object_stream.py:1487), but the test never checks for it, so a stream that ends in an error event still passes. |
| test_qf_backend_unavailable_returns_openai_error | 6 OpenAI-compatible 503 when the internal OGX backend is unavailable | WEAK | The test scales the Praxis state database to 0 (T:99-100), not the OGX backend the plan and Jira name (STD case 6 precondition "OGX internal endpoint is unavailable"; jira_data.yaml:269). OGX is never on the suite Praxis's path (server_config.py:119-122), so the planned failure is never produced. The 503 + `type/message/code` check (T:113-119) runs against a different failure, and Praxis's status code for a database outage is in neither checkout. The database is restored in `finally` (T:120-122). |
| test_qf_rollback_restores_ogx_response_access | 7 rollback restores OGX routing, state intact | WEAK | The test stores a response through OGX, migrates, patches `praxisMode.enabled: false` (T:147-157), then reads the response back through OGX. That read works only once OGX serves `responses` again (OP:pkg/config/generator.go:32-35), so it is real evidence of the rollback. But the only assertion is `rolled_back.id == baseline.id` (T:160-161), which is just "the read succeeded". The output and model are not compared with the baseline the test holds, and no new POST is sent through OGX (Jira AC: "POST /v1/responses returns a successful response via OGX"). `wait_for_status(READY)` (T:158) can also return before the reconcile, because the CR was already Ready. |
| test_qf_customer_client_compatibility_across_migration | 13 unchanged client works across migration | WRONG | This test fails on a correct product because of the test before it. Tests run in definition order (ODH:pytest.ini has no random-order plugin), so it runs right after the rollback test on the same class-scoped OGXServer. On rollback the operator deletes the migration Job (OP:controllers/migration_job.go:128-129, :639-652) and keeps phase `Validated` (:159-167). On re-enable it creates no new Job (:594-599, :101-103). The operator's own unit test pins this: "disable must delete the migration Job", "re-enable does not re-run the migration" (OP:controllers/migration_job_test.go:618-623). So `praxis_migration_runner()` (T:186) waits up to 600 s for a Job that never appears (ODH:tests/ogx/praxis/migration.py:85-95) and errors. Even in isolation the test would be WEAK: `output_text is not None` (T:184, :191) is always true because `output_text` always returns a str (ogx_client/types/response_object.py:870-877), and the "unchanged" client is pointed at a different base URL (T:183 vs :188-189). |
| test_qf_migration_readiness_conditions | 15 readiness conditions report False/True per state | WRONG | It runs after the rollback and test 13 on the same OGXServer. After rollback, `clearMigrationState` sets MigrationJobSucceeded, MigrationValidated and PraxisCutoverReady to False (OP:controllers/migration_job.go:176-179). Re-enabling never sets them True again, because no Job is observed (:101-103, :597-599). The runner call (T:205) also times out, as in test 13. On its own it would still fail on the suite topology. It asserts `PraxisReachable == True` (T:211-225), but with no `praxisSelector` the operator looks for `app.kubernetes.io/name=praxis-gateway` pods in namespace `praxis-standalone` (OP:controllers/praxis_preflight.go:110-125; api/v1beta1/ogxserver_types.go:47-57). The suite's Praxis is labelled `app=praxis-gateway` and runs in the test namespace (ODH:tests/ogx/praxis/constants.py:38-39; conftest.py:178-197). The plan's False-state half is not attempted. |

Loads: 5/5 (loading/RHAISTRAT-2277.md: 1 file, no conftest changed, collected 5; pytest-tests.log shows SETUP for all 5). All fixtures exist (ODH:tests/ogx/praxis/conftest.py:60-87, :220-267).

## 2. QualityFlow declines (`not_implemented`, 8)

| plan case | class | evidence |
|---|---|---|
| 1 Responses, Conversations and Embeddings available through Praxis | JUSTIFIED | The case needs all three APIs. The suite's Praxis has no embeddings backend: everything except `/v1/responses` goes to the vLLM chat endpoint (server_config.py:107-122). The operator does not make Praxis serve embeddings (OP:pkg/config/generator.go:35). The real Praxis configuration is in neither checkout. Responses and Conversations alone were drivable, but the case would still be incomplete. |
| 2 pre-upgrade Files, Vector Stores, Responses and Conversations accessible through the public entrypoint | JUSTIFIED | Files and Vector Stores have no route on the suite's Praxis (server_config.py:101-143), and the real Praxis delegation configuration is not in either checkout. |
| 3 file_search citations from existing vector stores through Praxis | JUSTIFIED | Same reason as case 2: the suite's Praxis has no file_search or vector-store path. |
| 10 file upload, vector store and attachment lifecycle through Praxis | JUSTIFIED | Same reason as case 2. |
| 11 embeddings through Praxis with expected dimensions | JUSTIFIED | Same reason as case 1. |
| 14 Praxis owns public auth and policy | JUSTIFIED | The suite's Praxis has no auth filter and its Route has no policy (server_config.py:75-145; conftest.py:220-245). The public AuthPolicy or Praxis auth configuration is in neither checkout. OGX's `upstream_header` auth (OP:pkg/config/generator.go:353-377) is a different boundary. |
| 8 single-writer ownership per resource | AVOIDABLE | QF says all four types must go through Praxis. In the shipped design they do not: in Praxis mode only `responses` and `conversations` move to Praxis (OP:pkg/config/generator.go:35, :71), and OGX keeps Files and Vector Stores. The suite has everything needed to check that each ID lands in exactly one database: both Postgres pods (ODH:tests/ogx/praxis/conftest.py:45-57, :270-281), the SQL helper `query_database` (utils.py:187), and the source and target table names (constants.py:10-16). It can also call `ogx_client.responses.create` in Praxis mode and expect it to be refused. |
| 12 non-RAG tool calling through Praxis | AVOIDABLE | QF says the test needs a tool-calling filter. A client-side function tool needs only the request translation the suite's Praxis already has (`openai_responses_to_chat_completions` to vLLM, server_config.py:107-121; one iteration is enough, :104). The route and client fixtures exist (conftest.py:220-245; T:20-35). QF wrote the streaming test (case 5) on the same untested translation path. |

Totals: 6 JUSTIFIED, 2 AVOIDABLE.

## 3. `existing_coverage` entries (2)

The STD marks 2 cases EXISTING_COVERAGE (`existing_coverage_count: 2`); summary.yaml has no separate list.

| plan case | named test | class | evidence |
|---|---|---|---|
| 4 tenant isolation across the Praxis-to-OGX boundary | ODH:tests/ogx/praxis/test_praxis_tenant_isolation.py::test_e2e_file_upload_and_isolation | PARTIAL | It exists and checks the case's outcome for Files only: cross-tenant, cross-user and both together are refused on retrieve and delete with 403/404 (:117-143). But it calls OGX directly through `ogx_test_route` (:82-85), on an OGXServer with no `praxisMode` (:57-70), and runs no migration. The operator applies the `x-user-id`/`x-tenant-id` upstream-header auth only in Praxis mode (OP:pkg/config/generator.go:328-329, :353-377), so the boundary configuration this case is about is not the one tested. |
| 9 OGX internal-only in Praxis mode | OP:controllers/external_exposure_test.go::TestPraxisOptIn_CreatesNoExternalExposurePrimitive | VERIFIED | Runs a real reconcile against envtest with `praxisMode.enabled: true` (:241-244, fixture :131-179). It asserts no OGX Ingress by name or by backend, a ClusterIP Service, and no externalIPs, LoadBalancer IP, ExternalName or NodePort (:184-224). That is exactly the case's criterion. As the file header says, this is the declared topology, not packet-level reachability (:30-32). |

The PARTIAL_COVERAGE references (not counted) all name tests that exist: test_db_migration.py:70, vector_io/test_vector_stores.py:177, vector_io/upgrade/test_upgrade_vector_store_rag.py:116 and test_praxis_tenant_isolation.py:212. The gaps they name are accurate.

## 4. The plan

**Expects unshipped behaviour: none counted.** Two doubtful points, not counted:
- Case 6 uses a plain `POST /v1/responses` as the "state-dependent request" that should fail when OGX is down. In Praxis mode, Responses state belongs to Praxis (OP:pkg/config/generator.go:32-35; the migration target tables are in Praxis, ODH:tests/ogx/praxis/constants.py:15-16), so only an OGX-backed operation such as file_search would depend on OGX.
- A source constant names `/v1/vector-stores` (STD source_constants). The real route, and the one the Jira AC names, is `/v1/vector_stores` (jira_data.yaml:261). No case uses it.

Case 7's "state intact" holds for state created before migration. Writes made through Praxis after cutover are lost on rollback (soft rollback, OP:controllers/status.go:239-241; api/v1beta1/ogxserver_webhook.go:70). The plan does not mention this.

**Shipped behaviour the plan misses:**
- The SoftRollbackAvailable condition and the rollback admission warning (OP:controllers/status.go:40-41, :239-241).
- The migration-Job failure path: phase Failed, MigrationJobSucceeded False, "Delete the Job to retry" (OP:controllers/migration_job.go:923-949).
- The TLSConfigured condition in Praxis mode (OP:controllers/praxis_preflight.go:76-108).
- `praxisSelector` versus the default `praxis-standalone` peer (:110-125).
- The Praxis-only NetworkPolicy peer (OP:controllers/external_exposure_test.go:301).
- OGX switching to upstream-header auth with an owner policy (OP:pkg/config/generator.go:353-377).
- The migration's fallback tenant and owner (OP:controllers/migration_job.go:55-62).
- Praxis mode being opt-in and off by default (OP:controllers/external_exposure_test.go:19-28).

Case 15 names the conditions but plans no specific preflight failures (distinct databases, watch label).

## 5. Acceptance criteria

`main_issue.acceptance_criteria` (jira_data.yaml:251-275) is a block of eight Given/When/Then and "measured by" statements under headings, with no bullets. Each statement is counted as one AC, in order.

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | Greenfield `/v1/responses` served by Praxis; one external route; OGX 8321 not reachable from outside | COVERED | 1 (public availability), 9 (OGX internal-only) |
| AC-2 | Greenfield embeddings through Praxis with correct dimensions | COVERED | 11 |
| AC-3 | Upgraded: existing file and vector-store IDs return the same data through Praxis | COVERED | 2 |
| AC-4 | Rollback: routing back to OGX, state intact, POST via OGX within 5 min | COVERED | 7 (the 5-minute bound is not in the plan) |
| AC-5 | RAG citations and valid annotation offsets from pre-upgrade files | COVERED | 3 |
| AC-6 | OGX unavailable gives a 503 with an OpenAI error body | COVERED | 6 |
| AC-7 | No resource written to two stores | COVERED | 8 |
| AC-8 | Tenant isolation across the Praxis-to-OGX boundary | COVERED | 4 |

SCORE RHAISTRAT-2277 | QF tests=5 real=0 weak=3 hollow=0 wrong=2 loads=5 declined=8 justified=6 avoidable=2 cases=15 real_cases=0 covered=2 verified=1 partial=1 false=0 plan_wrong=0 acs=8 ac_covered=8 ac_out_of_scope=0 ac_missed=0
