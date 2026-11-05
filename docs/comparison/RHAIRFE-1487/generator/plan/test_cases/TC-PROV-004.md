---
test_case_id: TC-PROV-004
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-PROV-004: Update Tenant CR — configuration changes are reconciled

**Objective**: Verify that updating a Tenant CR causes the
maas-controller to reconcile the changed configuration.

**Preconditions**:

- Tenant CR `tenant-a` exists and is reconciled (see TC-PROV-001)

**Test Steps**:

1. Patch the Tenant CR `tenant-a` to update a field (e.g., display name or quota)
2. Wait for controller reconciliation
3. Verify the updated configuration is reflected in the tenant namespace resources
4. Check controller logs for a reconciliation event triggered by the update

**Expected Results**:

- Controller logs show a reconciliation event for `tenant-a` following the update
- Updated field is reflected in the corresponding tenant resources
- No error conditions on the Tenant CR after update

**Notes**: To be filled later in the process.
