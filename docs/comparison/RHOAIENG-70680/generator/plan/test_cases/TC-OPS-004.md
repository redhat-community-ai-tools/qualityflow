---
test_case_id: TC-OPS-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: both
---
# TC-OPS-004: Existing model and MCP plugins remain functional after agent deployment

**Objective**: Verify that deploying the agent catalog plugin does not
break existing model catalog and MCP catalog plugins.

**Preconditions**:

- Model catalog and MCP catalog plugins were functional before agent
  plugin deployment

**Test Steps**:

1. Send GET request to the model catalog endpoint to verify models
   are returned
2. Send GET request to the MCP catalog endpoint to verify MCP servers
   are returned
3. Send GET request to `/readyz` and verify all three plugins are
   reported healthy
4. Send GET request to `/api/model_catalog/v1alpha1/sources` and verify
   sources for all asset types are present

**Expected Results**:

- Model catalog endpoint returns HTTP 200 with model data
- MCP catalog endpoint returns HTTP 200 with MCP server data
- `/readyz` reports healthy for model, MCP, and agent plugins
- Unified sources endpoint includes models, mcp_servers, and agents
  asset types

**Notes**: To be filled later in the process.
