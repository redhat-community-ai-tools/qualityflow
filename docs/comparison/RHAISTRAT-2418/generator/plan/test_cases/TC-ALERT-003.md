---
test_case_id: TC-ALERT-003
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-ALERT-003: Verify alert respects 10-minute sustained window

**Objective**: Confirm that `MaaSHighAuthDenyRate` does NOT fire
before the deny ratio has been sustained for the full 10-minute
`for:` duration.

**Preconditions**:

- PrometheusRule with `MaaSHighAuthDenyRate` alert applied
- No pre-existing firing alerts for `MaaSHighAuthDenyRate`

**Test Steps**:

1. Generate auth traffic with 20% deny rate.
2. After 9 minutes, query the Prometheus alerts API:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '.data.alerts[] | select(.labels.alertname ==
     "MaaSHighAuthDenyRate")'
   ```

3. Verify alert is NOT in `firing` state (may be `pending`).
4. Continue traffic for 2 more minutes (total 11 minutes).
5. Query the alerts API again.
6. Verify the alert is now in `firing` state.

**Expected Results**:

- At 9 minutes: alert is either absent or in `pending` state,
  NOT `firing`
- At 11 minutes: alert transitions to `firing` state
- The `for: 10m` duration is respected — no premature firing

**Notes**: To be filled later in the process.
