# RHAIRFE-1487 (MaaS multi-tenancy): run 10 grading, QF normal flow on the shipped code (GLM 5.3)

Paths: `maas:` = `<local>` (05a5ff90), `odh:` = `.../ship/opendatahub-tests/` (7ffaacc), `M/` = `odh:tests/ai_gateway/models_as_a_service/`, `O` = `.../qf/outputs/RHAIRFE-1487/`. QF test file `T` = `M/multitenancy/test_qf_rhairfe_1487.py` (8 tests, two classes; identical to `O/python-tests/test_qf_rhairfe_1487.py`). `git status` in odh shows only that file: no team file changed, no conftest added.

The plan is new: 13 scenarios. 5 are EXISTING_COVERAGE (1, 2, 3, 8, 9); this time the duplicate check ran (`existing_coverage_check: ran`, O/stp/RHAIRFE-1487_regression_analysis.yaml:270). QF wrote 8 tests for the other 8 scenarios (4, 5, 6, 7, 10, 11, 12, 13) and declined none (`not_implemented: []`, O/python-tests/summary.yaml).

**Tenant vs AITenant.** The ticket's May text says "Tenant CR". The plan uses "tenant" as a generic term (Document Conventions, O/stp/RHAIRFE-1487_test_plan.md:21). Its STD pins the shipped kind: `AITENANT_KIND: AITenant` (std yaml :83-86, `maas:maas-controller/api/maas/v1alpha1/aitenant_types.go:24-25`), and its RBAC says "create and delete AITenant resources" (:75). The tests use the AITenant resource only (`T:74`, `T:282-297` patches `AITenant.spec.oidc`, `aitenant_types.go:67-71`) plus `MaasTenantConfig` (`T:526-536`). Nothing uses the deprecated `Tenant` kind (`tenant_types.go:25, 39-43`). QF's product_refs cite `tenant_types.go:88`, but that line is the `TenantExternalOIDCConfig` struct that `AITenant.spec.oidc` uses, not the old kind. Both the plan and the tests follow the shipped AITenant.

Two facts decide most rows:
- **A MaaSModelRef reports Ready only once a subscription and an auth policy reference it.** The Ready condition is "True only when both governance and runtime are healthy" (`maasmodelref_types.go:106`, controller `maasmodelref_controller.go:274-281, 354-357, 443-457`).
- **The suite has the tenant fixtures** (two AITenants, their gateways, tenant-local models, subscriptions and keys, `M/multitenancy/conftest.py:160-566`), and they are fresh per class: random names (`:214`), created with teardown (`:184-191`).

## 1. QF tests (8)

