---
test_case_id: TC-SCHEMA-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-SCHEMA-001: Valid provider config accepted

**Objective**: Verify that an OGXServer CR with a valid VLLM inference provider in spec is accepted
by the webhook, reconciled by the operator, and reaches a Ready status.

**Preconditions**:

- OpenShift cluster with OGX operator installed and running
- User has permissions to create OGXServer CRs in the test namespace
- No existing OGXServer CR named `schema-test-valid` in the namespace

**Test Steps**:

1. Create a file `valid-provider.yaml` with the test data below.
2. Apply the CR: `oc apply -f valid-provider.yaml`
3. Verify the CR is accepted (no admission webhook errors).
4. Wait for the operator to reconcile: `oc wait ogxserver/schema-test-valid --for=condition=Ready
   --timeout=120s`
5. Inspect the CR status: `oc get ogxserver schema-test-valid -o yaml`

**Expected Results**:

- The `oc apply` command succeeds without validation errors.
- The operator reconciles the CR within the timeout period.
- The CR status shows `Ready` condition as `True`.
- The CR status contains no error messages related to schema validation.

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: schema-test-valid
spec:
  distribution:
    name: rh-dev
  workload:
    overrides:
      env:
        - name: VLLM_URL
          value: "https://vllm.example.svc:8000/v1"
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
