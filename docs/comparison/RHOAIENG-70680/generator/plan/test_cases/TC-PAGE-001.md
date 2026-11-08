---
test_case_id: TC-PAGE-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-PAGE-001: Pagination with pageSize limits results per page

**Objective**: Verify that the `pageSize` parameter limits the number of
agents returned per page and provides a nextPageToken for subsequent pages.

**Preconditions**:

- Total agent count exceeds the pageSize used in the test (22 agents
  loaded)

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `pageSize=5`
2. Verify the response contains exactly 5 items and a non-empty
   nextPageToken
3. Send GET request with `pageSize=5&nextPageToken={token}` using the
   token from step 2
4. Verify the second page returns agents not present in the first page

**Expected Results**:

- First response contains exactly 5 items
- First response `nextPageToken` is non-empty
- Second response contains the next batch of agents (up to 5)
- No agent appears in both pages
- Combined results from all pages equal the total agent count

**Test Data**:

```bash
PAGE1=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?pageSize=5")

NEXT_TOKEN=$(echo "${PAGE1}" | jq -r '.nextPageToken')

curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?pageSize=5&nextPageToken=${NEXT_TOKEN}"
```

**Notes**: To be filled later in the process.
