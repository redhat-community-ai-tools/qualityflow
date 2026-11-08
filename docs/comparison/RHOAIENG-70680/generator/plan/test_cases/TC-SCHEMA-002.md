---
test_case_id: TC-SCHEMA-002
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SCHEMA-002: Agent with minimal metadata uses defaults for optional fields

**Objective**: Verify that an agent with only required metadata fields
is loaded successfully, with optional fields either absent or set to
default values.

**Preconditions**:

- Custom catalog includes an agent with minimal metadata (name and
  description only, no framework or tags)

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` and identify
   the minimal-metadata agent
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}` for that agent
3. Verify required fields are present and optional fields are handled
   gracefully

**Expected Results**:

- Response status is HTTP 200
- Required fields (`name`, `description`, `id`) are present and
  non-empty
- Optional `customProperties` keys (framework, agentType, tags) are
  either absent or have empty/default values
- The agent is fully queryable via list and get endpoints despite
  missing optional metadata

**Notes**: To be filled later in the process.
