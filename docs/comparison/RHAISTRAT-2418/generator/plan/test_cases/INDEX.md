# Test Cases Index — Authorino Auth Decision Metrics

**Parent**: [TestPlan.md](../TestPlan.md)
**Source**: [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418)

## Quick Stats

- **Total Test Cases**: 27
- **P0 (Critical)**: 15
- **P1 (High)**: 10
- **P2 (Medium)**: 2

## METRICS — Raw Metric Availability and Label Schema

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-METRICS-001](TC-METRICS-001.md) | Verify auth decision counter metric with correct labels | P0 |
| [TC-METRICS-002](TC-METRICS-002.md) | Verify auth decision latency histogram metric | P0 |
| [TC-METRICS-003](TC-METRICS-003.md) | Verify evaluator invocation metrics | P1 |
| [TC-METRICS-004](TC-METRICS-004.md) | Verify authconfig label values are SHA-256 hashes | P0 |

## RULES — Recording Rule Computation and Correctness

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-RULES-001](TC-RULES-001.md) | Verify auth decision rate recording rule | P0 |
| [TC-RULES-002](TC-RULES-002.md) | Verify deny ratio recording rule computation | P0 |
| [TC-RULES-003](TC-RULES-003.md) | Verify P95 auth latency recording rule | P0 |
| [TC-RULES-004](TC-RULES-004.md) | Verify promtool unit tests pass | P0 |

## ALERT — Alert Firing Conditions and Suppression

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-ALERT-001](TC-ALERT-001.md) | Verify alert fires on high deny rate | P0 |
| [TC-ALERT-002](TC-ALERT-002.md) | Verify alert does not fire at low deny rate | P0 |
| [TC-ALERT-003](TC-ALERT-003.md) | Verify alert respects 10-minute sustained window | P1 |
| [TC-ALERT-004](TC-ALERT-004.md) | Verify alert suppressed on negligible traffic | P1 |

## DASH — Perses Dashboard Rendering and Interaction

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-DASH-001](TC-DASH-001.md) | Verify Perses dashboard CR deploys and is accessible | P0 |
| [TC-DASH-002](TC-DASH-002.md) | Verify decision rate stat panel shows data | P0 |
| [TC-DASH-003](TC-DASH-003.md) | Verify deny rate stat panel shows correct percentage | P0 |
| [TC-DASH-004](TC-DASH-004.md) | Verify decisions by status time series panel | P0 |
| [TC-DASH-005](TC-DASH-005.md) | Verify authconfig variable filter functionality | P1 |

## EDGE — Edge Cases

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-EDGE-001](TC-EDGE-001.md) | Verify dashboard handles zero auth traffic gracefully | P1 |
| [TC-EDGE-002](TC-EDGE-002.md) | Verify ServiceMonitor target recovery after pod restart | P1 |
| [TC-EDGE-003](TC-EDGE-003.md) | Verify counter reset handling during rolling update | P1 |
| [TC-EDGE-004](TC-EDGE-004.md) | Verify multi-replica metric aggregation | P2 |

## PRIVACY — Label Privacy and Data Sensitivity

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-PRIVACY-001](TC-PRIVACY-001.md) | Verify no user-identifying labels in metrics | P1 |
| [TC-PRIVACY-002](TC-PRIVACY-002.md) | Verify dashboard does not expose user-identifying data | P1 |

## DOC — Metrics Catalog Documentation

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-DOC-001](TC-DOC-001.md) | Verify metrics catalog documentation completeness | P2 |

## E2E — End-to-End Observability Pipeline

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-E2E-001](TC-E2E-001.md) | End-to-end metrics pipeline validation | P0 |
| [TC-E2E-002](TC-E2E-002.md) | End-to-end alert firing and dashboard correlation | P0 |
| [TC-E2E-003](TC-E2E-003.md) | End-to-end rolling update resilience | P1 |
