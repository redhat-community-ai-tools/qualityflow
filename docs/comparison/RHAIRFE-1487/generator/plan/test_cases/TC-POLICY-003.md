---
test_case_id: TC-POLICY-003
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-POLICY-003: MaaSAuthPolicy deleted — Kuadrant AuthPolicy removed

**Objective**: Verify that deleting a MaaSAuthPolicy causes
the maas-controller to remove the corresponding Kuadrant
AuthPolicy from the shared Gateway.

**Preconditions**:

- MaaSAuthPolicy for `tenant-a` exists and Kuadrant AuthPolicy has been generated (see TC-POLICY-001)

**Test Steps**:

1. Delete the MaaSAuthPolicy in `tenant-a`: `kubectl delete maasauthpolicy tenant-a-auth -n tenant-a`
2. Wait for controller reconciliation
3. Run `kubectl get authpolicy -A` and verify no AuthPolicy for `tenant-a` remains

**Expected Results**:

- Kuadrant AuthPolicy for `tenant-a` is deleted from the cluster
- No orphaned AuthPolicy referencing `tenant-a` remains
- Controller logs show cleanup event for `tenant-a` AuthPolicy

**Notes**: To be filled later in the process.