| test (T::…) | plan case | class | evidence |
|---|---|---|---|
| TestQFRhairfe1487Multitenancy::test_api_key_remains_valid_at_lifetime_boundary | 4 key valid at lifetime boundary | REAL | It mints a tenant A key with `expiresIn: 2160h` (`T:625-637`), exactly the shipped 90-day cap. `time.ParseDuration` accepts it, and only `> maxRegularDuration` is rejected (`maas:maas-api/internal/api_keys/service.go:116-117, 139-142`; `constant/const.go:26`; `token/types.go:16-25`). It asserts 201 with `key`/`expiresAt`, then that inference through tenant A's gateway returns 200 (`T:639-645`). Both of the case's acceptance criteria are checked |
| ::test_external_identity_provider_login_and_key_creation | 5 external IdP login + key creation | REAL | It sets `AITenant.spec.oidc` on the default tenant (`T:282-303`), gets a Keycloak password-grant token (`T:243-268`), and asserts that key creation with that token returns 201 with `key`/`id` and that revoking it returns 200 (`T:668-684`). The controller builds the OIDC rule from `AITenant.spec.oidc` (`aitenant_types.go:67-71`). It nearly duplicates the suite's `oidc_tests/test_oidc_token_flow.py:31-43`, whose fixture does the same patch (`oidc_tests/conftest.py:144-186`). The plan's coverage note missed that test and cited only the config-retention test |
| ::test_shared_model_access_follows_grant | 6 granted tenant sees and uses shared model | WRONG | The fixture `qf_shared_model_stack` waits for the new MaaSModelRef to be `Ready=True` (`T:382`) before `qf_shared_model_governance` creates its auth policy and subscription (`T:393-431`, which depends on the stack). An ungoverned modelRef never reports Ready (`maasmodelref_types.go:106`, `maasmodelref_controller.go:274-281, 443-457`), so setup times out after 300 s on every run. It is also not shared: the ExternalModel is attached to tenant A's gateway only (`T:170`). The shipped sharing case is one model with `gatewayRefs` to both tenant gateways plus a modelRef per tenant with `tenantRef` (`maas:test/e2e/tests/test_tenant_external_model_shared.py:183-205`). The listing and inference checks after that point use real names: alias = `spec.modelName` (`providers_external.go:424-444`), the `/{ns}/{model}/anything/{tag}` path, and the echo check |
| ::test_ungranted_tenant_cannot_discover_shared_model | 7 ungranted tenant cannot see or invoke it | WRONG | It hangs on the same `T:382` wait (setup only). It then expects 401/403 (`T:766-772`, with `CROSS_TENANT_INFERENCE_REJECTED_STATUSES = {401, 403}` at `M/multitenancy/utils.py:68`) from tenant B's gateway for a path that has no HTTPRoute there. The product's own test of this exact setup, a model attached to one tenant's gateway and requested through the other's, asserts only "not served". It lists 401/403/404 as the expected refusals, 404 being "no route" (`test_tenant_external_model_attachment.py:121-129, 210-232`). It notes that a cross-tenant 401/403 proves anything only when both tenants authorize the model (`test_tenant_external_model_shared.py:271-276, 311-315`). The model-list exclusion check (`T:748-756`) is fine |
| ::test_tenant_usage_monitoring_filters_isolate_data | 10 usage attributed and filterable by tenant | WEAK | It drives inference on both tenants. It then asserts only positive `authorized_calls_total{subscription=…}` and positive Loki counts per tenant subscription (`T:810-832`), plus two dashboards existing by name (`T:816-818`). The names are real: `usage-dashboard.yaml:96`, `usage-logs-admin-dashboard.yaml:17`, `usage-logs-dashboard.yaml:16`, Loki `subscription` label `usage-logs-admin-dashboard.yaml:63-65`. It never checks that one tenant's filter excludes the other's records. It never touches the shipped tenant attribution, `service.namespace` = tenant namespace (`tenant_usage_logs_envoyfilter.go:189-193`). It checks nothing on the dashboard rows. The case asks for "each filter returns only its tenant's usage records" |
| ::test_independent_tenant_rate_limit_enforcement | 11 tenant rate limits independent | REAL | It creates 30 vs 10000 tokens/min subscriptions in each tenant namespace on the tenant-local model (`T:541-574`; `tokenRateLimits` at `M/maas_subscription/utils.py:215-221`) and binds keys to them (`T:577-609`). It asserts tenant A goes 200 then 429 (`assert_mixed_200_and_429`, `M/utils.py:451-475`) and tenant B still gets 200 afterwards (`T:849-875`). This is the case's exact pass condition |
| ::test_tenant_isolation_after_platform_upgrade | 13 tenants Ready + isolated after upgrade | WEAK | It is marked `post_upgrade` (`T:878`) but uses the class's fresh isolation fixtures (`M/multitenancy/conftest.py:176-191, 214`). In a post-upgrade run those tenants are created after the upgrade, so it never checks that tenants from before the upgrade survived. The body repeats `inference/test_tenant_model_inference.py:44-78` (Ready, own 200, cross 401/403, `T:893-915`). The suite's real pre/post pair, with persisted tenant records, is `M/upgrade/test_maas_multitenant_upgrade.py:56-336` |
| TestQFRhairfe1487Documentation::test_documentation_covers_tenant_workflows | 12 docs cover onboarding, BYOIDP, shared-model governance | WEAK | Keyword checks only: "AITenant" in `multi-tenant-setup.md`, "oidc" in `external-oidc.md`, "ExternalModel" in `external-model-setup.md`, plus the CRD existing (`T:930-940`). The case asks for concrete, current steps. The chosen shared-model page covers no tenant sharing: it never mentions `tenantRef` or `gatewayRefs`, which appear only in `multi-tenant-setup.md` and the CRD reference. It skips unless the QF-only `SOURCE_REPO_PATH` env var is set (`T:921-924`), so it never runs in the team's CI |

Tally: 8 tests: REAL 3, WEAK 3, HOLLOW 0, WRONG 2.

