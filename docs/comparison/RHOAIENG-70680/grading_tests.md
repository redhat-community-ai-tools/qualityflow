# RHOAIENG-70680: run 5 tests graded (both tools on rits/zai-org/glm-5-3)

History: the first run-5 QF output for this ticket was run 4's archived file, which the model found in
`S/archive-run4/` and copied in verbatim (codegen.jsonl lines 91-113). QF was then re-run in isolation in
`<local>`. **The QF grading below is of that isolated run.**

Shipped code: `model-registry` at 8912d588 (paths below are relative to `model-registry/`). The isolated checkout
`<local>` is at the same commit; its only change is the added
test file. Suite: `opendatahub-tests` at 7ffaacc. QF plan: 36 cases (same STD as runs 3/4). GEN plan: 47 cases
(TC-*.md).

## QualityFlow tests (isolated re-run)

What it wrote: `catalog/internal/catalog/basecatalog/qf_agent_catalog_test.go` (package `basecatalog_test`), holding
`TestQfRHOAIENG70680AgentCatalog` with 35 `t.Run` subtests. Case 035 is declared `not_implemented`. The file
compiles (go vet + go test -c, per loading/), so all 35 load.

How the file works:
- Most subtests drive the shipped `agentcatalog.DBAgentCatalog` (`ListAgents`, `GetAgent`, `GetAgentArtifacts`,
  `GetFilterOptions`, db_agent.go:49-345) through hand-written fake repositories (test :23-88). The tests own those
  fakes, so for list, search, filter, paging and reload cases the outcome the case asks about is whatever the fake
  returns. Only the mapping and error logic in db_agent.go is really tested.
- A few subtests call `basecatalog.ReadSourceConfig` (basecatalog/config.go:12-32) or `AgentSourceCollection.Merge`
  (agentcatalog/sources.go:39).
- Three subtests (016, 029, 036) read repository files as text.
- The file sits in `basecatalog/`, but almost everything it tests is in `agentcatalog`. The package's existing mocks
  (agentcatalog/db_agent_test.go:19-96) and the DB-backed loader harness (loader_test.go:94-270) were not reused.

Compared with run 4, it no longer treats `readme` as a file path, and it uses the real API structs. But it still
wrote a subtest for each generator case (11-15, 30-34) that does not ship. Each one checks a different behaviour,
storage passthrough, under the case's name.

