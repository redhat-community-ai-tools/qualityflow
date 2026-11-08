---
test_case_id: TC-API-004
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-API-004: Agent plugin readiness check reports healthy

**Objective**: Verify the agent plugin registers correctly and reports
healthy via the `/readyz` endpoint.

**Test Steps**:

1. Send GET request to `/readyz`
2. Verify the response indicates the agent plugin is ready

**Expected Results**:

- Response status is HTTP 200
- Response body indicates agent plugin is healthy/ready
- Plugin name `agent_catalog` appears in the readiness response

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/readyz"
```

**Notes**: To be filled later in the process.
