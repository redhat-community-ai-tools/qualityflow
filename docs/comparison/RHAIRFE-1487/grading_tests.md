# RHAIRFE-1487 run 5 (both tools on GLM 5.3): test grading

Product: models-as-a-service at 05a5ff90 (cited `MaaS:<path>:<line>`). Suite: opendatahub-tests at 7ffaacc (cited `ODH:<path>:<line>`; `M/` = `tests/ai_gateway/models_as_a_service/`).

What shipped:
- One AITenant per tenant, each with its own Gateway, tenant namespace and per-tenant maas-api (`TENANT_NAME` = the AITenant name, MaaS:maas-controller/pkg/platform/tenantreconcile/params.go:1007-1019).
- MaaS CRs are admitted in a namespace that has a MaasTenantConfig (MaaS:maas-controller/pkg/webhook/tenant_namespace_validator.go:40-67).
- The suite already has two-tenant fixtures and helpers for all of this (ODH:M/multitenancy/conftest.py, M/multitenancy/utils.py, M/multitenancy/aitenant/utils.py).

Loading (mechanical, re-run with `pytest --setup-plan`): QF 9/9 load, GEN 27/27 load. This time both tools placed their tests where the suite's fixtures resolve.

Separate from loading, I checked every call to a suite helper against its signature, with the same script for both tools. QF has no mismatch. GEN calls `isolation_tenant_api_key_id` / `isolation_tenant_api_key_plaintext` with `subscription=`, but both take `subscription_name` (ODH:M/multitenancy/utils.py:496-500, :532-536). Those 9 tests raise TypeError before sending any request. I class them WRONG. Four of them would be REAL by content: APIKEY-004 and ISO-001/002/003.

## QualityFlow tests (9, M/multitenancy/qf/test_qf_rhairfe_1487.py + a conftest with 2 fixtures)

| test | plan case | class | evidence |
|---|---|---|---|
| ::TestQFRHAIRFE1487MultiTenant::test_tenant_onboarding_creates_isolated_usable_service | 1 | REAL | Both AITenants Ready, with their bootstrap children (namespace, Gateway, MaasTenantConfig) verified. Tenant A inference through its own gateway returns 200 (test:70-82). "Does not return B's private model" is not checked |
| ::test_concurrent_tenant_onboarding_keeps_settings_separate | 4 | WEAK | Checks only that the two contexts have distinct namespaces and gateway refs, plus their children (test:95-104). The fixture onboards the tenants one after the other (ODH:M/multitenancy/conftest.py:312), not concurrently, and no traffic is sent to either gateway |
| ::test_private_model_access_from_another_tenant_is_denied | 9 | REAL | Tenant A's key on tenant B's inference URL must get 401/403 (ODH:M/multitenancy/utils.py:211-224). Only one direction of the plan's two |
| ::test_another_tenant_cannot_read_private_usage_data | 10 | WRONG | maas-api has no usage-read route (MaaS:maas-api/cmd/main.go:331-387). The test instead does GET /v1/api-keys/{id} for A's key through B (main.go:365) and expects 404. That is foreign key lookup (case 12), not usage data |
| ::test_cross_tenant_key_discovery_and_management_are_denied | 12 | WEAK | Only the key search: A's search includes A's key and excludes B's (test:164-182). The plan's foreign lookup and revoke denials, and the unchanged owner inventory, are not tested, although `revoke_api_key` exists (ODH:M/utils.py:798) |
| ::test_tenant_key_lifetime_accepts_limit_and_rejects_excess | 13 | REAL | A key at 90×24h is created, and one at 91×24h gets 400 with "exceeds maximum". This matches `DefaultAPIKeyMaxExpirationDays = 90` (MaaS:maas-api/internal/constant/const.go:26) and the check at MaaS:maas-api/internal/api_keys/service.go:134-142. It covers tenant A only, at the default limit |
| ::test_tenant_deletion_leaves_other_tenant_serving_models | 25 | REAL | Deletes AITenant A and waits, then tenant B inference must return 200 (test:251-259). "During deletion" is not sampled, only after it |
| ::TestQFRHAIRFE1487GatewayPrerequisite::test_missing_gateway_prevents_successful_tenant_activation | 3 | REAL | The new fixture creates the AITenant without its bootstrap Gateway (qf/conftest.py:21-37). The test waits for phase `Failed` with Ready reason `GatewayCheckFailed`, which the controller sets when the Gateway is missing (MaaS:maas-controller/pkg/controller/maas/aitenant_controller.go:225-227, :422-423) |
| ::TestQFRHAIRFE1487TenantDeletion::test_tenant_removal_cleans_managed_resources_and_preserves_user_data | 24 | REAL | Deletes the AITenant, then checks that controller children are removed, the tenant namespace is preserved, and AITenant metadata is stripped (test:299-312). The plan's user-data hashes are not checked. It duplicates ODH:M/multitenancy/aitenant/test_cleanup.py:36 |

