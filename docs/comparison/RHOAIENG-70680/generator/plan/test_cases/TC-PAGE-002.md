---
test_case_id: TC-PAGE-002
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-PAGE-002: Order by NAME ascending sorts agents alphabetically

**Objective**: Verify that the `orderBy=NAME` with `sortOrder=ASC`
parameters return agents sorted alphabetically by name.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `orderBy=NAME&sortOrder=ASC`
2. Verify the returned agents are in ascending alphabetical order by name

**Expected Results**:

- Response status is HTTP 200
- Agent names are in ascending alphabetical order (A-Z)
- Each agent name is lexicographically less than or equal to the next

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?orderBy=NAME&sortOrder=ASC" \
  | jq '[.items[].name]'
```

**Notes**: To be filled later in the process.
