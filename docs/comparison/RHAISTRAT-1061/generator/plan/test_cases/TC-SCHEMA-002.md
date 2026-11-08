---
test_case_id: TC-SCHEMA-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-SCHEMA-002: Missing required fields rejected

**Objective**: Verify that an OGXServer CR with the required `spec.distribution` field omitted is
rejected by the admission webhook with a clear validation error.

**Preconditions**:

- OpenShift cluster with OGX operator installed and running
- User has permissions to create OGXServer CRs in the test namespace

**Test Steps**:

1. Create a file `missing-distribution.yaml` with the test data below
   (note: `spec.distribution` is intentionally omitted).
2. Apply the CR: `oc apply -f missing-distribution.yaml`
3. Capture the error output from the apply command.

**Expected Results**:

- The `oc apply` command fails with a non-zero exit code.
- The error message indicates a validation failure from the admission webhook.
- The error message references the missing `distribution` field
  (e.g., `spec.distribution: Required value` or similar).
- No OGXServer CR named `schema-test-missing` is created in the namespace
  (verify with `oc get ogxserver schema-test-missing` returning NotFound).

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: schema-test-missing
spec:
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
