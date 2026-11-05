---
test_case_id: TC-FILTER-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-003: filterQuery with LIKE operator performs partial matching

**Objective**: Verify that the filterQuery parameter with the `LIKE`
operator performs case-sensitive partial string matching on agent fields.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=name LIKE "%react%"`
2. Verify that only agents whose name contains "react" are returned

**Expected Results**:

- Response status is HTTP 200
- All returned agent names contain the substring `react` (case-sensitive)
- Agents without `react` in their name are excluded
- The `%` wildcard matches zero or more characters

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=name%20LIKE%20%22%25react%25%22"
```

**Notes**: To be filled later in the process.
