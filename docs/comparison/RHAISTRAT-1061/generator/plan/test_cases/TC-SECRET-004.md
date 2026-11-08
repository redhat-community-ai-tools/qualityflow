---
test_case_id: TC-SECRET-004
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-17'
---

# TC-SECRET-004: Secret missing ogx.io/watch label

**Objective**: Verify the operator reports a reconcile
error when a referenced Secret lacks the watch label.

**Preconditions**:

- OpenShift cluster with RHOAI operator installed
- OGX operator deployed and healthy
- `oc` CLI authenticated with cluster-admin or
  namespace-admin privileges
- Dedicated test namespace created

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project tc-secret-004
   ```

2. Create a Secret WITHOUT the `ogx.io/watch` label:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: v1
   kind: Secret
   metadata:
     name: unlabeled-secret
     namespace: tc-secret-004
   type: Opaque
   stringData:
     api-token: "test-token-value"
   EOF
   ```

3. Apply the OGXServer CR referencing the unlabeled
   Secret via SecretKeyRef:

   ```bash
   oc apply -f - <<'EOF'
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-no-watch-label
     namespace: tc-secret-004
   spec:
     providers:
       inference:
         remote:
           vllm:
           - id: vllm-inference
             endpoint: "https://vllm.svc:8000"
             apiToken:
               name: unlabeled-secret
               key: api-token
   EOF
   ```

4. Wait for the operator to attempt reconciliation:

   ```bash
   sleep 15
   ```

5. Check the OGXServer status conditions for an error
   or warning about the missing label:

   ```bash
   oc get ogxserver ogx-no-watch-label \
     -n tc-secret-004 \
     -o jsonpath='{.status.conditions}' \
     | python3 -m json.tool
   ```

6. Check for reconciliation error events in the
   namespace:

   ```bash
   oc get events -n tc-secret-004 \
     --sort-by='.lastTimestamp' \
     --field-selector reason!=Scheduled,reason!=Pulled
   ```

7. Check the operator logs for error messages about
   the missing label:

   ```bash
   oc logs -l app=ogx-operator \
     -n redhat-ods-applications --tail=50 \
     | grep -i 'watch\|label\|unlabeled-secret'
   ```

8. Verify the Deployment is absent or not ready
   because the Secret issue blocks reconciliation:

   ```bash
   READY=$(oc get deployment ogx-no-watch-label \
     -n tc-secret-004 \
     -o jsonpath='{.status.readyReplicas}' \
     2>/dev/null || echo "absent")
   if [ "$READY" = "absent" ] || [ "$READY" = "" ] \
     || [ "$READY" = "0" ]; then
     echo "PASS: Deployment absent or not ready"
   else
     echo "FAIL: Deployment has $READY ready replicas"
     exit 1
   fi
   ```

9. Fix the Secret by adding the `ogx.io/watch` label
   and verify the operator reconciles successfully:

   ```bash
   oc label secret unlabeled-secret \
     -n tc-secret-004 ogx.io/watch=true
   sleep 15
   oc get ogxserver ogx-no-watch-label \
     -n tc-secret-004 \
     -o jsonpath='{.status.conditions}' \
     | python3 -m json.tool
   ```

10. Clean up:

    ```bash
    oc delete project tc-secret-004
    ```

**Expected Results**:

- The operator detects the Secret is missing the
  `ogx.io/watch` label and reports a reconcile error
- The OGXServer status conditions contain an entry
  indicating the problem (e.g., type `Ready` with
  status `False` and a message referencing the
  missing label)
- Events in the namespace include a warning event
  from the operator about the unlabeled Secret
- The Deployment is either not created or not ready
  while the label is missing
- After adding the `ogx.io/watch` label to the Secret
  (step 9), the operator reconciles successfully and
  the status conditions clear the error

**Test Data**:

```yaml
# Secret WITHOUT ogx.io/watch label (intentional)
apiVersion: v1
kind: Secret
metadata:
  name: unlabeled-secret
type: Opaque
stringData:
  api-token: "test-token-value"
```

```yaml
# OGXServer CR referencing unlabeled Secret
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-no-watch-label
spec:
  providers:
    inference:
      remote:
        vllm:
        - id: vllm-inference
          endpoint: "https://vllm.svc:8000"
          apiToken:
            name: unlabeled-secret
            key: api-token
```

**Notes**: To be filled later in the process.
