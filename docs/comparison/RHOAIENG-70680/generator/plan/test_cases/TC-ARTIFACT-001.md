---
test_case_id: TC-ARTIFACT-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-ARTIFACT-001: List all artifacts for an agent

**Objective**: Verify the artifacts endpoint returns all artifacts
associated with a given agent ID.

**Preconditions**:

- At least one agent has both image-artifact and template-artifact types

**Test Steps**:

1. Obtain a valid agent ID from `/api/agent_catalog/v1alpha1/agents`
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}/artifacts`
3. Verify the response contains the agent's artifacts

**Expected Results**:

- Response status is HTTP 200
- Response contains `items` array with artifacts for the agent
- Each artifact has `artifactType`, `uri`, and other metadata fields
- Artifact types may include `image-artifact` and `template-artifact`

**Test Data**:

```bash
AGENT_ID=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents" \
  | jq -r '.items[0].id')

curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}/artifacts"
```

**Notes**: To be filled later in the process.
