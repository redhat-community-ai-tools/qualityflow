---
feature: authorino_auth_decision_metrics
source_key: RHAISTRAT-2418
score: 10
pass: true
verdict: Ready
scores:
  specificity: 2
  grounding: 2
  scope_fidelity: 2
  actionability: 2
  consistency: 2
last_updated: '2026-08-14'
auto_revised: false
before_score: 9
before_scores:
  specificity: 2
  grounding: 2
  scope_fidelity: 2
  actionability: 1
  consistency: 2
error: null
---
# Test Plan Review — Authorino Auth Decision Metrics

## Rubric Scores

| Criterion | Score | Notes |
|-----------|-------|-------|
| Specificity | 2/2 | Every risk fails the swap test — NaN deny ratio from 0/0, SHA-256 hash mapping, Prometheus datasource gap are all unique to this feature. Priorities reference MaaSHighAuthDenyRate, recording rules, and promtool by name. |
| Grounding | 2/2 | 15/15 Section 4 entries grounded in strategy text. Zero fabrications. TBDs are genuine unknowns from the strategy. Dashboard panel queries grounded in PR #1363 implementation. |
| Scope Fidelity | 2/2 | All 7 strategy deliverables map to test objectives. All 8 out-of-scope items absent from test plan endpoints and test levels. No orphans in either direction. |
| Actionability | 2/2 | OCP 4.16+ with rationale (monitoring.rhobs/v1 API group), RHOAI 3.6-ea1 pinned. grpcurl command with exact gRPC service path, port, and JSON payload for generating auth traffic. Named RBAC roles: cluster-admin, cluster-monitoring-view, Perses dashboard viewer, unprivileged user. File paths to all config resources. Full PromQL queries for dashboard verification. |
| Consistency | 2/2 | All 6 cross-checks pass. Section 10.2 lists all 15 endpoints from Section 4. Test levels match interface types. Section 6 has appropriate pre-create-cases placeholders. NFR categories consistent with feature scope. |

**Total: 10/10 — Verdict: Ready**

## Grounding Cross-Reference

| Section 4 Entry | Source Match | Status |
|-----------------|-------------|--------|
| `/server-metrics` (port 8080) | "Authorino exposes auth decision metrics on its `/server-metrics` endpoint (port 8080)" | Grounded |
| `auth_server_authconfig_response_status` | Strategy metrics table: "Counter — Auth decision results per AuthConfig" | Grounded |
| `auth_server_authconfig_duration_seconds` | Strategy metrics table: "Histogram — Auth decision latency per AuthConfig" | Grounded |
| `auth_server_evaluator_total` | Strategy metrics table: "Counter — Evaluator invocation counts" | Grounded |
| `auth_server_evaluator_duration_seconds` | Strategy metrics table: "Histogram — Evaluator execution latency" | Grounded |
| `maas:auth_decisions:rate5m` | "Recording rules…implemented in PR #1363: maas:auth_decisions:rate5m" | Grounded |
| `maas:auth_deny_ratio:rate5m` | Strategy recording rules table: "5-minute deny ratio per policy" | Grounded |
| `maas:auth_latency_p95:5m` | Strategy recording rules table: "P95 auth decision latency per policy" | Grounded |
| `MaaSHighAuthDenyRate` | Strategy alert table: "Warning — 10% deny ratio sustained for 10 minutes" | Grounded |
| ServiceMonitor | "authorino-server-metrics-servicemonitor.yaml — scrapes Authorino /server-metrics" | Grounded |
| PrometheusRule | "authorino-maas-metadata-evaluator-prometheusrule.yaml — contains rule group (PR #1363)" | Grounded |
| Perses Dashboard | Strategy HLR: "Perses dashboard displays aggregate auth decision counts and deny rates by policy" | Grounded |
| Dashboard panel: Decision totals | "Prometheus panels (P0): Decision totals, deny rate trends, latency by policy" | Grounded |
| Dashboard panel: Deny rate trends | Same source as above | Grounded |
| Dashboard panel: Latency by policy | Same source as above | Grounded |

## Section-by-Section Feedback

### Actionability (1/2)

**Sections 3.1 and 3.3** need improvement:

- **OpenShift and RHOAI versions**: Listed as TBD without specifying
  what document or decision would resolve them. The strategy does not
  specify target versions, so these are genuine gaps — but the test
  plan should note they are blocked on release planning.
- **RBAC roles**: Section 3.3 describes users by permission level
  ("User with access to Prometheus API") but does not name specific
  ClusterRole or Role bindings needed. A tester would need to
  investigate which RBAC roles grant Prometheus API access and Perses
  dashboard access.
- **Test traffic generation**: Section 3.2 mentions
  lazy-initialized metrics but does not explain how to generate auth
  traffic. The strategy's cluster verification comment describes using
  `grpcurl` to call Authorino gRPC Check directly — this procedure
  should be referenced or summarized.
- **Sample test data**: No example YAML for LLMInferenceService or
  AuthPolicy resources that would generate the auth traffic needed
  for testing.

These items are documented in TestPlanGaps.md and cannot be resolved
without additional source documents (feature refinement or ADR).

## Revision History

Initial assessment.
