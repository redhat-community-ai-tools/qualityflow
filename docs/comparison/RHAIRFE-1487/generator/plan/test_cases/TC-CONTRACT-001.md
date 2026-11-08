---
test_case_id: TC-CONTRACT-001
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CONTRACT-001: POST /internal/v1/subscriptions/select — returns correct subscription for tenant

**Objective**: Verify that the subscriptions/select endpoint
returns the correct subscription when called with a valid
tenant context.

**Preconditions**:

- Tenant `tenant-a` is provisioned with a MaaSSubscription for model `granite-7b`
- maas-api internal endpoint is accessible

**Test Steps**:

1. Send `POST /internal/v1/subscriptions/select` with tenant-a context and model `granite-7b`
2. Verify the response contains the tenant-a subscription details

**Test Data**:

```bash
curl -X POST https://<maas-api>/internal/v1/subscriptions/select \
  -H "Content-Type: application/json" \
  -H "X-MaaS-Tenant: tenant-a" \
  -d '{"modelRef": "granite-7b"}'
```

**Expected Results**:

- Response HTTP status is `200 OK`
- Response body contains subscription details matching tenant-a's subscription for `granite-7b`
- Response does not contain subscription data from any other tenant

**Notes**: To be filled later in the process.
