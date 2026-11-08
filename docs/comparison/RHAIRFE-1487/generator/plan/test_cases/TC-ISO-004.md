---
test_case_id: TC-ISO-004
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-ISO-004: Subscription changes in Tenant A are invisible to Tenant B

**Objective**: Verify that modifying a MaaSSubscription in
tenant-a does not affect or become visible to tenant-b.

**Preconditions**:

- `tenant-a` and `tenant-b` both have MaaSSubscriptions
- Both tenants have active API keys

**Test Steps**:

1. Record tenant-b's current subscription state (model list, rate limits)
2. Update tenant-a's MaaSSubscription (add a new model or change rate limit)
3. Re-query tenant-b's subscription state
4. Verify tenant-b's subscription is unchanged

**Expected Results**:

- Tenant-b's subscription state after step 3 is identical to the state recorded in step 1
- No new models or changed rate limits appear in tenant-b's subscription
- Controller logs show reconciliation only for tenant-a namespace

**Notes**: To be filled later in the process.
