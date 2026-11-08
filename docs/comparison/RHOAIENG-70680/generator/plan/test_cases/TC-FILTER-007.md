---
test_case_id: TC-FILTER-007
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-007: filterQuery with OR matches either condition

**Objective**: Verify that the filterQuery parameter with the `OR`
logical operator returns agents matching either condition.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework = "autogen" OR framework = "langflow"`
2. Verify that agents matching either condition are returned

**Expected Results**:

- Response status is HTTP 200
- Every returned agent has `customProperties.framework` equal to
  `autogen` or `langflow`
- The result set is the union of agents matching each individual condition
- `size` equals the sum of autogen agents plus langflow agents

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20%3D%20%22autogen%22%20OR%20framework%20%3D%20%22langflow%22"
```

**Notes**: To be filled later in the process.
