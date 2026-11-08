---
test_case_id: TC-UPGRADE-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-UPGRADE-001: Full 3.4 to 3.5 upgrade workflow

**Objective**: Verify the complete upgrade path from RHOAI 3.4 (LlamaStackDistribution v1alpha1) to
RHOAI 3.5 (OGXServer v1beta1), including DSC patching, dual-operator state, and new CR creation with
separate postgres.

**Preconditions**:

- RHOAI 3.4 installed and healthy
- A running LlamaStackDistribution CR (`llama-stack-upgrade-test`) serving inference traffic
- A working VLLM endpoint accessible via the `llama-stack-inference-model-secret` Secret
- Postgres instance for the LLSD (if shared with model registry, note for separate deployment later)
- `oc` CLI authenticated with cluster-admin privileges
- RHOAI 3.5 upgrade available via the operator catalog

**Test Steps**:

1. Deploy the pre-upgrade LlamaStackDistribution CR on RHOAI 3.4:

   ```bash
   oc apply -f - <<EOF
   apiVersion: llamastack.io/v1alpha1
   kind: LlamaStackDistribution
   metadata:
     name: llama-stack-upgrade-test
   spec:
     replicas: 1
     server:
       containerSpec:
         env:
           - name: VLLM_URL
             valueFrom:
               secretKeyRef:
                 key: VLLM_URL
                 name: llama-stack-inference-model-secret
       distribution:
         name: rh-dev
       storage:
         size: 5Gi
   EOF
   ```

2. Verify the LLSD pod is running and serving traffic:

   ```bash
   oc wait llamastackdistribution/llama-stack-upgrade-test --for=condition=Ready --timeout=180s
   LLSD_POD=$(oc get pod -l app.kubernetes.io/instance=llama-stack-upgrade-test -o jsonpath='{.items[0].metadata.name}')
   oc exec "$LLSD_POD" -- curl -s http://localhost:8321/v1/health
   ```

3. Record pre-upgrade state for comparison:

   ```bash
   oc get llamastackdistribution llama-stack-upgrade-test -o yaml > /tmp/pre-upgrade-llsd.yaml
   oc get pvc -l app.kubernetes.io/instance=llama-stack-upgrade-test -o yaml > /tmp/pre-upgrade-pvcs.yaml
   oc get pods -l app.kubernetes.io/instance=llama-stack-upgrade-test -o wide
   ```

4. Upgrade RHOAI from 3.4 to 3.5 (via operator subscription update):

   ```bash
   # The upgrade method depends on the installation channel
   # Verify the upgrade completes
   oc get csv -n redhat-ods-operator | grep rhods-operator
   ```

5. Verify dual-operator state (both old llamastack-operator and new ogx-operator pods running):

   ```bash
   oc get pods -n redhat-ods-applications | grep -E "llamastack-operator|ogx-operator"
   ```

6. Verify the old LLSD CR still exists unchanged after upgrade:

   ```bash
   oc get llamastackdistribution llama-stack-upgrade-test -o yaml | diff /tmp/pre-upgrade-llsd.yaml - || echo "Spec differences detected"
   ```

7. Patch the DSC to remove llamastackoperator and enable ogx:

   ```bash
   oc patch dsc default-dsc --type=merge -p '{
     "spec": {
       "components": {
         "llamastackoperator": {
           "managementState": "Removed"
         },
         "ogx": {
           "managementState": "Managed"
         }
       }
     }
   }'
   ```

8. Wait for DSC reconciliation:

   ```bash
   oc wait dsc/default-dsc --for=condition=Ready --timeout=180s
   ```

9. Deploy a separate postgres instance for the new OGXServer (to avoid model registry conflicts):

   ```bash
   oc apply -f - <<EOF
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: ogx-postgres
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: ogx-postgres
     template:
       metadata:
         labels:
           app: ogx-postgres
       spec:
         containers:
           - name: postgres
             image: registry.redhat.io/rhel9/postgresql-15:latest
             env:
               - name: POSTGRESQL_USER
                 value: ogx
               - name: POSTGRESQL_PASSWORD
                 value: ogx-password
               - name: POSTGRESQL_DATABASE
                 value: ogx
             ports:
               - containerPort: 5432
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: ogx-postgres
   spec:
     selector:
       app: ogx-postgres
     ports:
       - port: 5432
         targetPort: 5432
   EOF
   ```

10. Create the inference secret for the new OGXServer:

    ```bash
    oc create secret generic ogx-inference-secret \
      --from-literal=VLLM_URL="$(oc get secret llama-stack-inference-model-secret -o jsonpath='{.data.VLLM_URL}' | base64 -d)"
    ```

11. Apply the post-upgrade OGXServer CR:

    ```bash
    oc apply -f - <<EOF
    apiVersion: ogx.io/v1beta1
    kind: OGXServer
    metadata:
      name: ogx-upgrade-test
    spec:
      replicas: 1
      distribution:
        name: rh-dev
      workload:
        overrides:
          env:
            - name: VLLM_URL
              valueFrom:
                secretKeyRef:
                  key: VLLM_URL
                  name: ogx-inference-secret
        storage:
          size: 5Gi
    EOF
    ```

12. Wait for the OGXServer to become ready:

    ```bash
    oc wait ogxserver/ogx-upgrade-test --for=condition=Ready --timeout=180s
    ```

13. Verify the new OGXServer pod is running and serving traffic:

    ```bash
    OGX_POD=$(oc get pod -l app.kubernetes.io/instance=ogx-upgrade-test -o jsonpath='{.items[0].metadata.name}')
    oc exec "$OGX_POD" -- curl -s http://localhost:8321/v1/health
    ```

14. Verify inference works on the new OGXServer:

    ```bash
    OGX_ROUTE=$(oc get route ogx-upgrade-test -o jsonpath='{.spec.host}')
    curl -s "https://${OGX_ROUTE}/v1/inference/chat-completion" \
      -H "Content-Type: application/json" \
      -d '{"model_id": "test-model", "messages": [{"role": "user", "content": "Hello"}]}'
    ```

**Expected Results**:

- Pre-upgrade LLSD CR is running and serving traffic on RHOAI 3.4
- RHOAI upgrade from 3.4 to 3.5 completes without errors
- Both llamastack-operator and ogx-operator pods run simultaneously after upgrade
  (dual-operator state)
- The old LLSD CR persists unchanged after upgrade (no automatic CRD migration)
- DSC patch succeeds: `llamastackoperator: Removed`, `ogx: Managed`
- Separate postgres deployment is created for OGXServer
- New OGXServer CR (`ogx.io/v1beta1`) is accepted and reconciles to Ready state
- OGXServer pod starts and the health endpoint returns a successful response
- Inference requests succeed on the new OGXServer

**Test Data**:

```yaml
# Pre-upgrade CR (RHOAI 3.4)
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: llama-stack-upgrade-test
spec:
  replicas: 1
  server:
    containerSpec:
      env:
        - name: VLLM_URL
          valueFrom:
            secretKeyRef:
              key: VLLM_URL
              name: llama-stack-inference-model-secret
    distribution:
      name: rh-dev
    storage:
      size: 5Gi
```

```yaml
# Post-upgrade CR (RHOAI 3.5)
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-upgrade-test
spec:
  replicas: 1
  distribution:
    name: rh-dev
  workload:
    overrides:
      env:
        - name: VLLM_URL
          valueFrom:
            secretKeyRef:
              key: VLLM_URL
              name: ogx-inference-secret
    storage:
      size: 5Gi
```

**Notes**: To be filled later in the process.
