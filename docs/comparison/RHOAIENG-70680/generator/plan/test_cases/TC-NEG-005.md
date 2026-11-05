---
test_case_id: TC-NEG-005
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-NEG-005: Invalid sourceLabel returns empty results

**Objective**: Verify that filtering by a nonexistent sourceLabel returns
an empty result set rather than an error.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `sourceLabel=nonexistent-source-label`
2. Verify the response is a valid empty result

**Expected Results**:

- Response status is HTTP 200
- Response body contains `items` as an empty array
- `size` field is 0
- The service does not return a 404 or 500 error for unknown labels

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?sourceLabel=nonexistent-source-label"
```

**Notes**: To be filled later in the process.
