---
test_case_id: TC-ARTIFACT-002
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-ARTIFACT-002: Filter artifacts by type image-artifact

**Objective**: Verify that the `artifactType` query parameter filters
artifacts to only return image artifacts.

**Test Steps**:

1. Obtain a valid agent ID that has image artifacts
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}/artifacts?artifactType=image-artifact`
3. Verify only image-artifact types are returned

**Expected Results**:

- Response status is HTTP 200
- All items in the response have `artifactType` equal to
  `image-artifact`
- No `template-artifact` entries appear in the response
- Each image artifact contains a valid `uri` pointing to an image
  resource

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}/artifacts?artifactType=image-artifact"
```

**Notes**: To be filled later in the process.
