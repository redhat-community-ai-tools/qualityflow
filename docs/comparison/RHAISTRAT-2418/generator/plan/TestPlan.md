---
feature: authorino_auth_decision_metrics
source_key: RHAISTRAT-2418
source_type: strat
status: In Review
author: MaaS Team
components:
- Model and Agent Observability
additional_docs: []
last_updated: '2026-08-14'
version: 1.1.0
reviewers: []
---
# Authorino Auth Decision Metrics Test Plan

**MaaS Team – Per-Policy Auth Decision Monitoring**

**Strategy**: [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates the integration of per-policy authorization decision
metrics from Authorino into the RHOAI monitoring stack. The feature surfaces
auth decision counters, recording rules, alerts, and Perses dashboards to
give operators visibility into authentication and authorization patterns
across MaaS models. Testing ensures metrics are correctly scraped with the
expected label schema, recording rules compute accurate aggregations, the
MaaSHighAuthDenyRate alert fires under the specified conditions, and Perses
dashboard panels render auth decision data reliably — including graceful
handling of zero-traffic and pod restart edge cases.

The recording rules, alert, and promtool unit tests are already implemented
in PR #1363 of the models-as-a-service repository. The remaining deliverables
are the Perses dashboard, metrics catalog documentation, and integration
testing of the full observability pipeline.

### 1.2 Scope

#### In Scope (MaaS Team Responsibilities)

- Prometheus recording rules for auth decision rate
  (`maas:auth_decisions:rate5m`), deny ratio
  (`maas:auth_deny_ratio:rate5m`), and P95 latency
  (`maas:auth_latency_p95:5m`)
- `MaaSHighAuthDenyRate` alert (fires when deny ratio exceeds 10% for
  10 minutes)
- Perses dashboard (`perses.dev/v1alpha1`) displaying aggregate auth
  decision counts, deny rates, and latency by policy
- Unit tests for recording rules and alerts using promtool (9 test cases)
- Documentation of auth decision metrics in RHOAI metrics catalog
- Edge case handling: zero auth traffic (cold start), Authorino pod
  restarts, counter resets during rolling updates
- Privacy compliance: no user-identifying information in Prometheus
  metric labels
- ServiceMonitor and PrometheusRule resources at
  `deployment/base/observability/`
- Dashboard deployment via monitoring service controller to
  `opt/manifests/dashboard/observability/{rhoai,odh}/`

#### Out of Scope (Other Teams)

- Upstream changes to Authorino or Kuadrant code
- Per-user metrics in Prometheus (deferred to OTel/Loki integration)
- Operator lifecycle migration for observability resources (deferred)
- TelemetryPolicy scoping (decoupled effort)
- Limitador rate-limit decision metrics (tracked in RHAIRFE-2782)
- Envoy per-tenant request metrics (tracked in RHAIRFE-2782)
- Cross-layer capacity governance dashboards
- Changes to Authorino authentication logic or AuthPolicy schema

### 1.3 Test Objectives

1. Verify that Authorino auth decision metrics are scraped into RHOAI
   Prometheus with correct labels (`authconfig`, `namespace`, `status`,
   `evaluator_name`, `evaluator_type`) and that `authconfig` label values
   are SHA-256 hashes.
2. Validate that recording rules (`maas:auth_decisions:rate5m`,
   `maas:auth_deny_ratio:rate5m`, `maas:auth_latency_p95:5m`) compute
   correctly over auth decision metrics and handle counter resets during
   rolling updates.
3. Confirm that `MaaSHighAuthDenyRate` alert fires when deny ratio
   exceeds 10% for 10 minutes and does not fire spuriously during
   Authorino pod restarts.
4. Verify that Perses dashboard panels render auth decision totals, deny
   rate trends, and latency by policy from Prometheus datasources and
   gracefully handle zero auth traffic scenarios.
5. Validate that all promtool unit tests (9 test cases) pass for
   recording rules and alert definitions.
6. Confirm that ServiceMonitor target health checks recover to "up"
   status after Authorino pod restarts.
7. Validate that metrics catalog documentation includes all required
   fields (metric name, type, label schema, source component, scrape
   endpoint, interval, PromQL query examples).

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — Prometheus `/server-metrics` endpoint
  scraping, PromQL query validation against recording rule outputs,
  Perses API dashboard verification
- **Data Validation Testing** — Metric label schema correctness
  (`authconfig`, `namespace`, `status`), counter and histogram value
  accuracy, recording rule computation validation
- **Functional Testing** — Alert firing conditions, dashboard panel
  rendering, graceful degradation under zero traffic, counter reset
  handling during rolling updates
- **Performance Testing** — Prometheus query performance with
  namespace-scoped recording rules, cardinality impact assessment
  across AuthConfigs
- **UI Testing** — Perses dashboard panel interactions, zero-data state
  rendering, deny rate trend visualization

### 2.2 Test Types

- **Positive Testing** — Valid auth traffic produces expected metrics,
  dashboards display correctly, alerts fire at threshold
- **Negative Testing** — Zero traffic scenarios, pod restarts, counter
  resets, NaN handling in deny ratio
- **Boundary Testing** — Deny ratio at exactly 10% threshold, multiple
  Authorino replicas, high cardinality scenarios
- **Regression Testing** — Existing ServiceMonitor unchanged, no impact
  to other monitoring, existing Perses dashboards unaffected

### 2.3 Test Priorities

- **P0 (Critical)** — Metrics appear in Prometheus with correct labels,
  recording rules compute correctly, `MaaSHighAuthDenyRate` alert fires
  at threshold, promtool unit tests pass
- **P1 (High)** — Perses dashboard renders correctly, zero-traffic
  graceful degradation, counter reset handling, ServiceMonitor target
  recovery after pod restarts, no user-identifying labels in metrics
- **P2 (Medium)** — Metrics catalog documentation completeness,
  namespace portability (ODH vs RHOAI), hash-to-name mapping UX,
  multi-replica aggregation correctness

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- OpenShift cluster 4.16+ (required for `monitoring.rhobs/v1` API
  group support)
- RHOAI 3.6-ea1
- Authorino service running and processing auth decisions
- Prometheus Operator with CRDs installed
  (`monitoring.coreos.com/v1` API group)
- Perses CRDs available (`perses.dev/v1alpha1`)
- opendatahub-operator for dashboard deployment
- Monitoring stack configured (Prometheus)
- API groups: `monitoring.coreos.com/v1` and `monitoring.rhobs/v1`

### 3.2 Test Data Requirements

- LLMInferenceService and/or MaaS models deployed to generate auth
  traffic
- Auth requests to trigger lazy-initialized metrics
  (`auth_server_*` metrics appear after first auth traffic).
  Generate traffic by calling Authorino gRPC Check directly:

  ```bash
  grpcurl -plaintext -d '{"attributes": {"request": {"http": \
    {"method": "GET", "path": "/test"}}}}' \
    <authorino-service>:50051 \
    envoy.service.auth.v3.Authorization/Check
  ```

  Repeat several times to produce both `OK` and non-`OK` status
  values for recording rule validation.
- Existing ServiceMonitor configuration:
  `authorino-server-metrics-servicemonitor.yaml`
- PrometheusRule configuration:
  `authorino-maas-metadata-evaluator-prometheusrule.yaml`
  (extended in PR #1363)
- Standalone recording rules:
  `deployment/base/observability/maas-auth-alerting.rules.yaml`
- Promtool unit tests:
  `deployment/base/observability/maas-auth-alerting.unit-tests.yaml`
  (9 test cases)
- Existing Perses dashboards at
  `opt/manifests/dashboard/observability/{rhoai,odh}/`
- Auth decisions dashboard definition:
  `deployment/components/observability/observability/dashboards/auth-decisions-dashboard.yaml`
  (PR #1363)

### 3.3 Test Users

- **cluster-admin** — Full cluster access for deploying
  PrometheusRule (`monitoring.coreos.com/v1`), Perses dashboards
  (`perses.dev/v1alpha1`), and managing resources in
  `kuadrant-system` (ODH) or `rh-connectivity-link` (RHOAI)
- **cluster-monitoring-view** — Read-only access to Prometheus
  API for metric queries and alert verification
- **Perses dashboard viewer** — User with access to Perses API
  for dashboard rendering verification (role TBD per Perses
  RBAC configuration)
- **Unprivileged user** — For RBAC negative testing: verify
  that users without monitoring roles cannot access auth
  decision metrics or dashboard panels

---

## 4. Metrics and Components Under Test

| Endpoint/Method | Type | Purpose | Priority |
|-----------------|------|---------|----------|
| `/server-metrics` (port 8080) | REST API | Authorino metrics endpoint exposing auth decision metrics | P0 |
| `auth_server_authconfig_response_status` | Prometheus Counter | Auth decision counts by authconfig, namespace, status | P0 |
| `auth_server_authconfig_duration_seconds` | Prometheus Histogram | Auth decision latency distribution by authconfig, namespace | P0 |
| `auth_server_evaluator_total` | Prometheus Counter | Evaluator invocation counts by evaluator_name, evaluator_type | P1 |
| `auth_server_evaluator_duration_seconds` | Prometheus Histogram | Evaluator latency distribution by evaluator_name, evaluator_type | P1 |
| `maas:auth_decisions:rate5m` | Recording Rule | 5-minute rolling rate of auth decisions | P0 |
| `maas:auth_deny_ratio:rate5m` | Recording Rule | 5-minute rolling ratio of denied auth decisions | P0 |
| `maas:auth_latency_p95:5m` | Recording Rule | 95th percentile auth decision latency over 5 minutes | P0 |
| `MaaSHighAuthDenyRate` | Prometheus Alert | Fires when deny ratio exceeds 10% for 10 minutes (Warning) | P0 |
| ServiceMonitor | Kubernetes CR | Scrape configuration for Authorino `/server-metrics` | P0 |
| PrometheusRule | Kubernetes CR | Recording rules and alert definitions | P0 |
| Perses Dashboard | Kubernetes CR | Dashboard definition for auth metrics visualization | P0 |
| Dashboard panel: Decision totals | UI Component | Aggregate auth decision counts by policy | P0 |
| Dashboard panel: Deny rate trends | UI Component | Deny rate over time by policy | P0 |
| Dashboard panel: Latency by policy | UI Component | P95 latency by authconfig | P0 |

### 4.1 Dashboard Panel Queries

The Perses dashboard (`dashboard-4-maas-auth-decisions-admin`) is defined
in `deployment/components/observability/observability/dashboards/auth-decisions-dashboard.yaml`
(PR #1363). It uses the `data-science-prometheus-datasource` datasource
and an `authconfig` variable filter sourced from
`PrometheusLabelValuesVariable`.

| Panel | PromQL Query | Purpose |
|-------|-------------|---------|
| Auth decisions/sec | `sum(maas:auth_decisions:rate5m{authconfig=~"$authconfig"}) or vector(0)` | Aggregate decision rate stat |
| Deny rate | `((sum(maas:auth_decisions:rate5m{authconfig=~"$authconfig",status!="OK"}) / sum(maas:auth_decisions:rate5m{authconfig=~"$authconfig"})) > -Inf) or vector(0)` | Overall deny percentage stat |
| Avg policy P95 auth latency | `avg(maas:auth_latency_p95:5m{authconfig=~"$authconfig"} > -Inf) or vector(0)` | Average P95 latency stat |
| Active policies | `count(group by (authconfig) (maas:auth_decisions:rate5m{authconfig=~"$authconfig"})) or vector(0)` | Count of active AuthConfigs |
| Auth decisions by status | `sum by (status) (maas:auth_decisions:rate5m{authconfig=~"$authconfig"})` | Stacked area time series |
| Auth decisions by policy | `sum by (authconfig) (maas:auth_decisions:rate5m{authconfig=~"$authconfig"})` | Per-policy time series |
| Deny ratio by policy | `maas:auth_deny_ratio:rate5m{authconfig=~"$authconfig"}` | Per-policy deny ratio time series |
| P95 auth latency by policy | `maas:auth_latency_p95:5m{authconfig=~"$authconfig"} > -Inf` | Per-policy latency time series |

**Zero-data handling**: Stat panels use `or vector(0)` fallback (display
0, not NaN/error). Time series panels use `> -Inf` NaN filter (hide NaN
points, show empty graph when traffic ceases).

---

## 5. Test Cases

**27 test cases** generated across 8 categories.

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| METRICS | 4 | 3 P0, 1 P1 |
| RULES | 4 | 4 P0 |
| ALERT | 4 | 2 P0, 2 P1 |
| DASH | 5 | 4 P0, 1 P1 |
| EDGE | 4 | 3 P1, 1 P2 |
| PRIVACY | 2 | 2 P1 |
| DOC | 1 | 1 P2 |
| E2E | 3 | 2 P0, 1 P1 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- **METRICS** — Raw metric availability and label schema validation
- **RULES** — Recording rule computation and correctness
- **ALERT** — Alert firing conditions and suppression
- **DASH** — Perses dashboard rendering and interaction
- **EDGE** — Edge cases (zero traffic, pod restarts, counter resets)
- **PRIVACY** — Label privacy and data sensitivity validation
- **DOC** — Metrics catalog documentation completeness
- **E2E** — End-to-end observability pipeline scenarios

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
|----|----------|-------------------|----------|
| TC-E2E-001 | Metrics pipeline validation | `/server-metrics`, all raw metrics, all recording rules, Perses Dashboard, all dashboard panels | P0 |
| TC-E2E-002 | Alert firing and dashboard correlation | `MaaSHighAuthDenyRate`, `maas:auth_deny_ratio:rate5m`, Dashboard: Deny rate trends | P0 |
| TC-E2E-003 | Rolling update resilience | ServiceMonitor, all recording rules, Perses Dashboard, all dashboard panels | P1 |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| `/server-metrics` (port 8080) | TC-E2E-001 |
| `auth_server_authconfig_response_status` | TC-E2E-001 |
| `auth_server_authconfig_duration_seconds` | TC-E2E-001 |
| `auth_server_evaluator_total` | — |
| `auth_server_evaluator_duration_seconds` | — |
| `maas:auth_decisions:rate5m` | TC-E2E-001, TC-E2E-003 |
| `maas:auth_deny_ratio:rate5m` | TC-E2E-001, TC-E2E-002 |
| `maas:auth_latency_p95:5m` | TC-E2E-001 |
| `MaaSHighAuthDenyRate` | TC-E2E-002, TC-E2E-003 |
| ServiceMonitor | TC-E2E-001, TC-E2E-003 |
| PrometheusRule | TC-E2E-001 |
| Perses Dashboard | TC-E2E-001, TC-E2E-003 |
| Dashboard panel: Decision totals | TC-E2E-001 |
| Dashboard panel: Deny rate trends | TC-E2E-001, TC-E2E-002 |
| Dashboard panel: Latency by policy | TC-E2E-001 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

**Not Applicable** — This feature operates entirely within the
cluster boundary. Metrics collection, recording rules, alerts,
and Perses dashboards are all cluster-resident Kubernetes
resources. No runtime image pulls, external registry access, or
network-dependent catalog sources are required. Authorino is
already deployed and the feature adds only observability
components.

### 7.2 Upgrade/Migration

Recording rules and alerts are additive to the existing
PrometheusRule resource. No changes to the existing ServiceMonitor
or scrape configuration are required. Testing should verify:

- New recording rules integrate cleanly into existing
  PrometheusRule without disrupting current alerts
- Perses dashboards are created successfully on upgrade
- Existing ServiceMonitor continues scraping correctly
  post-upgrade
- No metric discontinuity or data loss during operator upgrade
- Clusters without the new recording rules remain unaffected
- Rollback removes recording rules and dashboard cleanly
- Perses dashboard deploys via kustomize overlay in
  `deployment/components/observability/observability/dashboards/`;
  verify kustomize resource inclusion after upgrade

### 7.3 Performance/Scalability

Prometheus metric cardinality is bounded by the combination of
AuthConfigs, status values, and evaluator names, which constrains
metric volume and prevents unbounded growth. Testing should
verify:

- Query performance for namespace-scoped recording rules
- Cardinality impact on Prometheus storage across maximum
  expected AuthConfigs
- Aggregation correctness with multiple Authorino replicas
- Dashboard query performance with high metric cardinality
- Prometheus scrape targets handle scale across multiple
  AuthConfigs and high request rates
- No performance SLOs are specified in the strategy (flagged as
  a gap)

### 7.4 RBAC/Authorization

The strategy confirms that no sensitive data appears in
Prometheus metric labels and no user-identifying information is
exposed in auth decision metrics. Testing should verify:

- Only authorized users can access Perses dashboards displaying
  auth decision metrics
- ServiceMonitor and PrometheusRule resources respect
  appropriate RBAC roles
- Namespace-scoped access works correctly — users see only
  metrics for namespaces they have permission to access
- No user-identifying information leaks through metric labels
  or dashboard filters

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| `auth_server_*` metrics are lazy-initialized (appear after first auth traffic) | Medium | High | Document initialization behavior; generate test traffic before verification |
| `authconfig` labels are SHA-256 hashes, not human-readable policy names | Medium | High | Accept hash labels for EA1 with documentation mapping; design proper mapping for GA |
| Prometheus datasource gap: recording rules in user-workload Prometheus vs Perses dashboard datasource | High | Medium | Verify `data-science-prometheus-datasource` alignment as first task; if misaligned, reconfigure or prioritize operator lifecycle migration |
| Namespace portability: `kuadrant-system` (ODH) vs `rh-connectivity-link` (RHOAI) | Medium | Medium | Recording rules use `namespace=~"rh-connectivity-link\|kuadrant-system"`; test in both environments |
| Multiple Authorino replicas: aggregation correctness across targets | High | Medium | Verify recording rule PromQL uses `sum by()` grouping; review dashboard queries for correct aggregation |
| NaN in deny ratio when traffic stops (0/0 = NaN) | Low | High | Dashboard stat panels use `or vector(0)` fallback; time series panels use `> -Inf` NaN filter. Alert includes `> 0.001` traffic floor guard to suppress on negligible traffic. |
| Cross-repo coordination latency for opendatahub-operator PRs | Medium | Medium | Engage Platform team early; open draft PR for dashboard manifests for early feedback |
| Counter resets during rolling updates cause transient rate spikes | Medium | High | Verify recording rules use `rate()` or `increase()` (not raw counters); validate during test rollouts |
| ServiceMonitor scrape failures during Authorino unavailability | Medium | Low | Monitor Prometheus target health; verify target recovery after pod restarts |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- OpenShift cluster with RHOAI installed
- Authorino service exposing `/server-metrics` endpoint on port 8080
- Prometheus Operator managing ServiceMonitor and PrometheusRule
  resources
- Perses operator managing dashboard CRDs
- Monitoring namespace for Prometheus components
- Namespaces: `kuadrant-system` (ODH) or `rh-connectivity-link`
  (RHOAI) for Authorino
- Datasource: `data-science-prometheus-datasource` (must query
  same Prometheus instance as `monitoring.coreos.com/v1`
  PrometheusRule)

### 9.2 Configuration

- ServiceMonitor:
  `deployment/base/observability/authorino-server-metrics-servicemonitor.yaml`
- PrometheusRule:
  `deployment/base/observability/authorino-maas-metadata-evaluator-prometheusrule.yaml`
- Recording rules:
  `deployment/base/observability/maas-auth-alerting.rules.yaml`
- Perses dashboard manifests in
  `opt/manifests/dashboard/observability/{rhoai,odh}/`
- Auth decisions dashboard:
  `deployment/components/observability/observability/dashboards/auth-decisions-dashboard.yaml`
- Metric labels: `{authconfig, namespace, status}` — authconfig
  uses SHA-256 hashes, status uses gRPC codes (OK,
  UNAUTHENTICATED, PERMISSION_DENIED, NOT_FOUND)

### 9.3 Test Tools

- `promtool` — unit testing recording rules and alerts
- `kubectl` / `oc` — Kubernetes resource management
- Prometheus API client or `curl` — querying metrics
- Perses API client or `curl` — dashboard verification
- `install-observability.sh` script (maas-controller repo) for
  deployment
- `grpcurl` or similar — testing auth endpoints that generate
  metrics

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| METRICS | 4 | 3 | 1 | 0 |
| RULES | 4 | 4 | 0 | 0 |
| ALERT | 4 | 2 | 2 | 0 |
| DASH | 5 | 4 | 1 | 0 |
| EDGE | 4 | 0 | 3 | 1 |
| PRIVACY | 2 | 0 | 2 | 0 |
| DOC | 1 | 0 | 0 | 1 |
| E2E | 3 | 2 | 1 | 0 |
| **Total** | **27** | **15** | **10** | **2** |

### 10.2 Metric/Component Coverage

| Endpoint | Test Cases | Coverage |
|----------|------------|----------|
| `/server-metrics` (port 8080) | TC-METRICS-001, TC-METRICS-002, TC-E2E-001 | |
| `auth_server_authconfig_response_status` | TC-METRICS-001, TC-METRICS-004, TC-PRIVACY-001, TC-E2E-001 | |
| `auth_server_authconfig_duration_seconds` | TC-METRICS-002, TC-E2E-001 | |
| `auth_server_evaluator_total` | TC-METRICS-003 | |
| `auth_server_evaluator_duration_seconds` | TC-METRICS-003 | |
| `maas:auth_decisions:rate5m` | TC-RULES-001, TC-DASH-002, TC-DASH-004, TC-E2E-001 | |
| `maas:auth_deny_ratio:rate5m` | TC-RULES-002, TC-DASH-003, TC-E2E-001, TC-E2E-002 | |
| `maas:auth_latency_p95:5m` | TC-RULES-003, TC-E2E-001 | |
| `MaaSHighAuthDenyRate` | TC-ALERT-001, TC-ALERT-002, TC-ALERT-003, TC-ALERT-004, TC-E2E-002 | |
| ServiceMonitor | TC-EDGE-002, TC-E2E-001, TC-E2E-003 | |
| PrometheusRule | TC-RULES-004, TC-E2E-001 | |
| Perses Dashboard | TC-DASH-001, TC-E2E-001, TC-E2E-003 | |
| Dashboard panel: Decision totals | TC-DASH-002, TC-E2E-001 | |
| Dashboard panel: Deny rate trends | TC-DASH-003, TC-DASH-004, TC-E2E-001, TC-E2E-002 | |
| Dashboard panel: Latency by policy | TC-DASH-005, TC-E2E-001 | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-14 | Initial test plan |

---

**End of Test Plan**
