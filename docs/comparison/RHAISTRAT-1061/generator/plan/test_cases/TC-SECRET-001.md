---
test_case_id: TC-SECRET-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-SECRET-001: VLLM apiToken SecretKeyRef auto-injection

**Objective**: Verify that a VLLM apiToken SecretKeyRef
is auto-injected as an env var into the Deployment.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or
  namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-secret-001
   ```

2. Create the Secret with the `ogx.io/watch` label:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: Secret
   metadata:
     name: vllm-secret
     namespace: tc-secret-001
     labels:
       ogx.io/watch: "true"
   type: Opaque
   stringData:
     api-token: "test-vllm-api-token-value"
   EOF
   ```

3. Apply the OGXServer CR with a VLLM inference provider
   using SecretKeyRef for apiToken:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-secret-vllm
     namespace: tc-secret-001
   spec:
     providers:
       inference:
         remote:
           vllm:
           - id: vllm-inference
             endpoint: "https://vllm.svc:8000"
             apiToken:
               name: vllm-secret
               key: api-token
   EOF
   ```

4. Wait for the operator to reconcile:

   ```bash
   sleep 15
   oc get ogxserver ogx-secret-vllm \
     -n tc-secret-001 -o yaml
   ```

5. Verify the Deployment has the auto-injected env var
   referencing the Secret:

   ```bash
   oc get deployment ogx-secret-vllm \
     -n tc-secret-001 \
     -o jsonpath='{.spec.template.spec.containers[0].env}' \
     | python3 -m json.tool
   ```

6. Confirm the env var name follows the expected pattern
   (e.g., `OGX_VLLM_INFERENCE_API_TOKEN`):

   ```bash
   oc get deployment ogx-secret-vllm \
     -n tc-secret-001 \
     -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' \
     | tr ' ' '\n' | grep -i 'OGX.*VLLM.*TOKEN'
   ```

7. Verify the env var uses `valueFrom.secretKeyRef` pointing
   to the correct Secret name and key:

   ```bash
   oc get deployment ogx-secret-vllm \
     -n tc-secret-001 -o yaml \
     | grep -A5 'secretKeyRef'
   ```

8. Inspect the generated ConfigMap for `${env.VAR}` syntax
   referencing the auto-injected env var:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-secret-001 \
     -l app.kubernetes.io/instance=ogx-secret-vllm \
     -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-secret-001 \
     -o jsonpath='{.data.config\.yaml}'
   ```

9. Verify the config.yaml contains an `${env.` reference
   for the API token field:

   ```bash
   oc get configmap "$CM_NAME" -n tc-secret-001 \
     -o jsonpath='{.data.config\.yaml}' \
     | grep '${env\.'
   ```

10. Clean up:

    ```bash
    oc delete project tc-secret-001
    ```

**Expected Results**:

- The Deployment contains an auto-injected env var
  (e.g., `OGX_VLLM_INFERENCE_API_TOKEN`) that was not
  explicitly defined in the CR
- The env var uses `valueFrom.secretKeyRef` with
  `name: vllm-secret` and `key: api-token`
- The generated config.yaml references the env var
  using `${env.OGX_VLLM_INFERENCE_API_TOKEN}` syntax
  (or the operator's actual naming convention)
- The operator did not inline the Secret value into
  the ConfigMap in plaintext

**Test Data**:

```yaml
# Secret with ogx.io/watch label
apiVersion: v1
kind: Secret
metadata:
  name: vllm-secret
  labels:
    ogx.io/watch: "true"
type: Opaque
stringData:
  api-token: "test-vllm-api-token-value"
```

```yaml
# OGXServer CR with SecretKeyRef for apiToken
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-secret-vllm
spec:
  providers:
    inference:
      remote:
        vllm:
        - id: vllm-inference
          endpoint: "https://vllm.svc:8000"
          apiToken:
            name: vllm-secret
            key: api-token
```

**Notes**: To be filled later in the process.
