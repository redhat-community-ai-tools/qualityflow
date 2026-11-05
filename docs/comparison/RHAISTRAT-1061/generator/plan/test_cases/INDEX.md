# Test Cases — OGXServer Runtime Config

**Test Plan**: [../TestPlan.md](../TestPlan.md)

**Total: 44 test cases** — P0: 35, P1: 8, P2: 1 (configgen CLI — no TC)

---

## TC-SCHEMA — CRD Schema Validation (4 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-SCHEMA-001](TC-SCHEMA-001.md) | Valid provider config accepted | P0 |
| [TC-SCHEMA-002](TC-SCHEMA-002.md) | Missing required fields rejected | P0 |
| [TC-SCHEMA-003](TC-SCHEMA-003.md) | Invalid provider type rejected | P0 |
| [TC-SCHEMA-004](TC-SCHEMA-004.md) | CEL validation — MinItems/MaxItems | P0 |

## TC-WEBHOOK — Admission Webhook (1 case)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-WEBHOOK-001](TC-WEBHOOK-001.md) | Webhook rejects MinItems violation | P0 |

## TC-MERGE — Config Merge Logic (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-MERGE-001](TC-MERGE-001.md) | Provider merge — whole-API-type replacement | P0 |
| [TC-MERGE-002](TC-MERGE-002.md) | Partial storage override (Blocked) | P1 |
| [TC-MERGE-003](TC-MERGE-003.md) | disabledAPIs removes capabilities | P0 |

## TC-RENDER — ConfigMap Rendering (2 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-RENDER-001](TC-RENDER-001.md) | Immutable ConfigMap created with hash | P0 |
| [TC-RENDER-002](TC-RENDER-002.md) | Config change creates new ConfigMap | P0 |

## TC-ROLLOUT — Pod Rollout (1 case)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-ROLLOUT-001](TC-ROLLOUT-001.md) | Config change triggers rolling update | P0 |

## TC-OCI — OCI Label Loading (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-OCI-001](TC-OCI-001.md) | Base config loaded from OCI labels | P0 |
| [TC-OCI-002](TC-OCI-002.md) | Embedded config fallback | P1 |
| [TC-OCI-003](TC-OCI-003.md) | OCI label format validation | P1 |

## TC-OVERRIDE — overrideConfig Precedence (1 case)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-OVERRIDE-001](TC-OVERRIDE-001.md) | overrideConfig takes precedence | P0 |

## TC-SECRET — SecretKeyRef Auto-Injection (4 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-SECRET-001](TC-SECRET-001.md) | VLLM apiToken SecretKeyRef injection | P0 |
| [TC-SECRET-002](TC-SECRET-002.md) | pgvector password SecretKeyRef injection | P0 |
| [TC-SECRET-003](TC-SECRET-003.md) | Multiple providers, different Secrets | P0 |
| [TC-SECRET-004](TC-SECRET-004.md) | Secret missing ogx.io/watch label | P0 |

## TC-BASECONFIG — Base Config Resolution (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-BASECONFIG-001](TC-BASECONFIG-001.md) | baseConfig precedence over OCI labels | P0 |
| [TC-BASECONFIG-002](TC-BASECONFIG-002.md) | Missing baseConfig ConfigMap — terminal error | P0 |
| [TC-BASECONFIG-003](TC-BASECONFIG-003.md) | baseConfig alone has no effect | P1 |

## TC-LIFECYCLE — ConfigMap Lifecycle (2 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-LIFECYCLE-001](TC-LIFECYCLE-001.md) | ConfigMap reused when spec unchanged | P0 |
| [TC-LIFECYCLE-002](TC-LIFECYCLE-002.md) | Old ConfigMaps cleaned up (retention=2) | P0 |

## TC-CEL — CEL Mutual Exclusivity (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-CEL-001](TC-CEL-001.md) | overrideConfig + providers rejected | P0 |
| [TC-CEL-002](TC-CEL-002.md) | overrideConfig + disabledAPIs rejected | P0 |
| [TC-CEL-003](TC-CEL-003.md) | overrideConfig + baseConfig rejected | P0 |

## TC-ADOPT — Legacy Resource Adoption (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-ADOPT-001](TC-ADOPT-001.md) | Annotation-driven PVC adoption | P0 |
| [TC-ADOPT-002](TC-ADOPT-002.md) | PVC orphaned on CR deletion | P1 |
| [TC-ADOPT-003](TC-ADOPT-003.md) | Invalid annotations don't disrupt | P1 |

## TC-UPGRADE — Migration (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-UPGRADE-001](TC-UPGRADE-001.md) | Full 3.4 to 3.5 upgrade workflow | P0 |
| [TC-UPGRADE-002](TC-UPGRADE-002.md) | Workload continuity during upgrade | P0 |
| [TC-UPGRADE-003](TC-UPGRADE-003.md) | v1alpha1 API rejected after upgrade | P0 |

## TC-PROVIDER — Provider Expansion (2 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-PROVIDER-001](TC-PROVIDER-001.md) | VLLM inference provider | P0 |
| [TC-PROVIDER-002](TC-PROVIDER-002.md) | Bedrock with session token/role ARN | P1 |

## TC-STORAGE — Storage Backend (1 case)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-STORAGE-001](TC-STORAGE-001.md) | Postgres storage backend | P0 |

## TC-NEG — Validation Gap Tests (3 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-NEG-001](TC-NEG-001.md) | Unknown storage type defaults silently | P0 |
| [TC-NEG-002](TC-NEG-002.md) | Invalid disabledAPIs silently ignored | P0 |
| [TC-NEG-003](TC-NEG-003.md) | Provider merge replaces entire block | P0 |

## TC-NETPOL — NetworkPolicy (1 case)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-NETPOL-001](TC-NETPOL-001.md) | NetworkPolicy per-CR toggle | P1 |

## TC-E2E — End-to-End Scenarios (4 cases)

| Test Case | Title | Priority |
| --- | --- | --- |
| [TC-E2E-001](TC-E2E-001.md) | Declarative config to running server | P0 |
| [TC-E2E-002](TC-E2E-002.md) | overrideConfig to running server | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Full upgrade journey | P0 |
| [TC-E2E-004](TC-E2E-004.md) | Legacy adoption journey | P0 |
