---
test_case_id: TC-LIFECYCLE-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-LIFECYCLE-001: ConfigMap reused when spec unchanged

**Objective**: Verify that reconciling an unchanged OGXServer CR
reuses the existing ConfigMap instead of creating a new one.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-lifecycle-001
   ```

2. Apply an OGXServer CR with declarative providers:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-lifecycle-test
     namespace: tc-lifecycle-001
   spec:
     providers:
       inference:
         - provider_id: vllm-stable
           provider_type: remote::vllm
           config:
             url: "https://model-endpoint/v1"
   EOF
   ```

3. Wait for the server pod to become ready:

   ```bash
   oc wait --for=condition=Ready pod \
     -l app=ogx-lifecycle-test \
     -n tc-lifecycle-001 --timeout=300s
   ```

4. Record the generated ConfigMap name and its hash:

   ```bash
   INITIAL_CM=$(oc get configmap -n tc-lifecycle-001 \
     -l ogx.redhat.com/server=ogx-lifecycle-test \
     -o jsonpath='{.items[0].metadata.name}')
   INITIAL_UID=$(oc get configmap "$INITIAL_CM" \
     -n tc-lifecycle-001 \
     -o jsonpath='{.metadata.uid}')
   echo "Initial CM: $INITIAL_CM (UID: $INITIAL_UID)"
   ```

5. Record the total number of ConfigMaps:

   ```bash
   CM_COUNT_BEFORE=$(oc get configmap \
     -n tc-lifecycle-001 \
     -l ogx.redhat.com/server=ogx-lifecycle-test \
     --no-headers | wc -l)
   echo "ConfigMap count before: $CM_COUNT_BEFORE"
   ```

6. Trigger a reconcile by deleting the server pod:

   ```bash
   oc delete pod -l app=ogx-lifecycle-test \
     -n tc-lifecycle-001
   ```

7. Wait for the replacement pod to become ready:

   ```bash
   oc wait --for=condition=Ready pod \
     -l app=ogx-lifecycle-test \
     -n tc-lifecycle-001 --timeout=300s
   ```

8. Verify the same ConfigMap is still in use:

   ```bash
   AFTER_CM=$(oc get configmap -n tc-lifecycle-001 \
     -l ogx.redhat.com/server=ogx-lifecycle-test \
     -o jsonpath='{.items[0].metadata.name}')
   AFTER_UID=$(oc get configmap "$AFTER_CM" \
     -n tc-lifecycle-001 \
     -o jsonpath='{.metadata.uid}')
   echo "After CM: $AFTER_CM (UID: $AFTER_UID)"
   ```

9. Verify no new ConfigMaps were created:

   ```bash
   CM_COUNT_AFTER=$(oc get configmap \
     -n tc-lifecycle-001 \
     -l ogx.redhat.com/server=ogx-lifecycle-test \
     --no-headers | wc -l)
   echo "ConfigMap count after: $CM_COUNT_AFTER"
   ```

10. Compare before and after values:

    ```bash
    [ "$INITIAL_CM" = "$AFTER_CM" ] && \
      echo "PASS: Same ConfigMap name" || \
      echo "FAIL: ConfigMap name changed"
    [ "$INITIAL_UID" = "$AFTER_UID" ] && \
      echo "PASS: Same ConfigMap UID" || \
      echo "FAIL: ConfigMap UID changed"
    [ "$CM_COUNT_BEFORE" = "$CM_COUNT_AFTER" ] && \
      echo "PASS: No new ConfigMaps" || \
      echo "FAIL: ConfigMap count changed"
    ```

11. Clean up:

    ```bash
    oc delete project tc-lifecycle-001
    ```

**Expected Results**:

- After pod deletion and reconcile, the operator
  detects the spec is unchanged (content-hash match).
- The same ConfigMap (same name and UID) is reused.
- No additional ConfigMaps are created.
- The replacement pod mounts the original ConfigMap.
- The ConfigMap count remains the same before and
  after the reconcile.

**Test Data**:

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-lifecycle-test
spec:
  providers:
    inference:
      - provider_id: vllm-stable
        provider_type: remote::vllm
        config:
          url: "https://model-endpoint/v1"
```

**Notes**: To be filled later in the process.
