---
test_case_id: TC-PROV-002
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-PROV-002: Create Tenant CR — MaaSSubscription reconciled in tenant namespace

**Objective**: Verify that a MaaSSubscription created in a tenant namespace is reconciled by the maas-controller.

**Preconditions**:

- Tenant CR `tenant-a` exists and namespace is provisioned (see TC-PROV-001)
- MaaSModelRef CR for at least one model exists in the cluster

**Test Steps**:

1. Apply a MaaSSubscription CR in namespace `tenant-a`
2. Wait for controller reconciliation
3. Run `kubectl get maassubscription -n tenant-a -o yaml` and check status conditions
4. Verify no error events on the MaaSSubscription resource

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: MaaSSubscription
metadata:
  name: tenant-a-subscription
  namespace: tenant-a
spec:
  modelRef: granite-7b
  rateLimit: 100
```

**Expected Results**:

- MaaSSubscription status has a `Ready` or equivalent condition set to `True`
- No error events on the resource
- Controller logs show reconciliation of `tenant-a/tenant-a-subscription`

**Notes**: To be filled later in the process.
