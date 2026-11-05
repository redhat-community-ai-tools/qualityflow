---
test_case_id: TC-SCHEMA-003
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-SCHEMA-003: Invalid provider type rejected

**Objective**: Verify that an OGXServer CR containing an invalid `provider_type` value in the
providers list is rejected by the admission webhook with a validation error.

**Preconditions**:

- OpenShift cluster with OGX operator installed and running
- User has permissions to create OGXServer CRs in the test namespace

**Test Steps**:

1. Create a file `invalid-provider-type.yaml` with the test data below
   (note: `provider_type: not-a-real-type` is intentionally invalid).
2. Apply the CR: `oc apply -f invalid-provider-type.yaml`
3. Capture the error output from the apply command.

**Expected Results**:

- The `oc apply` command fails with a non-zero exit code.
- The error message indicates a validation failure from the admission webhook.
- The error message references the invalid `provider_type` value
  (e.g., `Unsupported value` or `spec.providers[0].provider_type: Invalid value`).
- No OGXServer CR named `schema-test-invalid-type` is created in the namespace.

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: schema-test-invalid-type
spec:
  distribution:
    name: rh-dev
  providers:
    - provider_id: bad-provider
      provider_type: not-a-real-type
      config:
        url: "https://example.com"
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
