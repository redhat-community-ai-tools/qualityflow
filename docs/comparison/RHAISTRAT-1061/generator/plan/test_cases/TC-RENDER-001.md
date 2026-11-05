---
test_case_id: TC-RENDER-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---
# TC-RENDER-001: Immutable ConfigMap created with hash name

**Objective**: Verify that applying an OGXServer CR causes the operator to create an immutable
ConfigMap named `<cr-name>-config-<hash>` containing valid `config.yaml`, mounted to the server pod.

**Test Steps**:

1. Apply an OGXServer CR:

   ```bash
   oc apply -f tc-render-001-cr.yaml
   ```

2. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/render-test-001 --for=condition=Ready --timeout=120s
   ```

3. List ConfigMaps owned by the CR and verify the naming pattern:

   ```bash
   oc get configmap -l ogx.io/owner=render-test-001 -o name
   ```

4. Verify the ConfigMap name matches the pattern `render-test-001-config-<hash>`:

   ```bash
   oc get configmap -l ogx.io/owner=render-test-001 -o jsonpath='{.items[0].metadata.name}'
   ```

5. Verify the ConfigMap is marked as immutable:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=render-test-001 -o jsonpath='{.items[0].metadata.name}') \
     -o jsonpath='{.immutable}'
   ```

6. Verify the ConfigMap contains valid `config.yaml` content:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=render-test-001 -o jsonpath='{.items[0].metadata.name}') \
     -o jsonpath='{.data.config\.yaml}' | yq '.'
   ```

7. Verify the ConfigMap is mounted to the server pod:

   ```bash
   oc get pod -l ogx.io/owner=render-test-001 \
     -o jsonpath='{.items[0].spec.volumes[*].configMap.name}'
   ```

8. Verify the mount path inside the container:

   ```bash
   oc get pod -l ogx.io/owner=render-test-001 \
     -o jsonpath='{.items[0].spec.containers[0].volumeMounts[*].mountPath}'
   ```

**Expected Results**:

- A ConfigMap named `render-test-001-config-<hash>` exists
  (where `<hash>` is a content-based hash suffix)
- The ConfigMap has `immutable: true`
- The ConfigMap's `data` field contains a `config.yaml` key with valid YAML content
- The `config.yaml` includes expected sections: `providers`, `apis`, and `metadata_store`
- The server pod's volume list references the ConfigMap by its exact hashed name
- The ConfigMap is mounted at the expected path inside the server container

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: render-test-001
spec:
  image: registry.redhat.io/rhoai/ogx-distribution-rhel9:latest
```

**Notes**: To be filled later in the process.
