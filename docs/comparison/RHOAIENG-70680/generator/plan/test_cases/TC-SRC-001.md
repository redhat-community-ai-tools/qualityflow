---
test_case_id: TC-SRC-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SRC-001: sourceLabel resolves to correct sourceID for filtering

**Objective**: Verify that sourceLabel-to-sourceID resolution works
correctly, returning only agents from the source matching the given label.

**Preconditions**:

- At least two agent catalog sources configured with distinct labels
  (e.g., "redhat-starter-kits" and "custom-agents")

**Test Steps**:

1. Send GET request to
   `/api/model_catalog/v1alpha1/sources?assetType=agents` and note the
   labels and IDs of available sources
2. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `sourceLabel=redhat-starter-kits`
3. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `sourceLabel=custom-agents`
4. Verify each response contains only agents from the specified source

**Expected Results**:

- Each response contains agents exclusively from the source whose label
  matches the parameter
- The agent sets from different sourceLabel queries are disjoint
- Agent count per source matches the known catalog sizes (15 for default,
  7 for custom)

**Notes**: To be filled later in the process.
