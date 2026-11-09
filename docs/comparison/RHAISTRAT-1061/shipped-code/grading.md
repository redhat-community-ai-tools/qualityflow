# RHAISTRAT-1061: run 10 (QualityFlow on the shipped code, GLM 5.3, QF main 3b7ffa3)

R = <local> Shipped code: `ship/ogx-k8s-operator` at 2f5096a (written `op/` below);
suite: `ship/opendatahub-tests` at 7ffaacc (`odh/`). `git status` in each checkout shows only the QF file:
`op/pkg/config/qf_runtime_config_test.go` (Go, scenarios 1, 9, 14) and `odh/tests/ogx/test_qf_runtime_config.py`
(written `T`, scenarios 4, 8, 10, 11). Both are byte-identical to the copies under `outputs/RHAISTRAT-1061/{go,python}-tests/`.

Plan: 15 scenarios. 7 marked EXISTING_COVERAGE (2, 3, 5, 6, 7, 12, 15), 7 with a test, 1 `not_implemented` (13).
summary.yaml has no `existing_coverage` key, so the 7 claims are taken from the STD's `covered_by`.

## Loading

From `loading/RHAISTRAT-1061.md`: the Go file compiles (3 tests), and pytest collects 4 with every fixture resolved. I
also ran the three Go tests locally (`go test -run TestQF ./pkg/config`, no cluster, offline). All 3 pass, and the
checkout is unchanged. loads=7.

**Run 7's F1 does not repeat.** Every Python test now uses the suite's `ogx_server` fixture, which requests
`ogx_server_secret` (odh/tests/ogx/conftest.py:124), so the distribution Secret exists. The same Secret causes a new
problem in test 4 (see G1).

## Shipped facts used below

- **G1. A referenced Secret must carry `ogx.io/watch: "true"`.** The operator's cache holds only Secrets with that
  label (op/main.go:123-127). For a generated config, `resolveSecretRefsHash` fetches every Secret that `spec.providers`
  references through that cached client, and returns an error when one is missing (op/controllers/ogxserver_controller.go:629-636).
  The error sets the phase to Failed (ogxserver_controller.go:1214-1216). The API documents the label requirement
  (op/api/v1beta1/provider_types_inference.go:140-142). The suite creates `ogx-distribution-secret` with no labels
  (odh/tests/ogx/conftest.py:95-103).
- **G2. The suite's server is not declarative.** `build_ogx_server_config` sets only `distribution` and `workload`
  (with `overrides.env`), plus optional `network`, `tls` and `workload.storage` (odh/tests/ogx/server_config.py:174-201).
  `HasDeclarativeConfig` is providers/resources/storage/disabledAPIs (op/api/v1beta1/ogxserver_types.go:806-811).
  Without one of them, no config is generated (op/controllers/configmap_reconciler.go:64-66, 104-106). Credentials,
  Postgres and pgvector all arrive as `workload.overrides.env` entries (server_config.py:78-139;
  odh/tests/fixtures/vector_io.py:69-79). The secret hash that rolls the pod covers only generated-config secret refs
  (ogxserver_controller.go:619-621).
- **G3. Nothing waits for the operator after a patch.** `wait_for_status(READY)` returns on the phase that is still
  Ready from before the patch: the phase leaves Ready only when replica counts differ (ogxserver_controller.go:1293-1305).
  `wait_for_unique_ogx_pod` returns as soon as exactly one active pod exists (odh/tests/ogx/utils.py:166-193). Neither
  waits for `status.configGeneration.configMapName` or `observedGeneration` (ogxserver_types.go:679-682, 745).

## 1. QF tests

