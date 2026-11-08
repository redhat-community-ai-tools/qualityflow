---
test_case_id: TC-UPGRADE-003
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-UPGRADE-003: v1alpha1 API rejected after upgrade

**Objective**: Verify that after upgrading to RHOAI 3.5, the `llamastack.io/v1alpha1` API is no
longer available and attempts to apply a LlamaStackDistribution CR are rejected with a "no matches
for kind" error.

**Preconditions**:

- RHOAI 3.5 upgrade completed (from 3.4)
- DSC patched with `llamastackoperator: Removed` and `ogx: Managed`
- `oc` CLI authenticated with cluster-admin privileges

**Test Steps**:

1. Verify the current RHOAI version is 3.5:

   ```bash
   oc get csv -n redhat-ods-operator | grep rhods-operator
   ```

2. Check that the `llamastack.io/v1alpha1` API resource is no longer registered:

   ```bash
   oc api-resources | grep -i llamastack
   ```

3. Check that the `ogx.io/v1beta1` API resource is registered:

   ```bash
   oc api-resources | grep -i ogx
   ```

4. Attempt to apply a `llamastack.io/v1alpha1` LlamaStackDistribution CR:

   ```bash
   oc apply -f - <<EOF
   apiVersion: llamastack.io/v1alpha1
   kind: LlamaStackDistribution
   metadata:
     name: should-fail-v1alpha1
   spec:
     replicas: 1
     server:
       containerSpec:
         env:
           - name: VLLM_URL
             value: "http://vllm:8000"
       distribution:
         name: rh-dev
       storage:
         size: 5Gi
   EOF
   ```

5. Capture and verify the error message:

   ```bash
   ERROR_OUTPUT=$(oc apply -f /dev/stdin 2>&1 <<EOF
   apiVersion: llamastack.io/v1alpha1
   kind: LlamaStackDistribution
   metadata:
     name: should-fail-v1alpha1
   spec:
     replicas: 1
     server:
       containerSpec:
         env:
           - name: VLLM_URL
             value: "http://vllm:8000"
       distribution:
         name: rh-dev
       storage:
         size: 5Gi
   EOF
   )
   echo "$ERROR_OUTPUT"
   echo "$ERROR_OUTPUT" | grep -q "no matches for kind" && echo "PASS: Expected error received" || echo "FAIL: Unexpected response"
   ```

6. Verify the CR was NOT created:

   ```bash
   oc get llamastackdistribution should-fail-v1alpha1 2>&1 || true
   ```

7. Verify that `ogx.io/v1beta1` OGXServer CRs can still be created:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-api-check
   spec:
     replicas: 1
     distribution:
       name: rh-dev
     workload:
       storage:
         size: 5Gi
   EOF
   oc get ogxserver ogx-api-check -o jsonpath='{.metadata.name}'
   ```

8. Clean up:

   ```bash
   oc delete ogxserver ogx-api-check --ignore-not-found
   ```

**Expected Results**:

- `oc api-resources` does NOT list `llamastack.io` or `LlamaStackDistribution`
- `oc api-resources` lists `ogx.io` with `OGXServer` kind
- Applying a `llamastack.io/v1alpha1` LlamaStackDistribution CR fails with an error containing `no
  matches for kind "LlamaStackDistribution" in version "llamastack.io/v1alpha1"`
- No LlamaStackDistribution resource is created
- Applying an `ogx.io/v1beta1` OGXServer CR succeeds (the new API is functional)

**Test Data**:

```yaml
# v1alpha1 CR that should be rejected
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: should-fail-v1alpha1
spec:
  replicas: 1
  server:
    containerSpec:
      env:
        - name: VLLM_URL
          value: "http://vllm:8000"
    distribution:
      name: rh-dev
    storage:
      size: 5Gi
```

```yaml
# v1beta1 CR that should be accepted
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-api-check
spec:
  replicas: 1
  distribution:
    name: rh-dev
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
