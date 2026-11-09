# RHAISTRAT-2418 (per-policy Authorino auth decision metrics): run 10 grading (QF main 3b7ffa3, GLM 5.3)

Product: models-as-a-service at 05a5ff90 (cited `maas:`). Suite: opendatahub-tests at 7ffaaccc (cited `odh:`).
R = <local> O = R/qf/outputs/RHAISTRAT-2418. QF test: `odh:tests/ai_gateway/models_as_a_service/observability/test_qf_auth_decision_metrics.py` (cited `T:`).

## What shipped, and does the plan stay with it?

- **Shipped:**
  - ServiceMonitor `authorino-server-metrics`, scraping `/server-metrics` every 30s (maas:deployment/base/observability/authorino-server-metrics-servicemonitor.yaml:18,28-32).
    It is applied by install-observability.sh only when nothing else scrapes `/server-metrics` (maas:scripts/observability/install-observability.sh:74-81).
  - Counter `auth_server_authconfig_response_status` with labels `namespace, authconfig, status` (maas:docs/content/observability/metrics-and-dashboards.md:65).
  - Alerts on it: `MaaSAuthorinoAuthenticationHighFailureRate` and `...HighLatency` (maas:deployment/base/observability/authorino-maas-oidc-prometheusrule.yaml:20-55), plus `MaaSAuthorinoMetadataEvaluatorHighFailureRate` (authorino-maas-metadata-evaluator-prometheusrule.yaml:19-37).
- **Not shipped:** a repo-wide grep finds 0 hits for `MaaSHighAuthDenyRate`, `maas:auth_`, `auth-decisions`,
  `maas-auth-alerting`, `cluster-prometheus-datasource` and `ensureAuthDecisionsDashboard`.
  - The only dashboard maas-controller ensures is the usage one, behind `usageMetricsDashboard` (maas:maas-controller/pkg/controller/maas/self_deployment_controller.go:464,538-565).
- **The plan does not stay with what shipped.** As in runs 6 and 7, it was built from the open, held PR #1363.
  - QF knew this. The regression analysis says the new symbols exist "only in open PR #1363" (O/stp/RHAISTRAT-2418_regression_analysis.yaml:2,17,198). The STP mentions the open PR (test_plan.md:97) and leaves the "implementation available in the test build" entry criterion unchecked.
  - Even so, 12 of 14 scenarios test PR #1363 content: recording rules, `MaaSHighAuthDenyRate`, an auth-decisions Perses dashboard, a promtool test file and the controller hook.
- **The tests mostly do stay with what shipped:**
  - The two REAL tests query the shipped counter.
  - 11 of 12 PR-only scenarios were declined, with correct reasons.
  - The exception is TS-13: its test asserts on the unshipped alert.
- **Team file edited:** QF edited the team's `observability/conftest.py`. It added only a `pytest_configure` that registers the `qf_test_id` marker (odh:...observability/conftest.py:453-458). The suite runs `--strict-markers` (odh:pytest.ini:78). No fixture was redefined.
- **Loading:** 3 collected, `--setup-plan` clean (loading/RHAISTRAT-2418.md).

## 1. QF tests (3)

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| T::TestQFAuthDecisionMetrics::test_qf_per_policy_authorization_metrics_are_collected | TS-01 counter non-empty with authconfig/namespace/status | REAL | **What it does:** sends one allowed request and one with an invalid key (expects 401/403) through `verify_chat_completions` (odh:tests/ai_gateway/models_as_a_service/utils.py:380-431). It then polls the shipped counter on the cluster thanos-querier (odh:tests/conftest.py:931-937) and asserts the three labels (T:79-102; metric at metrics-and-dashboards.md:65; the same selector as oidc-prometheusrule.yaml:30). **Caveat:** it lacks the `minimal_subscription_for_modelcar` and `maas_auth_policy_tinyllama_modelcar` usefixtures that the suite's own usage-logs class applies (odh:.../observability/test_maas_usage_logs.py:20-25). Without them, API-key creation needs a subscription (odh:tests/ai_gateway/models_as_a_service/conftest.py:1480-1483), and `maas_gateway_auth_policy_ready` falls back to the free-tier policy (conftest.py:1031-1032). So the modelcar's authorized request most likely fails before the metric check |
| T::TestQFAuthDecisionMetrics::test_qf_authorization_metrics_omit_user_identity | TS-02 no user-identity labels | REAL | Same traffic. It then asserts that no series of the shipped counter carries `enduser.id`, `user`, `cost_center`, `organization_id` or `subscription` (T:117-141). That is the scenario's exact assertion, on the real metric. Same setup caveat as TS-01 |
| T::TestQFAuthDecisionMetrics::test_qf_authorino_target_recovers_without_spurious_alert | TS-13 target up after restart, no spurious alert | WRONG | **Unshipped alert:** it asserts that `ALERTS{alertname="MaaSHighAuthDenyRate"}` is empty (T:27,179-181). That alert does not exist (0 hits), so the assertion is vacuous and can never fail. The shipped deny alert is `MaaSAuthorinoAuthenticationHighFailureRate` (oidc-prometheusrule.yaml:20). **Other defects:** the target check queries `up{exported_job=~".*authorino.*"}` (T:26). Prometheus's per-target `up` series for a ServiceMonitor target carries `job`, not `exported_job`, and the suite never uses `exported_job`. The test also waits for `Available=False` after scaling to 0 (T:155-166), which a Deployment at 0 replicas does not report |

## 2. not_implemented (11)

