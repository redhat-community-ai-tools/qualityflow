---
test_case_id: TC-API-006
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-API-006: List agent sources returns agent catalog sources

**Objective**: Verify the unified sources endpoint returns agent catalog
sources when filtered by assetType=agents.

**Test Steps**:

1. Send GET request to
   `/api/model_catalog/v1alpha1/sources?assetType=agents`
2. Verify the response lists all configured agent catalog sources

**Expected Results**:

- Response status is HTTP 200
- Response contains sources configured for agent catalogs
- Each source includes `name`, `label`, `enabled`, and `assetType` fields
- The `assetType` field value is `agents` for all returned sources
- Both operator-managed default sources and user-configured custom sources
  appear in the response

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/model_catalog/v1alpha1/sources?assetType=agents"
```

**Notes**: To be filled later in the process.