| test | plan case | class | evidence (one line) |
|---|---|---|---|
| qf_runtime_config_test.go::TestQFMinimalDeclarativeConfigIsUsable | 1 documented minimal declaration gives a Ready server, config mounted at /etc/ogx/config.yaml, GET /v1/version works | WEAK | It drives the real `GenerateConfig` (op/pkg/config/generator.go:42), and its strings exist: `remote::openai` (provider.go:159-172), `${env.OGX_OPENAI_PRIMARY_API_KEY}` (secret.go:29, 337-345). It checks only that generation succeeds, not Ready, the mount (resource_helper.go:89) or a server request |
| qf_runtime_config_test.go::TestQFGeneratedConfigDoesNotExposeSecretValues | 9 a unique credential value never appears in the generated ConfigMap; the pod uses a SecretKeyRef | WEAK | The placeholder check and the `SecretKeyRef openai-creds/api-key` check are real (secret.go:116-125, 327-337). The leak check looks for `super-secret-api-key`, a value the test never puts anywhere, so it cannot fail. No Secret value exists in the test, so it cannot detect a leak |
| qf_runtime_config_test.go::TestQFOnlyCurrentAPIVersionIsAccepted | 14 previous API version rejected, ogx.io/v1beta1 accepted | WEAK | The accept half decodes through the product's registration (api/v1beta1/groupversion_info.go:28). The reject half holds only because the test builds a scheme with v1beta1 alone. `ogx.io/v1alpha1 LlamaStackDistribution` never existed: the legacy API is `llamastack.io/v1alpha1` (api/v1alpha1/groupversion_info.go:19, 29). What is actually accepted is decided by the CRD (config/crd/bases/ogx.io_ogxservers.yaml:46, 7073), which it never touches |
| T::TestQFDeclaredProvidersAndModelsServeInference::test_declared_providers_and_models_serve_inference (T:37) | 4 declared provider and model serve inference | WRONG | G1: it points `spec.providers...openai[].apiKey` at the suite's unlabeled `ogx-distribution-secret` (T:59-62) without labelling it, so the reconcile fails and the phase goes Failed. G3: it either fails on Failed, or passes against the old pod, which serves the same model through the distribution's own vLLM provider (server_config.py:79-87). With a labeled Secret it would still be WEAK: it checks only that choices are non-empty, not that the reply came from `openai-primary` |
| T::TestQFDeclaredStoragePreservesDataAcrossRestart::test_declared_storage_preserves_data_across_restart (T:105) | 8 declared `spec.storage` keeps data across a restart | WRONG | Tests a different feature. No `spec.storage` is declared: `ogx_storage_size` becomes `workload.storage.size`, a PVC (server_config.py:196-201), and the vector store lives in the env-configured pgvector and Postgres (vector_io.py:69-79; server_config.py:125-139). G2: no runtime config is generated, so `ApplyStorage` (pkg/config/storage.go) is never exercised |
| T::TestQFCredentialRotationRestoresProviderAccess::test_credential_rotation_restores_provider_access (T:150) | 10 invalidate a credential, rotate it, and access is restored | WRONG | Tests a different path: the Gemini key is a `workload.overrides.env` secretKeyRef (server_config.py:114-121), not a `spec.providers` reference. G2: for that path no secret hash is computed (ogxserver_controller.go:619-621), and the Secret is unlabeled, so it is not watched (main.go:123-127). The pod keeps the old key and the call succeeds with it. The test never invalidates the credential first, so it cannot show anything was restored |
| T::TestQFRuntimeUpdatesApplyWithoutUnnecessaryRestarts::test_runtime_updates_apply_without_unnecessary_restarts (T:198) | 11 a changed setting rolls out and takes effect; unchanged content does not restart | WEAK | Its premise holds: adding `disabledAPIs: [responses]` makes the CR declarative, the pod moves to a generated ConfigMap and rolls (configmap_reconciler.go:64-66, 50-52). But G3: the "changed" check reads the pod right after the patch, which is most likely still the old one. It never checks that `responses` is gone ("takes effect"). The second patch is identical to the first, a no-op that cannot trigger a reconcile, so the "unchanged" half cannot fail |

Totals: 7 tests, REAL 0, WEAK 4, HOLLOW 0, WRONG 3.

## 2. `not_implemented`

| plan case | class | evidence |
|---|---|---|
| 13 documented migration plus a supported upgrade preserve settings and stored data ("supported source version unknown") | AVOIDABLE | The suite's upgrade tests do not depend on a source version: a `pre_upgrade` class and a `post_upgrade` class (odh/tests/ogx/vector_io/upgrade/test_upgrade_vector_store_rag.py:76-78, 114-116) reuse one server across the upgrade (odh/tests/ogx/conftest.py:64-67, 159-169). Stored data across an upgrade is done exactly this way. Settings preservation fits the same pattern (pre-upgrade: patch a declarative field, as test 11 does; post-upgrade: check it). Only the LlamaStackDistribution manual-migration half lacks suite support (utilities/resources has no LLSD wrapper), and that half alone would be JUSTIFIED |

## 3. `existing_coverage` (STD `covered_by`; summary.yaml has none)

