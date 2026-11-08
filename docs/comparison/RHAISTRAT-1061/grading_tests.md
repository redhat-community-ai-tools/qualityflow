# RHAISTRAT-1061 — generated tests scored (run 5, both tools on GLM 5.3)

Shipped code: `ogx-k8s-operator` at 2f5096a; suite `opendatahub-tests` at 7ffaacc. Paths are repo-relative
(`ogx-k8s-operator/...`, `opendatahub-tests/...`).

## QualityFlow

QualityFlow wrote one Go file, `ogx-k8s-operator/controllers/qf_runtime_config_test.go`, with one test function
(`TestQFRuntimeConfigScenarios`) and 12 `t.Run` subtests. Each subtest is graded as one test. They call shipped code
directly (`config.GenerateConfig`, `OGXServerValidator.ValidateCreate`). Four of them (004, 011, 012, 023) use the
package's own envtest harness: `k8sClient`, started by `TestMain` with the real CRDs (controllers/suite_test.go:46-53),
plus `createTestNamespace`, `NewOGXServerBuilder` and `createTestReconciler` (controllers/testing_support_test.go:50,140,450,531).
All 12 compile, so all 12 count as loading.

Most plan cases expect a live outcome, such as a request result or a restart count. A config-only assertion is WEAK
unless the case's expected outcome is itself a config, admission or error result. That is the same rule runs 3 and 4 used.

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| qf_runtime_config_test.go::TestQFRuntimeConfigScenarios/TS-RHAISTRAT-1061-002 | 2 omitted settings keep distribution defaults (config and request results) | WEAK | Feeds an empty spec to `GenerateConfig` and checks that the base apis, provider, model and storage come through unchanged (pkg/config/merge.go:40-46,61-70,73-76; generator.go:241-262). This covers the config half more fully than run 4 did, but no request is sent |
| …/TS-RHAISTRAT-1061-003 | 3 malformed base config gives a clear parse error | REAL | Malformed YAML returns `failed to parse base config: <yaml error>` (pkg/config/merge.go:28-30, generator.go:44-46), and the test asserts it |
| …/TS-RHAISTRAT-1061-004 | 4 missing base config reference gives a clear error | WRONG | Reconciles a CR whose `baseConfig` points to an absent ConfigMap, then asserts `failed to resolve base config from ConfigMap` (configmap_reconciler.go:116). That path is never reached: `reconcileBaseConfigMap` runs first and returns `failed to find referenced base ConfigMap ns/name` (ogxserver_controller.go:1437-1443, called from :789). With no providers, `shouldGenerateConfig` is false anyway (configmap_reconciler.go:104-106). Neither asserted substring is ever produced, so the test fails against the shipped code |
| …/TS-RHAISTRAT-1061-005 | 5 each documented runtime field example accepted with its value | WEAK | Checks five fields with their exact rendered values: `base_url`, `api_token` as `${env.OGX_QF_VLLM_API_TOKEN}` (provider.go:140-149, secret.go:340-346), the model's `provider_id`, `kv_sqlite` (storage.go:35-36,81-85), and the disabled API removed. It is one combined spec, not each documented field applied independently, so network, TLS, workload and SQL are not covered |
| …/TS-RHAISTRAT-1061-007 | 7 each model request uses its assigned provider | WEAK | Now checks each model's `provider_id` pairing (serializeModels, generator.go:290-305), which run 4 missed. No request is sent, so routing is never observed |
| …/TS-RHAISTRAT-1061-008 | 8 duplicate provider IDs rejected with an identifying error | REAL | `ValidateCreate` returns `duplicate provider ID %q` (api/v1beta1/ogxserver_webhook.go:228-233) |
| …/TS-RHAISTRAT-1061-009 | 9 unknown provider reference rejected | REAL | `validateProviderReferences` returns `references unknown provider ID` (ogxserver_webhook.go:253-260) |
| …/TS-RHAISTRAT-1061-010 | 10 a disabled API is refused to clients | WEAK | Checks only that `vector_io` is dropped from `apis` (MergeAPIs, merge.go:73-88). The expected outcome, a refused request, is never exercised |
| …/TS-RHAISTRAT-1061-011 | 11 provider + disabled API conflict rejected | REAL | Creates the CR through envtest with the real CRD. The CEL rule `inference cannot be both in providers and disabledAPIs` (ogxserver_types.go:546) rejects it. This is the same setup the operator's own ogxserver_cel_test.go:780 uses. The assertion (`"inference"` in the error) is loose |
| …/TS-RHAISTRAT-1061-012 | 12 unsupported API selection rejected | REAL | `disabledAPIs: [not-an-api]` fails the `items:Enum` (ogxserver_types.go:576) with `Unsupported value`, which the test asserts |
| …/TS-RHAISTRAT-1061-015 | 15 generated config holds references, never secret values | REAL | Asserts that the `${env.OGX_QF_VLLM_API_TOKEN}` reference is rendered (provider.go:147-149, secret.go:345-346) and that the Secret's name and key are absent. Caveat: no secret value is ever supplied, so the "never a value" half holds by construction |
| …/TS-RHAISTRAT-1061-023 | 23 mixed custom + declarative rejected | REAL | Uses envtest with `overrideConfig` and `providers`. The CEL message `overrideConfig and providers are mutually exclusive` (ogxserver_types.go:541) is asserted. This matches the operator's own ogxserver_cel_test.go:690 |

