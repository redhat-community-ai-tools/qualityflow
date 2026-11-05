---
feature: runtime_config_in_crd
strat_key: RHAISTRAT-1061
status: Open
gap_count: 12
last_updated: '2026-06-16'
---
# Gaps — OGXServer Runtime Config

## Resolved by Slack thread + PR review (v1.1.0)

- ~~CRD naming~~ — Resolved: CRD is `ogx.io/v1beta1` `OGXServer` (PRs #288-290)
- ~~Webhook implementation~~ — Resolved: validating admission webhook confirmed with cert-manager +
  OpenShift support (PR #122 ODH sync)
- ~~ConfigMap naming convention~~ — Resolved: immutable ConfigMaps named `<name>-config-<hash>`
  (PR #295)
- ~~OCI label format~~ — Resolved: `com.ogx.config.<filename>`, `com.ogx.distribution.configs`, etc.
  (generate-config-labels.sh)
- ~~Safety API status~~ — Resolved: safety API removed (PR #294)
- ~~overrideConfig backward compat~~ — Resolved: `spec.overrideConfig` takes precedence over
  declarative generation (PR #295)
- ~~Migration detection logic~~ — Resolved: annotation-driven legacy adoption with PVC orphaning
  (PR #292)
- ~~Feature flag details~~ — Resolved: global ConfigMap feature flags removed, NetworkPolicy is
  per-CR toggle (PR #290)
- ~~configgen CLI availability~~ — Partially resolved: CLI exists per RHAIENG-5698, but no spec
  available

## Scope & Endpoints (remaining)

- **Unknown storage types silently default to SQLite without warning** — would be resolved by: ADR
  specifying validation behavior (should warn/reject, not silently default)
- **disabledAPIs silently ignores invalid API names** — would be resolved by: ADR specifying
  validation behavior (should warn/reject invalid entries)
- **MergeProviders replaces entire API type blocks without documentation** — would be resolved by:
  Design doc clarifying merge semantics (whole-API-type replacement vs. additive merge)
- **Config pipeline field preservation** (RHAIENG-5699) —
  Spec doc confirms these fields MUST be preserved from base config:
  `telemetry`, `server.auth`, `vector_stores`,
  `registered_resources.vector_dbs`, `tool_groups`.
  Needs TC-PRESERVE-001: assert each field present in rendered
  config.yaml with values matching the base OCI config, and diff
  shows only intentionally merged sections changed.
- **Partial storage overrides replace entire base config storage section** — would be resolved by:
  Design doc specifying merge semantics for partial spec.storage overrides

## Test Strategy & Risks (remaining)

- **No ADR for config merge semantics** — would be resolved by: ADR or design doc specifying merge
  behavior (replacement vs additive) for providers, storage, and capabilities
- **No CRD field versioning strategy** — would be resolved by: ADR specifying how fields are
  added/deprecated across CRD versions

## Environment & Infrastructure (remaining)

- **Exact OpenShift version** — would be resolved by: release notes or feature refinement
- **RHOAI operator version** — would be resolved by: release notes
- **Postgres version and setup** — would be resolved by: ADR or test infrastructure guide
- **External provider credentials** — VertexAI, Watsonx, Bedrock testing requires API
  keys/credentials; would be resolved by: test infrastructure guide
- **Concurrent reconciliation limits** — would be resolved by: ADR specifying expected behavior
