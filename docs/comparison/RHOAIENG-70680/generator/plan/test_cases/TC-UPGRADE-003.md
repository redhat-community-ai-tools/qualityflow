---
test_case_id: TC-UPGRADE-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: both
---
# TC-UPGRADE-003: Unified sources endpoint backwards compatibility

**Objective**: Verify that the unified `/sources` endpoint continues to
return model and MCP sources correctly after the agent plugin is added,
with agent sources appearing as a new asset type.

**Preconditions**:

- Pre-upgrade: `/sources` returns model and MCP sources

**Test Steps**:

1. Pre-upgrade: send GET to `/api/model_catalog/v1alpha1/sources` and
   record the model and MCP source entries
2. Perform the operator upgrade
3. Post-upgrade: send GET to `/api/model_catalog/v1alpha1/sources` and
   verify model and MCP sources are unchanged
4. Post-upgrade: verify agent sources appear with `assetType=agents`
5. Post-upgrade: send GET with `assetType=models` and verify only model
   sources are returned (no agent contamination)
6. Post-upgrade: send GET with `assetType=mcp_servers` and verify only
   MCP sources are returned

**Expected Results**:

- Model source entries are identical before and after upgrade
- MCP source entries are identical before and after upgrade
- Agent sources appear as new entries with `assetType=agents`
- Filtering by individual assetType returns only the matching sources
- No source entries are duplicated or corrupted

**Notes**: To be filled later in the process.
