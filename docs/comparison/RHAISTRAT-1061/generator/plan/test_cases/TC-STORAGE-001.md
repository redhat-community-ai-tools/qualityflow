---
test_case_id: TC-STORAGE-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-STORAGE-001: Postgres storage backend

**Objective**: Verify that an OGXServer CR with Postgres storage config generates the correct
config.yaml, the server connects to PostgreSQL, and metadata is stored successfully.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created
- PostgreSQL 15 container image available: `registry.redhat.io/rhel9/postgresql-15:latest`

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-storage-001
   ```

2. Deploy a PostgreSQL 15 instance:

   ```bash
   oc create secret generic ogx-postgres-secret \
     -n tc-storage-001 \
     --from-literal=password="ogx-test-password-$(date +%s | sha256sum | head -c 12)"

   oc apply -f - <<'EOF'
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: ogx-postgres
     namespace: tc-storage-001
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
           - name: postgresql
             image: registry.redhat.io/rhel9/postgresql-15:latest
             ports:
               - containerPort: 5432
             env:
               - name: POSTGRESQL_USER
                 value: ogx
               - name: POSTGRESQL_PASSWORD
                 valueFrom:
                   secretKeyRef:
                     name: ogx-postgres-secret
                     key: password
               - name: POSTGRESQL_DATABASE
                 value: ogx_metadata
             resources:
               requests:
                 memory: 256Mi
                 cpu: 100m
               limits:
                 memory: 512Mi
                 cpu: 500m
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: ogx-postgres
     namespace: tc-storage-001
   spec:
     selector:
       app: ogx-postgres
     ports:
       - port: 5432
         targetPort: 5432
   EOF
   ```

3. Wait for PostgreSQL to become ready:

   ```bash
   oc wait deployment ogx-postgres -n tc-storage-001 --for=condition=Available --timeout=120s
   ```

4. Verify PostgreSQL is accepting connections:

   ```bash
   PG_POD=$(oc get pods -n tc-storage-001 -l app=ogx-postgres -o jsonpath='{.items[0].metadata.name}')
   oc exec -n tc-storage-001 "$PG_POD" -- psql -U ogx -d ogx_metadata -c "SELECT 1;"
   ```

5. Apply the OGXServer CR with Postgres storage configuration:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-postgres-storage
     namespace: tc-storage-001
   spec:
     storage:
       type: postgres
       config:
         host: ogx-postgres.tc-storage-001.svc.cluster.local
         port: 5432
         db: ogx_metadata
         user: ogx
         password:
           valueFrom:
             secretKeyRef:
               name: ogx-postgres-secret
               key: password
   EOF
   ```

6. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver ogx-postgres-storage -n tc-storage-001 --for=condition=Ready --timeout=180s
   ```

7. Inspect the generated ConfigMap for correct Postgres storage configuration:

   ```bash
   CM_NAME=$(oc get configmaps -n tc-storage-001 -l app.kubernetes.io/instance=ogx-postgres-storage -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$CM_NAME" -n tc-storage-001 -o jsonpath='{.data.config\.yaml}'
   ```

8. Verify the config.yaml contains Postgres connection details (not SQLite):

   ```bash
   oc get configmap "$CM_NAME" -n tc-storage-001 -o jsonpath='{.data.config\.yaml}' | grep -E 'postgres|host|port|db:'
   ```

9. Check the OGX server logs for successful Postgres connection:

   ```bash
   oc logs -l app.kubernetes.io/instance=ogx-postgres-storage -n tc-storage-001 --tail=50 | grep -i 'postgres\|storage\|database\|connect'
   ```

10. Verify metadata is being stored in Postgres by checking for OGX tables:

    ```bash
    PG_POD=$(oc get pods -n tc-storage-001 -l app=ogx-postgres -o jsonpath='{.items[0].metadata.name}')
    oc exec -n tc-storage-001 "$PG_POD" -- psql -U ogx -d ogx_metadata -c "\dt"
    ```

11. Clean up:

    ```bash
    oc delete project tc-storage-001
    ```

**Expected Results**:

- PostgreSQL 15 deploys and accepts connections on port 5432
- The OGXServer CR is accepted and reconciled successfully
- The generated config.yaml contains Postgres storage configuration with:
  - Storage type set to postgres (not sqlite)
  - `host` pointing to the PostgreSQL service
  - `port` set to 5432
  - `db` set to `ogx_metadata`
  - `user` set to `ogx`
  - Password resolved from the Secret reference
- The OGX server pod starts and connects to PostgreSQL without errors
- PostgreSQL contains OGX metadata tables after server initialization
- No SQLite files are created in the server pod

**Test Data**:

OGXServer CR with Postgres storage:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-postgres-storage
spec:
  storage:
    type: postgres
    config:
      host: ogx-postgres.<namespace>.svc.cluster.local
      port: 5432
      db: ogx_metadata
      user: ogx
      password:
        valueFrom:
          secretKeyRef:
            name: ogx-postgres-secret
            key: password
```

PostgreSQL deployment:

```yaml
image: registry.redhat.io/rhel9/postgresql-15:latest
env:
  POSTGRESQL_USER: ogx
  POSTGRESQL_PASSWORD: <from-secret>
  POSTGRESQL_DATABASE: ogx_metadata
```

**Notes**:

- To be filled later in the process.
