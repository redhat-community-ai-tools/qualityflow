---
test_case_id: TC-APIKEY-004
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-APIKEY-004: GET /v1/api-keys — list returns only keys scoped to the requesting tenant

**Objective**: Verify that listing API keys for tenant-a does not return any keys belonging to tenant-b.

**Preconditions**:

- At least one API key created for `tenant-a` (see TC-APIKEY-001)
- At least one API key created for `tenant-b`

**Test Steps**:

1. Send `GET /v1/api-keys` authenticated as tenant-a
2. Parse the list of returned API keys
3. Verify all returned keys belong to `tenant-a`
4. Verify no key IDs belonging to tenant-b appear in the response

**Test Data**:

```bash
curl -X GET https://<maas-api>/v1/api-keys \
  -H "Authorization: Bearer <tenant-a-token>"
```

**Expected Results**:

- Response HTTP status is `200 OK`
- Response body contains only keys where `tenant == tenant-a`
- No keys with `tenant == tenant-b` are present in the response

**Notes**: To be filled later in the process.
