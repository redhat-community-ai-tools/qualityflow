---
test_case_id: TC-SRC-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: both
---
# TC-SRC-004: Unified sources endpoint returns all asset types

**Objective**: Verify that the unified `/sources` endpoint without
assetType filter returns sources for models, MCP servers, and agents.

**Test Steps**:

1. Send GET request to `/api/model_catalog/v1alpha1/sources` without
   any query parameters
2. Verify the response includes sources for all three asset types

**Expected Results**:

- Response status is HTTP 200
- Response contains sources with `assetType` values including `models`,
  `mcp_servers`, and `agents`
- Existing model and MCP sources are present alongside agent sources
- Adding the agent plugin did not remove or modify existing source
  entries

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/model_catalog/v1alpha1/sources" \
  | jq '[.items[].assetType] | unique'
```

**Notes**: To be filled later in the process.
