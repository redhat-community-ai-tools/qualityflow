---
test_case_id: TC-API-002
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-API-002: Get agent by ID returns correct agent details

**Objective**: Verify retrieving a single agent by its ID returns the
complete agent metadata including all fields and custom properties.

**Preconditions**:

- At least one agent loaded in the catalog with a known ID

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` to obtain
   a valid agent ID from the response
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}` using the obtained ID
3. Verify the response contains all expected fields for that agent

**Expected Results**:

- Response status is HTTP 200
- Response body contains the agent object (not wrapped in `items`)
- Agent object includes: `id`, `name`, `description`, `externalId`,
  `createTimeSinceEpoch`, `lastUpdateTimeSinceEpoch`, `customProperties`
- The `name` field matches the name returned in the list response
- Custom properties include framework, agentType, tags, and any
  source-specific metadata

**Test Data**:

```bash
AGENT_ID=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents" \
  | jq -r '.items[0].id')

curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}"
```

**Notes**: To be filled later in the process.
