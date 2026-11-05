---
test_case_id: TC-UPGRADE-001
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
upgrade_phase: post
---
# TC-UPGRADE-001: Operator upgrade creates agent ConfigMap and volume mounts

**Objective**: Verify that upgrading the RHOAI operator from a version
without agent catalog to one with it correctly adds the agent_catalogs
section to the ConfigMap, creates volume mounts, and wires the
`--catalogs-path` argument.

**Preconditions**:

- RHOAI operator at a version that does not include the agent catalog
  feature
- Model catalog and MCP catalog plugins are functional

**Test Steps**:

1. Record the current `default-catalog-sources` ConfigMap contents
   (no agent_catalogs section expected)
2. Upgrade the RHOAI operator to the version with agent catalog support
3. Wait for the operator reconciliation to complete
4. Verify the `default-catalog-sources` ConfigMap now contains an
   `agent_catalogs` section
5. Verify the catalog service deployment has new volume mounts for
   agent catalog data
6. Verify the `--catalogs-path` argument includes the agent sources path
7. Verify `/readyz` reports the agent_catalog plugin as healthy

**Expected Results**:

- Pre-upgrade ConfigMap does not contain `agent_catalogs`
- Post-upgrade ConfigMap contains `agent_catalogs` with at least one
  default source entry
- Volume mount for shared-data is added to the catalog service pod
- Init container is configured to load agents-catalog.yaml
- `/readyz` includes agent_catalog plugin in healthy status
- ConfigMap creation is idempotent (re-running upgrade does not
  duplicate entries)

**Notes**: To be filled later in the process.
