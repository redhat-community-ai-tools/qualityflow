---
test_case_id: TC-NEG-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-NEG-001: Unknown storage type silently defaults to SQLite

**Objective**: Verify the operator behavior when an OGXServer CR specifies an unknown storage type
(typo), confirming whether it rejects, warns, or silently defaults to SQLite.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace and apply the OGXServer CR with an invalid storage type:

   ```bash
   oc new-project tc-neg-001
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-neg-storage
     namespace: tc-neg-001
   spec:
     storage:
       type: redos
       config:
         host: redis.tc-neg-001.svc.cluster.local
         port: 6379
   EOF
   ```

2. Check whether the CR is accepted or rejected by the validating webhook:

   ```bash
   # Capture the exit code and output from step 1
   echo $?
   ```

3. If the CR was accepted, check the OGXServer status for warnings or error conditions:

   ```bash
   oc get ogxserver ogx-neg-storage -n tc-neg-001 -o yaml
   oc get events -n tc-neg-001 --sort-by='.lastTimestamp'
   ```

4. Inspect the generated ConfigMap to determine which storage backend was actually configured:

   ```bash
   oc get configmaps -n tc-neg-001 -l app.kubernetes.io/instance=ogx-neg-storage -o yaml
   ```

5. If the server pod started, check the server logs for any storage-related warnings:

   ```bash
   oc logs -l app.kubernetes.io/instance=ogx-neg-storage -n tc-neg-001 --tail=50
   ```

6. Clean up:

   ```bash
   oc delete project tc-neg-001
   ```

**Expected Results**:

- The validating webhook SHOULD reject the CR with a clear error message listing valid storage types
  (sqlite, postgres, redis)
- OR the CR status SHOULD show a warning condition indicating the unknown storage type
- The operator SHOULD NOT silently default to SQLite without any indication to the user

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-neg-storage
spec:
  storage:
    type: redos
    config:
      host: redis.tc-neg-001.svc.cluster.local
      port: 6379
```

**Notes**:

- Known gap [RHAIENG-5697](https://issues.redhat.com/browse/RHAIENG-5697): the operator currently
  defaults silently to SQLite when an unknown storage type is specified
- This test documents the current behavior and will be updated once the validation gap is resolved
- Valid storage types to check against: sqlite, postgres, redis
