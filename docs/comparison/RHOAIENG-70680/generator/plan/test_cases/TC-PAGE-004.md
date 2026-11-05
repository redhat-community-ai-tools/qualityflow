---
test_case_id: TC-PAGE-004
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-PAGE-004: Pagination with filter maintains consistent ordering

**Objective**: Verify that paginating through filtered results produces
consistent ordering — no duplicates or missing agents across pages.

**Preconditions**:

- Filtered result set has more agents than pageSize

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework = "langgraph"&pageSize=2&orderBy=NAME&sortOrder=ASC`
2. Collect all agent IDs from page 1
3. Follow `nextPageToken` to get page 2
4. Verify no overlap between pages and ordering is maintained

**Expected Results**:

- No agent ID appears on more than one page
- Agent names remain in ascending alphabetical order across pages
- The total count of unique agents across all pages matches the
  unfiltered count for the framework filter
- The last page has an empty `nextPageToken`

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20%3D%20%22langgraph%22&pageSize=2&orderBy=NAME&sortOrder=ASC"
```

**Notes**: To be filled later in the process.
