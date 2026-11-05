---
test_case_id: TC-CTRL-003
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CTRL-003: Multiple tenant namespaces — all reconciled simultaneously

**Objective**: Verify that the maas-controller correctly
reconciles resources across multiple tenant namespaces
without interference between tenants.

**Preconditions**:

- maas-controller is running
- Three tenant namespaces exist: `tenant-a`, `tenant-b`, `tenant-c`, each labeled with `maas.opendatahub.io/tenant`

**Test Steps**:

1. Create a MaaSSubscription in each of `tenant-a`, `tenant-b`, and `tenant-c` simultaneously
2. Wait for controller reconciliation
3. Verify MaaSSubscription status in each namespace independently
4. Check controller logs for reconciliation events for all three tenants

**Expected Results**:

- MaaSSubscription in `tenant-a`, `tenant-b`, and `tenant-c` all reach `Ready` status
- Controller logs show separate reconciliation events for each namespace
- Resources in one tenant namespace are not modified by reconciliation of another tenant

**Notes**: To be filled later in the process.
