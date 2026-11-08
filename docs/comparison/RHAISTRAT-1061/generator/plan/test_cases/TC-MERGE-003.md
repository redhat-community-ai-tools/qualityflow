---
test_case_id: TC-MERGE-003
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---
# TC-MERGE-003: disabledAPIs removes capabilities from generated config

**Objective**: Verify that applying a CR with `spec.disabledAPIs` listing "safety" causes the
generated `config.yaml` to exclude all safety providers.

**Test Steps**:

1. Confirm the base config includes safety providers by inspecting the distribution image OCI
   labels:

   ```bash
   oc image info <distribution-image> --filter-by-os linux/amd64 -o json | \
     jq -r '.config.config.Labels["com.ogx.distribution.configs"]'
   ```

2. Apply an OGXServer CR with safety disabled:

   ```bash
   oc apply -f tc-merge-003-cr.yaml
   ```

3. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/merge-test-003 --for=condition=Ready --timeout=120s
   ```

4. Retrieve the generated ConfigMap and check for safety providers:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=merge-test-003 -o name | head -1) \
     -o jsonpath='{.data.config\.yaml}' | yq '.providers.safety'
   ```

5. Verify the server's enabled APIs do not include safety:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=merge-test-003 -o name | head -1) \
     -o jsonpath='{.data.config\.yaml}' | yq '.apis'
   ```

6. Verify the server pod is running and healthy:

   ```bash
   oc get pods -l ogx.io/owner=merge-test-003 -o wide
   ```

**Expected Results**:

- The generated `config.yaml` does not contain a `providers.safety` section (empty or absent)
- The `apis` list in the generated config does not include "safety"
- Other API types not listed in `disabledAPIs` (e.g., inference, memory) remain present in the
  config
- The server pod starts successfully without safety capabilities

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: merge-test-003
spec:
  image: registry.redhat.io/rhoai/ogx-distribution-rhel9:latest
  disabledAPIs:
    - safety
```

**Notes**: To be filled later in the process.
