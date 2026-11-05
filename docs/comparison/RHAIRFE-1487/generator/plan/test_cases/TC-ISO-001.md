---
test_case_id: TC-ISO-001
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-ISO-001: Tenant A cannot access Tenant B's models or subscriptions

**Objective**: Verify that a tenant-a user cannot discover
or access models and subscriptions belonging to tenant-b.

**Preconditions**:

- Tenants `tenant-a` and `tenant-b` are provisioned
- `tenant-b` has a MaaSSubscription for model `llama-3-8b` that `tenant-a` does not have

**Test Steps**:

1. Authenticate as a tenant-a user
2. Call `GET /v1/subscriptions` or equivalent model listing endpoint
3. Verify `llama-3-8b` subscription from tenant-b does not appear in the response
4. Attempt to directly access the tenant-b subscription by ID
5. Verify the request is rejected

**Expected Results**:

- `GET /v1/subscriptions` as tenant-a returns only tenant-a subscriptions
- Direct access to tenant-b subscription ID returns `403 Forbidden` or `404 Not Found`
- No tenant-b model or subscription data is present in any tenant-a response

**Notes**: To be filled later in the process.