### QualityFlow declines (`not_implemented`)

The suite's live OGX harness: `ogx_server` with indirect params (opendatahub-tests/tests/ogx/conftest.py:113),
`ogx_client` (:313), `enabled_ogx_operator` (:71), `postgres_deployment` (:576), and the post-upgrade branch (:159).
The operator's controllers envtest suite (controllers/suite_test.go:46-53) is the one this file already uses for 004.

| plan case | class | evidence |
|---|---|---|
| 1 minimal config gives a usable server (inference succeeds) | AVOIDABLE | Live inference is what the suite normally does: `ogx_server` / `ogx_client` (tests/ogx/conftest.py:113,313), with the vLLM URL and token wired in tests/ogx/server_config.py:79-86 |
| 6 declared providers/models serve inference | AVOIDABLE | Same harness. The operator expands the typed vLLM provider (pkg/config/provider.go:140-157) |
| 13 declared storage survives server restart | AVOIDABLE | SQL storage via `postgres_deployment` (tests/ogx/conftest.py:576) plus `ogx_client`; a restart is a pod delete |
| 14 missing credentials give an actionable error | AVOIDABLE | Credentials are `secretKeyRef` env vars (pkg/config/secret.go:327-337), so a missing Secret shows on the pod by name and never by value. The live harness (`ogx_server`, conftest.py:113) can observe it. The operator adds no status of its own for this |
| 16 credential rotation restores access | JUSTIFIED | Needs a second valid provider credential. The suite has a single token (tests/ogx/server_config.py:82) |
| 17 updated settings take effect in requests | AVOIDABLE | A changed spec regenerates a hash-named ConfigMap (controllers/configmap_reconciler.go:61-101). The suite can patch the CR and query with `ogx_client` |
| 18 unchanged settings cause no restart | AVOIDABLE | The decline is right that a hash alone proves nothing. But the controllers envtest suite can reconcile twice and compare the Deployment pod template, since the ConfigMap name is content-addressed (configmap_reconciler.go:50-52,94-97). Live, `ogx_server` plus pod UIDs would also do it |
| 19 invalid update keeps last usable config | AVOIDABLE | A generation failure returns before any ConfigMap or Deployment change (configmap_reconciler.go:86-90, ogxserver_controller.go:672-678) |
| 20 successive updates converge | AVOIDABLE | Same reconcile path (configmap_reconciler.go:61-101), with two patches and `ogx_client` |
| 21 settings survive operator restart | AVOIDABLE | `enabled_ogx_operator` (tests/ogx/conftest.py:71) plus the admin client can restart the operator, and `ogx_client` re-checks |
| 22 custom config controls the running server | AVOIDABLE | `spec.overrideConfig` is handled at ogxserver_controller.go:1377-1420. The suite already labels ConfigMaps `ogx.io/watch` (tests/ogx/conftest.py:178) |
| 24 missing custom config gives an actionable error | AVOIDABLE | `failed to find referenced ConfigMap ns/name` (ogxserver_controller.go:1402) is reachable from the same envtest reconcile that 004 already drives |
| 25 documented manual migration | JUSTIFIED | The suite has no `LlamaStackDistribution` fixture, and documented manual steps are not code |
| 26 upgrade keeps customizations | AVOIDABLE | Suite upgrade harness: tests/ogx/conftest.py:159 (post_upgrade) and tests/ogx/inference/upgrade/test_upgrade_chat_completions.py |
| 27 incompatible upgrade keeps running deployment | JUSTIFIED | Needs a known config-generation incompatibility between two builds, and the code defines none |

