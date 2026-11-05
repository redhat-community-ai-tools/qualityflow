---
test_case_id: TC-PROV-001
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-PROV-001: Create Tenant CR — namespace provisioned with correct label

**Objective**: Verify that creating a Tenant CR causes the
maas-controller to create a namespace labeled with
`maas.opendatahub.io/tenant`.

**Preconditions**:

- OpenShift 4.19+ cluster with RHOAI 3.4+ and MaaS operator deployed
- Cluster admin credentials available
- maas-controller running

**Test Steps**:

1. Apply a Tenant CR named `tenant-a` via `kubectl apply`
2. Wait for the controller to reconcile (observe controller logs or CR status)
3. Run `kubectl get namespace tenant-a -o yaml` and inspect labels
4. Verify the namespace status is `Active`

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: Tenant
metadata:
  name: tenant-a
spec:
  displayName: "Tenant A"
```

**Expected Results**:

- Namespace `tenant-a` exists on the cluster
- Namespace has label `maas.opendatahub.io/tenant: tenant-a`
- Namespace status is `Active`

**Notes**: To be filled later in the process.
