---
test_case_id: TC-DASH-005
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DASH-005: Verify authconfig variable filter functionality

**Objective**: Confirm that the `authconfig` ListVariable filter
on the dashboard correctly filters all panels when a specific
policy is selected.

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- Auth traffic generated for at least 2 distinct AuthConfig
  policies (2+ deployed models)

**Test Steps**:

1. Query available authconfig label values:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/label/\
     authconfig/values" | jq '.data'
   ```

2. Select one specific authconfig hash value from the result.
3. Query the decision rate panel with the filter applied:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum(maas:auth_decisions:rate5m{authconfig=\"<hash>\"})\
     or vector(0)" | jq '.data.result[0].value[1]'
   ```

4. Verify the result shows data only for the selected policy.
5. Repeat for the deny ratio panel with the same filter.
6. Verify the "Active policies" stat shows 1 when a single
   authconfig is selected.

**Expected Results**:

- Variable filter returns the list of SHA-256 authconfig hashes
  sourced from `PrometheusLabelValuesVariable`
- Selecting a single authconfig filters all panels to show only
  that policy's data
- "Active policies" stat panel shows 1
- Selecting "$__all" (default) shows data for all policies

**Notes**: To be filled later in the process.
