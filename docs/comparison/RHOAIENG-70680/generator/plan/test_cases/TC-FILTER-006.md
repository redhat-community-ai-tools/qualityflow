---
test_case_id: TC-FILTER-006
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-006: filterQuery with AND combines multiple conditions

**Objective**: Verify that the filterQuery parameter with the `AND`
logical operator correctly combines two filter conditions.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework = "langgraph" AND agentType = "conversational"`
2. Verify that only agents matching both conditions are returned

**Expected Results**:

- Response status is HTTP 200
- Every returned agent has `customProperties.framework` equal to
  `langgraph` AND `customProperties.agentType` equal to `conversational`
- Agents matching only one condition are excluded

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20%3D%20%22langgraph%22%20AND%20agentType%20%3D%20%22conversational%22"
```

**Notes**: To be filled later in the process.
