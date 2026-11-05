---
test_case_id: TC-SEARCH-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SEARCH-004: Combined search and filter narrows results

**Objective**: Verify that the `q` keyword search parameter works
correctly in combination with the `filterQuery` parameter.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `q=agent&filterQuery=framework = "langgraph"`
2. Verify that results match both the keyword and filter criteria

**Expected Results**:

- Response status is HTTP 200
- All returned agents match the keyword `agent` in a searchable field
  AND have framework equal to `langgraph`
- The combined result is the intersection of both filters
- `size` is less than or equal to either filter applied individually

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?q=agent&filterQuery=framework%20%3D%20%22langgraph%22"
```

**Notes**: To be filled later in the process.
