---
test_case_id: TC-NEG-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-NEG-002: Invalid API name in disabledAPIs silently ignored

**Objective**: Verify the operator behavior when an OGXServer CR specifies an invalid API name in
spec.disabledAPIs, confirming whether it rejects, warns, or silently ignores the typo.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace and apply the OGXServer CR with an invalid API name:

   ```bash
   oc new-project tc-neg-002
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-neg-disabled-api
     namespace: tc-neg-002
   spec:
     disabledAPIs:
       - infrence
   EOF
   ```

2. Check whether the CR is accepted or rejected by the validating webhook:

   ```bash
   echo $?
   ```

3. If the CR was accepted, inspect the OGXServer status for warnings:

   ```bash
   oc get ogxserver ogx-neg-disabled-api -n tc-neg-002 -o yaml
   oc get events -n tc-neg-002 --sort-by='.lastTimestamp'
   ```

4. Inspect the generated ConfigMap to check if "infrence" appears or if inference is still enabled:

   ```bash
   oc get configmaps -n tc-neg-002 -l app.kubernetes.io/instance=ogx-neg-disabled-api -o yaml
   ```

5. If the server started, verify that the inference API is still available
   (since the typo should not have disabled it):

   ```bash
   OGX_POD=$(oc get pods -n tc-neg-002 -l app.kubernetes.io/instance=ogx-neg-disabled-api -o jsonpath='{.items[0].metadata.name}')
   oc exec -n tc-neg-002 "$OGX_POD" -- curl -s http://localhost:8321/v1/inference/models 2>/dev/null || echo "inference API check failed"
   ```

6. Clean up:

   ```bash
   oc delete project tc-neg-002
   ```

**Expected Results**:

- The validating webhook SHOULD reject the CR with a clear error message listing valid API names
  (inference, vector_io, agents, eval, etc.)
- OR the CR status SHOULD show a warning condition indicating the unrecognized API name "infrence"
- The inference API SHOULD remain enabled since "infrence" is not a valid API name
- The operator SHOULD NOT silently ignore the invalid entry without any user-visible feedback

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-neg-disabled-api
spec:
  disabledAPIs:
    - infrence
```

**Notes**:

- Known gap [RHAIENG-5697](https://issues.redhat.com/browse/RHAIENG-5697): the operator currently
  silently ignores invalid API names in disabledAPIs
- This test documents the current behavior and will be updated once the validation gap is resolved
- Valid API names to check against include: inference, vector_io, agents, eval, tool_runtime,
  datasetio, scoring, post_training
