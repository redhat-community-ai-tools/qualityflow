---
feature: authorino_auth_decision_metrics
source_key: RHAISTRAT-2418
status: Open
gap_count: 10
last_updated: '2026-08-14'
---
# Gaps — Authorino Auth Decision Metrics

## Scope & Endpoints

- **ServiceMonitor target health check mechanism** — AC #7 requires
  target recovery to "up" status but doesn't specify the metric or
  endpoint used for health checks or recovery timeout. Would be
  resolved by: Prometheus Operator documentation reference or design
  doc.

## Test Strategy & Risks

- **No performance SLOs specified** — No concrete query latency or
  cardinality limits defined, making performance testing validation
  impossible without targets. Would be resolved by: feature refinement
  or ADR.
- **Datasource verification procedure undefined** — Datasource
  alignment is flagged as a blocker but no verification steps are
  provided. Would be resolved by: ADR or design doc.
- **Hash-to-name mapping design for GA** — Listed as a dependency
  without a corresponding design approach. Would be resolved by:
  design doc.

## Environment & Infrastructure

- **Specific OpenShift version requirement** — Set to 4.16+ based on
  `monitoring.rhobs/v1` API group requirement. Exact minimum TBD.
- **Prometheus Operator version compatibility** — Would be resolved by:
  feature refinement or ADR.
- **Perses operator version compatibility** — Would be resolved by:
  feature refinement or ADR.
- **Minimum cluster resource requirements (CPU, memory, node count)** —
  Would be resolved by: design doc or ADR.
- **data-science-prometheus-datasource configuration details** — Would
  be resolved by: ADR or design doc.
- **Expected metric cardinality and volume under load** — Would be
  resolved by: design doc or ADR.
