---
test_case_id: TC-MERGE-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---
# TC-MERGE-001: Provider merge is whole-API-type replacement

**Objective**: Verify that applying an OGXServer CR with one inference provider override replaces
ALL base config inference providers (whole-API-type replacement, not additive merge).

**Test Steps**:

1. Identify the base config inference providers by inspecting the OCI label on the distribution
   image:

   ```bash
   oc image info <distribution-image> --filter-by-os linux/amd64 -o json | \
     jq -r '.config.config.Labels["com.ogx.distribution.configs"]'
   ```

2. Apply an OGXServer CR with a single inference provider override:

   ```bash
   oc apply -f tc-merge-001-cr.yaml
   ```

3. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/merge-test-001 --for=condition=Ready --timeout=120s
   ```

4. Retrieve the generated ConfigMap:

   ```bash
   oc get configmap -l ogx.io/owner=merge-test-001 -o yaml
   ```

5. Extract and inspect the `config.yaml` from the ConfigMap:

   ```bash
   oc get configmap $(oc get configmap -l ogx.io/owner=merge-test-001 -o name | head -1) \
     -o jsonpath='{.data.config\.yaml}' | yq '.providers.inference'
   ```

**Expected Results**:

- The generated `config.yaml` contains ONLY the single inference provider specified in the CR
- None of the base config's original inference providers appear in the generated config
- The merge behavior is whole-API-type replacement: specifying any inference provider replaces the
  entire inference provider list
- Other API types not overridden in the CR (e.g., safety, memory) retain their base config values

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: merge-test-001
spec:
  image: registry.redhat.io/rhoai/ogx-distribution-rhel9:latest
  providers:
    inference:
      - type: vllm
        config:
          url: "https://vllm-model.example.com/v1"
          allowedModels:
            - "llama-3.1-8b"
```

**Notes**: To be filled later in the process.
