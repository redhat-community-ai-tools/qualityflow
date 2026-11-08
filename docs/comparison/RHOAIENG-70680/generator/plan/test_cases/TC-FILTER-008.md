---
test_case_id: TC-FILTER-008
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-008: sourceLabel parameter filters agents by source

**Objective**: Verify that the sourceLabel query parameter filters agents
to only those from the specified catalog source.

**Preconditions**:

- Multiple agent catalog sources configured (default Red Hat starter kits
  and custom user source)

**Test Steps**:

1. Send GET request to
   `/api/model_catalog/v1alpha1/sources?assetType=agents` to obtain
   a source label
2. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `sourceLabel={label}` using a known source label
3. Verify that only agents from that source are returned

**Expected Results**:

- Response status is HTTP 200
- All returned agents belong to the source with the specified label
- Agents from other sources are excluded
- The sourceLabel is correctly resolved to a sourceID internally

**Test Data**:

```bash
SOURCE_LABEL="redhat-starter-kits"
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?sourceLabel=${SOURCE_LABEL}"
```

**Notes**: To be filled later in the process.
