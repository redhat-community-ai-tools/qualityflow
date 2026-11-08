---
test_case_id: TC-LIFECYCLE-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-LIFECYCLE-002: Old ConfigMaps cleaned up (retention=2)

**Objective**: Verify that the operator retains only the latest 2
ConfigMaps and garbage-collects older ones after spec changes.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- Dedicated test namespace created
- Default configMapRetention is 2

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-lifecycle-002
   ```

2. Apply the initial OGXServer CR (generates CM #1):

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-retention-test
     namespace: tc-lifecycle-002
   spec:
     providers:
       inference:
         - provider_id: vllm-v1
           provider_type: remote::vllm
           config:
             url: "https://endpoint-v1/v1"
   EOF
   ```

3. Wait for the server to become ready:

   ```bash
   oc wait ogxserver/ogx-retention-test \
     -n tc-lifecycle-002 \
     --for=condition=Ready --timeout=300s
   ```

4. Record ConfigMap #1:

   ```bash
   CM1=$(oc get configmap -n tc-lifecycle-002 \
     -l ogx.redhat.com/server=ogx-retention-test \
     -o jsonpath='{.items[0].metadata.name}')
   echo "CM1: $CM1"
   ```

5. Update providers to trigger CM #2:

   ```bash
   oc patch ogxserver ogx-retention-test \
     -n tc-lifecycle-002 --type=merge -p '
   spec:
     providers:
       inference:
         - provider_id: vllm-v2
           provider_type: remote::vllm
           config:
             url: "https://endpoint-v2/v1"
   '
   ```

6. Wait for rollout and record ConfigMap #2:

   ```bash
   oc rollout status deployment/ogx-retention-test \
     -n tc-lifecycle-002 --timeout=120s
   CM2=$(oc get configmap -n tc-lifecycle-002 \
     -l ogx.redhat.com/server=ogx-retention-test \
     -o jsonpath='{.items[*].metadata.name}' | \
     tr ' ' '\n' | grep -v "$CM1" | head -1)
   echo "CM2: $CM2"
   ```

7. Verify both CM1 and CM2 exist (retention=2):

   ```bash
   oc get configmap -n tc-lifecycle-002 \
     -l ogx.redhat.com/server=ogx-retention-test \
     --no-headers
   CM_COUNT=$(oc get configmap -n tc-lifecycle-002 \
     -l ogx.redhat.com/server=ogx-retention-test \
     --no-headers | wc -l)
   echo "ConfigMap count after 2 changes: $CM_COUNT"
   ```

8. Update providers again to trigger CM #3:

   ```bash
   oc patch ogxserver ogx-retention-test \
     -n tc-lifecycle-002 --type=merge -p '
   spec:
     providers:
       inference:
         - provider_id: vllm-v3
           provider_type: remote::vllm
           config:
             url: "https://endpoint-v3/v1"
   '
   ```

9. Wait for rollout to complete:

   ```bash
   oc rollout status deployment/ogx-retention-test \
     -n tc-lifecycle-002 --timeout=120s
   ```

10. List all ConfigMaps and verify retention:

    ```bash
    oc get configmap -n tc-lifecycle-002 \
      -l ogx.redhat.com/server=ogx-retention-test \
      --no-headers \
      -o custom-columns=NAME:.metadata.name,\
    CREATED:.metadata.creationTimestamp
    ```

11. Verify exactly 2 ConfigMaps remain:

    ```bash
    CM_FINAL=$(oc get configmap -n tc-lifecycle-002 \
      -l ogx.redhat.com/server=ogx-retention-test \
      --no-headers | wc -l)
    echo "Final ConfigMap count: $CM_FINAL"
    [ "$CM_FINAL" -eq 2 ] && \
      echo "PASS: Retention policy enforced" || \
      echo "FAIL: Expected 2, got $CM_FINAL"
    ```

12. Verify CM1 (oldest) was garbage-collected:

    ```bash
    oc get configmap "$CM1" -n tc-lifecycle-002 \
      2>&1 || echo "CM1 confirmed deleted"
    ```

13. Verify CM2 and CM3 (latest 2) still exist:

    ```bash
    REMAINING=$(oc get configmap \
      -n tc-lifecycle-002 \
      -l ogx.redhat.com/server=ogx-retention-test \
      -o jsonpath='{.items[*].metadata.name}')
    echo "Remaining ConfigMaps: $REMAINING"
    ```

14. Update providers a fourth time to trigger CM #4:

    ```bash
    oc patch ogxserver ogx-retention-test \
      -n tc-lifecycle-002 --type=merge -p '
    spec:
      providers:
        inference:
          - provider_id: vllm-v4
            provider_type: remote::vllm
            config:
              url: "https://endpoint-v4/v1"
    '
    oc rollout status deployment/ogx-retention-test \
      -n tc-lifecycle-002 --timeout=120s
    ```

15. Verify retention still holds at 2:

    ```bash
    CM_AFTER_V4=$(oc get configmap \
      -n tc-lifecycle-002 \
      -l ogx.redhat.com/server=ogx-retention-test \
      --no-headers | wc -l)
    echo "ConfigMap count after 4th change: $CM_AFTER_V4"
    [ "$CM_AFTER_V4" -eq 2 ] && \
      echo "PASS: Retention stable" || \
      echo "FAIL: Expected 2, got $CM_AFTER_V4"
    ```

16. Clean up:

    ```bash
    oc delete project tc-lifecycle-002
    ```

**Expected Results**:

- After the first spec change, 2 ConfigMaps exist
  (CM1 and CM2), matching the retention limit.
- After the second spec change (CM3 created), CM1 is
  garbage-collected. Only CM2 and CM3 remain.
- After the third spec change (CM4 created), CM2 is
  garbage-collected. Only CM3 and CM4 remain.
- At no point do more than 2 ConfigMaps exist for
  this OGXServer instance.
- The active Deployment always references the latest
  ConfigMap.
- Garbage collection happens automatically during
  reconciliation, not via a separate controller.

**Test Data**:

```yaml
# Initial CR
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-retention-test
spec:
  providers:
    inference:
      - provider_id: vllm-v1
        provider_type: remote::vllm
        config:
          url: "https://endpoint-v1/v1"
```

```yaml
# Patch sequence (v2, v3, v4) — only provider_id
# and url change to produce distinct config hashes
spec:
  providers:
    inference:
      - provider_id: vllm-vN
        provider_type: remote::vllm
        config:
          url: "https://endpoint-vN/v1"
```

**Notes**: To be filled later in the process.
