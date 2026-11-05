---
test_case_id: TC-OCI-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-OCI-001: Base config loaded from OCI labels

**Objective**: Verify the OGX operator reads base configuration from OCI image labels
(`com.ogx.config.<filename>`) and populates the generated ConfigMap accordingly.

**Test Steps**:

1. Identify the distribution image to use and verify it carries OCI labels:

   ```bash
   skopeo inspect --no-tags docker://<distribution-image>:<tag> | \
     jq '.Labels | to_entries[] | select(.key | startswith("com.ogx.config."))'
   ```

2. Confirm the `com.ogx.config.config.yaml` label exists and its value is valid base64-encoded YAML:

   ```bash
   skopeo inspect --no-tags docker://<distribution-image>:<tag> | \
     jq -r '.Labels["com.ogx.config.config.yaml"]' | base64 -d | python3 -c "import sys, yaml; yaml.safe_load(sys.stdin)"
   ```

3. Deploy an OGXServer CR pointing to the distribution image:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.redhat.com/v1alpha1
   kind: OGXServer
   metadata:
     name: test-oci-base-config
     namespace: test-ogx
   spec:
     image: <distribution-image>:<tag>
   EOF
   ```

4. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver/test-oci-base-config -n test-ogx \
     --for=condition=Ready --timeout=300s
   ```

5. Retrieve the generated ConfigMap and extract config.yaml:

   ```bash
   oc get configmap -n test-ogx -l ogx.redhat.com/server=test-oci-base-config \
     -o jsonpath='{.items[0].data.config\.yaml}'
   ```

6. Compare the ConfigMap config.yaml content against the decoded OCI label value from step 2.

**Expected Results**:

- `skopeo inspect` shows labels prefixed with `com.ogx.config.` on the distribution image.
- The `com.ogx.config.config.yaml` label value decodes to valid YAML.
- The OGXServer reaches Ready condition without errors.
- The generated ConfigMap contains a `config.yaml` key whose content matches the base config
  extracted from the OCI label.
- No warnings or errors in the operator logs related to OCI label parsing.

**Test Data**:

Use an official OGX distribution image known to carry OCI labels. The exact image reference depends
on the RHOAI version under test.

**Notes**: To be filled later in the process.
