---
test_case_id: TC-ALERT-002
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-ALERT-002: Verify alert does not fire at low deny rate

**Objective**: Confirm that `MaaSHighAuthDenyRate` does NOT fire
when the deny ratio is at or below 10%.

**Preconditions**:

- PrometheusRule with `MaaSHighAuthDenyRate` alert applied
- No pre-existing firing alerts for `MaaSHighAuthDenyRate`

**Test Steps**:

1. Generate auth traffic with approximately 5% deny rate for
   15 minutes: 95% valid requests and 5% invalid requests.
2. After 15 minutes, query the Prometheus alerts API:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '.data.alerts[] | select(.labels.alertname ==
     "MaaSHighAuthDenyRate")'
   ```

3. Verify the alert is NOT present or is in `inactive` state.

**Expected Results**:

- `MaaSHighAuthDenyRate` alert does NOT appear in firing alerts
- The deny ratio recording rule `maas:auth_deny_ratio:rate5m`
  shows a value of approximately 0.05 (below the 0.1 threshold)

**Notes**: To be filled later in the process.
