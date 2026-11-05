---
test_case_id: TC-FILTER-002
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-FILTER-002: filterQuery with not-equals operator excludes framework

**Objective**: Verify that the filterQuery parameter with the `!=` operator
excludes agents matching the specified framework.

**Test Steps**:

1. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `filterQuery=framework != "crewai"`
2. Verify that no agents with framework `crewai` are returned

**Expected Results**:

- Response status is HTTP 200
- No items in the response have `customProperties.framework` value
  equal to `crewai`
- Agents with other frameworks are present
- `size` field is less than the total unfiltered agent count

**Test Data**:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "${CATALOG_ROUTE}/api/agent_catalog/v1alpha1/agents?filterQuery=framework%20!%3D%20%22crewai%22"
```

**Notes**: To be filled later in the process.
