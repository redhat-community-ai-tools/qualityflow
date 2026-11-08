---
test_case_id: TC-FILTER-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-004: filterQuery with ILIKE operator performs case-insensitive matching

**Objective**: Verify that the filterQuery parameter with the `ILIKE`
operator performs case-insensitive partial string matching.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=name ILIKE "%REACT%"`
2. Verify that agents whose name contains "react" in any case are returned

**Expected Results**:

- Response status is HTTP 200
- Returned agents include names containing `react`, `React`, `REACT`,
  or any mixed case
- ILIKE behaves identically to LIKE except for case sensitivity

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=name%20ILIKE%20%22%25REACT%25%22"
```

**Notes**: To be filled later in the process.
