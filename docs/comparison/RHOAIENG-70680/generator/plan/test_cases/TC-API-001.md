---
test_case_id: TC-API-001
source_key: RHOAIENG-70680
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-API-001: List all agents returns populated response

**Objective**: Verify the list agents endpoint returns all agents loaded
from both default and custom catalog sources.

**Preconditions**:

- Custom agent catalog YAML with 7 agents injected via ConfigMap patch
- Red Hat starter kits catalog loaded by operator (15 agents)

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents`
   without any query parameters
2. Verify HTTP response status and body structure

**Expected Results**:

- Response status is HTTP 200
- Response body contains `items` array with 22 agents (15 default + 7
  custom)
- Each item contains at minimum: `id`, `name`, `description`,
  `createTimeSinceEpoch`, `lastUpdateTimeSinceEpoch`
- Response includes `size` field matching the number of items returned
- Response includes `nextPageToken` field (may be empty if all fit in
  one page)

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents"
```

**Expected Response**:

```json
{
  "items": [
    {
      "id": "1",
      "name": "langgraph-react-agent",
      "description": "A ReAct agent built with LangGraph...",
      "createTimeSinceEpoch": "1720000000000",
      "lastUpdateTimeSinceEpoch": "1720000000000",
      "customProperties": {}
    }
  ],
  "size": 22,
  "nextPageToken": ""
}
```

**Notes**: To be filled later in the process.
