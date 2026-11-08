---
test_case_id: TC-ARTIFACT-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-ARTIFACT-003: Filter artifacts by type template-artifact

**Objective**: Verify that the `artifactType` query parameter filters
artifacts to only return template artifacts containing the agent.yaml
content.

**Test Steps**:

1. Obtain a valid agent ID that has template artifacts
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}/artifacts?artifactType=template-artifact`
3. Verify only template-artifact types are returned

**Expected Results**:

- Response status is HTTP 200
- All items in the response have `artifactType` equal to
  `template-artifact`
- No `image-artifact` entries appear in the response
- Template artifacts contain the agent.yaml content stored as JSON

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}/artifacts?artifactType=template-artifact"
```

**Notes**: To be filled later in the process.
