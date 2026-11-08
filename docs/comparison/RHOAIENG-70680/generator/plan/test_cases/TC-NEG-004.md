---
test_case_id: TC-NEG-004
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-NEG-004: Invalid nextPageToken returns error or empty results

**Objective**: Verify that providing an invalid or expired nextPageToken
is handled gracefully.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `nextPageToken=invalidtoken123`
2. Verify the response handles the invalid token gracefully

**Expected Results**:

- Response is either HTTP 400 with an error message about the invalid
  token, or HTTP 200 with an empty result set
- The service does not crash or return a 500 error

**Test Data**:

```bash
curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?nextPageToken=invalidtoken123"
```

**Notes**: To be filled later in the process.
