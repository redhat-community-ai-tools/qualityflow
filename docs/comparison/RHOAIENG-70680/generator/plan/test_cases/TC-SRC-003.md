---
test_case_id: TC-SRC-003
source_key: RHOAIENG-70680
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SRC-003: Disabled agent source excludes agents from listing

**Objective**: Verify that agents from a disabled source are not returned
in the list agents response.

**Preconditions**:

- A custom agent catalog source is configured and enabled
- Agents from the source are visible in the API

**Test Steps**:

1. Verify agents from the custom source appear in
   `/api/agent_catalog/v1alpha1/agents`
2. Patch the `model-catalog-sources` ConfigMap to set the custom source
   `enabled: false`
3. Wait for the catalog service to reload sources
4. Send GET request to `/api/agent_catalog/v1alpha1/agents`
5. Verify agents from the disabled source are no longer returned

**Expected Results**:

- After disabling, no agents from the disabled source appear in the
  listing
- Agents from other enabled sources remain visible
- The total `size` decreases by the number of agents in the disabled
  source
- The disabled source still appears in
  `/api/model_catalog/v1alpha1/sources?assetType=agents` with
  `enabled: false`

**Notes**: To be filled later in the process.
