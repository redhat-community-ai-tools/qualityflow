---
test_case_id: TC-ALERT-004
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-ALERT-004: Verify alert suppressed on negligible traffic

**Objective**: Confirm that `MaaSHighAuthDenyRate` does NOT fire
when traffic volume is negligible (below the `> 0.001` rps traffic
floor guard), even if the deny ratio is 100%.

**Preconditions**:

- PrometheusRule with `MaaSHighAuthDenyRate` alert applied
- No pre-existing firing alerts for `MaaSHighAuthDenyRate`

**Test Steps**:

1. Send a single denied auth request, then stop all traffic.
2. Wait 15 minutes.
3. Query the Prometheus alerts API:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '.data.alerts[] | select(.labels.alertname ==
     "MaaSHighAuthDenyRate")'
   ```

4. Verify the alert is NOT firing despite the deny ratio being
   1.0 (100%).

**Expected Results**:

- `MaaSHighAuthDenyRate` alert does NOT fire
- The traffic floor guard (`sum(...rate...) > 0.001`) prevents
  alert firing when request rate is negligible
- The deny ratio may show as 1.0 but the volume condition
  prevents the alert from triggering

**Notes**: To be filled later in the process.