| scenario | class | evidence (one line) |
|---|---|---|
| TS-03 dashboard panels show decisions and deny rate | JUSTIFIED | No auth-decisions PersesDashboard ships. The only dashboard is the usage one (deployment/components/observability/observability/dashboards/usage-dashboard.yaml; self_deployment_controller.go:538-565) |
| TS-04 dashboard datasource resolves `maas:auth_*` rules | JUSTIFIED | 0 hits for `cluster-prometheus-datasource` and `maas:auth_` |
| TS-05 dashboard at zero traffic | JUSTIFIED | No auth dashboard |
| TS-06 dashboard across counter resets | JUSTIFIED | No auth dashboard and no recording rules |
| TS-07 MaaSHighAuthDenyRate fires (warning) | JUSTIFIED | Alert not shipped. The shipped analogue (oidc-prometheusrule.yaml:20-38) is not per-policy and uses `for: 5m`, not 10m |
| TS-08 alert silent at or below 10% | JUSTIFIED | Same alert |
| TS-09 alert silent before 10 min | JUSTIFIED | Same alert. The shipped analogue's hold is 5m (:36) |
| TS-10 alert respects traffic floor | JUSTIFIED | Same alert. The shipped analogue does have a 0.001 floor (:35), but the scenario names the unshipped alert |
| TS-11 promtool `maas-auth-alerting.unit-tests.yaml` passes | JUSTIFIED | The file is not in the repo (0 hits) |
| TS-12 auth dashboard deploys with usage gate off | JUSTIFIED | No `ensureAuthDecisionsDashboard`. Only `ensureUsageDashboard`, gated on `usageMetricsDashboard` (self_deployment_controller.go:564-565) |
| TS-14 catalog has scrape interval and two example queries | JUSTIFIED | The shipped Authorino table has name, type, labels, description and the endpoint (metrics-and-dashboards.md:57-71). It has no scrape interval and no example operator queries (:57-85) |

## 3. existing_coverage

None claimed (`existing_coverage_count: 0`, std yaml:24; the summary has no `existing_coverage`). That is accurate: the suite has no test of any `auth_server_*` metric (grep: only the QF file).

| scenario | named test | verdict | evidence |
|---|---|---|---|
| none | | | |

## 4. The plan

- **12 of 14 scenarios expect behaviour the shipped code does not have.** All of it comes from the held PR #1363:
  - TS-03 to TS-06: auth-decisions dashboard, its datasource, `maas:auth_*` rules.
  - TS-07 to TS-10: `MaaSHighAuthDenyRate`.
  - TS-11: promtool file.
  - TS-12: controller hook.
  - TS-13: names `MaaSHighAuthDenyRate`. Its target-up half is shipped.
  - TS-14: doc fields absent at metrics-and-dashboards.md:57-85.
- Only TS-01 and TS-02 rest on shipped code: the raw counter and its labels.
- **Compared with run 7 (20 scenarios, 15 unshipped):**
  - The plan is smaller and now mentions the open PR.
  - It still plans against it rather than against main.
- **What the plan misses of what did ship:**
  - The shipped auth alerts: `MaaSAuthorinoAuthenticationHighFailureRate` and `HighLatency` (oidc-prometheusrule.yaml:20-55). These are the real 10%-deny-style alert.
  - `MaaSAuthorinoMetadataEvaluatorHighFailureRate` (metadata-evaluator-prometheusrule.yaml:19-37).
  - The `auth_server_evaluator_*` metrics (metrics-and-dashboards.md:67-68).
  - The ServiceMonitor's own spec: `/server-metrics`, 30s (servicemonitor.yaml:28-32).
  - install-observability.sh's skip-if-already-scraped branch (:76-77).

## 5. Acceptance criteria

`main_issue.acceptance_criteria` is one block of 10 items, each starting "Given…" or a statement. The ticket itself refers to "AC #10". Items are numbered in order.
AC-2, 3, 4, 6, 8 and 10 describe PR #1363 work that did not ship, so they are covered on paper only.

| AC | text (short) | verdict | plan scenario |
|---|---|---|---|
| AC-1 | Prometheus has `auth_server_authconfig_response_status` with authconfig/namespace/status | COVERED | TS-01 |
| AC-2 | Perses panel shows per-policy allow/deny and deny rate via cluster-prometheus-datasource | COVERED | TS-03 |
| AC-3 | MaaSHighAuthDenyRate fires at >10% for 10 min, warning | COVERED | TS-07 (+TS-08 to TS-10) |
| AC-4 | promtool unit tests for new rules and alerts pass | COVERED | TS-11 |
| AC-5 | metrics catalog entry with all fields and two example queries | COVERED | TS-14 |
| AC-6 | dashboard shows no data or zero gracefully at cold start | COVERED | TS-05 |
| AC-7 | target recovers to up after restart, no spurious alerts | COVERED | TS-13 |
| AC-8 | counter resets handled, no negative spikes | COVERED | TS-06 |
| AC-9 | no user-identifying labels on the counter | COVERED | TS-02 |
| AC-10 | dashboard data verified through its own declared datasource | COVERED | TS-04 |

SCORE RHAISTRAT-2418 | QF tests=3 real=2 weak=0 hollow=0 wrong=1 loads=3 declined=11 justified=11 avoidable=0 cases=14 real_cases=2 covered=0 verified=0 partial=0 false=0 plan_wrong=12 acs=10 ac_covered=10 ac_out_of_scope=0 ac_missed=0
