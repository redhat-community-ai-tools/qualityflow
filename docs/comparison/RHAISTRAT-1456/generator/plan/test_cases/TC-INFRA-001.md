---
test_case_id: TC-INFRA-001
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-INFRA-001: LlamaStackDistribution CR deployment with PostgreSQL

**Objective**: Validate that the llama-stack-k8s-operator provisions a
OGX instance with PostgreSQL backend for session state
persistence when a LlamaStackDistribution CR is created.

**Preconditions**:

- OpenShift cluster with RHOAI 3.5 deployed
- llama-stack-k8s-operator installed and running
- PostgreSQL instance available (either operator-managed or
  pre-provisioned) on port 5432

**Test Steps**:

1. Create a LlamaStackDistribution CR with config.yaml registering
   Memories and Compaction providers and PostgreSQL connection
   configuration.
2. Wait for the operator to reconcile (watch CR status):

   ```bash
   oc get llamastackdistribution <name> -n <namespace> -w
   ```

3. Verify the operator creates the expected resources:

   ```bash
   oc get deployment -l app=llamastack -n <namespace>
   oc get service -l app=llamastack -n <namespace>
   oc get pods -l app=llamastack -n <namespace>
   ```

4. Verify the OGX service health endpoint returns HTTP 200:

   ```bash
   oc exec -n <namespace> deploy/llamastack -- \
     curl -fsS -o /dev/null -w "%{http_code}" \
       http://localhost:8321/health | grep -qx 200
   ```

5. Verify PostgreSQL connection is established and session store
   tables exist:

   ```bash
   psql -h <pg-host> -p 5432 -U <pg-user> -d <pg-db> \
     -c "\dt" | grep -i session
   ```

**Expected Results**:

- LlamaStackDistribution CR status transitions to Ready
- Deployment created with correct container image and config
  volume mount
- Service created exposing port 8321 (ClusterIP)
- Pod reaches Running/Ready state within the configured timeout
  window
- Health endpoint returns HTTP 200
- PostgreSQL contains session store tables (schema may vary
  by implementation)

**Test Data**:

```yaml
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: codex-test
  namespace: ds-project
spec:
  config:
    providers:
      memory:
        type: postgresql
        config:
          host: postgresql.ds-project.svc.cluster.local
          port: 5432
          database: llamastack
          username: llamastack
          password_secret: pg-credentials
      compaction:
        type: default
    inference:
      model: meta-llama/Llama-3.3-70B-Instruct
      endpoint: http://vllm:8000/v1
```

**Validation**:

- `oc get llamastackdistribution codex-test -o jsonpath='{.status.phase}'`
  returns `Ready`
- `oc logs deploy/llamastack -n ds-project` contains no ERROR-level
  entries related to PostgreSQL connection or provider registration

**Notes**: To be filled later in the process.