## Test Plan Generator

The generator wrote 18 files under `opendatahub-tests/tests/runtime_config_in_crd/`: 44 test functions, one per
plan case, with no parametrization. They drive the cluster by shelling out to `oc` through their own `utils.py`, not
through the suite's fixtures. All 44 load (`--setup-plan` collected 44, with no errors).

Shipped facts that sink most of them:
- **F1, no `Ready` condition.** `apply_and_wait_ready` (utils.py:119-122) runs `oc wait --for=condition=Ready` on
  the OGXServer. The operator sets no `Ready` condition. Its condition types are listed in controllers/status.go:9-41,
  and `Ready` exists only as `status.phase` (api/v1beta1/ogxserver_types.go:633). Every test that waits this way times out.
- **F2, no `ogx.io/owner` label.** `get_generated_configmap` and `get_owned_deployment` (utils.py:134-163) select
  by `ogx.io/owner=<name>`, a label the operator never sets (it appears nowhere in the repo). Generated ConfigMaps
  carry `app.kubernetes.io/instance` and `ogx.io/generated-config` (configmap_reconciler.go:190-197).
- **F3, wrong ConfigMap reference shape.** `baseConfig` and `overrideConfig` take `{name, key}` directly
  (ConfigMapKeyRef, ogxserver_types.go:125-136), not `{configMapRef: {...}}`.
- **F4, wrong providers shape.** `spec.providers` is an object keyed by API type (ProvidersSpec). `MinItems=1` sits on
  each per-type list, such as `vllm` (api/v1beta1/provider_types_inference.go:286-291), not on `spec.providers`.
