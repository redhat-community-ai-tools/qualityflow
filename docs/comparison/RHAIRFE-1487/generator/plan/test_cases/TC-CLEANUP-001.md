---
test_case_id: TC-CLEANUP-001
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CLEANUP-001: Delete Tenant CR — all tenant-owned resources removed

**Objective**: Verify that deleting a Tenant CR triggers the
maas-controller to remove all tenant-owned Kubernetes
resources with no orphaned objects.

**Preconditions**:

- Tenant `tenant-a` is fully provisioned with: namespace,
  MaaSSubscription, MaaSAuthPolicy, Kuadrant AuthPolicy
- At least one API key exists for `tenant-a`

**Test Steps**:

1. Record all resources owned by `tenant-a` (namespace, CRs, generated policies)
2. Delete the Tenant CR: `kubectl delete tenant tenant-a`
3. Wait for finalizer processing and controller reconciliation
4. Check for existence of each recorded resource

**Expected Results**:

- Namespace `tenant-a` is deleted
- MaaSSubscription in `tenant-a` is deleted
- MaaSAuthPolicy in `tenant-a` is deleted
- Kuadrant AuthPolicy for `tenant-a` is deleted
- No resources with `tenant-a` ownership remain in the cluster
- `kubectl get namespace tenant-a` returns `NotFound`

**Notes**: To be filled later in the process.
