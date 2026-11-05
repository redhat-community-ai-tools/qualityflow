---
test_case_id: TC-SEARCH-001
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SEARCH-001: Keyword search with q parameter matches across fields

**Objective**: Verify that the `q` query parameter performs keyword search
across multiple agent fields (name, description, tags).

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `q=conversational`
2. Verify that agents matching the keyword in any searchable field
   are returned

**Expected Results**:

- Response status is HTTP 200
- Returned agents have the term `conversational` in their name,
  description, tags, or other searchable metadata fields
- Agents with no match for the keyword are excluded
- Search is performed across multiple fields, not limited to name only

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?q=conversational"
```

**Notes**: To be filled later in the process.
