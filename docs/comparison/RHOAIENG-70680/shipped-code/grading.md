# RHOAIENG-70680 (Agent catalog backend): run 10 grading, QualityFlow on GLM 5.3

Product: `model-registry` at 8912d588 (`MR/`); `ac/` = `MR/catalog/internal/catalog/agentcatalog/`.
Suite: `opendatahub-tests` 7ffaacc; `agc/` = `tests/ai_hub/agent_catalog/`.
QF's files (both new, in the suite checkout): `agc/qf/test_qf_agent_catalog_sources.py` (cited `qf:N`) and
`agc/qf/conftest.py` (cited `qfc:N`, QF's own fixture; no team file edited). Copies in `O/python-tests/` are identical.
Plan: 41 scenarios. QF marked 26 EXISTING_COVERAGE, wrote 2 tests (031, 039) and declined 13.

The metadata pipeline (README fetch, `readmePath`, link rewriting, offline flag) is not in either checkout. I read it
read-only on GitHub: `opendatahub-io/model-metadata-collection` PRs #169, #171 and #174 are all MERGED (#174 on
2026-07-15). `MMC/` = that repo at #174's merge commit f36e19e. So `readmePath` did ship, in the metadata repo. It never
shipped in model-registry, which is what earlier gradings meant. This run writes no test for it and declines those
scenarios for the right reason (the repo is not checked out).

## Loading

From `loading/RHOAIENG-70680.md`: 1 test file plus QF's conftest; `pytest --setup-plan` collected 2. Both load.

## 1. QF tests (2)

| test | plan case | class | evidence |
|---|---|---|---|
| qf::TestQualityFlowAgentCatalogSources::test_generated_custom_source_loads_into_catalog_service (qf:49-90) | 031 a generated custom source loads into the catalog | REAL | It uses the suite's `agent_catalog_configmap_patch` (`agc/conftest.py:75-150`), which adds a yaml source to `agent-catalog-sources` and waits until the API grows by 5. It then asserts that `GET /sources?assetType=agents` lists `test_agent_catalog` with `status == "available"` (qf:64-79). The product sets that status after a good load (`ac/loader.go:189-195`; `MR/catalog/internal/catalog/basecatalog/source_types.go:12`). It also asserts that all 5 agent names are listed (qf:81-89). That is the plan's ASSERT-01. Caveats: the catalog is the suite's hand-written `TEST_AGENTS_YAML` (`agc/config/constants.py:62-111`), not skill output (the skill cannot run under pytest). The plan's "without disrupting existing sources" is not asserted. And the test repeats `agc/config/test_custom_agent_catalog.py:27-45` and `:84-107`; it adds only that this one source is `available`. It should have been a coverage claim |
| qf::TestQualityFlowAgentCatalogSources::test_malformed_custom_source_yaml_is_rejected[malformed_custom_source_yaml] (qf:92-155) | 039 malformed custom source YAML is rejected | WRONG | The "malformed" YAML is valid: `agents: [{name: malformed-agent, displayName: Malformed Agent}]` (qf:39-43; it parses). QF re-indented the plan's broken fixture (the STD's has `displayName` at the list's indent, which does fail to parse) into a well-formed one. The product reads it without error (`ac/yaml_provider.go:54-65`), saves the agent (`ac/loader.go:109-154`) and marks the source `available` (`ac/loader.go:195`). So the `status == "error"` assert (qf:135) and the log check for `error parsing YAML` (qf:143, text from `ac/yaml_provider.go:62`) cannot pass. Setup fails first anyway. `qfc:59-74` waits for exactly pre+5 agents, but the source adds a sixth. And in a class run, 031's class-scoped patch is still active (`agc/conftest.py:75`), so `pre_patch_size` already includes the 5 test agents. Teardown then waits for `default_agent_count` while that patch is still on (qfc:77-84) |

Totals: REAL 1, WEAK 0, HOLLOW 0, WRONG 1. Loads 2/2.

## 2. QF declines (13)

