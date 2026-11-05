---
test_case_id: TC-RENDER-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---
# TC-RENDER-002: Config change creates new ConfigMap

**Objective**: Verify that modifying `spec.providers` on an existing OGXServer CR causes the
operator to create a new immutable ConfigMap with a different hash, update the Deployment reference,
and trigger a rolling update.

**Test Steps**:

1. Apply the initial OGXServer CR:

   ```bash
   oc apply -f tc-render-002-cr-initial.yaml
   ```

2. Wait for the operator to reconcile:

   ```bash
   oc wait ogxserver/render-test-002 --for=condition=Ready --timeout=120s
   ```

3. Record the initial ConfigMap name and pod generation:

   ```bash
   INITIAL_CM=$(oc get configmap -l ogx.io/owner=render-test-002 -o jsonpath='{.items[0].metadata.name}')
   INITIAL_POD=$(oc get pod -l ogx.io/owner=render-test-002 -o jsonpath='{.items[0].metadata.name}')
   echo "Initial ConfigMap: $INITIAL_CM"
   echo "Initial Pod: $INITIAL_POD"
   ```

4. Update the CR with a modified provider configuration:

   ```bash
   oc apply -f tc-render-002-cr-updated.yaml
   ```

5. Wait for the rolling update to complete:

   ```bash
   oc rollout status deployment/render-test-002 --timeout=120s
   ```

6. List all ConfigMaps owned by the CR:

   ```bash
   oc get configmap -l ogx.io/owner=render-test-002 -o name
   ```

7. Verify a new ConfigMap was created with a different hash:

   ```bash
   NEW_CM=$(oc get configmap -l ogx.io/owner=render-test-002 -o jsonpath='{.items[-1].metadata.name}')
   echo "New ConfigMap: $NEW_CM"
   [ "$INITIAL_CM" != "$NEW_CM" ] && echo "PASS: Different ConfigMap" || echo "FAIL: Same ConfigMap"
   ```

8. Verify the Deployment references the new ConfigMap:

   ```bash
   oc get deployment render-test-002 \
     -o jsonpath='{.spec.template.spec.volumes[*].configMap.name}'
   ```

9. Verify a new pod was created (rolling update occurred):

   ```bash
   CURRENT_POD=$(oc get pod -l ogx.io/owner=render-test-002 -o jsonpath='{.items[0].metadata.name}')
   [ "$INITIAL_POD" != "$CURRENT_POD" ] && echo "PASS: Rolling update" || echo "FAIL: No rolling update"
   ```

**Expected Results**:

- A new ConfigMap `render-test-002-config-<new-hash>` is created with a hash different from the
  initial ConfigMap
- The new ConfigMap contains the updated provider configuration (OpenAI provider instead of VLLM)
- The Deployment's pod template references the new ConfigMap name
- A rolling update is triggered, replacing the old pod with a new one
- The new pod is running and healthy after the rollout completes

**Test Data**:

Initial CR (`tc-render-002-cr-initial.yaml`):

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: render-test-002
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

Updated CR (`tc-render-002-cr-updated.yaml`):

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: render-test-002
spec:
  image: registry.redhat.io/rhoai/ogx-distribution-rhel9:latest
  providers:
    inference:
      - type: openai
        config:
          url: "https://openai-compatible.example.com/v1"
          allowedModels:
            - "gpt-4o"
```

**Notes**: To be filled later in the process.
