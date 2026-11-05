---
test_case_id: TC-SCHEMA-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SCHEMA-003: Custom properties forwarded from upstream YAML

**Objective**: Verify that custom properties defined in the upstream
agent catalog YAML are forwarded through the API response without
modification.

**Preconditions**:

- Custom catalog includes agents with source-specific custom properties
  (e.g., `modelProvider`, `tooling`, `complexity`)

**Test Steps**:

1. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}` for an agent known
   to have custom properties
2. Verify the `customProperties` object contains the upstream-defined
   properties with correct values

**Expected Results**:

- `customProperties` contains all custom fields defined in the source
  YAML
- Property values match the source YAML exactly (no transformation
  or truncation)
- Standard properties (framework, agentType, tags) coexist with custom
  properties
- Custom properties are included in filter options if applicable

**Notes**: To be filled later in the process.
