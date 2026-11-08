---
test_case_id: TC-PROVIDER-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-PROVIDER-001: VLLM inference provider expansion

**Objective**: Verify that an OGXServer CR with a VLLM provider generates the correct config.yaml
with provider_type "remote::vllm", URL, and API token, and that the server starts and lists the
provider.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created
- A vLLM-compatible inference endpoint accessible from the cluster
  (or a mock endpoint for validation)
- Environment variables `VLLM_URL` and `VLLM_API_TOKEN` set or a Secret containing these values

**Test Steps**:

1. Create the test namespace and the vLLM credentials secret:

   ```bash
   oc new-project tc-provider-001
   oc create secret generic vllm-credentials \
     -n tc-provider-001 \
     --from-literal=api-token="${VLLM_API_TOKEN}"
   ```

2. Apply the OGXServer CR with a VLLM inference provider:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-vllm
     namespace: tc-provider-001
   spec:
     providers:
       inference:
         - provider_id: vllm-default
           provider_type: remote::vllm
           config:
             url: ${VLLM_URL}
             api_token: ${VLLM_API_TOKEN}
   EOF
   ```

3. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver ogx-vllm -n tc-provider-001 --for=condition=Ready --timeout=180s
   ```

4. Inspect the generated ConfigMap for correct VLLM provider configuration:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-provider-001 -l app.kubernetes.io/instance=ogx-vllm -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-provider-001 -o jsonpath='{.data.config\.yaml}'
   ```

5. Verify the provider appears in the server's provider list:

   ```bash
   OGX_ROUTE=$(oc get route ogx-vllm -n tc-provider-001 -o jsonpath='{.spec.host}' 2>/dev/null)
   if [ -n "$OGX_ROUTE" ]; then
     curl -sk "https://${OGX_ROUTE}/v1/providers" | python3 -m json.tool
   else
     OGX_POD=$(oc get pods -n tc-provider-001 -l app.kubernetes.io/instance=ogx-vllm -o jsonpath='{.items[0].metadata.name}')
     oc exec -n tc-provider-001 "$OGX_POD" -- curl -s http://localhost:8321/v1/providers
   fi
   ```

6. Check server logs for successful provider initialization:

   ```bash
   oc logs -l app.kubernetes.io/instance=ogx-vllm -n tc-provider-001 --tail=30 | grep -i 'vllm\|provider\|inference'
   ```

7. Clean up:

   ```bash
   oc delete project tc-provider-001
   ```

**Expected Results**:

- The generated config.yaml contains an inference provider entry with:
  - `provider_id: vllm-default`
  - `provider_type: remote::vllm`
  - `config.url` set to the VLLM endpoint URL
  - `config.api_token` set to the API token value
- The OGXServer pod starts successfully and reaches Ready state
- The `/v1/providers` endpoint lists `vllm-default` as an available inference provider
- Server logs show successful initialization of the VLLM provider without errors

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-vllm
spec:
  providers:
    inference:
      - provider_id: vllm-default
        provider_type: remote::vllm
        config:
          url: ${VLLM_URL}
          api_token: ${VLLM_API_TOKEN}
```

**Notes**:

- To be filled later in the process.
