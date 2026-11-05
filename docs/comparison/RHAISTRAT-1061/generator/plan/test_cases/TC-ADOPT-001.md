---
test_case_id: TC-ADOPT-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-ADOPT-001: Annotation-driven PVC adoption

**Objective**: Verify the OGX operator adopts a legacy LlamaStackDistribution PVC into an OGXServer
CR when adoption annotations are applied.

**Preconditions**:

- RHOAI 3.5 installed with OGX operator running
- DSC configured with `ogx: Managed`
- Namespace with no existing OGXServer CR
- `oc` CLI authenticated with cluster-admin privileges

**Test Steps**:

1. Create a PVC with legacy LLSD labels simulating a leftover from a LlamaStackDistribution
   deployment:

   ```bash
   oc apply -f - <<EOF
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: llsd-legacy-storage
     labels:
       app.kubernetes.io/managed-by: llamastack-operator
       app.kubernetes.io/instance: llama-stack-legacy
   spec:
     accessModes:
       - ReadWriteOnce
     resources:
       requests:
         storage: 5Gi
   EOF
   ```

2. Verify the PVC is created and bound:

   ```bash
   oc get pvc llsd-legacy-storage -o jsonpath='{.status.phase}'
   ```

3. Apply an OGXServer CR with adoption annotations referencing the legacy PVC:

   ```yaml
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-adopt-test
     annotations:
       ogx.io/adopt-pvc: llsd-legacy-storage
   spec:
     replicas: 1
     distribution:
       name: rh-dev
     workload:
       storage:
         size: 5Gi
   ```

4. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/ogx-adopt-test --for=condition=Ready --timeout=120s
   ```

5. Check the PVC owner reference was set to the OGXServer CR:

   ```bash
   oc get pvc llsd-legacy-storage -o jsonpath='{.metadata.ownerReferences[0].kind}'
   ```

6. Check the adoption status condition on the OGXServer CR:

   ```bash
   oc get ogxserver ogx-adopt-test -o jsonpath='{.status.conditions}' | jq '.[] | select(.type=="ResourcesAdopted")'
   ```

7. Verify the PVC is mounted in the OGXServer pod:

   ```bash
   oc get pod -l app.kubernetes.io/instance=ogx-adopt-test -o jsonpath='{.items[0].spec.volumes[*].persistentVolumeClaim.claimName}'
   ```

**Expected Results**:

- PVC `llsd-legacy-storage` is created and bound
- OGXServer CR reconciles successfully and reaches Ready state
- PVC `ownerReferences[0].kind` is `OGXServer` and `ownerReferences[0].name` is `ogx-adopt-test`
- OGXServer status condition `ResourcesAdopted` is `True` with a message referencing the adopted PVC
- The OGXServer pod mounts the adopted PVC

**Test Data**:

```yaml
# Legacy PVC with LLSD labels
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: llsd-legacy-storage
  labels:
    app.kubernetes.io/managed-by: llamastack-operator
    app.kubernetes.io/instance: llama-stack-legacy
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

```yaml
# OGXServer CR with adoption annotation
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-adopt-test
  annotations:
    ogx.io/adopt-pvc: llsd-legacy-storage
spec:
  replicas: 1
  distribution:
    name: rh-dev
  workload:
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
