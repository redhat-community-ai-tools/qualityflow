---
test_case_id: TC-PAGE-003
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-PAGE-003: Order by CREATE_TIME descending sorts newest first

**Objective**: Verify that the `orderBy=CREATE_TIME` with
`sortOrder=DESC` parameters return agents sorted by creation time with
newest agents first.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `orderBy=CREATE_TIME&sortOrder=DESC`
2. Verify the returned agents are in descending order by creation
   timestamp

**Expected Results**:

- Response status is HTTP 200
- Agent `createTimeSinceEpoch` values are in descending order
- The first agent in the list has the most recent creation timestamp

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?orderBy=CREATE_TIME&sortOrder=DESC" \
  | jq '[.items[].createTimeSinceEpoch]'
```

**Notes**: To be filled later in the process.
