---
test_case_id: TC-ADOPT-003
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-ADOPT-003: Invalid adoption annotations don't disrupt reconciliation

**Objective**: Verify that applying an OGXServer CR with invalid adoption annotations
(referencing non-existent resources) does not crash the operator and allows normal reconciliation to
proceed.

**Preconditions**:

- RHOAI 3.5 installed with OGX operator running
- DSC configured with `ogx: Managed`
- Namespace with no PVC named `nonexistent-pvc`
- `oc` CLI authenticated with cluster-admin privileges

**Test Steps**:

1. Confirm no PVC named `nonexistent-pvc` exists in the namespace:

   ```bash
   oc get pvc nonexistent-pvc 2>&1 || true
   ```

2. Apply an OGXServer CR with an adoption annotation referencing a non-existent PVC:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-invalid-adopt
     annotations:
       ogx.io/adopt-pvc: nonexistent-pvc
   spec:
     replicas: 1
     distribution:
       name: rh-dev
     workload:
       storage:
         size: 5Gi
   EOF
   ```

3. Wait for reconciliation to proceed (the CR should still reconcile):

   ```bash
   oc wait ogxserver/ogx-invalid-adopt --for=condition=Ready --timeout=120s
   ```

4. Check the operator pod logs for errors related to the invalid adoption annotation:

   ```bash
   OPERATOR_POD=$(oc get pod -n redhat-ods-applications -l app.kubernetes.io/name=ogx-operator -o jsonpath='{.items[0].metadata.name}')
   oc logs "$OPERATOR_POD" -n redhat-ods-applications --tail=50 | grep -i "adopt\|nonexistent"
   ```

5. Verify the operator pod is still running (no crash loop):

   ```bash
   oc get pod -n redhat-ods-applications -l app.kubernetes.io/name=ogx-operator -o jsonpath='{.items[0].status.phase}'
   ```

6. Check the OGXServer status conditions for an adoption warning or failure condition:

   ```bash
   oc get ogxserver ogx-invalid-adopt -o jsonpath='{.status.conditions}' | jq '.'
   ```

7. Verify the OGXServer pod is running (server started despite invalid adoption):

   ```bash
   oc get pod -l app.kubernetes.io/instance=ogx-invalid-adopt -o jsonpath='{.items[0].status.phase}'
   ```

8. Clean up:

   ```bash
   oc delete ogxserver ogx-invalid-adopt --ignore-not-found
   ```

**Expected Results**:

- OGXServer CR is accepted by the API server (no admission webhook rejection)
- Operator does not crash or enter CrashLoopBackOff due to the invalid annotation
- Operator pod remains in Running phase throughout
- OGXServer CR reaches Ready state (the server starts normally with its own new PVC)
- Status conditions include a warning or informational message about the failed adoption attempt
  (e.g., `ResourcesAdopted: False` with a message indicating the PVC was not found)
- Operator logs contain a warning-level message about the non-existent PVC, not a panic or fatal
  error

**Test Data**:

```yaml
# OGXServer CR with invalid adoption annotation
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-invalid-adopt
  annotations:
    ogx.io/adopt-pvc: nonexistent-pvc
spec:
  replicas: 1
  distribution:
    name: rh-dev
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
