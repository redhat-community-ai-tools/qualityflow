---
test_case_id: TC-SEARCH-002
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SEARCH-002: Name filter with LIKE matching

**Objective**: Verify that the `name` query parameter performs SQL LIKE
matching on agent names.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `name=react`
2. Verify that only agents whose name contains "react" are returned

**Expected Results**:

- Response status is HTTP 200
- All returned agent names contain the substring `react`
- The name parameter behaves as a LIKE filter (implicit `%name%`
  wildcards)
- Agents whose names do not contain the substring are excluded

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?name=react"
```

**Notes**: To be filled later in the process.
