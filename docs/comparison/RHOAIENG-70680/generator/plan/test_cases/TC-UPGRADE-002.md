---
test_case_id: TC-UPGRADE-002
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: both
---
# TC-UPGRADE-002: Database schema compatibility after upgrade

**Objective**: Verify that the shared PostgreSQL database (MLMD schema)
correctly supports new agent context types alongside existing model and
MCP context types after upgrade.

**Preconditions**:

- Pre-upgrade: model and MCP catalog data exists in the database
- Upgrade to version with agent catalog plugin

**Test Steps**:

1. Pre-upgrade: verify model catalog queries return data
2. Pre-upgrade: verify MCP catalog queries return data
3. Perform the operator upgrade
4. Post-upgrade: verify model catalog queries still return the same data
5. Post-upgrade: verify MCP catalog queries still return the same data
6. Post-upgrade: verify agent catalog queries return agent data
7. Verify no MLMD schema migration errors in operator or catalog service
   logs

**Expected Results**:

- Pre-upgrade model and MCP data is preserved intact after upgrade
- New agent context types are registered in the MLMD schema without
  affecting existing types
- No database migration errors in logs
- All three catalog types (model, MCP, agent) coexist in the shared
  database

**Notes**: To be filled later in the process.
