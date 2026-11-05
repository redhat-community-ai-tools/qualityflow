---
test_case_id: TC-SECRET-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-SECRET-002: pgvector password SecretKeyRef auto-injection

**Objective**: Verify that a pgvector password SecretKeyRef
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
   oc new-project tc-secret-002
   ```

2. Create the Secret with the `ogx.io/watch` label:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: Secret
   metadata:
     name: pgvector-secret
     namespace: tc-secret-002
     labels:
       ogx.io/watch: "true"
   type: Opaque
   stringData:
     db-password: "test-pgvector-password"
   EOF
   ```

3. Apply the OGXServer CR with a pgvector vector_io
   provider using SecretKeyRef for the password:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-secret-pgvector
     namespace: tc-secret-002
   spec:
     providers:
       vectorIo:
         remote:
           pgvector:
           - id: pgvector-store
             host: "pgvector.tc-secret-002.svc"
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
   oc get ogxserver ogx-secret-pgvector \
     -n tc-secret-002 -o yaml
   ```

5. Verify the Deployment has the auto-injected env var
   referencing the Secret:

   ```bash
   oc get deployment ogx-secret-pgvector \
     -n tc-secret-002 \
     -o jsonpath='{.spec.template.spec.containers[0].env}' \
     | python3 -m json.tool
   ```

6. Confirm the env var name follows the expected pattern
   (e.g., `OGX_PGVECTOR_PASSWORD`):

   ```bash
   oc get deployment ogx-secret-pgvector \
     -n tc-secret-002 \
     -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' \
     | tr ' ' '\n' | grep -i 'OGX.*PGVECTOR.*PASSWORD'
   ```

7. Verify the env var uses `valueFrom.secretKeyRef`
   pointing to the correct Secret name and key:

   ```bash
   oc get deployment ogx-secret-pgvector \
     -n tc-secret-002 -o yaml \
     | grep -A5 'secretKeyRef'
   ```

8. Inspect the generated config.yaml for `${env.VAR}`
   syntax referencing the password env var:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-secret-002 \
     -l app.kubernetes.io/instance=ogx-secret-pgvector \
     -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-secret-002 \
     -o jsonpath='{.data.config\.yaml}'
   ```

9. Verify the config.yaml uses `${env.` for the
   password field (not a plaintext value):

   ```bash
   oc get configmap "$CM_NAME" -n tc-secret-002 \
     -o jsonpath='{.data.config\.yaml}' \
     | grep '${env\.'
   ```

10. Clean up:

    ```bash
    oc delete project tc-secret-002
    ```

**Expected Results**:

- The Deployment contains an auto-injected env var
  (e.g., `OGX_PGVECTOR_PASSWORD`) that was not
  explicitly defined in the CR
- The env var uses `valueFrom.secretKeyRef` with
  `name: pgvector-secret` and `key: db-password`
- The generated config.yaml references the env var
  using `${env.OGX_PGVECTOR_PASSWORD}` syntax
  (or the operator's actual naming convention)
- The operator did not inline the Secret value into
  the ConfigMap in plaintext

**Test Data**:

```yaml
# Secret with ogx.io/watch label
apiVersion: v1
kind: Secret
metadata:
  name: pgvector-secret
  labels:
    ogx.io/watch: "true"
type: Opaque
stringData:
  db-password: "test-pgvector-password"
```

```yaml
# OGXServer CR with SecretKeyRef for password
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-secret-pgvector
spec:
  providers:
    vectorIo:
      remote:
        pgvector:
        - id: pgvector-store
          host: "pgvector.tc-secret-002.svc"
          port: 5432
          database: "vectors"
          user: "ogx"
          password:
            name: pgvector-secret
            key: db-password
```

**Notes**: To be filled later in the process.