## QualityFlow declines (`not_implemented`, 24)

The verdicts follow run 4 (score-tests-run4/RHAIRFE-1487.md). I re-checked each one against the run-5 reasons and checkouts.

| plan case | class | evidence |
|---|---|---|
| 5, 6, 16 (identical usernames across tenant IdPs, foreign IdP tokens, wrong issuer/audience) | JUSTIFIED (3) | ODH has one Keycloak realm and client (M/oidc_tests/conftest.py), so it cannot provide two IdPs or a validly signed token from a second issuer |
| 18, 21, 22, 23 (one model shared across tenant gateways; quotas on it) | JUSTIFIED (4) | No fixture serves one model through two tenant gateways. Per-tenant rate limiting exists only on per-tenant models (ODH:M/upgrade/utils.py:1463) |
| 26 (interrupted deletion resumes) | JUSTIFIED | Nothing can stop a deletion part-way |
| 27, 28 (metrics/Perses/Loki attribution, tenant filter) | JUSTIFIED (2) | The outcome includes Perses dashboards, which the suite cannot read |
| 30, 31 (documented workflows, docs on denied sharing) | JUSTIFIED (2) | Documentation conformance, not product behaviour (30 also needs the shared model) |
| 2 (unauthorized provisioning denied) | AVOIDABLE | `unprivileged_client` (ODH:tests/conftest.py:479) plus `aitenant_from_spec` (ODH:M/utils.py:977) make an RBAC denial on create directly testable |
| 7 (forged tenant identity rejected) | AVOIDABLE | Tampered-token checks (M/oidc_tests/test_oidc_token_flow.py) and tenant-gateway negative tests (M/multitenancy/security/) exist |
| 8 (discovery lists only authorized models) | AVOIDABLE | QF's reason (both tenants get the same model name) is answered by `provision_tenant_model` (ODH:M/multitenancy/utils.py:871), which creates an A-only model. Per-tenant GET /v1/models is in the fixtures |
| 11 (long-lived key outlives login) | AVOIDABLE | Mint a key from a short-lived OIDC token (M/oidc_tests/conftest.py). Validate checks only the key (MaaS:maas-api/internal/api_keys/handler.go:666-707) |
| 14 (revoked key denied on a model) | AVOIDABLE | `revoke_api_key` (ODH:M/utils.py:798) plus the revoked-key rejection pattern (M/oidc_tests/test_oidc_model_access.py). Revocation does not depend on the model being shared |
| 15 (external user gets a key and uses a model) | AVOIDABLE | The OIDC key and inference fixtures exist (M/oidc_tests/conftest.py, test_oidc_model_access.py) |
| 17 (IdP change leaves other tenants usable) | AVOIDABLE | `spec.oidc` is mutable (MaaS:maas-controller/api/maas/v1alpha1/aitenant_types.go:71), and tenant B can be checked with the existing inference fixtures |
| 19, 20 (ungranted tenant denied, grant removal ends access) | AVOIDABLE (2) | A tenant-local model plus `make_tenant_model_accessible` (ODH:M/multitenancy/utils.py:982) grants access (auth policy and subscription), and exiting it removes the grant |
| 29 (simultaneous traffic keeps separate usage totals) | AVOIDABLE | Usage logs carry the tenant workload namespace (MaaS:maas-controller/pkg/platform/tenantreconcile/usage_logs_envoyfilter.go:31-35), and ODH has usage-logging helpers (tests/ai_gateway/models_as_a_service/observability/utils.py) |
| 32, 33 (upgrade keeps identities, keys, grants and cross-tenant denials) | AVOIDABLE (2) | QF says no such upgrade fixture exists. It does: ODH:M/upgrade/test_maas_multitenant_upgrade.py:57-285, with pre/post cross-tenant key and inference rejection at :79, :122, :267 |

