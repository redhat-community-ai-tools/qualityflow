---
test_case_id: TC-SECRET-003
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-SECRET-003: Multiple providers with different Secrets

**Objective**: Verify that multiple providers referencing
different Secrets all get correct auto-injected env vars.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or
  namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-secret-003
   ```

2. Create three separate Secrets, each with the
   `ogx.io/watch` label:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: Secret
   metadata:
     name: vllm-secret-a
     namespace: tc-secret-003
     labels:
       ogx.io/watch: "true"
   type: Opaque
   stringData:
     api-token: "vllm-token-provider-a"
   ---
   apiVersion: v1
   kind: Secret
   metadata:
     name: vllm-secret-b
     namespace: tc-secret-003
     labels:
       ogx.io/watch: "true"
   type: Opaque
   stringData:
     api-token: "vllm-token-provider-b"
   ---
   apiVersion: v1
   kind: Secret
   metadata:
     name: pgvector-secret
     namespace: tc-secret-003
     labels:
       ogx.io/watch: "true"
   type: Opaque
   stringData:
     db-password: "pgvector-test-password"
   EOF
   ```

3. Apply the OGXServer CR with two inference providers
   and one vectorIo provider, each referencing a
   different Secret:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-multi-secret
     namespace: tc-secret-003
   spec:
     providers:
       inference:
         remote:
           vllm:
           - id: vllm-inference-a
             endpoint: "https://vllm-a.svc:8000"
             apiToken:
               name: vllm-secret-a
               key: api-token
           - id: vllm-inference-b
             endpoint: "https://vllm-b.svc:8000"
             apiToken:
               name: vllm-secret-b
               key: api-token
       vectorIo:
         remote:
           pgvector:
           - id: pgvector-store
             host: "pgvector.tc-secret-003.svc"
             port: 5432
             database: "vectors"
             user: "ogx"
             password:
               name: pgvector-secret
               key: db-password
   EOF
   ```

4. Wait for the operator to reconcile:

   ```bash
   sleep 15
   oc get ogxserver ogx-multi-secret \
     -n tc-secret-003 -o yaml
   ```

5. List all env vars on the Deployment container
   and verify three distinct auto-injected env vars
   exist:

   ```bash
   oc get deployment ogx-multi-secret \
     -n tc-secret-003 \
     -o jsonpath='{.spec.template.spec.containers[0].env}' \
     | python3 -m json.tool
   ```

6. Verify each env var references the correct Secret
   name and key (no collisions):

   ```bash
   oc get deployment ogx-multi-secret \
     -n tc-secret-003 -o yaml \
     | grep -B2 -A5 'secretKeyRef'
   ```

7. Verify each auto-injected env var has a unique
   name (no duplicates):

   ```bash
   oc get deployment ogx-multi-secret \
     -n tc-secret-003 \
     -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' \
     | tr ' ' '\n' | sort | uniq -d
   ```

8. Inspect the generated config.yaml and verify
   all three provider credential fields use
   `${env.VAR}` references:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-secret-003 \
     -l app.kubernetes.io/instance=ogx-multi-secret \
     -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-secret-003 \
     -o jsonpath='{.data.config\.yaml}'
   ```

9. Count the number of `${env.` references in the
   generated config and confirm there are at least 3:

   ```bash
   oc get configmap "$CM_NAME" -n tc-secret-003 \
     -o jsonpath='{.data.config\.yaml}' \
     | grep -c '${env\.'
   ```

10. Clean up:

    ```bash
    oc delete project tc-secret-003
    ```

**Expected Results**:

- The Deployment contains three distinct auto-injected
  env vars, one for each SecretKeyRef in the CR
- Each env var has a unique name (no collisions between
  the two VLLM providers and the pgvector provider)
- Each env var uses `valueFrom.secretKeyRef` pointing
  to the correct Secret name and key:
  - Provider `vllm-inference-a` -> `vllm-secret-a` /
    `api-token`
  - Provider `vllm-inference-b` -> `vllm-secret-b` /
    `api-token`
  - Provider `pgvector-store` -> `pgvector-secret` /
    `db-password`
- The generated config.yaml has three `${env.VAR}`
  references, one per provider credential
- No Secret values appear in plaintext in the ConfigMap
- Step 7 (duplicate check) produces no output,
  confirming all env var names are unique

**Test Data**:

```yaml
# Three Secrets with ogx.io/watch label
apiVersion: v1
kind: Secret
metadata:
  name: vllm-secret-a
  labels:
    ogx.io/watch: "true"
type: Opaque
stringData:
  api-token: "vllm-token-provider-a"
---
apiVersion: v1
kind: Secret
metadata:
  name: vllm-secret-b
  labels:
    ogx.io/watch: "true"
type: Opaque
stringData:
  api-token: "vllm-token-provider-b"
---
apiVersion: v1
kind: Secret
metadata:
  name: pgvector-secret
  labels:
    ogx.io/watch: "true"
type: Opaque
stringData:
  db-password: "pgvector-test-password"
```

```yaml
# OGXServer CR with multiple providers
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-multi-secret
spec:
  providers:
    inference:
      remote:
        vllm:
        - id: vllm-inference-a
          endpoint: "https://vllm-a.svc:8000"
          apiToken:
            name: vllm-secret-a
            key: api-token
        - id: vllm-inference-b
          endpoint: "https://vllm-b.svc:8000"
          apiToken:
            name: vllm-secret-b
            key: api-token
    vectorIo:
      remote:
        pgvector:
        - id: pgvector-store
          host: "pgvector.tc-secret-003.svc"
          port: 5432
          database: "vectors"
          user: "ogx"
          password:
            name: pgvector-secret
            key: db-password
```

**Notes**: To be filled later in the process.
