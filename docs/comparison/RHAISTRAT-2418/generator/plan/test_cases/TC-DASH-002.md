---
test_case_id: TC-DASH-002
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DASH-002: Verify decision rate stat panel shows data

**Objective**: Confirm that the "Auth decisions/sec" stat panel
shows a non-zero value after generating auth traffic.

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- Auth traffic generated for at least 5 minutes

**Test Steps**:

1. Execute the panel's PromQL query directly:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum(maas:auth_decisions:rate5m) or vector(0)" | \
     jq '.data.result[0].value[1]'
   ```

2. Verify the returned value is a positive number.
3. Access the Perses dashboard via the Perses API or UI.
4. Verify the "Auth decisions/sec" stat panel displays a
   non-zero decimal value.

**Expected Results**:

- PromQL query returns a positive value matching the traffic rate
- The stat panel renders a numeric value (not "No data", NaN,
  or an error)
- The `or vector(0)` fallback is not active (traffic is flowing)

**Notes**: To be filled later in the process.