Loads: the mechanical check collected 8 tests (loading/RHAIRFE-1487.md: 7 run through setup-plan with 1 skipped, the docs test; 1 deselected by the suite's upgrade gating, `odh:conftest.py:290-335`). All 8 resolve. **loads=6.** The two shared-model tests would not get past setup (the `T:382` wait above), the same rule as the request.param precedent. The docs test loads but always skips without `SOURCE_REPO_PATH`.

## 2. not_implemented (0)

None. `not_implemented: []` (O/python-tests/summary.yaml). declined=0.

## 3. existing_coverage (5 EXISTING_COVERAGE scenarios)

| scenario | named test | class | evidence |
|---|---|---|---|
| 1 tenant provisioning creates isolated environment | `M/multitenancy/aitenant/test_tenant_setup.py::test_aitenant_bootstrap_creates_tenant_environment` | VERIFIED | `:34-44` → `verify_aitenant_ready` (Ready + phase Active, `M/utils.py:1069-1074`) and `verify_aitenant_bootstrap_children` (`aitenant/utils.py:185-284`). Together they check `status.gatewayRef`, `status.tenantNamespace`, the namespace's labels and annotations, the Gateway class and Programmed state, and `MaasTenantConfig/default-tenant` Ready. That matches the plan's stated coverage and the shipped bootstrap (`aitenant_controller.go:159-282`: namespace, gateway claim, tenant config, admin RBAC, phase Active) |
| 2 API keys tenant-isolated | `M/multitenancy/isolation/test_auth_isolation.py::test_get_api_key_from_other_tenant_gateway_not_found` + `::test_search_in_tenant_does_not_return_other_tenant_keys` | VERIFIED | `:93-113`: A's key fetched via B returns 404. `:120-149`: search via A includes A's key and excludes B's. Shipped: `user.Tenant != key.Tenant` (`maas-api/internal/api_keys/handler.go:321`) and tenant-filtered search (`store_postgres.go:259, 378`) |
| 3 cross-tenant inference rejected | `M/multitenancy/inference/test_tenant_model_inference.py::test_tenant_a_key_on_tenant_b_gateway_rejected` | VERIFIED | `:63-78`: A's key on B's gateway gets 401/403 (`M/multitenancy/utils.py:211-242`). The own-gateway 200 control is in the same class (`:44-60`). Shipped key lookup is tenant-scoped (`store_postgres.go:642`) |
| 8 tenant cleanup preserves namespace | `M/multitenancy/aitenant/test_cleanup.py::test_aitenant_deletion_cleans_up_children_and_preserves_namespace` | VERIFIED | `:36-57`: delete and wait; then MaasTenantConfig and RBAC children removed with the pre-provisioned Gateway kept (`aitenant/utils.py:692-728`), the namespace kept, and ownership metadata stripped (`:663-689, 731-743`). That is the case's stated outcome. Shipped delete path: `aitenant_controller.go:1003-1092`. API-key revocation (`:1022-1040`) is implied by the AITenant going away, since the finalizer is held until keys are revoked, but it is not asserted directly |
| 9 missing/invalid/forged credentials denied | `M/multitenancy/security/test_tenant_gateway_negative_security.py` (3 named tests) | VERIFIED | Missing key (`:54-79`), invalid `sk-oai-` key (`:81-109`) and 5 forged `X-MaaS-*` headers with a valid-key 200 control (`:111-163`). Each must get 401/403 on both tenant gateways |

Totals: 5 claims: 5 VERIFIED, 0 PARTIAL, 0 FALSE. Not counted, from the PARTIAL_COVERAGE scenario 5: `test_aitenant_oidc_stays_in_aitenant_spec` exists (`aitenant/test_bootstrap_features.py:70`) and checks config retention only, as the plan says.

## 4. The plan

13 scenarios, all mapped to the 8 ACs plus credential denial, rate limits and upgrade.

**One scenario expects behaviour the shipped code lacks.** Scenario 10 wants "each tenant filter returns only that tenant's metrics, dashboard rows, and logs". The usage dashboards have no tenant variable: their variables are user, subscription, model, api_key and view_by (`usage-logs-admin-dashboard.yaml:30-118`). Tenant attribution exists only as the logs' `service.namespace` (`tenant_usage_logs_envoyfilter.go:189-193`).

AC-1's "operator creates … gateway" is not shipped either: the Gateway is admin-provisioned (`aitenant_types.go:63-65`), and activation fails with `GatewayCheckFailed` without it (`aitenant_controller.go:225-231`). The plan's scenario 1 follows the shipped behaviour, so it is not counted.

Scenario 4 handles the "months/years" conflict honestly: it tests the 90-day boundary and flags the gap (std yaml :119-123, :207-208).

Shipped behaviour the plan misses:
- API-key revocation on tenant delete (`aitenant_controller.go:1022-1040, 1265-1316`).
- Rejection of keys longer than the cap (`service.go:139-142`).
- The `GatewayCheckFailed` path (`aitenant_controller.go:225-231`).
- The tenantRef-ambiguity failure for a model attached to two gateways (`maasmodelref_types.go:49-58`; product e2e `TestSharedModelAmbiguousModelRef`).
- Per-tenant quota isolation on a shared model (`test_tenant_external_model_shared.py:1-16`).

## 5. Acceptance criteria (O/stp/RHAIRFE-1487_jira_data.yaml, 8 items)

| AC | text (short) | status | plan scenario |
|---|---|---|---|
| AC-1 | one CR provisions tenant: namespace, gateway, identity, policies | COVERED | TS-001 (existing coverage; the shipped gateway is pre-provisioned) |
| AC-2 | tenants cannot discover or access other tenants' models, keys, usage | COVERED | TS-002, TS-003, TS-007, TS-010 |
| AC-3 | long-lived (months/years) keys scoped to the tenant | COVERED | TS-004 (90-day shipped cap, conflict flagged) |
| AC-4 | Bring Your Own IDP | COVERED | TS-005 |
| AC-5 | shared foundation models granted per tenant across tenant gateways | COVERED | TS-006, TS-007 |
| AC-6 | tenant CR deletion cleans up tenant-owned resources | COVERED | TS-008 |
| AC-7 | observability attributes and filters usage per tenant | COVERED | TS-010 |
| AC-8 | docs: onboarding, BYOIDP, shared-model governance | COVERED | TS-012 |

SCORE RHAIRFE-1487 | QF tests=8 real=3 weak=3 hollow=0 wrong=2 loads=6 declined=0 justified=0 avoidable=0 cases=13 real_cases=3 covered=5 verified=5 partial=0 false=0 plan_wrong=1 acs=8 ac_covered=8 ac_out_of_scope=0 ac_missed=0
