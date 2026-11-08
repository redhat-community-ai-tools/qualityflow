---
feature: runtime_config_in_crd
strat_key: RHAISTRAT-1061
version: 1.4.0
status: Draft
author: OGX QE
additional_docs:
- https://github.com/ogx-ai/ogx/blob/main/scripts/generate-config-labels.sh
- https://github.com/ogx-ai/ogx-k8s-operator/pull/295
- https://github.com/ogx-ai/ogx-k8s-operator/pull/289
- https://github.com/ogx-ai/ogx-k8s-operator/pull/292
- https://github.com/ogx-ai/ogx-k8s-operator/pull/294
last_updated: '2026-06-16'
reviewers: []
---
# OGXServer Runtime Config Test Plan

**OGX QE – CRD Runtime Configuration Validation**

**Strategy**: [RHAISTRAT-1061](https://redhat.atlassian.net/browse/RHAISTRAT-1061)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates the introduction of declarative runtime configuration for the OGXServer CRD
(`ogx.io/v1beta1`). The feature eliminates the manual ConfigMap workflow where users had to craft a
versioned `config.yaml` and create a ConfigMap themselves. Instead, users declare runtime config
(providers, resources, storage, disabledAPIs) directly on the OGXServer CR, and the operator
generates `config.yaml` into an immutable ConfigMap (`<name>-config-<hash>`), mounts it to the
server pod, and triggers rolling updates on config changes.

Testing focuses on CRD schema validation, config generation pipeline correctness
(OCI label loading, merge logic, provider expansion, storage expansion), legacy resource adoption
from LlamaStackDistribution, upgrade/migration, and known validation gaps identified during code
review (RHAIENG-5697/5698/5699).

### 1.2 Scope

#### In Scope (OGX QE Responsibilities)

- OGXServer CRD (`ogx.io/v1beta1`) with declarative runtime config fields: `spec.providers`,
  `spec.resources`, `spec.storage`, `spec.disabledAPIs`
- CRD validation: required fields, patterns, enums, CEL validations, MinItems/MaxItems on provider
  arrays
- Validating admission webhook (cert-manager + OpenShift webhook support)
- Config generation pipeline: base config loading from OCI labels (`com.ogx.distribution.configs`),
  user override merge, immutable ConfigMap rendering (`<name>-config-<hash>`)
- `spec.overrideConfig` precedence over declarative generation
- Provider expansion: VLLM, OpenAI, VertexAI, Watsonx, Bedrock
  (with per-provider config: TLS, proxy, timeouts, headers, allowed models)
- Storage backends: SQLite, Redis, Postgres
- Legacy resource adoption: annotation-driven adoption of LLSD resources (PVC, Service, Ingress)
  into OGXServer, PVC orphaning (not deleted)
- NetworkPolicy: per-CR toggle via `spec.network.networkPolicy.enabled`
- Upgrade path: LlamaStackDistribution (llamastack.io/v1alpha1) to OGXServer (ogx.io/v1beta1)
- OCI label format validation on distribution images
- Known validation gaps
  (silent defaults, ignored invalid API names, whole-API-type replacement merge)
- Midstream/downstream distribution compatibility
- Safety API removal (confirmed removed in PR #294)

#### Out of Scope (Other Teams)

- Fields outside the supported subset of config.yaml
- Non-standard provider types not enumerated in CRD validation
- Automated rollback
  (rollback path must be documented and tested, but rollback automation is not a deliverable)
- OGX server internal behavior beyond config loading (inference correctness, model serving)
- Documentation content review (handled by CCS team via RHAIENG-2702)
- ODH platform module handler integration (handled by platform team)

### 1.3 Test Objectives

1. Validate OGXServer CRD schema accepts all provider and resource config types and rejects invalid
   provider types, missing required fields, and invalid CEL-validated fields
2. Verify operator generates valid `config.yaml` into an immutable ConfigMap
   (`<name>-config-<hash>`), correctly merging user overrides onto base config loaded from OCI
   labels (`com.ogx.distribution.configs`)
3. Confirm `spec.overrideConfig` takes precedence over declarative config generation
4. Validate legacy resource adoption: annotation-driven adoption of LLSD PVCs, Services, and
   Ingresses into OGXServer, PVCs are orphaned (not deleted) on CR deletion
5. Validate upgrade path from LlamaStackDistribution to OGXServer, including CRD migration and
   resource re-adoption
6. Verify OCI label-based config loading works in air-gapped registries, with embedded config
   fallback when labels are absent
7. Validate known validation gaps: unknown storage types should warn/reject
   (not silently default to SQLite), invalid `disabledAPIs` entries should be rejected, and
   `MergeProviders` whole-API-type replacement behavior is correct

---

## 2. Test Strategy

### 2.1 Test Levels

- **CRD Schema Validation Testing** — Verify CRD accepts valid configs and rejects invalid ones via
  admission webhook and CEL validations
- **API Integration Testing** — Test operator reconciliation loop: CRD field changes produce correct
  immutable ConfigMap content and trigger pod rollouts
- **Data Validation Testing** — Verify config merge logic, OCI label parsing
  (`com.ogx.config.<filename>`), base64 decoding, provider expansion
- **Functional Testing** — End-to-end: apply OGXServer CR with runtime config, verify server starts
  with rendered config
- **Adoption Testing** — Legacy LLSD resource adoption via annotations, PVC orphaning, adoption
  status conditions
- **Upgrade/Migration Testing** — LlamaStackDistribution to OGXServer migration, resource
  re-adoption

### 2.2 Test Types

- **Positive Testing** — Valid runtime configs with all supported provider/storage combinations
- **Negative Testing** — Invalid inputs: unknown storage types, invalid API names in `disabledAPIs`,
  missing required fields, invalid provider types, invalid adoption annotations
- **Boundary Testing** — MinItems/MaxItems on provider arrays, large config.yaml sizes, all
  capabilities enabled simultaneously
- **Regression Testing** — `spec.overrideConfig` continues to work alongside declarative config, no
  silent data loss during merge

### 2.3 Test Priorities

- **P0 (Critical)** — CRD validation (webhook, CEL rules, required fields), immutable ConfigMap
  generation from CRD fields, pod rollout on config change, `spec.overrideConfig` precedence, OCI
  label config loading, legacy resource adoption, upgrade from LlamaStackDistribution to OGXServer
- **P1 (High)** — Provider expansion for all supported types
  (VertexAI, Watsonx, Bedrock with per-provider TLS/proxy/headers), Postgres storage, air-gapped
  registry support with embedded fallback, ConfigMap cleanup on CR deletion, midstream/downstream
  field preservation, NetworkPolicy per-CR toggle
- **P2 (Medium)** — configgen CLI (OCI label resolution, stdin input), concurrent reconciliation
  behavior, edge cases in merge logic (partial storage overrides), PVC orphaning edge cases

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- OpenShift 4.x (version per RHOAI support matrix for 3.5 GA —
  modular architecture pushed from EA2 to GA per DevTestOps
  build infra dependency)
- RHOAI 3.5 GA (OGX modular operator delivery target; OGX is slated for GA in 3.5)
- OGX operator (`quay.io/ogx-ai/ogx-k8s-operator`) with runtime config feature
- cert-manager (for validating admission webhook TLS)
- Container registry with air-gapped registry option for OCI label testing
- Python 3.11+ (for openshift-python-wrapper, opendatahub-tests)
- CRD versions: `llamastack.io/v1alpha1` (pre-upgrade, legacy branch) and `ogx.io/v1beta1` (current)

### 3.2 Test Data Requirements

#### Sample OGXServer CRs

**Minimal CR with distribution (v1beta1)**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-upgrade-test
spec:
  replicas: 1
  distribution:
    name: rh-dev
  workload:
    overrides:
      env:
        - name: VLLM_URL
          valueFrom:
            secretKeyRef:
              key: VLLM_URL
              name: ogx-inference-secret
        - name: POSTGRES_HOST
          value: "ogx-postgres.<namespace>.svc.cluster.local"
        - name: POSTGRES_PORT
          value: "5432"
        - name: POSTGRES_DB
          value: "ogx_metadata"
        - name: POSTGRES_USER
          value: "ogx"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              key: password
              name: ogx-postgres-secret
    storage:
      size: 5Gi
```

**Multi-tenant CR with Keycloak auth, pgvector, and minio** — uses `ogx.io/v1alpha1` with
`spec.config.configMapName` (overrideConfig pattern).

#### Postgres Setup

**Metadata Postgres** — `registry.redhat.io/rhel9/postgresql-15:latest` with `POSTGRESQL_USER=ogx`,
`POSTGRESQL_DATABASE=ogx_metadata`.

**pgvector Postgres** —
`quay.io/jgarciao/pgvector@sha256:6e0b281a99959919bec7c94718162e75cbbf48e6fd3a5c7529067fa701264082`
with `POSTGRES_DB=pgvector`. Requires `CREATE EXTENSION IF NOT EXISTS vector;` post-deploy.

**Shared infra Postgres** — PostgreSQL 15, PVC-backed, liveness/readiness probes.

#### Deploy & Test Script

Complete end-to-end deploy script with secrets, postgres, pgvector, OGXServer CR, route, health
check, and functional test execution.

Required env vars:

```bash
NAMESPACE="ogx-test"
VLLM_URL="https://<inference-endpoint>/v1"
VLLM_API_TOKEN="<token>"
VLLM_EMBEDDING_URL="https://<embedding-endpoint>/v1"
VLLM_EMBEDDING_API_TOKEN="<embedding-token>"
EMBEDDING_MODEL="Nomic-embed-text-v2-moe"
```

#### Upgrade Test Fixtures (3.4 → 3.5)

Complete pre-upgrade and post-upgrade fixtures:

| File | Purpose |
| --- | --- |
| `llamastack-cr.yaml` | Pre-upgrade `llamastack.io/v1alpha1` `LlamaStackDistribution` CR |
| `postgres.yaml` | Pre-upgrade PostgreSQL (shared with old LlamaStack) |
| `ogx-cr.yaml` | Post-upgrade `ogx.io/v1beta1` `OGXServer` CR |
| `ogx-postgres.yaml` | Post-upgrade separate postgres (metadata) + pgvector (vector_io) |
| `deploy-llamastack-34.sh` | Deploy script for 3.4 baseline (LLSD + postgres + tests) |
| `deploy-and-test.sh` | Deploy script for 3.5 (OGXServer + postgres + pgvector + tests) |
| `RESULTS.md` | Actual upgrade test results with 10 key findings |

**Pre-upgrade LlamaStackDistribution CR** (`llamastack.io/v1alpha1`):

```yaml
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: llama-stack-upgrade-test
spec:
  replicas: 1
  server:
    containerSpec:
      env:
        - name: VLLM_URL
          valueFrom:
            secretKeyRef:
              key: VLLM_URL
              name: llama-stack-inference-model-secret
        - name: POSTGRES_HOST
          value: "postgres.<namespace>.svc.cluster.local"
    distribution:
      name: rh-dev
    storage:
      size: 5Gi
```

#### Key Findings from Upgrade Testing (verified 2026-05-27)

1. **No automatic CRD migration** — old `LlamaStackDistribution` CR persists; no `OGXServer`
   auto-created
2. **v1alpha1 API is gone** — only `ogx.io/v1beta1` is served; `oc apply` with v1alpha1 fails
3. **Spec structure changed** — `spec.server.containerSpec.env` → `spec.workload.overrides.env`,
   `spec.server.distribution.name` → `spec.distribution.name`
4. **Separate postgres required** — new OGXServer cannot share postgres with old LlamaStack
   (model registry conflicts)
5. **pgvector needs dedicated image** — `registry.redhat.io/rhel9/postgresql-15` lacks `vector`
   extension; use `quay.io/jgarciao/pgvector`
6. **DSC manual patch required** — `llamastackoperator: Managed` → `llamastackoperator: Removed` +
   `ogx: Managed`
7. **Dual-operator state** — after DSC patch, both old and new operator pods run simultaneously
8. **Workload continuity preserved** — LlamaStack pods keep serving throughout upgrade
9. **Inline vector_io providers stripped** from `rh-dev` image — only remote providers work
10. **All 35 tests pass** on OGX 1.0.2 (26 Bruno + 9 notebooks)

#### Other Test Data

- **Base config.yaml templates** — embedded in distribution image OCI labels
  (base64-encoded via `com.ogx.config.<filename>`)
- **Legacy LLSD resources** — pre-existing LlamaStackDistribution CRs, PVCs, Services, Ingresses
  with adoption annotations
- **Invalid config samples** — unknown storage types, invalid `disabledAPIs` values, missing
  required fields, MinItems/MaxItems violations
- **Distribution images** — with and without OCI labels (to test embedded config fallback)
- **`spec.overrideConfig` samples** — ConfigMap references to verify precedence over declarative
  config (see multi-tenant pattern above)

### 3.3 Test Users

- **Cluster admin** — CRD installation, operator deployment, namespace creation
- **Namespace admin** — creating/updating OGXServer CRs, ConfigMaps, Deployments
- **Service account** — operator controller reconciliation
  (RBAC roles for ConfigMap, Deployment, Pod read/write)
- **Unprivileged user** — validating RBAC enforcement on restricted CRD fields

---

## 4. CRD Fields and Operator Methods Under Test

| Endpoint/Method | Type | Purpose | Priority |
| --- | --- | --- | --- |
| OGXServer CRD (`spec.providers`) | CRD | Declarative provider config (VLLM, OpenAI, VertexAI, Watsonx, Bedrock) | P0 |
| OGXServer CRD (`spec.resources`) | CRD | Resource registrations (models, shields) | P0 |
| OGXServer CRD (`spec.storage`) | CRD | Storage backend config (SQLite, Redis, Postgres) | P0 |
| OGXServer CRD (`spec.disabledAPIs`) | CRD | Disable specific API capabilities | P0 |
| OGXServer CRD (`spec.overrideConfig`) | CRD | ConfigMap override — takes precedence over declarative config | P0 |
| OGXServer CRD (`spec.network.networkPolicy`) | CRD | Per-CR NetworkPolicy toggle (`enabled` flag) | P1 |
| Validating admission webhook | Webhook | Reject invalid CRD fields, enforce CEL rules, MinItems/MaxItems | P0 |
| Operator: config generation pipeline | Method | Generate `config.yaml` from `spec.providers` + `spec.resources` + `spec.storage` + `spec.disabledAPIs` | P0 |
| Operator: OCI label loading | Method | Fetch base64-encoded config from `com.ogx.config.<filename>` labels | P0 |
| Operator: merge config | Method | Merge user overrides onto base config (whole-API-type replacement for providers) | P0 |
| Operator: immutable ConfigMap creation | Method | Create `<name>-config-<hash>` ConfigMap, mount to server pod | P0 |
| Operator: pod rollout trigger | Method | Config hash change triggers rolling update | P0 |
| Operator: embedded config fallback | Method | Fall back to embedded config when OCI labels absent | P1 |
| OGXServer CRD (`spec.baseConfig`) | CRD | Explicit base config ConfigMap — takes precedence over OCI labels | P0 |
| OGXServer CRD (`spec.network.port`) | CRD | Override base `server.port` in generated config | P1 |
| Operator: SecretKeyRef auto-injection | Method | Auto-inject env vars into Deployment for provider SecretKeyRef credentials | P0 |
| Operator: ConfigMap retention | Method | Retain only latest 2 immutable ConfigMaps (`configMapRetention=2`) | P0 |
| Operator: ConfigMap reuse | Method | Reuse existing ConfigMap when CR spec unchanged (content-hash match) | P0 |
| CEL: mutual exclusivity | Validation | `overrideConfig` mutually exclusive with `providers`, `resources`, `storage`, `disabledAPIs`, `baseConfig` | P0 |
| Operator: legacy adoption | Method | Annotation-driven adoption of LLSD PVC/Service/Ingress | P0 |
| Operator: PVC orphaning | Method | PVCs are NOT deleted on CR deletion (orphaned for safety) | P1 |
| Operator: adoption status conditions | Method | Track adoption state in CR `.status.conditions` | P1 |
| Migration: LlamaStackDistribution to OGXServer | CRD | Full CRD migration from `llamastack.io/v1alpha1` to `ogx.io/v1beta1` | P0 |
| `configgen` CLI (OCI label resolution) | CLI | Fetch `config.yaml` from OCI labels for offline config generation | P2 |

---

## 5. Test Cases

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)
**Total: 44 test cases** — P0: 35, P1: 8, P2: 1 (configgen CLI — no TC generated)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
| --- | --- | --- |
| TC-SCHEMA | 4 | 4 P0 |
| TC-WEBHOOK | 1 | 1 P0 |
| TC-MERGE | 3 | 2 P0, 1 P1 |
| TC-RENDER | 2 | 2 P0 |
| TC-ROLLOUT | 1 | 1 P0 |
| TC-OCI | 3 | 1 P0, 2 P1 |
| TC-OVERRIDE | 1 | 1 P0 |
| TC-ADOPT | 3 | 1 P0, 2 P1 |
| TC-UPGRADE | 3 | 3 P0 |
| TC-PROVIDER | 2 | 1 P0, 1 P1 |
| TC-STORAGE | 1 | 1 P0 |
| TC-NEG | 3 | 3 P0 |
| TC-NETPOL | 1 | 1 P1 |
| TC-SECRET | 4 | 4 P0 |
| TC-BASECONFIG | 3 | 2 P0, 1 P1 |
| TC-LIFECYCLE | 2 | 2 P0 |
| TC-CEL | 3 | 3 P0 |
| TC-E2E | 4 | 4 P0 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- `TC-SCHEMA` — CRD schema validation (field acceptance, rejection, defaults, CEL rules)
- `TC-WEBHOOK` — Admission webhook validation (MinItems/MaxItems, required fields)
- `TC-MERGE` — Config merge logic (base + overrides, provider replacement, storage merge)
- `TC-RENDER` — Immutable ConfigMap rendering and content validation
- `TC-ROLLOUT` — Pod rollout triggers (config hash, deployment updates)
- `TC-OCI` — OCI label loading, caching, fallback, air-gapped scenarios
- `TC-OVERRIDE` — `spec.overrideConfig` precedence over declarative config
- `TC-ADOPT` — Legacy LLSD resource adoption (PVC, Service, Ingress, annotations)
- `TC-UPGRADE` — LlamaStackDistribution to OGXServer migration
- `TC-PROVIDER` — Provider-specific expansion (VLLM, OpenAI, VertexAI, Watsonx, Bedrock)
- `TC-STORAGE` — Storage backend expansion (SQLite, Redis, Postgres)
- `TC-NEG` — Negative tests (invalid inputs, validation gaps)
- `TC-NETPOL` — NetworkPolicy per-CR toggle
- `TC-SECRET` — SecretKeyRef auto-injection (provider credentials → env vars)
- `TC-BASECONFIG` — Explicit base config ConfigMap (precedence over OCI labels)
- `TC-LIFECYCLE` — Immutable ConfigMap retention and reuse
- `TC-CEL` — CEL mutual exclusivity validation (overrideConfig vs declarative fields)
- `TC-E2E` — End-to-end scenarios (CR apply → server starts with config)

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the strategy. Each scenario maps to
one or more TC-E2E-*.md test cases generated by `/test-plan.create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan.create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
| --- | --- | --- | --- |
| TC-E2E-001 | Declarative config — CR to running server | spec.providers, spec.storage, config pipeline, OCI loading, merge, ConfigMap creation, rollout | P0 |
| TC-E2E-002 | overrideConfig — ConfigMap-based config to running server | spec.overrideConfig, config pipeline | P0 |
| TC-E2E-003 | Full upgrade journey | Migration LLSD→OGXServer, legacy adoption, config pipeline | P0 |
| TC-E2E-004 | Legacy adoption journey | Legacy adoption, PVC orphaning, adoption conditions, rollout | P0 |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
| --- | --- |
| OGXServer CRD (`spec.providers`) | TC-E2E-001 |
| OGXServer CRD (`spec.resources`) | TC-E2E-001 |
| OGXServer CRD (`spec.storage`) | TC-E2E-001 |
| OGXServer CRD (`spec.disabledAPIs`) | TC-E2E-001 |
| OGXServer CRD (`spec.overrideConfig`) | TC-E2E-002 |
| Validating admission webhook | TC-E2E-001 |
| Operator: config generation pipeline | TC-E2E-001, TC-E2E-002 |
| Operator: OCI label loading | TC-E2E-001 |
| Operator: merge config | TC-E2E-001 |
| Operator: immutable ConfigMap creation | TC-E2E-001, TC-E2E-002 |
| Operator: pod rollout trigger | TC-E2E-001, TC-E2E-004 |
| Operator: legacy adoption | TC-E2E-003, TC-E2E-004 |
| Operator: PVC orphaning | TC-E2E-004 |
| Operator: adoption status conditions | TC-E2E-004 |
| Migration: LlamaStackDistribution to OGXServer | TC-E2E-003 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category does not apply to this feature,
state **Not Applicable** with a brief justification.

### 7.1 Disconnected/Air-Gapped

This feature has direct air-gapped implications due to OCI label-based config loading:

- **OCI label resolution from mirrored registries**: Operator fetches config from
  `com.ogx.config.<filename>` labels. Verify operator resolves labels from mirrored/internal
  registries without external network access.
- **Embedded config fallback**: When OCI labels are absent
  (images without labels, mirroring that strips labels), operator falls back to embedded config.
  Verify fallback path works correctly.
- **Config caching by image digest**: Operator caches configs by digest to avoid repeated registry
  fetches. Verify cache is populated on first fetch and subsequent reconciliations use cached
  config.
- **Distribution image mirroring**: All official distribution images must include OCI labels
  (`com.ogx.distribution.name`, `com.ogx.distribution.version`,
  `com.ogx.distribution.default-config`,
  `com.ogx.distribution.configs`).
  Verify mirrored images preserve OCI labels.

### 7.2 Upgrade/Migration

This feature introduces significant upgrade/migration concerns:

- **CRD migration**: `llamastack.io/v1alpha1` `LlamaStackDistribution` to `ogx.io/v1beta1`
  `OGXServer`. This is a full API group, version, and kind change — not a simple version bump.
  Verify CRD migration workflow.
- **Legacy resource adoption**: Annotation-driven adoption of existing LLSD PVCs, Services, and
  Ingresses into OGXServer. PVCs are orphaned (not deleted) for data safety. Verify adoption
  annotations, status conditions, and re-adoption after annotation removal.
- **`spec.overrideConfig` backward compatibility**: Existing users with ConfigMap-based config
  (`spec.overrideConfig`, formerly `spec.userConfig`) must continue to function. Verify
  `overrideConfig` takes precedence over declarative config generation.
- **Zero-downtime upgrade**: In-place upgrade must not cause service interruption. Verify rolling
  restart behavior driven by immutable ConfigMap hash changes.
- **Rollback**: Rollback procedure must be documented and tested. Legacy branch preserved for
  reference.
- **Safety API removal**: Safety provider type, disabled API entry, and CEL validations were removed
  in PR #294. Verify no regressions from removal.

### 7.3 Performance/Scalability

**Not Applicable** — This feature operates at the operator reconciliation level
(Kubernetes controller). There is no user-facing latency path or data-volume-dependent behavior.
Config rendering is a one-time operation per CR change. OCI label fetching and caching is bounded by
the number of distinct distribution images.

### 7.4 RBAC/Authorization

- **Service account permissions**: Operator service account requires ClusterRole for OGXServer CR
  (get, list, watch, status, finalizers) and Role for namespace-scoped operands
  (ConfigMap create/update/delete, Deployment patch, Pod list/watch). Verify operator functions with
  minimum required permissions per the module handler developer guide.
- **Namespace isolation**: Operator must only manage ConfigMaps in the same namespace as the
  OGXServer CR. Verify no cross-namespace resource access.
- **Webhook RBAC**: Validating admission webhook requires cert-manager certificates. Verify webhook
  TLS is correctly provisioned.
- **Multi-tenancy**: Multiple OGXServer CRs in different namespaces should not interfere with each
  other's ConfigMaps or Deployments.

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
| --- | --- | --- | --- |
| Silent config corruption from merge logic replacing entire API type blocks (RHAIENG-5697) | High | High | Test provider merge behavior explicitly; verify whole-API-type replacement is documented and correct |
| Unknown storage types silently default to SQLite without warning (RHAIENG-5697) | High | Medium | Test all invalid storage type inputs; verify webhook validation rejects or warns |
| `disabledAPIs` silently ignores invalid API names (RHAIENG-5697) | High | Medium | Test with typo'd API names; verify validation rejects invalid entries |
| Config pipeline drops fields downstream distributions depend on (RHAIENG-5699) | High | Medium | Test with downstream distribution CRs that use `registered_resources.vector_dbs`, `tool_groups`, partial storage |
| OCI label fetch failures in air-gapped registries | High | Medium | Test with mirrored registry; verify embedded config fallback works |
| CRD migration breaks existing deployments (llamastack.io → ogx.io) | High | Medium | Test full migration workflow with pre-existing LLSD resources; verify adoption path |
| PVC data loss during legacy adoption | High | Low | Verify PVCs are orphaned (not deleted); test re-adoption after annotation removal |
| Partial storage overrides replace entire base config storage section (RHAIENG-5699) | Medium | Medium | Test partial storage override (only KV backend); verify SQL backend is preserved |
| ConfigMap cleanup fails under concurrent reconciliation (RHAIENG-5698) | Medium | Low | Test rapid CR create/delete cycles; verify no orphaned ConfigMaps |
| `spec.overrideConfig` stops working after declarative config introduction | Medium | Low | Test that overrideConfig still takes full precedence over generated config |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- Single OpenShift 4.x cluster (RHOAI 3.5 GA compatible — modular architecture target)
- OGX operator (`quay.io/ogx-ai/ogx-k8s-operator`) with v1beta1 CRD support
- cert-manager for webhook TLS provisioning
- Air-gapped/mirrored container registry for OCI label tests
- Postgres instance for storage provider testing
- Pre-built distribution images with OCI labels
  (starter, remote-vllm, meta-reference-gpu, postgres-demo)

### 9.2 Configuration

- CRD definitions: `llamastack.io/v1alpha1` (legacy) and `ogx.io/v1beta1` (current)
- Operator subscription from appropriate catalog source (midstream/downstream)
- Legacy LLSD resources with adoption annotations for migration testing
- `spec.overrideConfig` ConfigMaps for backward compatibility scenarios
- OCI image labels: `com.ogx.config.<filename>`, `com.ogx.distribution.name`,
  `com.ogx.distribution.version`, `com.ogx.distribution.default-config`,
  `com.ogx.distribution.configs`

### 9.3 Test Tools

- `kubectl` / `oc` — CR CRUD, ConfigMap inspection, Pod logs, Deployment status
- `openshift-python-wrapper` — programmatic CR manipulation (after RHAIENG-3597 updates)
- `opendatahub-tests` — automated test suite (after RHAIENG-3597 updates)
- `yq` / `jq` — YAML/JSON config inspection and diffing
- `skopeo inspect` — OCI image label verification
- `base64` — decoding OCI label config.yaml content
- `psql` — Postgres storage provider validation
- `curl` / `grpcurl` — OGX server API endpoint testing after config changes
- `diff` — comparing rendered ConfigMaps before/after upgrade

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
| --- | --- | --- | --- | --- |
| TC-SCHEMA | 4 | 4 | 0 | 0 |
| TC-WEBHOOK | 1 | 1 | 0 | 0 |
| TC-MERGE | 3 | 2 | 1 | 0 |
| TC-RENDER | 2 | 2 | 0 | 0 |
| TC-ROLLOUT | 1 | 1 | 0 | 0 |
| TC-OCI | 3 | 1 | 2 | 0 |
| TC-OVERRIDE | 1 | 1 | 0 | 0 |
| TC-ADOPT | 3 | 1 | 2 | 0 |
| TC-UPGRADE | 3 | 3 | 0 | 0 |
| TC-PROVIDER | 2 | 1 | 1 | 0 |
| TC-STORAGE | 1 | 1 | 0 | 0 |
| TC-NEG | 3 | 3 | 0 | 0 |
| TC-NETPOL | 1 | 0 | 1 | 0 |
| TC-SECRET | 4 | 4 | 0 | 0 |
| TC-BASECONFIG | 3 | 2 | 1 | 0 |
| TC-LIFECYCLE | 2 | 2 | 0 | 0 |
| TC-CEL | 3 | 3 | 0 | 0 |
| TC-E2E | 4 | 4 | 0 | 0 |
| **Total** | **44** | **35** | **8** | **0** |

### 10.2 CRD Field/Method Coverage

| Endpoint/Method | Test Cases | Coverage |
| --- | --- | --- |
| OGXServer CRD (`spec.providers`) | TC-SCHEMA-001, TC-SCHEMA-003, TC-PROVIDER-001, TC-PROVIDER-002, TC-E2E-001 | |
| OGXServer CRD (`spec.resources`) | TC-E2E-001 | |
| OGXServer CRD (`spec.storage`) | TC-STORAGE-001, TC-MERGE-002, TC-NEG-001, TC-E2E-001 | |
| OGXServer CRD (`spec.disabledAPIs`) | TC-MERGE-003, TC-NEG-002 | |
| OGXServer CRD (`spec.overrideConfig`) | TC-OVERRIDE-001, TC-E2E-002 | |
| OGXServer CRD (`spec.network.networkPolicy`) | TC-NETPOL-001 | |
| Validating admission webhook | TC-WEBHOOK-001, TC-SCHEMA-002, TC-SCHEMA-003, TC-SCHEMA-004 | |
| Operator: config generation pipeline | TC-RENDER-001, TC-RENDER-002, TC-E2E-001, TC-E2E-002 | |
| Operator: OCI label loading | TC-OCI-001, TC-OCI-003, TC-E2E-001 | |
| Operator: merge config | TC-MERGE-001, TC-MERGE-002, TC-MERGE-003, TC-NEG-003 | |
| Operator: immutable ConfigMap creation | TC-RENDER-001, TC-RENDER-002, TC-E2E-001 | |
| Operator: pod rollout trigger | TC-ROLLOUT-001, TC-RENDER-002, TC-E2E-001 | |
| Operator: embedded config fallback | TC-OCI-002 | |
| Operator: config caching by digest (TBD) | — | |
| Operator: ConfigMap cleanup (TBD) | — | |
| Operator: legacy adoption | TC-ADOPT-001, TC-ADOPT-003, TC-E2E-003, TC-E2E-004 | |
| Operator: PVC orphaning | TC-ADOPT-002, TC-E2E-004 | |
| Migration: LlamaStackDistribution to OGXServer | TC-UPGRADE-001, TC-UPGRADE-002, TC-UPGRADE-003, TC-E2E-003 | |
| OGXServer CRD (`spec.baseConfig`) | TC-BASECONFIG-001, TC-BASECONFIG-002, TC-BASECONFIG-003 | |
| OGXServer CRD (`spec.network.port`) | — (P1, not yet covered) | |
| Operator: SecretKeyRef auto-injection | TC-SECRET-001, TC-SECRET-002, TC-SECRET-003, TC-SECRET-004 | |
| Operator: ConfigMap retention | TC-LIFECYCLE-002 | |
| Operator: ConfigMap reuse | TC-LIFECYCLE-001 | |
| CEL: mutual exclusivity | TC-CEL-001, TC-CEL-002, TC-CEL-003 | |
| `configgen` CLI (OCI label resolution) | — (P2, TBD) | |

### 10.3 GitHub PRs

| PR | Repo | Summary | Status |
| --- | --- | --- | --- |
| [#288](https://github.com/ogx-ai/ogx-k8s-operator/pull/288) | ogx-k8s-operator | Rename to OGX repo | Merged |
| [#289](https://github.com/ogx-ai/ogx-k8s-operator/pull/289) | ogx-k8s-operator | Add OGXServer CRD types (`ogx.io/v1beta1`) | Merged |
| [#290](https://github.com/ogx-ai/ogx-k8s-operator/pull/290) | ogx-k8s-operator | Add OGXServer controller (reconciler rename) | Merged |
| [#292](https://github.com/ogx-ai/ogx-k8s-operator/pull/292) | ogx-k8s-operator | Legacy resource adoption for OGXServer | Merged |
| [#294](https://github.com/ogx-ai/ogx-k8s-operator/pull/294) | ogx-k8s-operator | Refine provider specs; remove safety API | Merged |
| [#295](https://github.com/ogx-ai/ogx-k8s-operator/pull/295) | ogx-k8s-operator | Config generation pipeline | Merged |
| [#122](https://github.com/opendatahub-io/ogx-k8s-operator/pull/122) | opendatahub-io/ogx-k8s-operator | ODH sync: rename LlamaStack to ODH | Merged |
| [#2647](https://github.com/RedHatQE/openshift-python-wrapper/pull/2647) | openshift-python-wrapper | v1alpha2 wrapper support | Open |

### 10.4 OCI Label Format

Generated by
[`scripts/generate-config-labels.sh`](https://github.com/ogx-ai/ogx/blob/main/scripts/generate-config-labels.sh):

| Label | Content |
| --- | --- |
| `com.ogx.config.<filename>` | Base64-encoded YAML config file |
| `com.ogx.distribution.name` | Distribution name (e.g., `remote-vllm`) |
| `com.ogx.distribution.version` | Distribution version |
| `com.ogx.distribution.default-config` | Default config filename (e.g., `config.yaml`) |
| `com.ogx.distribution.configs` | Comma-separated list of config filenames |

### 10.5 Document Change Log

| Version | Date | Changes |
| --- | --- | --- |
| 1.0.0 | 2026-06-16 | Initial test plan (using LlamaStackDistribution/v1alpha2 naming) |
| 1.1.0 | 2026-06-16 | Updated to OGXServer/v1beta1 naming, added PR details, OCI label format, legacy adoption, safety API removal, webhook confirmation |
| 1.2.0 | 2026-06-16 | Added concrete test data: sample OGXServer CRs, Postgres/pgvector manifests, deploy scripts, upgrade test fixtures and 10 key findings from 3.4→3.5 upgrade testing |
| 1.3.0 | 2026-06-16 | Generated 32 test cases (25 P0, 7 P1) across 14 categories |
| 1.4.0 | 2026-06-17 | Added 12 test cases from Vaishnavi's spec doc: SecretKeyRef auto-injection (4), baseConfig (3), ConfigMap lifecycle (2), CEL mutual exclusivity (3). Resolved ConfigMap cleanup TBD (retention=2). Total: 44 TCs |

---

**End of Test Plan**
