---
test_case_id: TC-CEL-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-CEL-001: overrideConfig + providers rejected

**Objective**: Verify that a CR specifying both
`spec.overrideConfig` and `spec.providers` is rejected
by CEL mutual exclusivity validation at admission time.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- OGXServer CRD includes CEL rules enforcing mutual
  exclusivity between overrideConfig and providers
- `oc` CLI authenticated with namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-cel-001
   ```

2. Apply the CR with both `spec.overrideConfig` and
   `spec.providers` set:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: cel-test-001
     namespace: tc-cel-001
   spec:
     distribution:
       name: rh-dev
     overrideConfig:
       configMapRef:
         name: my-config
         key: config.yaml
     providers:
       inference:
         remote:
           vllm:
           - id: vllm-1
             endpoint: "https://vllm.svc:8000"
   EOF
   ```

3. Capture the exit code and error output:

   ```bash
   echo "Exit code: $?"
   ```

4. Confirm no CR was created:

   ```bash
   oc get ogxserver cel-test-001 -n tc-cel-001 \
     -o name 2>&1 || echo "CR not found (expected)"
   ```

5. Clean up:

   ```bash
   oc delete project tc-cel-001
   ```

**Expected Results**:

- The `oc apply` command fails with a non-zero exit code.
- The error message indicates a CEL validation failure
  referencing mutual exclusivity between `overrideConfig`
  and `providers`.
- No OGXServer CR named `cel-test-001` is created.
- The error is raised at admission time (not by the
  operator reconciliation loop).

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: cel-test-001
spec:
  distribution:
    name: rh-dev
  overrideConfig:
    configMapRef:
      name: my-config
      key: config.yaml
  providers:
    inference:
      remote:
        vllm:
        - id: vllm-1
          endpoint: "https://vllm.svc:8000"
```

**Notes**: To be filled later in the process.