- **F5, invented config key.** The generated config has no `metadata_store` key. Storage is under `storage`
  (generator.go:241-262, 379-385).

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_adopt_runtime_config_in_crd.py::test_tc_adopt_001 | TC-ADOPT-001 PVC adoption | WRONG | The annotations `ogx.io/adopt-pvc` / `adopt-service` do not exist; the real ones are `ogx.io/adopt-storage` / `adopt-networking` (ogxserver_types.go:69,71). The condition `ResourcesAdopted` does not exist; the real one is `StorageAdopted` (status.go:21). Also F1 and F2 |
| …::test_tc_adopt_002 | TC-ADOPT-002 PVC orphaned on delete | WRONG | Same nonexistent `ogx.io/adopt-pvc` annotation, plus F1 |
| …::test_tc_adopt_003 | TC-ADOPT-003 invalid adoption annotation reported | WRONG | Same nonexistent annotation and `ResourcesAdopted` condition. The real report is `AdoptionConfigInvalid` (status.go:25). Also F1 |
| test_baseconfig_runtime_config_in_crd.py::test_tc_baseconfig_001 | TC-BASECONFIG-001 baseConfig over OCI labels | WRONG | F3 (`baseConfig.configMapRef`), F1, F2. The base config also has no `version`, so it would fail parsing (merge.go:32-33) |
| …::test_tc_baseconfig_002 | TC-BASECONFIG-002 missing baseConfig → terminal error | WRONG | F3. It waits for a condition type `ConfigGenerationFailed`, which is only a reason on the `ConfigGenerated` condition (ogxserver_controller.go:675, status.go:19) |
| …::test_tc_baseconfig_003 | TC-BASECONFIG-003 baseConfig alone is inert | WRONG | F3, F1, F2 |
| test_cel_runtime_config_in_crd.py::test_tc_cel_001 | TC-CEL-001 overrideConfig + providers rejected | WRONG | F3 (`overrideConfig.configMapRef`), and `providers.inference: []` is a list where an object is required (provider_types_inference.go:345-350). Rejection comes from the bad shape, and the substring check passes on field paths, so the CEL rule (ogxserver_types.go:541) is not what is shown |
| …::test_tc_cel_002 | TC-CEL-002 overrideConfig + disabledAPIs rejected | WRONG | F3: the CR fails on the unknown or missing `overrideConfig` fields before the rule at ogxserver_types.go:544 matters |
| …::test_tc_cel_003 | TC-CEL-003 overrideConfig + baseConfig rejected | WRONG | F3 on both refs (rule at ogxserver_types.go:545) |
| test_e2e_runtime_config_in_crd.py::test_tc_e2e_001 | TC-E2E-001 declarative CR to running server | WRONG | `spec.replicas` does not exist; it is `spec.workload.replicas` (ogxserver_types.go:438). Also F1, F2, F5 |
| …::test_tc_e2e_002 | TC-E2E-002 overrideConfig to running server | WRONG | F3, `spec.replicas`, F1, F2 |
| …::test_tc_e2e_003 | TC-E2E-003 full upgrade journey | WRONG | F1 and F2. It also never upgrades and runs none of the 35 functional tests |
| …::test_tc_e2e_004 | TC-E2E-004 legacy adoption journey | WRONG | Nonexistent `ogx.io/adopt-pvc` / `adopt-service` annotations (ogxserver_types.go:69,71), plus F1 |
| test_lifecycle_runtime_config_in_crd.py::test_tc_lifecycle_001 | TC-LIFECYCLE-001 ConfigMap reused when unchanged | WRONG | F1, and it deletes pods and selects ConfigMaps by the nonexistent `ogx.io/owner` label (F2) |
| …::test_tc_lifecycle_002 | TC-LIFECYCLE-002 retention of 2 | WRONG | vLLM entries have no `endpoint`, which is required (provider_types_inference.go:114-117). Also F1, F2 |
| test_merge_runtime_config_in_crd.py::test_tc_merge_001 | TC-MERGE-001 whole-API-type replacement | WRONG | F1, F2 |
| …::test_tc_merge_002 | TC-MERGE-002 partial storage override | WRONG | `storage.kv.config` does not exist; KVStorageSpec takes `type` and `endpoint` (ogxserver_types.go:179; storage.go:53-63). Also F5, F1 |
| …::test_tc_merge_003 | TC-MERGE-003 disabledAPIs removes capabilities | WRONG | `disabledAPIs: [safety]` is outside the enum (ogxserver_types.go:576), so the CR is rejected at admission and never reaches Ready (F1) |
| test_neg_runtime_config_in_crd.py::test_tc_neg_001 | TC-NEG-001 unknown storage type reported | WRONG | `spec.storage.type` does not exist; StateStorageSpec has `kv` / `sql`. The assertion expects a storage-type list in stderr, which an unknown-field error does not contain |
| …::test_tc_neg_002 | TC-NEG-002 invalid disabledAPIs name | REAL | `disabledAPIs: [infrence]` fails the CRD enum at admission (ogxserver_types.go:576), and stderr names `infrence` and `disabledAPIs`. This is the plan's first expected branch |
| …::test_tc_neg_003 | TC-NEG-003 provider block replaced | WRONG | F1, F2 |
| test_netpol_runtime_config_in_crd.py::test_tc_netpol_001 | TC-NETPOL-001 NetworkPolicy toggle | WRONG | `spec.network.networkPolicy` does not exist; it is `spec.network.policy.enabled` (ogxserver_types.go:335; ogxserver_controller.go:250-251). Also F1 |
| test_oci_runtime_config_in_crd.py::test_tc_oci_001 | TC-OCI-001 base config from OCI labels | WRONG | F1 and F2. It also expects the generated config to equal the label config exactly, but the generator adds `distro_name` and `server.port` (generator.go:244-248, 323-335) |
| …::test_tc_oci_002 | TC-OCI-002 embedded fallback | WRONG | Skips unless an env var is set; when run, it uses a top-level `spec.image` that does not exist (it is `distribution.image`, ogxserver_types.go:103). It expects a fallback the resolver does not have: missing labels are an error (pkg/config/resolver.go:87-96) |
| …::test_tc_oci_003 | TC-OCI-003 OCI label format | WRONG | It must first pass the F1 wait. It reads the image from `spec.image` / `status.image` rather than resolving it |
| test_override_runtime_config_in_crd.py::test_tc_override_001 | TC-OVERRIDE-001 overrideConfig precedence | WRONG | F3. The CR also sets `overrideConfig` and `providers` together, which the CRD rejects (ogxserver_types.go:541), so it never reaches Ready (F1) |
| test_provider_runtime_config_in_crd.py::test_tc_provider_001 | TC-PROVIDER-001 vLLM expansion | WRONG | Asserts `config.url`, but the operator renders `base_url` (provider.go:141-143). It also waits for OGXServer Ready after applying the Secret (F1), and uses F2 |
| …::test_tc_provider_002 | TC-PROVIDER-002 Bedrock session token / role ARN | WRONG | Snake-case string fields (`aws_access_key_id`, `role_arn`, ...) do not exist. Bedrock takes camelCase SecretKeyRefs such as `awsAccessKeyId` (provider_types_inference.go:188-203). Also F1 |
| test_render_runtime_config_in_crd.py::test_tc_render_001 | TC-RENDER-001 immutable hash-named ConfigMap | WRONG | F1, F2, F5 (`metadata_store`) |
| …::test_tc_render_002 | TC-RENDER-002 change makes a new ConfigMap | WRONG | F1, F2 |
| test_rollout_runtime_config_in_crd.py::test_tc_rollout_001 | TC-ROLLOUT-001 rollout on change | WRONG | F1, and selects pods and ConfigMaps by `ogx.io/owner` (F2) |
| test_schema_runtime_config_in_crd.py::test_tc_schema_001 | TC-SCHEMA-001 valid config accepted | WRONG | Its outcome is the `Ready` condition (F1), which the operator does not set |
| …::test_tc_schema_002 | TC-SCHEMA-002 missing required field rejected | REAL | Omits `spec.distribution`, which is required (ogxserver_types.go:557-558). Admission fails with `spec.distribution: Required value`, which the test asserts |
| …::test_tc_schema_003 | TC-SCHEMA-003 invalid provider_type rejected | WRONG | Sends `spec.providers` as a list of `{provider_id, provider_type}`. The CRD has typed provider objects and no `provider_type` field (F4) |
| …::test_tc_schema_004 | TC-SCHEMA-004 MinItems on provider arrays | WRONG | `spec.providers: []` is a type error, not MinItems; MinItems is on the per-type lists (F4). The asserted `Too few items` never appears |
| test_secret_runtime_config_in_crd.py::test_tc_secret_001 | TC-SECRET-001 vLLM apiToken injection | WRONG | The env var name `OGX_VLLM_INFERENCE_API_TOKEN` and the `${env.…}` reference are right (secret.go:327-346). But the test can only reach them through F1 and F2, so it fails before asserting |
| …::test_tc_secret_002 | TC-SECRET-002 pgvector password injection | WRONG | F1, F2 |
| …::test_tc_secret_003 | TC-SECRET-003 three distinct env vars | WRONG | F1, F2 |
| …::test_tc_secret_004 | TC-SECRET-004 unlabeled Secret reported | WRONG | Expects a status message about `ogx.io/watch` on a provider Secret. The operator checks that label only for the migration Job's Secret (migration_job.go:355-362), never in the provider reconcile |
| test_storage_runtime_config_in_crd.py::test_tc_storage_001 | TC-STORAGE-001 Postgres storage | WRONG | `storage.type` / `storage.config` do not exist; storage is `kv` / `sql` (storage.go:27-51). Also F5, F1 |
| test_upgrade_runtime_config_in_crd.py::test_tc_upgrade_001 | TC-UPGRADE-001 3.4→3.5 upgrade | WRONG | Asserts `conditions["Ready"] == "True"`, a condition the operator never sets (F1). It also never upgrades |
| …::test_tc_upgrade_002 | TC-UPGRADE-002 workload continuity during upgrade | WEAK | Checks the legacy LLSD's health and one chat completion once, after the fact. It never checks continuity during the upgrade or that the pod UID stayed the same, which is the expected outcome |
| …::test_tc_upgrade_003 | TC-UPGRADE-003 v1alpha1 rejected after upgrade | WRONG | Never applies a v1alpha1 CR. It ends on the F1 wait |
| test_webhook_runtime_config_in_crd.py::test_tc_webhook_001 | TC-WEBHOOK-001 webhook rejects MinItems | WRONG | `spec.providers: []` is the wrong shape (F4). The Certificate `ogx-validating-webhook` in `ogx-operator` is not in the manifests either: config/certmanager/certificate.yaml:14 names it `serving-cert` |

### Generator skips

None. All 44 plan cases have a test function. `test_tc_oci_002` skips at runtime without an env var, but it has a
body and is graded above.

SCORE RHAISTRAT-1061 | QF tests=12 real=7 weak=4 hollow=0 wrong=1 loads=12 declined=15 justified=3 avoidable=12 cases=27 real_cases=7 | GEN tests=44 real=2 weak=1 hollow=0 wrong=41 loads=44 declined=0 justified=0 avoidable=0 cases=44 real_cases=2
