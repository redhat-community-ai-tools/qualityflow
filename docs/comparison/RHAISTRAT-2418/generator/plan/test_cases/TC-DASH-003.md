---
test_case_id: TC-DASH-003
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DASH-003: Verify deny rate stat panel shows correct percentage

**Objective**: Confirm that the "Deny rate" stat panel shows the
correct deny percentage after generating mixed OK/denied traffic.

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- Mixed auth traffic with known deny ratio generated for at least
  5 minutes (e.g., 75% OK, 25% denied)

**Test Steps**:

1. Execute the panel's PromQL query:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     (sum(maas:auth_decisions:rate5m{status!=\"OK\"}) / \
     sum(maas:auth_decisions:rate5m)) > -Inf" | \
     jq '.data.result[0].value[1]'
   ```

2. Verify the value is approximately 0.25 (25%).
3. Verify the stat panel displays the value as a percentage
   (format: `percent-decimal`).

**Expected Results**:

- PromQL query returns a value of approximately 0.25
- The stat panel displays approximately "25.0%" (matching the
  generated traffic ratio within 5 percentage points)
- The `> -Inf` NaN filter removes any NaN values from the
  calculation

**Notes**: To be filled later in the process.
