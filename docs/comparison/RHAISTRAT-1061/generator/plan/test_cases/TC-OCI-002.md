---
test_case_id: TC-OCI-002
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-OCI-002: Embedded config fallback when OCI labels absent

**Objective**: Verify that when the distribution image does not carry OCI labels, the operator falls
back to embedded configuration and the OGXServer starts successfully.

**Test Steps**:

1. Identify or build a distribution image without OCI labels and confirm labels are absent:

   ```bash
   skopeo inspect --no-tags docker://<image-without-labels>:<tag> | \
     jq '.Labels | to_entries[] | select(.key | startswith("com.ogx."))'
   ```

   The output should be empty or contain no `com.ogx.config.*` keys.
2. Deploy an OGXServer CR pointing to the label-free image:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.redhat.com/v1alpha1
   kind: OGXServer
   metadata:
     name: test-oci-fallback
     namespace: test-ogx
   spec:
     image: <image-without-labels>:<tag>
   EOF
   ```

3. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver/test-oci-fallback -n test-ogx \
     --for=condition=Ready --timeout=300s
   ```

4. Check the operator logs for fallback behavior:

   ```bash
   oc logs deployment/ogx-operator -n ogx-system --since=2m | \
     grep -i -E "fallback|embedded|label"
   ```

5. Verify the server pod is running and serving requests:

   ```bash
   oc get pods -n test-ogx -l ogx.redhat.com/server=test-oci-fallback
   oc exec -n test-ogx deploy/test-oci-fallback -- \
     curl -sf http://localhost:8321/v1/health
   ```

6. Retrieve the generated ConfigMap and confirm it contains a valid config.yaml:

   ```bash
   oc get configmap -n test-ogx -l ogx.redhat.com/server=test-oci-fallback \
     -o jsonpath='{.items[0].data.config\.yaml}' | \
     python3 -c "import sys, yaml; yaml.safe_load(sys.stdin) and print('valid')"
   ```

**Expected Results**:

- `skopeo inspect` confirms no `com.ogx.config.*` labels on the image.
- The operator logs indicate a fallback to embedded configuration (no crash or error).
- The OGXServer reaches Ready condition.
- The server pod is Running and the health endpoint returns a successful response.
- The generated ConfigMap contains a valid config.yaml derived from embedded defaults.

**Test Data**:

A distribution image without OCI labels is required. This can be a custom-built image or an older
image predating OCI label support.

**Notes**: To be filled later in the process.
