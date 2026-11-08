---
test_case_id: TC-FILTER-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-001: filterQuery with equals operator filters by framework

**Objective**: Verify that the filterQuery parameter with the `=` operator
correctly filters agents by framework field.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework = "langgraph"`
2. Verify that only agents with framework `langgraph` are returned

**Expected Results**:

- Response status is HTTP 200
- All items in the response have `customProperties.framework` value
  matching `langgraph`
- Agents with other frameworks (crewai, autogen, etc.) are not present
  in the response
- `size` field reflects the filtered count

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20%3D%20%22langgraph%22"
```

**Notes**: To be filled later in the process.
