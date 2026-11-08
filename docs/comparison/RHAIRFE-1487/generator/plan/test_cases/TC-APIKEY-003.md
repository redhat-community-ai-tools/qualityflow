---
test_case_id: TC-APIKEY-003
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-APIKEY-003: POST /internal/v1/api-keys/validate — cross-tenant key returns 401

**Objective**: Verify that an API key issued for tenant-a is
rejected when validated in the context of tenant-b.

**Preconditions**:

- A valid API key for `tenant-a` has been created (see TC-APIKEY-001)
- Tenant `tenant-b` is provisioned

**Test Steps**:

1. Send `POST /internal/v1/api-keys/validate` with the
   tenant-a API key but in the context of tenant-b
   (e.g., with tenant-b gateway or tenant-b context header)
2. Check the response status code

**Test Data**:

```bash
curl -X POST https://<maas-api>/internal/v1/api-keys/validate \
  -H "Content-Type: application/json" \
  -H "X-MaaS-Tenant: tenant-b" \
  -d '{"apiKey": "<tenant-a-api-key>"}'
```

**Expected Results**:

- Response HTTP status is `401 Unauthorized`
- Response body does not contain any tenant-a data
- No tenant-b resources are accessible with a tenant-a key

**Notes**: To be filled later in the process.
