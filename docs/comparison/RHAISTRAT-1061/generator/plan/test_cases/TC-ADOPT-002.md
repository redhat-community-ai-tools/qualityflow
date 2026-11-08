---
test_case_id: TC-ADOPT-002
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-ADOPT-002: PVC orphaned on CR deletion

**Objective**: Verify that deleting an OGXServer CR that adopted a legacy PVC does not delete the
PVC, preserving data safety through orphaning.

**Preconditions**:

- RHOAI 3.5 installed with OGX operator running
- TC-ADOPT-001 completed successfully
  (OGXServer CR `ogx-adopt-test` has adopted PVC `llsd-legacy-storage`)
- The OGXServer CR is in Ready state with the adopted PVC mounted
- `oc` CLI authenticated with cluster-admin privileges

**Test Steps**:

1. Confirm the OGXServer CR and adopted PVC exist and the PVC has an owner reference:

   ```bash
   oc get ogxserver ogx-adopt-test -o jsonpath='{.status.conditions}' | jq '.[] | select(.type=="Ready")'
   oc get pvc llsd-legacy-storage -o jsonpath='{.metadata.ownerReferences}'
   ```

2. Write a test marker file to the PVC to verify data integrity after deletion:

   ```bash
   POD=$(oc get pod -l app.kubernetes.io/instance=ogx-adopt-test -o jsonpath='{.items[0].metadata.name}')
   oc exec "$POD" -- sh -c 'echo "adoption-integrity-check" > /data/test-marker.txt'
   ```

3. Delete the OGXServer CR:

   ```bash
   oc delete ogxserver ogx-adopt-test
   ```

4. Wait for the CR to be fully deleted:

   ```bash
   oc wait ogxserver/ogx-adopt-test --for=delete --timeout=60s
   ```

5. Verify the PVC still exists:

   ```bash
   oc get pvc llsd-legacy-storage -o jsonpath='{.metadata.name}'
   ```

6. Verify the PVC no longer has an owner reference (orphaned):

   ```bash
   oc get pvc llsd-legacy-storage -o jsonpath='{.metadata.ownerReferences}'
   ```

7. Verify data integrity by mounting the PVC in a temporary pod:

   ```bash
   oc run pvc-check --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
     --restart=Never \
     --overrides='{
       "spec": {
         "containers": [{
           "name": "pvc-check",
           "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
           "command": ["cat", "/data/test-marker.txt"],
           "volumeMounts": [{"name": "data", "mountPath": "/data"}]
         }],
         "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "llsd-legacy-storage"}}]
       }
     }'
   oc wait pod/pvc-check --for=condition=Ready --timeout=30s
   oc logs pvc-check
   ```

8. Clean up temporary pod:

   ```bash
   oc delete pod pvc-check --ignore-not-found
   ```

**Expected Results**:

- OGXServer CR `ogx-adopt-test` is deleted successfully
- PVC `llsd-legacy-storage` is NOT deleted (still exists in the namespace)
- PVC owner reference is removed (empty or absent `ownerReferences` field)
- Data written to the PVC before CR deletion is intact
  (`test-marker.txt` contains `adoption-integrity-check`)

**Test Data**:

```yaml
# No new resources to create — this test operates on resources from TC-ADOPT-001
# Temporary verification pod spec:
apiVersion: v1
kind: Pod
metadata:
  name: pvc-check
spec:
  restartPolicy: Never
  containers:
    - name: pvc-check
      image: registry.access.redhat.com/ubi9/ubi-minimal:latest
      command: ["cat", "/data/test-marker.txt"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: llsd-legacy-storage
```

**Notes**: To be filled later in the process.
