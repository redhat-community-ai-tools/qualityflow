---
test_case_id: TC-DASH-004
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DASH-004: Verify decisions by status time series panel

**Objective**: Confirm that the "Auth decisions by status" time
series panel shows stacked area chart with separate series for
each gRPC status code.

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- Mixed auth traffic generated producing both OK and non-OK
  statuses

**Test Steps**:

1. Execute the panel's PromQL query:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum by (status) (maas:auth_decisions:rate5m)" | \
     jq '.data.result[] | {status: .metric.status,
     value: .value[1]}'
   ```

2. Verify results contain separate series for `OK` and at
   least one non-OK status (e.g., `UNAUTHENTICATED`).
3. Verify each series has a positive value.
4. On the dashboard, verify the panel renders as a stacked
   area chart (visual configuration: `areaOpacity: 0.6`,
   `stack: all`).

**Expected Results**:

- PromQL query returns multiple series, one per status value
- `OK` series has the highest rate value
- Non-OK series (e.g., `UNAUTHENTICATED`, `PERMISSION_DENIED`)
  have positive values matching generated traffic
- Chart renders as stacked area with distinct series per status

**Notes**: To be filled later in the process.
