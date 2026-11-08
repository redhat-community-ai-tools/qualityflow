---
test_case_id: TC-MERGE-002
strat_key: RHAISTRAT-1061
priority: P1
status: Blocked
automation_status: Not Started
last_updated: '2026-06-16'
---
# TC-MERGE-002: Partial storage override replaces entire storage section

**Objective**: Verify whether applying a CR with only KV storage specified preserves or drops the
SQL storage from the base config, documenting the actual merge behavior for the known gap
(RHAIENG-5699).

**Test Steps**:

1. Identify the base config storage section by inspecting the distribution image OCI labels:

   ```bash
   oc image info <distribution-image> --filter-by-os linux/amd64 -o json | \
     jq -r '.config.config.Labels["com.ogx.distribution.configs"]'
   ```

   Confirm that the base config includes both `kvstore` and `sqlstore` entries.
2. Apply an OGXServer CR that specifies only KV storage:

   ```bash
   oc apply -f tc-merge-002-cr.yaml
   ```

3. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/merge-test-002 --for=condition=Ready --timeout=120s
   ```

4. Retrieve the generated ConfigMap and extract the storage section:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=merge-test-002 -o name | head -1) \
     -o jsonpath='{.data.config\.yaml}' | yq '.metadata_store'
   ```

5. Check whether SQL storage from the base config is present or absent:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=merge-test-002 -o name | head -1) \
     -o jsonpath='{.data.config\.yaml}' | yq '.metadata_store.type'
   ```

**Expected Results**:

- If whole-section replacement applies: the generated `config.yaml` contains ONLY the Redis KV
  storage; the base config's SQLite SQL storage is dropped entirely
- If additive merge applies: the generated `config.yaml` retains both Redis KV storage (from CR) and
  SQLite SQL storage (from base config)
- Document the actual observed behavior and compare against the known gap RHAIENG-5699
- The server should start successfully regardless of which merge strategy is applied

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: merge-test-002
spec:
  image: registry.redhat.io/rhoai/ogx-distribution-rhel9:latest
  storage:
    kvstore:
      type: redis
      config:
        host: "redis.example.com"
        port: 6379
```

**Notes**: **Blocked** on RHAIENG-5699 — merge semantics for partial
storage overrides are undefined. This test documents observed behavior
rather than asserting correct behavior. Once the gap is resolved with a
design decision (replacement vs additive), update Expected Results to
assert the intended behavior and change status to Draft.
