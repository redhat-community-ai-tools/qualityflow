---
test_case_id: TC-NEG-001
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-NEG-001: Get nonexistent agent ID returns 404

**Objective**: Verify that requesting an agent with a nonexistent ID
returns an HTTP 404 response.

**Test Steps**:

1. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/99999999` using an ID that does
   not exist in the catalog
2. Verify the response is a 404 error

**Expected Results**:

- Response status is HTTP 404
- Response body contains an error message indicating the agent was not
  found

**Test Data**:

```bash
curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/99999999"
```

**Notes**: To be filled later in the process.
