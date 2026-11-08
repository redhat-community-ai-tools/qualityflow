# RHAISTRAT-2418: run 5 (both tools on GLM 5.3), test grading

Product: models-as-a-service at 05a5ff90 (MaaS below). Suite: opendatahub-tests at 7ffaacc (ODH below).

What shipped (re-checked in the run-5 checkout, unchanged from runs 3 and 4):
- The Authorino `/server-metrics` ServiceMonitor `authorino-server-metrics`, interval 30s
  (MaaS deployment/base/observability/authorino-server-metrics-servicemonitor.yaml:15-32).
- The raw metrics `auth_server_authconfig_response_status{namespace,authconfig,status}`,
  `auth_server_authconfig_duration_seconds{namespace,authconfig}` and
  `auth_server_evaluator_total{...,evaluator_type,evaluator_name}` (docs/content/observability/metrics-and-dashboards.md:59-68).
- The alerts `MaaSAuthorinoAuthenticationHighFailureRate` (UNAUTHENTICATED ratio > 0.10, floor > 0.001 rps, `for: 5m`) and
  `MaaSAuthorinoAuthenticationHighLatency` (authorino-maas-oidc-prometheusrule.yaml:20-55).

None of the ticket's proposed names ship. A repo-wide grep finds no `maas:auth_decisions:rate5m`,
`maas:auth_deny_ratio:rate5m`, `maas:auth_latency_p95:5m`, `MaaSHighAuthDenyRate` or `promtool`.
deployment/base/observability/ has no `maas-auth-alerting.*` file, and
deployment/components/observability/observability/dashboards/ holds only usage-dashboard.yaml.

## QualityFlow tests

None. Run 5 wrote nothing (`files: []`, both diffs empty, `verification: skipped`); all 24 scenarios are in
`not_implemented`. This time the summary lists the missing product interfaces correctly
(`product_interface_status.missing_product_interfaces`), and its `product_refs` cite real lines.

| test (file::name) | plan case | class | evidence |
|---|---|---|---|
| (none) | | | |

## QualityFlow declines (`not_implemented`, 24)

Twenty-one declines are right: those cases depend on recording rules, an alert, a dashboard or a catalog that did not ship.
Three cases can be carried by the shipped raw metrics plus the suite's MaaS fixtures, and the reasons given for them are
false. Each says "the suite has no AuthConfig-policy or allowed/denied credential fixture" (1, 20) or "no fixture for a
controlled outage" (2).

| plan case | class | evidence |
|---|---|---|
| 1 policy auth-decision deltas match the recorded requests by authconfig, namespace and status | AVOIDABLE | The counter with exactly those labels ships (metrics-and-dashboards.md:65), so deltas need no recording rule. The suite has two independent MaaS auth policies (ODH tests/ai_gateway/models_as_a_service/conftest.py:1333 `maas_auth_policy_tinyllama_free`, :1383 `maas_auth_policy_tinyllama_modelcar`), a model URL and API key, so an absent or bad key gives the denied case (observability/conftest.py:407-446), and the RHOAI Thanos client (observability/conftest.py:144-166) |
| 2 auth metrics target returns to up and fresh decision samples appear after an outage | AVOIDABLE | The suite already patches and rolls out the Authorino deployment and waits for `Available` (models_as_a_service/conftest.py:932-1013), and polls a metric to a value (observability/test_maas_observability.py:41-56, `validate_metrics_field`). The scrape target ships (servicemonitor.yaml:15-32), and fresh samples are the raw counter. Only the "agreed recovery bound" would be a chosen timeout |
| 20 auth decision series carry only policy, namespace, status and standard labels | AVOIDABLE | Send traffic through the two policies with the suite's key fixtures (as in case 1), then read the label set of the shipped `auth_server_authconfig_response_status` (metrics-and-dashboards.md:65) through `maas_observability_prometheus` (observability/conftest.py:144-166). The test needs no new helper: a set comparison on the result's `metric` dict is enough |
| 3, 4, 5, 6 recording-rule rates, deny ratios, latency P95, zero-denial ratio | JUSTIFIED (4) | `maas:auth_decisions:rate5m`, `maas:auth_deny_ratio:rate5m` and `maas:auth_latency_p95:5m` do not ship; deployment/base/observability/ has no recording rule. P95 exists only inside the alert expression (oidc prometheusrule.yaml:47-50), and there is no promtool harness |
| 7-12 auth-decisions dashboard (totals, latency, unavailable data, cold start, stopped traffic, restart spikes) | JUSTIFIED (6) | No auth-decisions dashboard ships; dashboards/ holds only usage-dashboard.yaml |
| 13 monitoring configuration survives the upgrade | JUSTIFIED | The preconditions are "stored monitoring rules and a configured dashboard" with before/after dashboard values, and the dashboard and rules do not ship. Half the stated reason is false: the suite does have MaaS upgrade tests (models_as_a_service/upgrade/test_maas_upgrade.py) |
| 14, 15, 16, 17 `MaaSHighAuthDenyRate` pending/firing, threshold, burst, negligible-traffic rule tests | JUSTIFIED (4) | The alert does not ship. The shipped `MaaSAuthorinoAuthenticationHighFailureRate` uses `for: 5m`, not ten minutes, and counts only UNAUTHENTICATED (oidc prometheusrule.yaml:28-36). Its >10% and >0.001 values match 15 and 17, but there is no rule-unit harness for the planned timestamped series |
| 18, 19 deployed warning during rollouts / sustained denials | JUSTIFIED (2) | Both are about the approved `MaaSHighAuthDenyRate` warning, which is not shipped (oidc prometheusrule.yaml:20 is a different alert with a different duration) |
| 21 ODH and RHOAI namespace variants side by side | JUSTIFIED | A cluster runs one of kuadrant-system and rh-connectivity-link, and the suite picks whichever exists (models_as_a_service/conftest.py:934-940). The case compares the two |
| 22 policy aggregate equals the sum over replicas | JUSTIFIED | The "policy aggregate" is the recording-rule output, which does not ship. The suite has no multi-replica Authorino fixture |
| 23, 24 metrics catalog completeness; catalog examples answer auth questions | JUSTIFIED (2) | The only catalog is a docs table (metrics-and-dashboards.md:59-68) with no value domains, operator questions or authentication example queries. Its "Common Queries" use `authorized_hits`/`authorized_calls` |