`…` = `catalog/internal/catalog/basecatalog/qf_agent_catalog_test.go::TestQfRHOAIENG70680AgentCatalog`. The test
lines are in that file.

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| …/001 (:133-141) | 1 list = union of two sources' inventories | WEAK | The fake repo returns the two agents; the test only checks prefix stripping (`displayNameFromStoredName`, db_agent.go:272-274). Loading two sources and listing their union never happens |
| …/002 (:144-158) | 2 search/filters return the matching set | WEAK | Asserts that `Query`/`SourceIDs`/`FilterQuery` reach the repo (db_agent.go:84-97). The matching (service/agent.go:154-192) is faked away, so no result set is checked |
| …/003 (:161-174) | 3 ordered pages, no gaps or duplicates | WEAK | Two separate fakes; the test only checks token passthrough (db_agent.go:108-110,128-130). Ordering and paging live in the faked repo |
| …/004 (:177-183) | 4 unmatched search gives an empty collection | REAL | Asserts non-nil empty `Items` and `Size==0`. The product builds `make([]openapi.Agent,0)` (db_agent.go:117-126), so the response is `[]`, not null |
| …/005 (:186-190) | 5 invalid discovery requests get the documented error | WEAK | One invalid kind only: a non-numeric id on detail gives `ErrBadRequest` (db_agent.go:136-139). The discovery (list) rejections (pageSize, nextPageToken, filterQuery → 400, v1alpha1/pagination.go:20-46) are untested |
| …/006 (:193-204) | 6 filter options equal the published distinct values | WEAK | Checks only that the `framework` key is present and `source_id` is excluded (db_agent.go:59-63). The option values are never compared |
| …/007 (:207-215) | 7 source selection returns that source's agents | WEAK | Checks only `SourceIDs` passthrough. Label resolution (`ByLabel`, api_agent_catalog_service_service.go:41-52) and the source filter (service/agent.go:178-189) are not exercised |
| …/008 (:218-237) | 8 details keep docs, model and env requirements | REAL | `GetAgent` → `mapDBAgentToAPI` maps `readme`/`framework`/`repositoryUrl`/`env` (db_agent.go:287-316). Asserts each value and `env[0].required==true` |
| …/009 (:240-243) | 9 unknown id gives not-found | WEAK | `require.Error` only, and the fake returns a plain error, not `ErrAgentNotFound`. The product would answer that with 500 (db_agent.go:146; internal/platform/errors/errors.go:14-27), and the test still passes |
| …/010 (:246-250) | 10 empty agent sources: catalog starts, model and MCP stay | WEAK | Only parses `agent_catalogs: []` (config.go:12-32). Startup, the empty list and the model/MCP sources are not checked |
| …/011 (:253-274) | 11 indexed starter kits → generated catalog metadata | WRONG | The generator does not ship (no README fetch, `readmePath` or `--skip-github-fetch` anywhere in the repo). It tests detail/template mapping instead, a different feature |
| …/012 (:277-284) | 12 repo README populates readme, links transformed | WRONG | No README retrieval or link transformation ships. It checks that the stored `readme` property passes through unchanged (db_agent.go:299-300) |
| …/013 (:287-292) | 13 unavailable repo docs (generator, TBD) | WRONG | Generator behaviour that does not ship. It checks that a missing readme is nil |
| …/014 (:295-299) | 14 skip documentation retrieval | WRONG | The flag does not exist. It marshals an empty `openapi.NewAgent` and checks the JSON has no `readme`, which never touches catalog logic |
| …/015 (:302-306) | 15 retrieval rate limits | WRONG | No retrieval ships. It checks that a fake repo error string is propagated by `ListAgents` (db_agent.go:112-115) |
| …/016 (:309-315) | 16 installation exposes the default curated agents via the API | WRONG | Greps the demo overlay file (`overlays/demo/dev-sample-agents.yaml`) for "agents:"/"name:". Installs use `rh_agents` from `/shared-data/redhat-agents-catalog.yaml` (overlays/odh/default-sources.yaml:82-90), and no API is called |
| …/017 (:318-324) | 17 admin-configured source exposes its agents | WEAK | Merges a source into `AgentSourceCollection` (sources.go:39) and reads it back. No agents and no API |
| …/018 (:327-331) | 18 invalid source config gives a diagnosable failure | REAL | `ReadSourceConfig` rejects duplicate agent ids with `duplicate agent catalog id: duplicate` (config.go:28-30,128-130), which names the section and the source |
| …/019 (:334-345) | 19 source config survives an upgrade | WRONG | Writes the same file twice and re-reads it. There is no upgrade and no template content, so it tests a different thing |
| …/020 (:348-355) | 20 listing distinguishes image and template artifacts, with content | WEAK | Checks only that the template item is `template-artifact` (hard-coded, db_agent.go:217-219). Images and content are not checked |
| …/021 (:358-369) | 21 artifactType filter + pagination give the exact subset | WEAK | Checks only the passthrough of `ParentResourceID`, `PageSize` and the token (db_agent.go:175-201). No pages are combined or compared with a subset |
| …/022 (:372-380) | 22 inline artifacts are exactly the image refs | WRONG | Its fake stores `artifactType:"image-artifact"`, and the test asserts that value. The loader stores only `uri` (yaml_provider.go:23-25,128-130), `AgentImageArtifact` has no unmarshal default (catalog/pkg/openapi/model_agent_image_artifact.go:47-60), and no shipped code sets `image-artifact`. Shipped inline artifacts would show `artifactType:""` |
| …/023 (:383-386) | 23 unknown agent's artifacts give 404 | WEAK | Same as 009: a plain fake error with `require.Error` only. The 404 path (db_agent.go:143-145) is not exercised |
| …/024 (:389-395) | 24 agent without artifacts gives an empty collection | REAL | `NotNil` + `Empty` on `Items` match the empty-not-null rule (db_agent.go:204-206) |
| …/025 (:398-405) | 25 changed templates replace the old ones | WEAK | The fake returns "new-content" and the test reads it back. The replacement (loader.go:141-150) never runs; loader_test.go:136 has that harness |
| …/026 (:408-413) | 26 removing all templates leaves none | WEAK | The fake returns nothing and the test checks that. Nothing is removed (loader.go:141-150; loader_test.go:270) |
| …/027 (:416-425) | 27 labels and logo in dedicated fields | REAL | Stored `labels` JSON and `logo` (the format yaml_provider.go:106-113 writes) come out in `Labels`/`Logo` (db_agent.go:303-311), and both are asserted |
| …/028 (:428-435) | 28 downloaded template equals the original agent.yaml | WEAK | Covers only the storage → API step (`Content`, db_agent.go:232-234). The step from the original agent.yaml to storage is not in the test |
| …/029 (:438-443) | 29 installed catalog serves shipped templates | WRONG | Greps the demo overlay for "templates:". That is not the installed default catalog (odh/default-sources.yaml:82-90), and nothing is served |
| …/030 (:446-454) | 30 readme from explicit/default location | WRONG | `readmePath` does not exist. It tests the template default name `agent.yaml` (db_agent.go:229-231), a different feature |
| …/031 (:457-462) | 31 unavailable `readmePath` | WRONG | No `readmePath` and no fallback ship. It checks that a missing readme is nil |
| …/032 (:465-472) | 32 relative links → GitHub tree URLs | WRONG | Asserts the relative link stays as it is, the opposite of the case. No rewriting ships |
| …/033 (:475-482) | 33 relative images replaced by alt text | WRONG | Asserts the image markup `![Architecture]` is still there, the opposite of the case. No rewriting ships |
| …/034 (:485-492) | 34 absolute links unchanged | WRONG | Generator case. It checks storage passthrough of the readme, which nothing rewrites, so it tests a different feature |
| …/036 (:499-510) | 36 API reference and preview limits match behaviour | WEAK | Reads api/openapi/src/plugins/agent.yaml as text and checks the 4 operationIds (:56,73,98,122), with no register/update/delete. Browse-only is confirmed, but the reference examples are never compared with behaviour |

