---
test_case_id: TC-PROV-003
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-PROV-003: Create Tenant CR — MaaSAuthPolicy reconciled in tenant namespace

**Objective**: Verify that a MaaSAuthPolicy created in a tenant namespace is reconciled by the maas-controller.

**Preconditions**:

- Tenant CR `tenant-a` exists and namespace is provisioned (see TC-PROV-001)

**Test Steps**:

1. Apply a MaaSAuthPolicy CR in namespace `tenant-a`
2. Wait for controller reconciliation
3. Run `kubectl get maasauthpolicy -n tenant-a -o yaml` and check status conditions
4. Verify no error events on the MaaSAuthPolicy resource

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: MaaSAuthPolicy
metadata:
  name: tenant-a-auth
  namespace: tenant-a
spec:
  authType: APIKey
```

**Expected Results**:

- MaaSAuthPolicy status has a `Ready` or equivalent condition set to `True`
- No error events on the resource
- Controller logs show reconciliation of `tenant-a/tenant-a-auth`

**Notes**: To be filled later in the process.
