---
test_case_id: TC-ARTIFACT-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-ARTIFACT-004: Artifacts endpoint pagination

**Objective**: Verify that the artifacts endpoint supports pagination
via `pageSize` and `nextPageToken` parameters.

**Preconditions**:

- An agent has more artifacts than the pageSize used in the test

**Test Steps**:

1. Obtain a valid agent ID with multiple artifacts
2. Send GET request to
   `/api/agent_catalog/v1alpha1/agents/{agent_id}/artifacts?pageSize=1`
3. Verify the response contains exactly 1 item and a non-empty
   nextPageToken
4. Send a follow-up request with the nextPageToken to get the next page
5. Verify the second page contains different artifacts

**Expected Results**:

- First response contains exactly 1 artifact item
- `nextPageToken` is non-empty on the first page
- Second page returns a different artifact not present on page 1
- No artifact appears on multiple pages

**Test Data**:

```bash
PAGE1=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}/artifacts?pageSize=1")

NEXT_TOKEN=$(echo "${PAGE1}" | jq -r '.nextPageToken')

curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents/${AGENT_ID}/artifacts?pageSize=1&nextPageToken=${NEXT_TOKEN}"
```

**Notes**: To be filled later in the process.