| scenario | named test | class | evidence |
|---|---|---|---|
| 2 omitted settings keep distribution defaults | TestGeneratePraxisDefaultConfigPreservesDefaultConfig | PARTIAL | Exists (op/pkg/config/config_test.go:843-871) and checks that unrelated sections survive, but only on the Praxis-default path. That path is reachable only in Praxis mode (generator.go:110-117). The normal declarative `GenerateConfig` drops unrecognized base sections (types.go:68-78; generator.go:241-266) |
| 3 malformed or missing base config gives clear errors | TestParseBaseConfig, TestRun | PARTIAL | Missing `version` and invalid YAML check only `err != nil` (config_test.go:157-179). TestRun's `err-bad-base-path` checks the message `missing required 'version' field` (cmd/configgen/testdata/err-bad-base-path/want-err; main_test.go:156-163). No case covers a missing base config: no file, or an absent baseConfig ConfigMap, which is a terminal error at configmap_reconciler.go:113-117 |
| 5 multiple providers keep distinct model assignments | TestExpandResources_DefaultProviderIsDeterministic | PARTIAL | Exists (config_test.go:325-357). It uses one model with no explicit provider, and checks that the lexicographic default (`azure-1`) does not depend on input order. Several models with distinct declared providers are never asserted |
| 6 duplicate and unknown provider references rejected | TestOGXServerCELValidation | FALSE | No such test exists: api/v1beta1 has only `TestCEL_*` functions. These checks are webhook validation, not CEL (ogxserver_webhook.go:219-259). They are covered under other names, TestValidateProviderIDs and TestValidateProviderReferences (ogxserver_webhook_test.go:353, 528), so the pointer is wrong, not the behaviour |
| 7 disabled APIs absent; provider/API conflicts rejected | TestGenerateConfig_DisabledAPIs, TestOGXServerCELValidation | FALSE | The first asserts only non-empty YAML, never that `vector_io` or `tool_runtime` are gone (config_test.go:759-783). The second does not exist. The real checks live elsewhere: TestMergeAPIs (config_test.go:236) and TestCEL_OGXServerSpec_DisabledAPIsProviderConflict (ogxserver_cel_test.go:758) |
| 12 override controls the server; mixed modes rejected | TestReconcileGeneratedConfig_SkippedWhenOverrideSet, TestOGXServerCELValidation | PARTIAL | The first asserts only that generation returns nil when overrideConfig is set (controllers/configmap_reconciler_test.go:158-200), not that the override is mounted. The second does not exist. The real check is TestCEL_OGXServerSpec_OverrideConfigExclusivity (ogxserver_cel_test.go:675) |
| 15 base config resolved from OCI labels | TestDefaultConfigResolver_OCILabelUsed, _OCILabelMissing | VERIFIED | The real resolver with an injected label fetcher. Used: the resolved bytes equal the decoded label (config_test.go:1386-1403). Missing: the error names `com.ogx.distribution.default-config` (config_test.go:1421-1433; resolver.go:87-89) |

Also seen in the partial-coverage pointers: `TestRolloutSuite` (scenario 11) does not exist. The e2e test is
TestRolloutWithStorage (op/tests/e2e/rollout_test.go:30).

## 4. The plan

No scenario expects behaviour the shipped code lacks (plan_wrong=0). Two are mislabeled:
- **Scenario 14.** Its "previous API version" is `ogx.io/v1alpha1`, a version that never existed. The STD cites
  CLAUDE.md:8, which says no such thing. The real predecessor is `llamastack.io/v1alpha1 LlamaStackDistribution`
  (api/v1alpha1/groupversion_info.go:19, 29), so the scenario exercises nothing about the old API.
- **Scenario 2.** "Unrelated base sections are preserved" holds only on the Praxis-default path; the declarative path
  drops them (generator.go:110-111).

The plan's main blind spot is the `ogx.io/watch` label. It sits in the preconditions only, with no negative scenario,
and it is what sinks test 4 (main.go:123-127).

Shipped behaviour the plan also misses:
- legacy adoption through the `ogx.io/adopt-storage` and `ogx.io/adopt-networking` annotations
  (controllers/legacy_adoption.go:90-94, 576). The STP says no automatic conversion exists;
- `spec.baseConfig` taking precedence over OCI labels (configmap_reconciler.go:113-117);
- `status.configGeneration` and the ConfigGenerated condition (ogxserver_types.go:682, 745);
- immutable, content-hashed generated ConfigMaps and their retention (configmap_reconciler.go:50-52);
- Praxis mode disabling responses and conversations in the generated config (generator.go:34). The STP names Praxis
  as a cross-integration, but no scenario covers it.

Seven of the 15 scenarios were handed to existing tests. Only one of those claims checks out in full. Two name a test
that does not exist (`TestOGXServerCELValidation`).

## 5. Acceptance criteria

`main_issue.acceptance_criteria` in `stp/RHAISTRAT-1061_jira_data.yaml` is null (line 34). The ticket has none
(acs=0). The seven criteria at line 683, which the STP lists, were derived by QF from the description; they are not the
ticket's.

| AC | status | plan scenario |
|---|---|---|
| none | — | — |

SCORE RHAISTRAT-1061 | QF tests=7 real=0 weak=4 hollow=0 wrong=3 loads=7 declined=1 justified=0 avoidable=1 cases=15 real_cases=0 covered=7 verified=1 partial=4 false=2 plan_wrong=0 acs=0 ac_covered=0 ac_out_of_scope=0 ac_missed=0
