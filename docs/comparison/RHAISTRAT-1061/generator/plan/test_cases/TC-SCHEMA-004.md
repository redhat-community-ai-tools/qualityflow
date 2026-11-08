---
test_case_id: TC-SCHEMA-004
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-SCHEMA-004: CEL validation — MinItems/MaxItems on provider arrays

**Objective**: Verify that an OGXServer CR with an empty providers array
(violating the MinItems constraint) is rejected by CEL-based validation in the CRD schema.

**Preconditions**:

- OpenShift cluster with OGX operator installed and running
- User has permissions to create OGXServer CRs in the test namespace
- The OGXServer CRD includes CEL validation rules enforcing MinItems on the `spec.providers` array

**Test Steps**:

1. Create a file `empty-providers.yaml` with the test data below
   (note: `providers` is an empty array `[]`).
2. Apply the CR: `oc apply -f empty-providers.yaml`
3. Capture the error output from the apply command.
4. Verify the rejection is from CEL validation
   (not the webhook or general OpenAPI schema validation).

**Expected Results**:

- The `oc apply` command fails with a non-zero exit code.
- The error message indicates a CEL validation failure
  (e.g., `failed rule` or `Invalid value` referencing the providers array length).
- The error references the MinItems constraint violation on `spec.providers`
  (e.g., `spec.providers: Too few items` or `spec.providers must have at least 1 item`).
- No OGXServer CR named `schema-test-empty-providers` is created in the namespace.

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: schema-test-empty-providers
spec:
  distribution:
    name: rh-dev
  providers: []
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
