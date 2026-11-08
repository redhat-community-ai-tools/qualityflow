---
test_case_id: TC-ROLLOUT-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-ROLLOUT-001: Config change triggers rolling update

**Objective**: Verify that modifying `spec.providers` in an OGXServer CR creates a new immutable
ConfigMap with a different content hash and triggers a rolling update that replaces the pod with one
using the updated configuration.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- A namespace for the test (e.g., `rollout-test`)

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project rollout-test
   ```

2. Apply an initial OGXServer CR:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-rollout-test
     namespace: rollout-test
   spec:
     replicas: 1
     distribution:
       name: rh-dev
   EOF
   ```

3. Wait for the pod to become Ready:

   ```bash
   oc wait --for=condition=Ready pod -l app=ogx-rollout-test -n rollout-test --timeout=120s
   ```

4. Record the current pod name and ConfigMap name:

   ```bash
   INITIAL_POD=$(oc get pods -l app=ogx-rollout-test -n rollout-test -o jsonpath='{.items[0].metadata.name}')
   INITIAL_CM=$(oc get configmaps -n rollout-test -o name | grep ogx-rollout-test)
   echo "Initial pod: $INITIAL_POD"
   echo "Initial ConfigMap: $INITIAL_CM"
   ```

5. Record the ConfigMap hash from the Deployment's pod template annotation or volume reference:

   ```bash
   INITIAL_HASH=$(oc get deployment ogx-rollout-test -n rollout-test -o jsonpath='{.spec.template.metadata.annotations.configHash}')
   echo "Initial config hash: $INITIAL_HASH"
   ```

6. Modify the CR by updating `spec.providers` (e.g., add or change a provider entry):

   ```bash
   oc patch ogxserver ogx-rollout-test -n rollout-test --type=merge -p '
   spec:
     providers:
       inference:
         - provider_id: vllm-updated
           provider_type: remote::vllm
           config:
             url: "https://updated-endpoint/v1"
   '
   ```

7. Wait for the rolling update to complete:

   ```bash
   oc rollout status deployment/ogx-rollout-test -n rollout-test --timeout=120s
   ```

8. Record the new ConfigMap name and pod name:

   ```bash
   NEW_CM=$(oc get configmaps -n rollout-test -o name | grep ogx-rollout-test | sort | tail -1)
   NEW_POD=$(oc get pods -l app=ogx-rollout-test -n rollout-test -o jsonpath='{.items[0].metadata.name}')
   NEW_HASH=$(oc get deployment ogx-rollout-test -n rollout-test -o jsonpath='{.spec.template.metadata.annotations.configHash}')
   echo "New ConfigMap: $NEW_CM"
   echo "New pod: $NEW_POD"
   echo "New config hash: $NEW_HASH"
   ```

9. Verify the new pod is using the updated configuration:

   ```bash
   oc get configmap ${NEW_CM##*/} -n rollout-test -o jsonpath='{.data.config\.yaml}'
   ```

**Expected Results**:

- A new immutable ConfigMap is created with a name containing a different content hash than the
  original
- The Deployment's pod template references the new ConfigMap (not the old one)
- The initial pod (`$INITIAL_POD`) is terminated and replaced by a new pod (`$NEW_POD`)
- The new ConfigMap hash (`$NEW_HASH`) differs from the initial hash (`$INITIAL_HASH`)
- The new pod's mounted config reflects the updated `spec.providers` values
- The old ConfigMap may be garbage-collected or retained (depending on operator behavior)

**Test Data**:

```yaml
# Initial CR
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-rollout-test
  namespace: rollout-test
spec:
  replicas: 1
  distribution:
    name: rh-dev
```

```yaml
# Patch to trigger rollout
spec:
  providers:
    inference:
      - provider_id: vllm-updated
        provider_type: remote::vllm
        config:
          url: "https://updated-endpoint/v1"
```

**Notes**: To be filled later in the process.
