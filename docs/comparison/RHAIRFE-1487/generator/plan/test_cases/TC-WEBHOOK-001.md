---
test_case_id: TC-WEBHOOK-001
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-WEBHOOK-001: Webhook rejects MaaSSubscription CREATE in unlabeled namespace

**Objective**: Verify that the admission webhook rejects a
MaaSSubscription creation attempt in a namespace that does
not have the `maas.opendatahub.io/tenant` label.

**Preconditions**:

- Admission webhook is deployed and active
- Namespace `no-label-ns` exists without the `maas.opendatahub.io/tenant` label

**Test Steps**:

1. Attempt to apply a MaaSSubscription CR in namespace `no-label-ns`
2. Observe the API server response

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: MaaSSubscription
metadata:
  name: rejected-subscription
  namespace: no-label-ns
spec:
  modelRef: granite-7b
```

**Expected Results**:

- `kubectl apply` returns a non-zero exit code
- Error message from the API server contains a rejection
  reason referencing the missing
  `maas.opendatahub.io/tenant` label
- No MaaSSubscription resource is created in `no-label-ns`

**Notes**: To be filled later in the process.
