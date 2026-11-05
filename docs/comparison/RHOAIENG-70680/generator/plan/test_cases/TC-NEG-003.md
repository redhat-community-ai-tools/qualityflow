---
test_case_id: TC-NEG-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-NEG-003: Invalid filterQuery syntax returns error

**Objective**: Verify that sending a malformed filterQuery expression
returns an appropriate error response.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework ==== "invalid"`
2. Verify the response indicates a parse error

**Expected Results**:

- Response status is HTTP 400
- Response body contains an error message indicating the filterQuery
  syntax is invalid
- The error message references the malformed expression

**Test Data**:

```bash
curl -s -w "\n%{http_code}" -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20%3D%3D%3D%3D%20%22invalid%22"
```

**Notes**: To be filled later in the process.
