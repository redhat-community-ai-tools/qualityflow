---
test_case_id: TC-OVERRIDE-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-OVERRIDE-001: spec.overrideConfig takes precedence over declarative config

**Objective**: Verify that when an OGXServer CR specifies both declarative providers via
`spec.providers` and a `spec.overrideConfig` referencing a ConfigMap, the server uses the
overrideConfig and ignores the declaratively generated configuration.

**Test Steps**:

1. Create a ConfigMap containing a custom config.yaml with a distinct, identifiable configuration:

   ```bash
   oc apply -f - <<EOF
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: custom-override-config
     namespace: test-ogx
   data:
     config.yaml: |
       version: '2'
       built_at: '2026-06-16T00:00:00Z'
       image_name: override-test
       apis:
         - inference
       providers:
         inference:
           - provider_id: override-provider
             provider_type: remote::ollama
             config:
               url: http://ollama-override:11434
   EOF
   ```

2. Deploy an OGXServer CR with both `spec.providers` (declarative) and `spec.overrideConfig`:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: test-override-precedence
     namespace: test-ogx
   spec:
     distribution:
      name: rh-dev
     providers:
       inference:
         - providerType: remote::vllm
           config:
             url: http://vllm-declarative:8000
     overrideConfig:
       configMapRef:
         name: custom-override-config
         key: config.yaml
   EOF
   ```

3. Wait for the OGXServer to become ready:

   ```bash
   oc wait ogxserver/test-override-precedence -n test-ogx \
     --for=condition=Ready --timeout=300s
   ```

4. Retrieve the active ConfigMap used by the server pod:

   ```bash
   oc get configmap -n test-ogx -l ogx.io/owner=test-override-precedence \
     -o jsonpath='{.items[0].data.config\.yaml}'
   ```

5. Verify the active config contains the override provider
   (`override-provider` with `remote::ollama`), not the declarative provider (`remote::vllm`):

   ```bash
   oc get configmap -n test-ogx -l ogx.io/owner=test-override-precedence \
     -o jsonpath='{.items[0].data.config\.yaml}' | \
     python3 -c "
   import sys, yaml
   cfg = yaml.safe_load(sys.stdin)
   providers = cfg.get('providers', {}).get('inference', [])
   ids = [p['provider_id'] for p in providers]
   assert 'override-provider' in ids, f'Expected override-provider, got {ids}'
   assert not any('vllm' in p.get('provider_type','') for p in providers), \
     'Declarative vllm provider should NOT be present'
   print('PASS: overrideConfig took precedence')
   "
   ```

6. Check operator logs to confirm override behavior was applied:

   ```bash
   oc logs deployment/ogx-operator -n ogx-system --since=2m | \
     grep -i -E "override|precedence|skip.*declarative"
   ```

**Expected Results**:

- The OGXServer reaches Ready condition without errors.
- The active config.yaml mounted in the server pod matches the overrideConfig content
  (provider_id `override-provider`, provider_type `remote::ollama`).
- The declarative provider (`remote::vllm`) is NOT present in the active configuration.
- Operator logs indicate that overrideConfig was used and declarative config generation was skipped.

**Test Data**:

The ConfigMap `custom-override-config` above contains a minimal but distinct configuration. The key
differentiator is the `override-provider` ID and `remote::ollama` type, which should not appear in
any declaratively generated config.

**Notes**: To be filled later in the process.