Totals: 35 subtests: REAL 5, WEAK 16, HOLLOW 0, WRONG 14. All 35 load, so REAL and loading: 5.

## QualityFlow declines (`not_implemented`)

| plan case | class | evidence |
|---|---|---|
| 35 docs describe discovery and admin source setup | JUSTIFIED | The only agent doc in the repo is the plugin-author guide (docs/writing-a-catalog-plugin.md). No user procedure exists to follow |

The other generator and docs cases (11-15, 30-34) needed declines on the same grounds, as run 3 found. They got WRONG
subtests instead.

## Test Plan Generator tests

All 11 files are in `tests/ai_hub/agent_catalog/` (root level, so they see the package conftest). They use the suite's
real fixtures (`agents_response`, `default_agents`, `agent_catalog_configmap_patch` with an indirect param, and
`agent_catalog_rest_urls`), and all 47 load.

Facts that decide several rows:
- `size` in the list response is the count on the current page (`Size: int32(len(apiAgents))`, db_agent.go:123-126),
  and the default page size is 10 (v1alpha1/pagination.go:14).
- `/artifacts` returns template artifacts only. `artifactType` accepts only `template-artifact`
  (model_agent_artifact_type_query_param.go:22-28), and any other value is a parse error
  (api_agent_catalog_service.go:229-236). Image URIs are inline in `Agent.artifacts` (db_agent.go:315-319).
- The filter `name` and the `q` search run on the stored name `<source_id>:<name>` (yaml_provider.go:69;
  service/entity_mappings_agent.go:34; service/agent.go:162-175). Agents are not child entities, so nothing strips the
  prefix (internal/platform/db/filter/query_builder.go:446). With the default source `rh_agents`, `name LIKE '%agent%'`
  and `q=agent` therefore match every default agent.