Totals: 12 JUSTIFIED, 12 AVOIDABLE.

## Test Plan Generator tests (27, tests/maas_multi_tenancy/)

This run the tests re-export the suite's MaaS conftests (conftest.py:1-3) and use its real fixtures and helpers. Most of the run-3 inventions are gone. What remains is the plan's own premises: the `X-MaaS-Tenant` header, the `apiKey` body, 401/403 status codes, and label-gated admission.

| test | plan case | class | evidence |
|---|---|---|---|
| test_apikey_…::test_tc_apikey_001 | TC-APIKEY-001 | REAL | Creates a key in tenant A, reads it back, and asserts `tenant` equals the AITenant name. The store returns the column (MaaS:maas-api/internal/api_keys/store_postgres.go:546-565). Its value is the AITenant name (aitenant_controller.go:1875, params.go:1019). It reads through the API instead of the plan's SQL |
| ::test_tc_apikey_002 | TC-APIKEY-002 | WRONG | TypeError at the helper call (`subscription=`, see above). It also sends `{"apiKey": …}`, but validate binds `key` (MaaS:maas-api/internal/api_keys/handler.go:661-663, so 400), and it expects `userID` and `modelRef`, which ValidationResult does not have (`userId`, no modelRef: api_keys/types.go:41-49) |
| ::test_tc_apikey_003 | TC-APIKEY-003 | WRONG | TypeError at the helper call. It also expects 401, but validate returns 200 `{valid:false}` for a bad key (handler.go:695-702), and the body field is wrong |
| ::test_tc_apikey_004 | TC-APIKEY-004 | WRONG | TypeError: `isolation_tenant_api_key_id(subscription=…)` takes `subscription_name` (ODH:M/multitenancy/utils.py:496-500). By content it would be REAL: A's search includes A's key and excludes B's |
| test_cleanup_…::test_tc_cleanup_001 | TC-CLEANUP-001 | REAL | Deletes the AITenant, then checks that children are removed, the namespace is preserved, and metadata is stripped. It follows the shipped behaviour (the namespace is kept), not the plan's "namespace deleted" |
| ::test_tc_cleanup_002 | TC-CLEANUP-002 | WEAK | After A is deleted, it checks only that AITenant B is Ready, B's namespace is Active, and the default tenant is unaffected. The plan's B subscription/auth policy Ready and the B key still working are not checked |
| test_contract_…::test_tc_contract_001 | TC-CONTRACT-001 | WRONG | Sends `{"model": …}` without `username`. Select answers 200 with `bad_request` "username is required" (MaaS:maas-api/internal/subscription/handler.go:96-101; the field is `requestedModel`, types.go:24-26), so `name` is absent |
| ::test_tc_contract_002 | TC-CONTRACT-002 | WRONG | TypeError at the helper call. It also expects 403, but select returns every error as HTTP 200 (subscription/handler.go:136) |
| test_ctrl_…::test_tc_ctrl_001 | TC-CTRL-001 | REAL | A discovery-labelled namespace (with MaasTenantConfig) gets a subscription that acquires the finalizer and reaches a reconciled phase. This matches ODH:M/multitenancy/aitenant/test_tenant_namespace_discovery.py:75. The plan's label name is replaced by the suite's real discovery labels |
| ::test_tc_ctrl_002 | TC-CTRL-002 | REAL | In an unlabelled namespace the subscription is admitted but stays unreconciled (no finalizer for 60 s), as at test_tenant_namespace_discovery.py:150 |
| ::test_tc_ctrl_003 | TC-CTRL-003 | REAL | Three labelled namespaces, and each subscription reconciles. Cross-tenant interference is not checked |
| test_e2e_…::test_tc_e2e_001 | TC-E2E-001 | WRONG | TypeError at the helper call. It also validates with `{"apiKey": …}` (handler.go:661-663 binds `key`, so 400) and expects 200 |
| ::test_tc_e2e_002 | TC-E2E-002 | WRONG | TypeError at the helper call. Its last step also expects the webhook to reject a subscription in a namespace that has a MaasTenantConfig (created by `synthetic_discovery_tenant_namespace`, ODH:M/multitenancy/aitenant/utils.py:1056-1066). The validator admits it (tenant_namespace_validator.go:49-51), as GEN's own CTRL-002 relies on |
| test_iso_…::test_tc_iso_001 | TC-ISO-001 | WRONG | TypeError at the helper call. By content it would be REAL: tenant A's /v1/models subscriptions equal only A's subscription (MaaS:maas-api/internal/handlers/models.go:325-343) |
| ::test_tc_iso_002 | TC-ISO-002 | WRONG | TypeError at the helper call. By content REAL: A's key on B's inference URL gets 401/403 |
| ::test_tc_iso_003 | TC-ISO-003 | WRONG | TypeError at the helper call. By content REAL: A's key search excludes B's key |
| ::test_tc_iso_004 | TC-ISO-004 | WEAK | Patches A's subscription, then immediately reads B's `spec` limit (test:160-173). The controller never writes B's spec, so the check is vacuous. No reconcile wait and no effective-limit check |
| test_policy_…::test_tc_policy_001 | TC-POLICY-001 | REAL | The tenant gateway AuthPolicy reconciled from the MaaSAuthPolicy exists, is Accepted, and its callback targets the per-tenant maas-api (ODH:M/multitenancy/utils.py:630-660). The plan's "shared Gateway" is replaced by the shipped per-tenant gateway |
| ::test_tc_policy_002 | TC-POLICY-002 | WRONG | Patches `subjects` and expects the gateway AuthPolicy's resourceVersion to change. Subjects go only into the per-model AuthPolicies (MaaS:maas-controller/pkg/controller/maas/maasauthpolicy_controller.go:1724-1731), not the gateway singleton (:482-484). The wait also returns at once (already Accepted) |
| ::test_tc_policy_003 | TC-POLICY-003 | WRONG | Expects the gateway AuthPolicy to be removed when the MaaSAuthPolicy is deleted. The controller resets it to the default-deny base instead (maasauthpolicy_controller.go:1892-1947) |
| test_prov_…::test_tc_prov_001 | TC-PROV-001 | REAL | AITenant Ready, and the bootstrap children (tenant namespace, Gateway, MaasTenantConfig) are verified |
| ::test_tc_prov_002 | TC-PROV-002 | REAL | The tenant MaaSSubscription reaches condition `Ready=True` (MaaS:maas-controller/pkg/controller/maas/maassubscription_controller.go:1297) |
| ::test_tc_prov_003 | TC-PROV-003 | REAL | The tenant MaaSAuthPolicy reaches `Ready=True` (maasauthpolicy_controller.go:2208) |
| ::test_tc_prov_004 | TC-PROV-004 | WEAK | Patches `spec.oidc` and then asserts it reads back the issuer it just wrote (test:81-88), which is an API-server echo. No reconciled effect is checked |
| test_webhook_…::test_tc_webhook_001 | TC-WEBHOOK-001 | WRONG | Expects rejection in a namespace that has a MaasTenantConfig. The validator admits it (tenant_namespace_validator.go:40-52); the label premise does not exist |
| ::test_tc_webhook_002 | TC-WEBHOOK-002 | WRONG | Same, for MaaSAuthPolicy |
| ::test_tc_webhook_003 | TC-WEBHOOK-003 | REAL | Create in an enabled tenant namespace is admitted with no webhook error (the `with` would raise on rejection) and the resource exists |

## Test Plan Generator skipped plan cases

None: all 27 plan cases have a test function.

SCORE RHAIRFE-1487 | QF tests=9 real=6 weak=2 hollow=0 wrong=1 loads=9 declined=24 justified=12 avoidable=12 cases=33 real_cases=6 | GEN tests=27 real=10 weak=3 hollow=0 wrong=14 loads=27 declined=0 justified=0 avoidable=0 cases=27 real_cases=10
