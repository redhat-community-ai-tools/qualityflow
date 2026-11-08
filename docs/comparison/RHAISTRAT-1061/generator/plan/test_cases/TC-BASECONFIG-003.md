---
test_case_id: TC-BASECONFIG-003
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-BASECONFIG-003: baseConfig alone without declarative fields

**Objective**: Verify that setting only `spec.baseConfig` without any
declarative fields does NOT activate config generation.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-baseconfig-003
   ```

2. Create the base ConfigMap:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: base-only-config
     namespace: tc-baseconfig-003
   data:
     config.yaml: |
       version: '2'
       apis:
         - agents
         - inference
       metadata_store:
         type: sqlite
         db_path: /var/lib/ogx/base-only.db
   EOF
   ```

3. Apply an OGXServer CR with ONLY `spec.baseConfig`
   set (no providers, resources, storage, or
   disabledAPIs):

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-baseconfig-only
     namespace: tc-baseconfig-003
   spec:
     baseConfig:
       configMapRef:
         name: base-only-config
         key: config.yaml
   EOF
   ```

4. Wait for the server pod to become ready:

   ```bash
   oc wait --for=condition=Ready pod \
     -l app=ogx-baseconfig-only \
     -n tc-baseconfig-003 --timeout=300s
   ```

5. Check whether a generated ConfigMap was created:

   ```bash
   oc get configmap -n tc-baseconfig-003 \
     -l ogx.redhat.com/server=ogx-baseconfig-only
   ```

6. Inspect the pod's mounted config volume to confirm
   it uses the default distribution config, not the
   base ConfigMap content:

   ```bash
   oc exec deploy/ogx-baseconfig-only \
     -n tc-baseconfig-003 -- \
     cat /etc/ogx/config.yaml
   ```

7. Verify operator logs show no config generation
   activity for this CR:

   ```bash
   oc logs deployment/ogx-operator \
     -n <operator-namespace> --tail=50 | \
     grep "ogx-baseconfig-only"
   ```

8. Clean up:

   ```bash
   oc delete project tc-baseconfig-003
   ```

**Expected Results**:

- The OGXServer CR is accepted and the server pod
  starts successfully.
- No generated ConfigMap is created by the operator
  (config generation is not activated).
- The server uses the default distribution config
  baked into the image, not the base ConfigMap content.
- The base ConfigMap (`base-only-config`) exists but
  is not referenced by the pod.
- Operator logs show no config merge or generation
  entries for this CR.

**Test Data**:

```yaml
# Base ConfigMap (should NOT be used)
apiVersion: v1
kind: ConfigMap
metadata:
  name: base-only-config
data:
  config.yaml: |
    version: '2'
    apis:
      - agents
      - inference
    metadata_store:
      type: sqlite
      db_path: /var/lib/ogx/base-only.db
```

```yaml
# OGXServer CR with baseConfig only
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-baseconfig-only
spec:
  baseConfig:
    configMapRef:
      name: base-only-config
      key: config.yaml
```

**Notes**: To be filled later in the process.
