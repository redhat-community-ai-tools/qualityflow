---
test_case_id: TC-ISO-003
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-ISO-003: Tenant A cannot enumerate Tenant B's API keys

**Objective**: Verify that a tenant-a user cannot list, view, or enumerate API keys belonging to tenant-b.

**Preconditions**:

- API keys exist for both `tenant-a` and `tenant-b`

**Test Steps**:

1. Authenticate as tenant-a
2. Send `GET /v1/api-keys` and collect all returned key IDs
3. Compare returned key IDs against known tenant-b key IDs

**Test Data**:

```bash
curl -X GET https://<maas-api>/v1/api-keys \
  -H "Authorization: Bearer <tenant-a-token>"
```

**Expected Results**:

- Response HTTP status is `200 OK`
- No tenant-b key IDs appear in the response
- Total number of keys returned matches only the count of tenant-a keys

**Notes**: To be filled later in the process.
