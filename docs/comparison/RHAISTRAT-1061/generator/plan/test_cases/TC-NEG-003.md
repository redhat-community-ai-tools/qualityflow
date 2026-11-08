---
test_case_id: TC-NEG-003
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-NEG-003: Provider merge replaces entire API block

**Objective**: Verify that when an OGXServer CR specifies a single inference provider, ALL base
config inference providers are replaced (not just the one added), and document whether this
whole-block replacement is the intended merge behavior.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or namespace-admin privileges
- Dedicated test namespace created
- Knowledge of the base distribution's default inference providers
  (check the OCI image labels or default config)

**Test Steps**:

1. Create the test namespace and deploy a baseline OGXServer CR without custom providers to capture
   the default config:

   ```bash
   oc new-project tc-neg-003
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-baseline
     namespace: tc-neg-003
   spec: {}
   EOF
   ```

2. Wait for the baseline server to become ready and capture the default inference providers:

   ```bash
   oc wait ogxserver ogx-baseline -n tc-neg-003 --for=condition=Ready --timeout=120s
   BASELINE_CM=$(oc get configmaps -n tc-neg-003 -l app.kubernetes.io/instance=ogx-baseline -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$BASELINE_CM" -n tc-neg-003 -o jsonpath='{.data.config\.yaml}' | grep -A 50 'inference:'
   ```

3. Delete the baseline and apply a CR with a single custom inference provider:

   ```bash
   oc delete ogxserver ogx-baseline -n tc-neg-003
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-merge-test
     namespace: tc-neg-003
   spec:
     providers:
       inference:
         - provider_id: custom-vllm
           provider_type: remote::vllm
           config:
             url: http://vllm.example.com:8000/v1
             api_token: test-token
   EOF
   ```

4. Wait for the server to become ready and inspect the generated config for inference providers:

   ```bash
   oc wait ogxserver ogx-merge-test -n tc-neg-003 --for=condition=Ready --timeout=120s
   MERGE_CM=$(oc get configmaps -n tc-neg-003 -l app.kubernetes.io/instance=ogx-merge-test -o jsonpath='{.items[0].metadata.name}')
   oc get configmap "$MERGE_CM" -n tc-neg-003 -o jsonpath='{.data.config\.yaml}' | grep -A 50 'inference:'
   ```

5. Compare the two configs — verify whether the base inference providers were replaced or merged:

   ```bash
   # The merged config should show ONLY custom-vllm under inference providers
   # If base providers (e.g., meta-reference, together, fireworks) are gone, this confirms whole-block replacement
   ```

6. Check if other API type provider blocks (e.g., vector_io, agents) are unaffected:

   ```bash
   oc get configmap "$MERGE_CM" -n tc-neg-003 -o jsonpath='{.data.config\.yaml}' | grep -A 20 'vector_io:'
   ```

7. Clean up:

   ```bash
   oc delete project tc-neg-003
   ```

**Expected Results**:

- When `spec.providers.inference` is specified in the CR, ALL base config inference providers are
  replaced by the CR-specified list
- Only `custom-vllm` should appear in the inference providers section of the generated config
- All default/base inference providers (e.g., meta-reference, together, fireworks) should be absent
- Provider blocks for other API types (vector_io, agents, etc.) should remain unchanged from the
  base config
- This replacement behavior should be documented clearly in the CRD or operator docs

**Test Data**:

Baseline CR (no custom providers):

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-baseline
spec: {}
```

CR with single custom inference provider:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-merge-test
spec:
  providers:
    inference:
      - provider_id: custom-vllm
        provider_type: remote::vllm
        config:
          url: http://vllm.example.com:8000/v1
          api_token: test-token
```

**Notes**:

- Known gap [RHAIENG-5697](https://issues.redhat.com/browse/RHAIENG-5697): the MergeProviders
  function replaces the entire API type block rather than merging individual providers additively
- This is a critical behavior to document because users may expect additive merging
  (adding one provider alongside defaults) rather than whole-block replacement
- The test should capture the exact list of default providers that get replaced for regression
  tracking