- `source_id` is the real v1alpha1 JSON key (renamed from `sourceId` in v1alpha1/alpha_response.go:196-202, 216-221).
- Agents have no `agentType`, `tags` or `license` field (yaml_provider.go:32-48; catalog/pkg/openapi/model_agent.go:23-53).

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_api_agent_catalog.py::test_tc_api_001 (:19) | TC-API-001 list returns default + custom agents | WEAK | Checks only that the custom names are present (:24). Default agents and the total count are unchecked |
| test_api_agent_catalog.py::test_tc_api_002 (:26) | TC-API-002 get by id returns that agent | REAL | Full-dict equality of `GET /agents/{id}` with the list entry (:38). Both go through `mapDBAgentToAPI` (db_agent.go:119,149) |
| test_api_agent_catalog.py::test_tc_api_003 (:40) | TC-API-003 filter options | WRONG | Requires `agentType` and `tags` filters (:51). Neither property exists (plugins/agent/plugin.go:36-47; db_agent.go:59-68) |
| test_api_agent_catalog.py::test_tc_api_004 (:54) | TC-API-004 agent plugin readiness | REAL | `/readyz` returns `{"status":"ready","plugins":{name:bool}}` (catalog/internal/plugin/server.go:305-347), and the plugin name is `agent` (plugins/agent/plugin.go:27) |
| test_api_agent_catalog.py::test_tc_api_005 (:72) | TC-API-005 service health | WRONG | Reads `body["plugins"]` (:88). `/healthz` returns only `{"status":"ok"}` (plugin/server.go:299-303) |
| test_api_agent_catalog.py::test_tc_api_006 (:90) | TC-API-006 agent sources by assetType | WEAK | Checks non-empty and `assetType=="agents"` (:102-103; filter at api_model_catalog_service_service.go:454-473). It never checks that the default `rh_agents` source or the custom source is listed |
| test_artifact_agent_catalog.py::test_tc_artifact_001 (:43) | TC-ARTIFACT-001 all artifacts for an agent | WRONG | Expects 6 image + 4 template items (:56-57). `/artifacts` lists only templates (db_agent.go:164-206) |
| test_artifact_agent_catalog.py::test_tc_artifact_002 (:59) | TC-ARTIFACT-002 artifactType=image-artifact | WRONG | `image-artifact` is not an allowed value (model_agent_artifact_type_query_param.go:22-28), so the request fails parsing (api_agent_catalog_service.go:232-236) |
| test_artifact_agent_catalog.py::test_tc_artifact_003 (:76) | TC-ARTIFACT-003 artifactType=template-artifact | REAL | Asserts exactly 4 templates, names {agent.yaml, deploy.yaml, service.yaml, route.yaml} from the fixture (artifacts/constants.py:31,48-73) and non-empty content. That matches db_agent.go:164-206, 229-234 |
| test_artifact_agent_catalog.py::test_tc_artifact_004 (:95) | TC-ARTIFACT-004 artifact pagination | WRONG | Pages the image-only agent (:101). It has no templates, so `/artifacts` returns 0 (db_agent.go:164-206) and `total_count > 1` (:106) fails |
| test_e2e_agent_catalog.py::test_tc_e2e_001 (:28) | TC-E2E-001 browse, search, detail, artifacts | WEAK | Checks `q` non-empty, detail==list item, and that `size`/`items` keys exist (:51-52). The artifacts can be empty; health, readiness and the search contents are not checked |
| test_e2e_agent_catalog.py::test_tc_e2e_002 (:54) | TC-E2E-002 custom source + browse combined | WEAK | Shows that both sources are present (:62-63). The `sourceLabel` check `filtered ⊆ all` (:69) cannot fail |
| test_e2e_agent_catalog.py::test_tc_e2e_003 (:71) | TC-E2E-003 filter, search, paginate | WRONG | Asserts `len(ids) == first_page["size"]` (:98), but `size` is the page count, 1 here (db_agent.go:125). It fails whenever more than one agent matches. `q=agent` is also vacuous for rh_agents |
| test_e2e_agent_catalog.py::test_tc_e2e_004 (:100) | TC-E2E-004 operator wiring end-to-end | WEAK | The ConfigMap key, mount and `--catalogs-path` checks (:113-127) match the suite's (config/test_default_agent_catalog.py:88-105). The init container, health, readiness, sources and agent count are not checked |
| test_filter_agent_catalog.py::test_tc_filter_001 (:37) | TC-FILTER-001 `=` | REAL | Server `framework='langgraph'` equals the client-side subset of `default_agents` (:45). `framework` is a property (entity_mappings_agent.go:40) |
| test_filter_agent_catalog.py::test_tc_filter_002 (:49) | TC-FILTER-002 `!=` | REAL | Equality with the client-side `!= crewai` set (:58). The parser has `!=` (filter/parser.go:83) |
| test_filter_agent_catalog.py::test_tc_filter_003 (:62) | TC-FILTER-003 LIKE | REAL | `name LIKE '%langgraph%'`: the `rh_agents:` prefix cannot change the match, so the expected set is right (:70) |
| test_filter_agent_catalog.py::test_tc_filter_004 (:74) | TC-FILTER-004 ILIKE | REAL | `name ILIKE '%REACT%'` vs the client's lower-case contains (:82). ILIKE path at query_builder.go:460 |
| test_filter_agent_catalog.py::test_tc_filter_005 (:86) | TC-FILTER-005 IN | REAL | `framework IN (...)` vs the client set (:96). IN at parser.go:83 |
| test_filter_agent_catalog.py::test_tc_filter_006 (:100) | TC-FILTER-006 AND | WEAK | The second condition `name LIKE '%agent%'` matches every stored `rh_agents:` name (yaml_provider.go:69; entity_mappings_agent.go:34). The query is effectively `framework=langgraph` alone, so a broken AND is not caught |
| test_filter_agent_catalog.py::test_tc_filter_007 (:118) | TC-FILTER-007 OR | REAL | `autogen OR claude-code` vs the client set (:127). OR at parser.go:65 |
| test_filter_agent_catalog.py::test_tc_filter_008 (:133) | TC-FILTER-008 sourceLabel | REAL | `sourceLabel=Red Hat Agents` equals the `source_id=="rh_agents"` subset (:145). `ByLabel` (api_agent_catalog_service_service.go:41-52) with the default source (overlays/odh/default-sources.yaml:83-90) |
| test_filter_agent_catalog.py::test_tc_filter_009 (:149) | TC-FILTER-009 nested AND/OR | WEAK | Same vacuous `name LIKE '%agent%'` as 006, so the AND precedence is not tested |
| test_neg_agent_catalog.py::test_tc_neg_001 (:18) | TC-NEG-001 unknown id gives 404 | WEAK | `pytest.raises(ResourceNotFoundError)` (:24) catches any non-2xx except 401 (tests/ai_hub/utils.py:934-939), a 500 included. The 404 is not checked |
| test_neg_agent_catalog.py::test_tc_neg_002 (:30) | TC-NEG-002 unknown agent's artifacts give 404 | WEAK | Same: any error passes (:36) |
| test_neg_agent_catalog.py::test_tc_neg_003 (:42) | TC-NEG-003 malformed filterQuery gives 400 | WEAK | Same: the 400 and the error message are unchecked (:48) |
| test_neg_agent_catalog.py::test_tc_neg_004 (:55) | TC-NEG-004 bogus nextPageToken gives 400, not 500 | WEAK | The product returns 400 (v1alpha1/pagination.go:41-44), but the test (:61) would also pass a 500, which the case forbids |
| test_neg_agent_catalog.py::test_tc_neg_005 (:68) | TC-NEG-005 unknown sourceLabel gives empty 200 | REAL | Asserts `size==0` and `items==[]` (:79-80). The handler returns an empty list on no label match (api_agent_catalog_service_service.go:41-47) |
| test_ops_agent_catalog.py::test_tc_ops_004 (:17) | TC-OPS-004 model, MCP and agent coexist | WRONG | Expects unfiltered `/sources` to list 3 asset types (:28). With no `assetType` it returns models only (api_model_catalog_service_service.go:454-473) |
| test_page_agent_catalog.py::test_tc_page_001 (:29) | TC-PAGE-001 pageSize limits pages | WEAK | Checks only `len<=2` (:36). The token branch `if size > 2` can never run, because `size` is at most the page size (db_agent.go:125). Page 2 is never fetched |
| test_page_agent_catalog.py::test_tc_page_002 (:40) | TC-PAGE-002 NAME ASC | REAL | NAME ordering (service/agent.go:207-212, 238). With the default source only, the stored-name order equals the API name order (:52) |
| test_page_agent_catalog.py::test_tc_page_003 (:54) | TC-PAGE-003 CREATE_TIME DESC | REAL | `CREATE_TIME` column (service/agent.go:236). Asserts descending `createTimeSinceEpoch` (:66), set at db_agent.go:276-279 |
| test_page_agent_catalog.py::test_tc_page_004 (:68) | TC-PAGE-004 filtered pagination consistent | REAL | Pages of 1, `orderBy=id` (service/agent.go:235,239). Asserts the framework, no duplicates, and a token until the last page (:87-94). Capped at the first 10 by the default page size |
| test_schema_agent_catalog.py::test_tc_schema_001 (:69) | TC-SCHEMA-001 complete metadata returned | WRONG | Asserts `agentType`/`tags`/`license` (:73-75), which do not exist (model_agent.go:23-53). Its fixture's plain-string `customProperties` also fail `MetadataValue` decoding (catalog/pkg/openapi/model_metadata_value.go:71-78), so the whole file fails to parse (yaml_provider.go:61-63) and no schema agent loads |
| test_schema_agent_catalog.py::test_tc_schema_002 (:78) | TC-SCHEMA-002 minimal metadata agent | WRONG | The assertions are valid fields, but the agent comes from the same unparsable file (model_metadata_value.go:71-78; yaml_provider.go:45,61-63), so it never loads |
| test_schema_agent_catalog.py::test_tc_schema_003 (:88) | TC-SCHEMA-003 custom properties forwarded | WRONG | Expects a plain dict `{"owner":"platform-qe",…}` (:91). The API returns `MetadataValue` objects (db_agent.go:324-339), and that input cannot be parsed anyway |
| test_search_agent_catalog.py::test_tc_search_001 (:32) | TC-SEARCH-001 q across fields | REAL | `q=ReAct` vs the suite's `search_agents` oracle on name/displayName/description (:41). The server searches name/description/displayName/framework (service/agent.go:162-175), and the prefix has no "react" |
| test_search_agent_catalog.py::test_tc_search_002 (:43) | TC-SEARCH-002 name LIKE | REAL | `name=%langgraph%` becomes `LIKE '%:%langgraph%'` (service/agent.go:158). That is equivalent to the client's contains check (:52) |
| test_search_agent_catalog.py::test_tc_search_003 (:54) | TC-SEARCH-003 no match gives empty | REAL | Asserts an empty set for a term no agent has (:60) |
| test_search_agent_catalog.py::test_tc_search_004 (:66) | TC-SEARCH-004 q + filterQuery | WEAK | `q=agent` matches every stored `rh_agents:` name (service/agent.go:166), so the q part is vacuous and only the filter is tested |
| test_src_agent_catalog.py::test_tc_src_001 (:25) | TC-SRC-001 sourceLabel → sourceID | REAL | Same body as filter_008 (:37). The two plan cases overlap, and the outcome is checked against the shipped default label |
| test_src_agent_catalog.py::test_tc_src_002 (:41) | TC-SRC-002 custom source via ConfigMap loads agents | WEAK | Only `any(source_id=="test_agent_catalog")` (:47). Names, frameworks and metadata vs the YAML, and `/sources`, are unchecked |
| test_src_agent_catalog.py::test_tc_src_003 (:49) | TC-SRC-003 disabled source excluded | REAL | Patches in an enabled and a disabled source. Asserts the enabled agent is present and the disabled one absent (:108-109). Disabled sources are skipped (agentcatalog/loader.go:76) |
| test_src_agent_catalog.py::test_tc_src_004 (:111) | TC-SRC-004 unified /sources lists all types | WRONG | Same as ops_004: unfiltered `/sources` defaults to models (api_model_catalog_service_service.go:454-456) |
| test_upgrade_agent_catalog.py::test_tc_upgrade_001 (:29) | TC-UPGRADE-001 upgrade adds agent ConfigMap and mounts | WEAK | Post-upgrade existence checks only (:40-54). No pre-upgrade baseline, readiness or idempotence check |
| test_upgrade_agent_catalog.py::test_tc_upgrade_002 (:56) | TC-UPGRADE-002 DB schema compatibility | WRONG | `SELECT DISTINCT type FROM "Context"` (:64), but `Context` has `type_id`, not `type` (internal/platform/db/schema/context.gen.go:12). The agent type is `kf.Agent`, not `agent` (agentcatalog/service/agent.go:19) |
| test_upgrade_agent_catalog.py::test_tc_upgrade_003 (:70) | TC-UPGRADE-003 /sources backwards compatible | WRONG | Unfiltered `/sources` with all 3 types expected (:81). It returns models only (api_model_catalog_service_service.go:454-456) |

Totals: 47 tests: REAL 19, WEAK 15, HOLLOW 0, WRONG 13. All 47 load. Many of the REAL filter, search, negative and
sourceLabel tests copy what the suite already does (search/test_agent_catalog_filtering.py:26-165,
search/test_agent_catalog_search.py:26-30, negative/test_agent_catalog_negative.py:18-70). They are correct but add
little coverage.

## Test Plan Generator skips (plan cases with no test function)

| plan case | class | evidence |
|---|---|---|
| (none) | | All 47 TCs have one test each |

SCORE RHOAIENG-70680 | QF tests=35 real=5 weak=16 hollow=0 wrong=14 loads=35 declined=1 justified=1 avoidable=0 cases=36 real_cases=5 real_and_loads=5 | GEN tests=47 real=19 weak=15 hollow=0 wrong=13 loads=47 declined=0 justified=0 avoidable=0 cases=47 real_cases=19 real_and_loads=19
