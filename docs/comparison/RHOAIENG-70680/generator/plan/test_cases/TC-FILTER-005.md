---
test_case_id: TC-FILTER-005
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-005: filterQuery with IN operator matches multiple values

**Objective**: Verify that the filterQuery parameter with the `IN` operator
matches agents whose field value is in the provided list.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework IN ("langgraph", "crewai")`
2. Verify that only agents with framework `langgraph` or `crewai`
   are returned

**Expected Results**:

- Response status is HTTP 200
- Every returned agent has `customProperties.framework` value of either
  `langgraph` or `crewai`
- Agents with other framework values (autogen, claude-code, langflow) are
  excluded
- `size` equals the sum of langgraph and crewai agents

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20IN%20(%22langgraph%22%2C%20%22crewai%22)"
```

**Notes**: To be filled later in the process.
