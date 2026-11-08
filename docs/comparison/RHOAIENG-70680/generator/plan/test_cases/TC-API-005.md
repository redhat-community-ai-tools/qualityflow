---
test_case_id: TC-API-005
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: both
---
# TC-API-005: Catalog service health check reports healthy

**Objective**: Verify the catalog service overall health endpoint reports
healthy when agent plugin is loaded alongside model and MCP plugins.

**Test Steps**:

1. Send GET request to `/healthz`
2. Verify the response indicates the catalog service is healthy

**Expected Results**:

- Response status is HTTP 200
- Response body indicates the service is healthy
- All registered plugins (model, MCP, agent) are operational

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/healthz"
```

**Notes**: To be filled later in the process.
