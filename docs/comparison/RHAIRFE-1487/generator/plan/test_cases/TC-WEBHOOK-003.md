---
test_case_id: TC-WEBHOOK-003
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-WEBHOOK-003: Webhook admits MaaSSubscription CREATE in correctly labeled namespace

**Objective**: Verify that the admission webhook allows a
MaaSSubscription creation in a namespace with the correct
`maas.opendatahub.io/tenant` label.

**Preconditions**:

- Admission webhook is deployed and active
- Namespace `tenant-a` exists with label `maas.opendatahub.io/tenant=tenant-a`

**Test Steps**:

1. Apply a MaaSSubscription CR in namespace `tenant-a`
2. Observe the API server response

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: MaaSSubscription
metadata:
  name: allowed-subscription
  namespace: tenant-a
spec:
  modelRef: granite-7b
```

**Expected Results**:

- `kubectl apply` returns exit code `0`
- MaaSSubscription `allowed-subscription` is created in `tenant-a`
- No webhook rejection error in the API server response

**Notes**: To be filled later in the process.
