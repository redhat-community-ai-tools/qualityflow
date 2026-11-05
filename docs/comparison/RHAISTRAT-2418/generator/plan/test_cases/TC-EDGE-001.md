---
test_case_id: TC-EDGE-001
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-EDGE-001: Verify dashboard handles zero auth traffic gracefully

**Objective**: Confirm that dashboard panels display zero or empty
states gracefully when no auth traffic has been generated (cold
start scenario).

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- No auth traffic generated (or traffic stopped for >10 minutes
  so rate windows expire)

**Test Steps**:

1. Verify no active auth traffic is flowing.
2. Query the decision rate stat panel query:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum(maas:auth_decisions:rate5m) or vector(0)" | \
     jq '.data.result[0].value[1]'
   ```

3. Verify the result is `0` (the `or vector(0)` fallback).
4. Query the deny rate stat panel query:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     ((sum(maas:auth_decisions:rate5m{status!=\"OK\"}) / \
     sum(maas:auth_decisions:rate5m)) > -Inf) or vector(0)" | \
     jq '.data.result[0].value[1]'
   ```

5. Verify the result is `0` (NaN filtered by `> -Inf`, fallback
   to `vector(0)`).
6. Verify the time series panels show empty graphs (no data
   points), not error states.

**Expected Results**:

- "Auth decisions/sec" stat panel shows 0, not NaN or error
- "Deny rate" stat panel shows 0%, not NaN or error
- "Active policies" stat panel shows 0
- Time series panels show empty graph area, no error messages
- No JavaScript errors or rendering failures in the dashboard

**Notes**: To be filled later in the process.
