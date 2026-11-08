# RHAIRFE-1487 — QualityFlow round 6

Method: round-2 `neutral/part2.md`, same 17 requirements; prior figures copied from that file and round-4 `score-part2.md`. Round 6 has **33 STD scenarios, all NEW**. Correctness reference: shipped models-as-a-service **2d4ad1e**, tests **c9ce889**. Redundancy reference: pre-feature tests snapshot **462fdaa** (product snapshot **d98eeb5**). No runtime tests executed.

| metric | generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1. Wrong / total | 22/27 | 0/29 (1/29 strict) | **33/33** |
| 2. Redundant new / total | 10/27 (+4 partial overlaps) | 0/29 | **0/33** (partial overlaps below) |
| 3. Requirements covered / total | 12/17 | 12/17 (11 strict) | **10/17** |
| 4. Runnable as written / after TBDs / evaluated | 1/10 sampled; after-TBD figure not separately reported | 3/3/10 sampled (full scan 5/5/29) | **0/0/10 sampled** |
| 5. Verified problems found | 0 | 8 | **5** |

Metric 1 evidence: Every scenario, TS-001–033, explicitly supplies `test_data.resource_definitions[].type: Tenant`, linked to `TenantKind`, and `tenant_resource_name: default-tenant`; these are concrete inputs, outside the TBD strings (first instance: STD lines 235–243). They carry the old singleton resource into independent-tenant acceptance cases, including onboarding, identity, deletion and documented workflows.
Shipped tenant bootstrap/lifecycle uses **AITenant**, with **MaasTenantConfig/default-tenant** as its runtime config (`docs/content/reference/crds/ai-tenant.md:3–9,30–34`). Legacy `Tenant` remains registered for migration, not as the independent-tenant bootstrap contract (`maas-controller/api/maas/v1alpha1/tenant_types.go:25–42`). Thus this is a wrong resource role, not a claim that the string or legacy type vanished. Count each affected scenario once, as the earlier rounds counted wrong kinds/precondition inputs.
The shared-model grant contract is TBD and the feature has not shipped; no additional correctness penalty for that ticket-reference intent. Unnamed tenant selectors and usage interfaces are unverified, not additional errors. `design_only: true` does not exempt concrete test inputs from metric 1.

Metric 2 evidence: Compared all NEW scenario objectives with snapshot `tests/model_serving/maas_billing/`; the snapshot has no independent multi-tenant suite. Later `multitenancy/` tests at c9ce889 are not eligible duplicates.
Partial overlaps, not counted under the same tenant-scope treatment used in round 4: TS-013 versus `maas_api_key/test_api_key_expiration.py:59,90` (one suite-wide limit, not two tenant-specific limits); TS-014 versus `test_api_key_gateway_rejection.py:test_revoked_key_rejected_at_inference` (default-tenant inference, not shared-model tenant access).
TS-015 overlaps `oidc_tests/test_oidc_model_access.py:test_oidc_key_lists_models_and_runs_inference`; TS-005/012 overlap `test_oidc_multi_user.py:test_api_key_isolation_between_users`. These existing tests do not establish independent tenant-scoped keys/providers. TS-007 adds tenant-selector behavior beyond the snapshot's tampered-token rejection. No complete duplicate credited.

Metric 3 evidence: Covered: **A1** TS-001/004 (onboarding with prepared gateway; automatic gateway creation explicitly unresolved), **A2a** TS-008/009, **A2b** TS-012, **A2c** TS-010, **A3** TS-011/013/014, **A4** TS-005/006/015–017, **A5** TS-018–020, **A6** TS-024–026, **A7** TS-027–029, **A8** TS-030/031. Wrong cases still receive coverage credit.
Absent: **S1** labelled-namespace reconciliation; **S2** tenant context in generated policies; **S3** api_keys tenant column; **S4** mint/validate tenant and ValidationResult; **S5** subscription tenant/select; **S6** unsupported-namespace MaaS webhook; **keys soft-deleted on tenant deletion**. TS-023 tests quota collision, not the subscription selection contract; TS-024 never asserts key invalidation or soft deletion.
Round 4's generous S2 credit relied on its authorization/cache-decision scenario and explicit `gatewayAuthzCacheKeySelector` analysis. Round 6's username/model/key-inventory checks do not explicitly target generated policy tenant context. Generic cleanup and per-test key revocation are not deletion-triggered key cleanup coverage.

Metric 4 evidence: **random.seed(1487)**, `random.sample(range(1,34),10)` over sorted test IDs gives **001,003,004,005,006,007,012,015,021,026**. All ten are non-runnable and none becomes runnable solely by answering TBDs.
Examples: TS-001 says “Apply the tenant onboarding request” without a manifest; TS-012 says “Send key list, lookup and revoke requests” without requests; TS-021 gives no quota configuration/traffic recipe; TS-026 gives no interruption/recovery commands. Setup is prose throughout, and the concrete resource inputs also require correction. No correct EXISTING mappings rescue the sample.

Metric 5 evidence: **Two conflicts raised by QF and verified:** STP I.2 explicitly contrasts automatic gateway creation with existing-gateway prerequisites, and complete cleanup with preserved namespace/user data. Shipped `concepts/multi-tenancy.md:55` requires a pre-created Gateway; `reference/crds/ai-tenant.md:32` preserves namespace and Gateway.
**Three untested shipped behaviors:** cross-tenant catalog filtering (TS-008), independent external-provider end-to-end isolation (TS-005/006/017), and tenant usage attribution (TS-027–029). QF labels these NEW and says “all tenant-specific gaps remain NEW” (regression analysis limitations). Snapshot tests lack these behaviors; the shipped tests still lack cross-tenant catalog assertions, OIDC bootstrap checks only config placement (`multitenancy/aitenant/test_bootstrap_features.py:70`), and tenant-labelled metrics have product unit coverage (`maas-api/internal/metrics/middleware_tenant_test.go:17–43`) but no corresponding deployed multi-tenant observability test.
Not credited: missing shared-model grants (QF never identifies them as unimplemented), year-lived-key conflict (only an unresolved lifetime question), deletion-triggered key revocation, or gateway-reuse rejection. Those latter two round-4 findings are not identified here. No existing-test defect is raised.

`lsp_status: partial` (`stp/RHAIRFE-1487_regression_analysis.yaml:1`). QF states: “SOURCE_REPO_PATH has no registered LSP server; used text search.” Tests-server definitions/references worked; no call-hierarchy API was available.

Solution exposure: **No affirmative sign found in the STP/STD.** QF says “The checked-out implementation is a configuration singleton; it does not establish all requested multi-tenant capabilities” (STP I.1), and records snapshot commits d98eeb5 / 462fdaa with empty PR details. Its quoted source constant `TenantKind = Tenant` at `tenant_types.go:25` matches the old snapshot exactly; shipped code instead calls it deprecated at lines 25–26. Prepared gateways and namespace retention were already in the snapshot/Jira clarification, so those accurate observations do not demonstrate solution access.

SUMMARY | RHAIRFE-1487 | wrong 33/33 | redundant 0/33 | covered 10/17 | runnable 0/10 | problems 5
