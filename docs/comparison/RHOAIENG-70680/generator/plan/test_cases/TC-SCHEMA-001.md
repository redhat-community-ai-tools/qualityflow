---
test_case_id: TC-SCHEMA-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SCHEMA-001: Agent with complete metadata returns all fields

**Objective**: Verify that an agent with full metadata (framework,
agentType, tags, description, license) returns all fields correctly
in the API response.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` and identify
   an agent known to have complete metadata
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}` for that agent
3. Verify all expected fields are present and populated

**Expected Results**:

- Response contains `name`, `description`, `externalId`,
  `createTimeSinceEpoch`, `lastUpdateTimeSinceEpoch`
- `customProperties` includes `framework`, `agentType`, `tags`,
  `license`, and any other source-specific metadata
- No fields are null or missing that should be populated from the
  source YAML

**Notes**: To be filled later in the process.
