---
test_case_id: TC-APIKEY-001
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-APIKEY-001: POST /v1/api-keys — create API key with tenant persisted in DB

**Objective**: Verify that creating an API key for a tenant
persists the `tenant` field in the `api_keys` table.

**Preconditions**:

- maas-api is running
- Tenant `tenant-a` is provisioned
- DB migration (S3) has been applied — `api_keys` table has `tenant` column
- Cluster admin credentials available

**Test Steps**:

1. Send `POST /v1/api-keys` with tenant-a credentials
2. Note the returned API key ID
3. Query the `api_keys` table: `SELECT id, tenant FROM api_keys WHERE id = '<key_id>'`
4. Verify the `tenant` column value matches `tenant-a`

**Test Data**:

```bash
curl -X POST https://<maas-api>/v1/api-keys \
  -H "Authorization: Bearer <tenant-a-token>" \
  -H "Content-Type: application/json" \
  -d '{"description": "test key for tenant-a"}'
```

**Expected Results**:

- Response HTTP status is `201 Created`
- Response body contains an `id` field
- `SELECT tenant FROM api_keys WHERE id = '<key_id>'` returns `tenant-a`

**Validation**:

- `psql -c "SELECT tenant FROM api_keys WHERE id='<key_id>'" maas` returns `tenant-a`

**Notes**: To be filled later in the process.
