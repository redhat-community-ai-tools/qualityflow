---
test_case_id: TC-CONTRACT-002
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CONTRACT-002: POST /internal/v1/subscriptions/select — wrong tenant returns 403

**Objective**: Verify that the subscriptions/select endpoint
rejects a request where the tenant context does not match
the authenticated identity.

**Preconditions**:

- Tenant `tenant-a` and `tenant-b` are both provisioned
- tenant-a has a subscription for `granite-7b`; tenant-b does not

**Test Steps**:

1. Send `POST /internal/v1/subscriptions/select`
   authenticated as tenant-a but with
   `X-MaaS-Tenant: tenant-b`
2. Check the response status code

**Test Data**:

```bash
curl -X POST https://<maas-api>/internal/v1/subscriptions/select \
  -H "Authorization: Bearer <tenant-a-token>" \
  -H "X-MaaS-Tenant: tenant-b" \
  -H "Content-Type: application/json" \
  -d '{"modelRef": "granite-7b"}'
```

**Expected Results**:

- Response HTTP status is `403 Forbidden`
- Response body does not contain any subscription data

**Notes**: To be filled later in the process.
