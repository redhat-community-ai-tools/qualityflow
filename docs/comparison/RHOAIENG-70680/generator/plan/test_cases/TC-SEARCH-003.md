---
test_case_id: TC-SEARCH-003
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SEARCH-003: Keyword search with no matches returns empty results

**Objective**: Verify that the `q` parameter returns an empty result set
when no agents match the search term.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `q=nonexistentagentxyz123`
2. Verify the response is a valid empty result

**Expected Results**:

- Response status is HTTP 200
- Response body contains `items` as an empty array
- `size` field is 0
- `nextPageToken` is empty

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?q=nonexistentagentxyz123"
```

**Expected Response**:

```json
{
  "items": [],
  "size": 0,
  "nextPageToken": ""
}
```

**Notes**: To be filled later in the process.
