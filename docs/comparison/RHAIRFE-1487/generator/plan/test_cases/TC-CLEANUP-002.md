---
test_case_id: TC-CLEANUP-002
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CLEANUP-002: Delete Tenant CR — other tenants are unaffected

**Objective**: Verify that deleting one tenant's CR and resources does not affect other active tenants.

**Preconditions**:

- Tenants `tenant-a` and `tenant-b` are both provisioned and active
- `tenant-b` has an active API key and MaaSSubscription

**Test Steps**:

1. Delete the Tenant CR for `tenant-a`
2. Wait for cleanup to complete
3. Verify `tenant-b` namespace still exists
4. Verify `tenant-b` MaaSSubscription and MaaSAuthPolicy still exist and are `Ready`
5. Validate a tenant-b API key still authenticates successfully

**Expected Results**:

- `tenant-b` namespace exists and is `Active`
- `tenant-b` MaaSSubscription and MaaSAuthPolicy are `Ready`
- Tenant-b API key validates successfully via `POST /internal/v1/api-keys/validate`
- No tenant-b resources are modified or deleted

**Notes**: To be filled later in the process.
