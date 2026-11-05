---
test_case_id: TC-API-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-API-003: Get filter options returns available filter fields and values

**Objective**: Verify the filter options endpoint returns the set of
filterable fields and their available values from loaded agents.

**Test Steps**:

1. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/filter_options`
2. Verify the response contains filter fields relevant to agent metadata

**Expected Results**:

- Response status is HTTP 200
- Response contains filterable fields including `framework`, `agentType`,
  and `tags`
- Each field lists the distinct values present in the loaded catalog
  (e.g., framework values include `langgraph`, `crewai`, `autogen`,
  `claude-code`, `langflow`)
- Values reflect agents from both default and custom sources

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/filter_options"
```

**Notes**: To be filled later in the process.
