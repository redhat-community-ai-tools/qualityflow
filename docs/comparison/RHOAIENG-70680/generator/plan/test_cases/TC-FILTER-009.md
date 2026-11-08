---
test_case_id: TC-FILTER-009
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-009: filterQuery with nested AND/OR combinations

**Objective**: Verify that the filterQuery parser handles complex
expressions combining AND and OR operators.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=(framework = "langgraph" OR framework = "crewai") AND agentType = "conversational"`
2. Verify that only agents matching the combined condition are returned

**Expected Results**:

- Response status is HTTP 200
- Every returned agent has framework `langgraph` or `crewai`, AND
  agentType `conversational`
- Agents with matching framework but different agentType are excluded
- Parentheses correctly control operator precedence

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=(framework%20%3D%20%22langgraph%22%20OR%20framework%20%3D%20%22crewai%22)%20AND%20agentType%20%3D%20%22conversational%22"
```

**Notes**: To be filled later in the process.