Totals: 3 AVOIDABLE, 21 JUSTIFIED. These are the same verdicts as run 4.

## Test Plan Generator tests (tests/authorino_auth_decision_metrics/)

Rule, the same as for RHAISTRAT-2277. A test that skips unless an env var nothing in the suite sets
(`AUTHORINO_CHECK_URL`, `AUTHORINO_METRICS_URL`, `PERSES_DASHBOARD_URL`, `RHOAI_METRICS_CATALOG_PATH`, `MAAS_REPO_PATH`)
cannot be REAL. The suite's own Authorino and MaaS fixtures exist (above). The Prometheus tests use the suite's
`prometheus` fixture (ODH tests/conftest.py:931-937, cluster thanos-querier). None of them generates its own traffic except
the ALERT tests.

| test (file::name) | plan case | class | evidence |
|---|---|---|---|
| test_alert_...::test_tc_alert_001 | TC-ALERT-001 alert fires after a sustained breach | WRONG | `MaaSHighAuthDenyRate` (`:13`) is not shipped. The shipped alert is `MaaSAuthorinoAuthenticationHighFailureRate`, `for: 5m` (oidc prometheusrule.yaml:20, :36) |
| test_alert_...::test_tc_alert_002 | TC-ALERT-002 inactive at or below 10% | WRONG | Queries `maas:auth_deny_ratio:rate5m` (`:147`), which is not shipped, and checks the unshipped alert |
| test_alert_...::test_tc_alert_003 | TC-ALERT-003 waits the full 10 minutes | WRONG | The unshipped alert, and the shipped duration is 5m, not 10 (oidc prometheusrule.yaml:36) |
| test_alert_...::test_tc_alert_004 | TC-ALERT-004 negligible traffic does not fire | WRONG | Asserts that the unshipped `MaaSHighAuthDenyRate` is not firing (`:212-213`), which passes vacuously. The shipped floor sits in a differently named alert (oidc prometheusrule.yaml:34-35) |
| test_dash_...::test_tc_dash_001 | TC-DASH-001 dashboard deployed | WRONG | Expects Perses dashboard `dashboard-4-maas-auth-decisions-admin` with eight panels (`:11-22`). Only usage-dashboard.yaml ships |
| test_dash_...::test_tc_dash_002 | TC-DASH-002 decision-rate panel | WRONG | The raw-metric query is real, but the test ends by requiring the unshipped dashboard (`:76`, `_get_dashboard` asserts 200). It also sends no traffic |
| test_dash_...::test_tc_dash_003 | TC-DASH-003 deny-rate panel | WRONG | Expects about 25% denial with no traffic generated (`:92`), then requires the unshipped dashboard (`:93`) |
| test_dash_...::test_tc_dash_004 | TC-DASH-004 status-series panel | WRONG | The OK / non-OK status check on the raw metric is right (`:101-111`), but the case is the dashboard's status panel, and the test requires the unshipped dashboard (`:112`) |
| test_dash_...::test_tc_dash_005 | TC-DASH-005 authconfig filter | WRONG | No shipped dashboard has an `authconfig` variable; usage-dashboard.yaml filters by user, subscription and model. The test requires the unshipped dashboard (`:142`) |
| test_doc_...::test_tc_doc_001 | TC-DOC-001 catalog documents the metrics | WRONG | Requires the `maas:*` rules, `MaaSHighAuthDenyRate` and "SHA-256" in the catalog (`:14-17`, `:46`). None appears in metrics-and-dashboards.md:56-78. It reads an env-path file, not the product |
| test_e2e_...::test_tc_e2e_001 | TC-E2E-001 raw metrics, rules, dashboard from live traffic | WRONG | Requires `maas:auth_latency_p95:5m` (`:60`), which is not shipped. It also expects about 20% denial without generating traffic |
| test_e2e_...::test_tc_e2e_002 | TC-E2E-002 breach fires and resolves the alert | WRONG | `MaaSHighAuthDenyRate` and `maas:auth_deny_ratio:rate5m` (`:70-78`) are not shipped |
| test_e2e_...::test_tc_e2e_003 | TC-E2E-003 survives an Authorino rollout | WRONG | The rollout patch is real (`:96-109`), but the before and after values are the unshipped `maas:auth_decisions:rate5m` (`:91`, `:115`) |
| test_edge_...::test_tc_edge_001 | TC-EDGE-001 dashboard shows safe zeros at cold start | WEAK | It uses shipped raw-metric names with `or vector(0)` (`:43-63`), but never creates a cold start and never reads the panels the case is about. It asserts zero policies on whatever cluster it meets, so it passes only on a cluster that has never seen auth traffic |
| test_edge_...::test_tc_edge_002 | TC-EDGE-002 target recovers after a pod restart | WEAK | It really restarts Authorino (annotation patch, `:79-92`) and polls `up` back to 1. Gaps: it never sees the target go down, its alert check is the unshipped `MaaSHighAuthDenyRate` (`:105`, vacuous), and `job="authorino-server-metrics"` is the ServiceMonitor's name. The ServiceMonitor sets no `jobLabel` (servicemonitor.yaml:23-32), so Prometheus labels `job` with the Service name, which is not in the checkouts |
| test_edge_...::test_tc_edge_003 | TC-EDGE-003 rates survive counter resets | WRONG | Samples the unshipped `maas:auth_decisions:rate5m` (`:118`, `:140`) |
| test_edge_...::test_tc_edge_004 | TC-EDGE-004 rules aggregate replicas | WRONG | Compares against the unshipped `maas:auth_decisions:rate5m` (`:171`, `:178`) |
| test_metrics_...::test_tc_metrics_001 | TC-METRICS-001 counter and labels | WEAK | It now checks the right label names and no user labels on the shipped counter (`:40-51`). It needs the `AUTHORINO_METRICS_URL` env var, sends no traffic, and does not check the gRPC-code status or hash value formats |
| test_metrics_...::test_tc_metrics_002 | TC-METRICS-002 latency histogram | WEAK | Buckets with `le`, non-zero `_count`/`_sum`, `authconfig`/`namespace` labels on the shipped histogram (`:58-69`) fit the TC. It needs the env URL and sends no traffic |
| test_metrics_...::test_tc_metrics_003 | TC-METRICS-003 evaluator metrics | WEAK | It now uses the shipped `evaluator_name`/`evaluator_type` labels (`:84-86`; metrics-and-dashboards.md:66). It needs the env URL and sends no traffic. `auth_server_evaluator_duration_seconds` is not in the MaaS catalog table, though it is an upstream Authorino metric |
| test_metrics_...::test_tc_metrics_004 | TC-METRICS-004 authconfig labels are hashes of the AuthConfigs | WEAK | It uses real fixtures only (admin_client AuthConfig list plus `prometheus`) and the shipped counter. But its key assertion is that labels equal `sha256(AuthConfig name)` (`:100-117`), a rule nothing in the checkouts defines, and not the TC's match against the resource names. It also sets AuthConfigs from every namespace against only the series that have traffic |
| test_privacy_...::test_tc_privacy_001 | TC-PRIVACY-001 no identity labels | WEAK | The forbidden set now matches the TC (`:12-18`), on the shipped metrics. It needs the env URL, sends no identity-bearing traffic, and does not check that the label set is limited to the allowed ones |
| test_privacy_...::test_tc_privacy_002 | TC-PRIVACY-002 dashboard exposes no identity data | WRONG | The case and the second half of the test target the unshipped auth-decisions dashboard (`:77-89`); dashboards/ holds only usage-dashboard.yaml |
| test_rules_...::test_tc_rules_001 | TC-RULES-001 decisions rate rule | WRONG | `maas:auth_decisions:rate5m` (`:24`) is not shipped |
| test_rules_...::test_tc_rules_002 | TC-RULES-002 deny-ratio rule | WRONG | `maas:auth_deny_ratio:rate5m` (`:39`) is not shipped |
| test_rules_...::test_tc_rules_003 | TC-RULES-003 P95 rule | WRONG | `maas:auth_latency_p95:5m` (`:55`) is not shipped |
| test_rules_...::test_tc_rules_004 | TC-RULES-004 promtool unit suite | WRONG | Runs promtool on `deployment/base/observability/maas-auth-alerting.unit-tests.yaml` (`:77`), which does not exist. It reads the repo, not the product |

Loads: 27/27 (`--setup-plan` re-run: 27 collected, no errors).

## Test Plan Generator skips

None. All 27 plan cases have a test function.

SCORE RHAISTRAT-2418 | QF tests=0 real=0 weak=0 hollow=0 wrong=0 loads=0 declined=24 justified=21 avoidable=3 cases=24 real_cases=0 | GEN tests=27 real=0 weak=7 hollow=0 wrong=20 loads=27 declined=0 justified=0 avoidable=0 cases=27 real_cases=0
