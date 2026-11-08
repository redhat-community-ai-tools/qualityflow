---
test_case_id: TC-BASECONFIG-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-BASECONFIG-001: Explicit baseConfig takes precedence over OCI labels

**Objective**: Verify that a ConfigMap referenced by `spec.baseConfig`
overrides OCI image labels as the base configuration source.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- Distribution image carrying OCI config labels available
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-baseconfig-001
   ```

2. Decode the OCI label config for later comparison:

   ```bash
   skopeo inspect --no-tags \
     docker://<distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.config.config.yaml"]' | \
     base64 -d > /tmp/oci-base-config.yaml
   cat /tmp/oci-base-config.yaml
   ```

3. Create a custom base ConfigMap with a distinct marker
   so it can be differentiated from the OCI label config:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: custom-base-config
     namespace: tc-baseconfig-001
   data:
     config.yaml: |
       version: '2'
       apis:
         - agents
         - inference
         - safety
       metadata_store:
         type: sqlite
         db_path: /var/lib/ogx/custom-base.db
   EOF
   ```

4. Apply an OGXServer CR with `spec.baseConfig` pointing
   to the custom ConfigMap AND `spec.providers` set:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-baseconfig-test
     namespace: tc-baseconfig-001
   spec:
     baseConfig:
       configMapRef:
         name: custom-base-config
         key: config.yaml
     providers:
       inference:
         - provider_id: vllm-test
           provider_type: remote::vllm
           config:
             url: "https://model-endpoint/v1"
   EOF
   ```

5. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver/ogx-baseconfig-test \
     -n tc-baseconfig-001 \
     --for=condition=Ready --timeout=300s
   ```

6. Retrieve the generated ConfigMap and extract the
   merged config:

   ```bash
   oc get configmap -n tc-baseconfig-001 \
     -l ogx.redhat.com/server=ogx-baseconfig-test \
     -o jsonpath='{.items[0].data.config\.yaml}' \
     > /tmp/generated-config.yaml
   cat /tmp/generated-config.yaml
   ```

7. Verify the generated config contains the custom base
   marker (sqlite path) and NOT the OCI label defaults:

   ```bash
   grep "custom-base.db" /tmp/generated-config.yaml
   diff /tmp/oci-base-config.yaml \
     /tmp/generated-config.yaml || true
   ```

8. Clean up:

   ```bash
   oc delete project tc-baseconfig-001
   ```

**Expected Results**:

- The OGXServer reaches Ready condition without errors.
- The generated ConfigMap merges `spec.providers` on top
  of the custom base ConfigMap content, not OCI labels.
- The generated config contains `custom-base.db` from the
  custom base ConfigMap.
- The generated config does NOT contain values unique to
  the OCI label base config.
- Operator logs show no warnings about OCI label parsing
  (OCI labels are skipped when baseConfig is set).

**Test Data**:

```yaml
# Custom base ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: custom-base-config
data:
  config.yaml: |
    version: '2'
    apis:
      - agents
      - inference
      - safety
    metadata_store:
      type: sqlite
      db_path: /var/lib/ogx/custom-base.db
```

```yaml
# OGXServer CR with baseConfig + providers
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-baseconfig-test
spec:
  baseConfig:
    configMapRef:
      name: custom-base-config
      key: config.yaml
  providers:
    inference:
      - provider_id: vllm-test
        provider_type: remote::vllm
        config:
          url: "https://model-endpoint/v1"
```

**Notes**: To be filled later in the process.
