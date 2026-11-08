---
test_case_id: TC-EDGE-002
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---
# TC-EDGE-002: Verify ServiceMonitor target recovery after pod restart

**Objective**: Confirm that the ServiceMonitor target for Authorino
recovers to "up" status after an Authorino pod restart, and that
no alerts fire spuriously during the restart window.

**Preconditions**:

- ServiceMonitor `authorino-server-metrics-servicemonitor` applied
- Authorino pods running and scrape target showing "up"
- Auth traffic flowing to generate baseline metrics

**Test Steps**:

1. Verify the Authorino scrape target is currently "up":

   ```bash
   curl -s "https://<prometheus-route>/api/v1/targets" | \
     jq '.data.activeTargets[] |
     select(.labels.job == "authorino-server-metrics") |
     .health'
   ```

2. Delete the Authorino pod to trigger a restart:

   ```bash
   kubectl delete pod -n <authorino-namespace> \
     -l app=authorino --wait=false
   ```

3. Immediately check target health — expect "down" during restart.
4. Wait for the pod to become ready (check pod status).
5. Re-check target health — expect "up" within 2 scrape intervals
   (default 30s each, so within ~60 seconds).
6. Check that `MaaSHighAuthDenyRate` did NOT fire during the
   restart window.

**Expected Results**:

- Target transitions from "up" to "down" during pod restart
- Target recovers to "up" within 2 scrape intervals after pod
  is ready
- `MaaSHighAuthDenyRate` alert does NOT fire during the restart
  window (traffic floor guard prevents spurious firing)
- Metrics resume after pod restart with no data gaps longer than
  2 scrape intervals

**Notes**: To be filled later in the process.