| scenario | class | evidence |
|---|---|---|
| 003 offline generation | JUSTIFIED | The pipeline and its `--skip-agent-enrichment` flag are in model-metadata-collection (PR #169 Makefile `process-agents`; `MMC/internal/catalog/agent_catalog.go:23,50,96-99`). That repo is not a configured checkout, and opendatahub-tests cannot run it |
| 011 installed catalog exposes the sample agents | AVOIDABLE | The installed release catalog can be read at runtime. `agc/metadata/conftest.py:13-23` reads `/shared-data/redhat-agents-catalog.yaml` from the catalog pod, and `agc/metadata/test_default_agent_metadata.py:60-65` already fails if any YAML agent is missing from the API. QF's reason ("no release name contract") ignores this fixture. A names check, or a coverage claim on that test, was available |
| 024 README from explicit and default locations | JUSTIFIED | `readmePath` selection is in `MMC/internal/catalog/agent_catalog.go:117-121`. model-registry only stores the finished `readme` (`ac/yaml_provider.go:37,100-102`). The input cannot be controlled from the suite |
| 025 unavailable README override returns an error | JUSTIFIED | Same repo, not checked out. The plan's expected error does not exist either (see §4) |
| 027 absolute links unchanged | JUSTIFIED | `resolveReadmeLinks` is in `MMC/internal/catalog/agent_catalog.go:209-226`. It needs a controlled README input, and the installed catalog does not keep the originals to compare against |
| 028 convention scan, 029 heuristic scan, 030 generated artifacts validate, 041 unsupported repo paths (4, same reason) | JUSTIFIED | The generator is the agent skill `MR/.agents/skills/create-agent-catalog-source/SKILL.md`: 563 lines of instructions for a coding agent (`allowed-tools: … AskUserQuestion`, :10), with no script, CLI or exit code. Steps 1-3 (:25-221) and 6 (:454-527) only run inside an LLM session, so pytest has nothing to invoke |
| 032 user documentation, 033 API reference and preview limitations (2) | JUSTIFIED | Neither checkout has Agent Catalog user docs or release notes. `git ls-files '*.md'` finds only skills, AGENTS.md/CLAUDE.md, `docs/writing-a-catalog-plugin.md` and a KEP |
| 034 source config survives a supported upgrade | AVOIDABLE | The suite already does this for MCP sources: `pre_upgrade` and `post_upgrade` markers (`pytest.ini:17-18`, collection in `conftest.py:289-307`) and the pattern in `tests/ai_hub/mcp_servers/upgrade/conftest.py:20-68` and `test_mcp_catalog_upgrade.py:20-60`. That pattern patches the user ConfigMap before the upgrade and checks it after. CI runs the upgrade between the two runs, so the test does not orchestrate it. QF's reason concedes the MCP fixtures exist. The agent equivalent needs only `agc/utils.py:14-22` and a source dict |
| 040 custom source missing required fields is rejected | JUSTIFIED | The product has no such rejection. Every field except `name` is an optional pointer (`ac/yaml_provider.go:32-48`), and the loader saves each entry without validating it (`ac/loader.go:109-154`). `ac/loader_test.go:96-104` loads an agent that has only a name and a description. QF's reason is correct, and the plan case is wrong (§4) |

Justified 11, avoidable 2.

## 3. existing_coverage (26, from the STD `covered_by`; `summary.yaml` has no `existing_coverage` key)

| # | named test | class | evidence |
|---|---|---|---|
| 001 | `agc/metadata/test_default_agent_metadata.py::test_default_agents_have_required_fields` | VERIFIED | Requires non-empty `id,name,description,displayName,source_id` on every served default agent (:12,29-46) |
| 002 | `…::TestAgentReadmeContent::test_agents_with_repository_url_have_readme` | VERIFIED | Every agent with `repositoryUrl` must have a non-empty `readme` (:105-119) |
| 004 | `agc/config/test_custom_agent_catalog.py::test_agents_list_returns_non_empty_catalog` | VERIFIED | With the test source patched in (pytestmark :14-21), asserts `TEST_AGENT_NAMES` and the LangGraph names are listed (:27-45) |
| 005 | `agc/search/test_agent_catalog_filtering.py::test_filter_returns_matching_agents` | PARTIAL | Seven filterQuery cases with an exact-set assert (:22-107), but no keyword search. The scenario and its AC are "search and filters". Search is in `agc/search/test_agent_catalog_search.py:36`, which is not cited |
| 006 | `agc/config/test_custom_agent_catalog.py::test_get_agent_by_id` | PARTIAL | Asserts only `GET /agents/{id}` == the list entry for `items[0]` (:63-82). The AC also asks that details "expose required information" (the title says documentation and configuration requirements). No `readme` or `env` assert |
| 007 | `agc/search/test_agent_catalog_filter_options.py::test_filter_options_returns_expected_fields` | PARTIAL | Checks only that the key `framework` is present (:41-43; `agc/search/constants.py:1-3`). The AC asks for "expected fields and values". No value is checked |
| 008 | `MR/catalog/cmd/catalog_startup_test.go` ("catalog startup tests") | VERIFIED | The startup child runs with `agent_catalogs: []` (and empty model/MCP/skill lists) (:261), and `TestCatalogStartupRollingUpgrade` requires `/readyz` 200 (:131-139). Startup with empty agent sources is asserted, though the test's own focus is the rolling upgrade, and the claim names no function |
| 009 | `agc/metadata/test_default_agent_metadata.py::test_yaml_agents_match_api_response` | VERIFIED | Diffs every YAML field read from the pod (`agc/metadata/conftest.py:13-23`) against the API (:48-79) |
| 010 | `agc/search/test_agent_catalog_filtering.py::test_filter_valid_source_label` | VERIFIED | `sourceLabel=Red Hat Agents` must return exactly the agents with `source_id == rh_agents` (:130-149) |
| 012 | `agc/config/test_default_agent_catalog.py::test_agent_catalog_configmap_exists` | VERIFIED | The ConfigMap exists, and `agent_catalogs == []` (:27-38) |
| 013 | `…::test_catalog_deployment_has_agent_sources_volume_mount` (+ `…_agent_catalogs_path_arg`, named in the STD assertion) | VERIFIED | Asserts the mount `/data/user-agent-sources` and the arg `--catalogs-path=/data/user-agent-sources/sources.yaml` (:82-106; `agc/config/constants.py:4-5`) |
| 014 | `…::test_default_agent_source_available` | VERIFIED | `rh_agents` is listed with `status == "available"` (:113-136) |
| 015 | `agc/artifacts/test_agent_artifacts.py::test_agent_artifact_types` | VERIFIED | For full, empty and image-only agents, asserts the count of inline image `artifacts` on the agent and, separately, the template count from `/artifacts` (:72-130). That is how the product splits them: `/artifacts` returns only templates (`ac/db_agent.go:164-205`) |
| 016 | `…::test_list_artifacts` (+ `test_artifacts_pagination`, named in the STD assertion) | VERIFIED | Count and type, with and without the `template-artifact` filter (:39-70). pageSize 1 to the end: no duplicates, a token while pages remain, count equals total (:175-229) |
| 017 | `…::test_template_artifacts_have_content_and_names` | VERIFIED | Exact name set `{agent.yaml, deploy.yaml, service.yaml, route.yaml}` and non-empty content (:132-152) |
| 018 | `ac/db_agent_test.go::TestGetAgentArtifacts_AgentNotFound` | VERIFIED | The repo returns `ErrAgentNotFound`, and the test asserts `ErrorIs(err, api.ErrNotFound)` (:108-115). This is the real mapping in `ac/db_agent.go:135-147,159-162`. Only the data layer is stubbed |
| 019 | `agc/metadata/test_agent_labels_logos_templates.py::test_agent_labels_match_yaml` | PARTIAL | Compares labels with the pod YAML (:34-55). The AC is "labels and logos match source YAML", and logos are not compared here. `test_all_agents_have_field[logo]` (:16-32) only checks they are non-empty |
| 020 | `agc/metadata/test_agent_catalog_template_artifacts.py::test_agents_have_template_artifacts` | VERIFIED | Every default agent has an `agent.yaml` template artifact (:21-35) |
| 021 | `test_agent_template_logo_is_valid_svg_data_uri` (cited in `test_agent_labels_logos_templates.py`) | VERIFIED | The test exists, but in `agc/metadata/test_agent_catalog_template_artifacts.py:76-104`, not the cited file. It requires the `data:image/svg+xml;base64,` prefix, valid base64 and SVG that parses. Template logo == agent logo is asserted at :52-74 |
| 022 | `ac/loader_test.go::TestAgentLoaderTemplateSaveFlow_ReloadReplacesTemplates` | VERIFIED | Real Postgres repos and the real loader: same agent ID after reload, old templates gone, only `template-c.yaml` remains (:136-190) |
| 023 | `ac/loader_test.go::TestAgentLoaderTemplateSaveFlow_ReloadWithNoTemplatesRemovesAll` | VERIFIED | After a reload with no `templates`, the stored templates are empty (:270-312) |
| 026 | `agc/metadata/test_default_agent_metadata.py::test_agent_readmes_have_no_relative_references` | VERIFIED | Fails on any relative markdown link, markdown image or HTML img in served READMEs (:121-159). That matches the AC and the shipped rewrite (links made absolute, images removed: `MMC/internal/catalog/agent_catalog.go:209-226`) |
| 035 | `agc/negative/test_agent_catalog_negative.py::test_invalid_request_returns_error` | VERIFIED | Six invalid requests must raise (:16-68). `ResourceNotFoundError` covers any status other than 200/201/401 (`tests/ai_hub/utils.py:934-939`), so the exact code is not pinned. The plan itself says error contracts are unconfirmed (STP Test Limitations) |
| 036 | `agc/negative/test_agent_catalog_negative.py::test_filter_nonexistent_label_returns_empty` | FALSE | It tests something else: `filterQuery=labels='nonexistent-label-xyz'`, an agent tag (:70-84), while the scenario is nonexistent *source* labels. The right test exists but is not cited: `agc/search/test_agent_catalog_filtering.py:151-165` (`sourceLabel=nonexistent` → size 0) |
| 037 | `test_artifacts_invalid_artifact_type` (cited in `agc/artifacts/test_agent_artifacts.py`) | VERIFIED | The test exists, but in `agc/negative/test_agent_catalog_negative.py:86-102`, not the cited file. `artifactType=image-artifact` must raise. The only valid enum value is `template-artifact` (`MR/api/openapi/src/plugins/agent.yaml:247-251`), so the parse error returns 400. Again any error status passes |
| 038 | `ac/db_agent_test.go::TestGetAgentArtifacts_EmptyResultReturnsEmptySliceNotNil` | VERIFIED | `NotNil(Items)`, `Empty(Items)`, `Size == 0` (:176-186), which is the real `ac/db_agent.go:204-206` |

Verified 21, partial 4, false 1. Two cited test files are wrong (021, 037), but the tests exist.

## 4. The plan

41 scenarios. Most follow the shipped code closely, and this time the plan names the real offline flag
(`--skip-agent-enrichment`, PR #169) and flags the Jira `--skip-github-fetch` mismatch itself. Two scenarios expect
behaviour that did not ship:

- **025**: unavailable `readmePath` should "return the defined error without producing a partial catalog". The shipped
  pipeline only logs `Warning: failed to fetch README` and writes the catalog anyway
  (`MMC/internal/catalog/agent_catalog.go:121-124`, then :70-89).
- **040**: incomplete custom sources should be rejected. The loader accepts them (`ac/yaml_provider.go:32-48`;
  `ac/loader.go:109-154`), and the skill fills in missing fields instead of rejecting them (SKILL.md:115-119).

A borderline case, not counted: in **003**, offline mode only emits agents whose index entry has inline name,
description and framework, and skips the rest (`MMC/internal/catalog/agent_catalog.go:131-142,148-162`). The shipped index
has paths only, so "every indexed agent appears" holds only with a fixture index that has overrides.

Shipped behaviour the plan misses:
- Agent-list pagination and ordering. Its own API review lists them, and the suite tests them at
  `agc/search/test_agent_catalog_pagination.py:18-130`.
- Disabled sources get `disabled`, and unknown source types get `error` (`ac/loader.go:76-83`).
- Missing or duplicate source ids are rejected (`ac/loader.go:252-257`).
- Agents of a removed source are deleted (`ac/loader.go:274-298`).
- Live file-watch reload with orphan cleanup (`ac/loader.go:157-163,172-221`).
- An unnamed template defaults to `agent.yaml` (`ac/yaml_provider.go:168-171`).

## 5. Acceptance criteria

`stp/RHOAIENG-70680_jira_data.yaml` `main_issue.acceptance_criteria` is null. The epic description has
"What this delivers" prose, not AC items.

| AC | status |
|---|---|
| none | — |

SCORE RHOAIENG-70680 | QF tests=2 real=1 weak=0 hollow=0 wrong=1 loads=2 declined=13 justified=11 avoidable=2 cases=41 real_cases=1 covered=26 verified=21 partial=4 false=1 plan_wrong=2 acs=0 ac_covered=0 ac_out_of_scope=0 ac_missed=0
