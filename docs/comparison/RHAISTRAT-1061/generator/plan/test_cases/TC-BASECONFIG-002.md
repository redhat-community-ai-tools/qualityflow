---
test_case_id: TC-BASECONFIG-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-BASECONFIG-002: baseConfig ConfigMap missing causes terminal error

**Objective**: Verify that referencing a non-existent ConfigMap in
`spec.baseConfig` produces a terminal error with no requeue.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-baseconfig-002
   ```

2. Confirm the referenced ConfigMap does NOT exist:

   ```bash
   oc get configmap nonexistent-config \
     -n tc-baseconfig-002 2>&1 || true
   ```

3. Apply an OGXServer CR referencing the missing
   ConfigMap with `spec.providers` also set:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-missing-baseconfig
     namespace: tc-baseconfig-002
   spec:
     baseConfig:
       configMapRef:
         name: nonexistent-config
         key: config.yaml
     providers:
       inference:
         - provider_id: vllm-test
           provider_type: remote::vllm
           config:
             url: "https://model-endpoint/v1"
   EOF
   ```

4. Wait briefly and check the OGXServer status:

   ```bash
   sleep 15
   oc get ogxserver ogx-missing-baseconfig \
     -n tc-baseconfig-002 -o yaml
   ```

5. Inspect the status conditions for
   ConfigGenerationFailed:

   ```bash
   oc get ogxserver ogx-missing-baseconfig \
     -n tc-baseconfig-002 \
     -o jsonpath='{.status.conditions}' | jq .
   ```

6. Verify no requeue by checking operator logs for
   repeated reconcile attempts:

   ```bash
   oc logs deployment/ogx-operator \
     -n <operator-namespace> --tail=50 | \
     grep -i "ogx-missing-baseconfig"
   ```

7. Verify no pods were created:

   ```bash
   oc get pods -n tc-baseconfig-002 \
     -l app=ogx-missing-baseconfig
   ```

8. Clean up:

   ```bash
   oc delete project tc-baseconfig-002
   ```

**Expected Results**:

- The CR is accepted by the API server (valid schema).
- The OGXServer status shows a terminal error condition
  with type `ConfigGenerationFailed`.
- The condition message clearly states the referenced
  ConfigMap `nonexistent-config` was not found.
- The operator does NOT requeue the CR (no repeated
  reconcile log entries after the initial failure).
- No server pods are created.
- No generated ConfigMap is created.

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-missing-baseconfig
spec:
  baseConfig:
    configMapRef:
      name: nonexistent-config
      key: config.yaml
  providers:
    inference:
      - provider_id: vllm-test
        provider_type: remote::vllm
        config:
          url: "https://model-endpoint/v1"
```

**Notes**: To be filled later in the process.
