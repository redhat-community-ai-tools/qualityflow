---
test_case_id: TC-WEBHOOK-002
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-WEBHOOK-002: Webhook rejects MaaSAuthPolicy CREATE in unlabeled namespace

**Objective**: Verify that the admission webhook rejects a
MaaSAuthPolicy creation attempt in a namespace without the
`maas.opendatahub.io/tenant` label.

**Preconditions**:

- Admission webhook is deployed and active
- Namespace `no-label-ns` exists without the `maas.opendatahub.io/tenant` label

**Test Steps**:

1. Attempt to apply a MaaSAuthPolicy CR in namespace `no-label-ns`
2. Observe the API server response

**Test Data**:

```yaml
apiVersion: maas.opendatahub.io/v1alpha1
kind: MaaSAuthPolicy
metadata:
  name: rejected-auth
  namespace: no-label-ns
spec:
  authType: APIKey
```

**Expected Results**:

- `kubectl apply` returns a non-zero exit code
- Error message references the missing `maas.opendatahub.io/tenant` label
- No MaaSAuthPolicy resource is created in `no-label-ns`

**Notes**: To be filled later in the process.
