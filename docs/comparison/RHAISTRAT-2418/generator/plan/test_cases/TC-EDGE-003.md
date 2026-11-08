---
test_case_id: TC-EDGE-003
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---
# TC-EDGE-003: Verify counter reset handling during rolling update

**Objective**: Confirm that recording rules using `rate()` and
`increase()` handle Prometheus counter resets correctly during
Authorino rolling updates — no negative spikes or incorrect values
appear in dashboard panels.

**Preconditions**:

- Auth traffic flowing to generate baseline metrics
- Dashboard deployed and showing data

**Test Steps**:

1. Record current values of `maas:auth_decisions:rate5m` and
   `maas:auth_deny_ratio:rate5m` as a baseline.
2. Trigger a rolling update of Authorino:

   ```bash
   kubectl rollout restart deployment/authorino \
     -n <authorino-namespace>
   ```

3. Monitor recording rule outputs every 30 seconds during the
   rollout (expected duration: 2-5 minutes):

   ```bash
   while true; do
     curl -s "https://<prometheus-route>/api/v1/query?query=\
       maas:auth_decisions:rate5m" | \
       jq '.data.result[].value[1]'
     sleep 30
   done
   ```

4. Verify no negative values appear in any rate output.
5. After rollout completes, verify rates return to approximately
   the baseline level.
6. Check dashboard time series panels for visual anomalies
   (negative spikes, sudden drops to zero).

**Expected Results**:

- `rate()` function handles counter resets automatically — no
  negative values in recording rule outputs
- Dashboard time series panels show a brief dip (acceptable)
  but no negative spikes
- Rates recover to baseline levels within 5 minutes of rollout
  completion
- `MaaSHighAuthDenyRate` alert does NOT fire spuriously during
  the rolling update

**Notes**: To be filled later in the process.
