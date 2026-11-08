---
test_case_id: TC-WEBHOOK-001
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-WEBHOOK-001: Webhook rejects CR with MinItems violation on provider arrays

**Objective**: Verify that the validating admission webhook rejects an OGXServer CR that contains an
empty inference providers array, returning a descriptive error, and that the webhook TLS is
provisioned by cert-manager.

**Test Steps**:

1. Verify the webhook TLS certificate is provisioned by cert-manager:

   ```bash
   oc get certificate -n ogx-system -l app.kubernetes.io/component=webhook
   oc get certificate -n ogx-system -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
   ```

2. Verify the ValidatingWebhookConfiguration exists and references the correct service:

   ```bash
   oc get validatingwebhookconfiguration -l app.kubernetes.io/part-of=ogx-operator \
     -o jsonpath='{.items[0].webhooks[0].clientConfig.service.name}'
   ```

3. Attempt to apply an OGXServer CR with an empty inference providers array:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: test-webhook-empty-providers
     namespace: test-ogx
   spec:
     distribution:
      name: rh-dev
     providers:
       inference: []
   EOF
   ```

4. Capture the error output from the apply command (it should fail):

   ```bash
   # Run the apply and capture stderr
   oc apply -f /tmp/empty-providers-cr.yaml 2>&1 | tee /tmp/webhook-error.txt
   echo "Exit code: $?"
   ```

5. Verify the error message references the MinItems constraint:

   ```bash
   grep -i -E "minItems|minimum|empty|at least" /tmp/webhook-error.txt
   ```

6. Verify the CR was NOT created:

   ```bash
   oc get ogxserver/test-webhook-empty-providers -n test-ogx 2>&1
   # Should return "not found"
   ```

7. As a control, apply a valid CR with at least one provider to confirm the webhook allows it:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: test-webhook-valid
     namespace: test-ogx
   spec:
     distribution:
      name: rh-dev
     providers:
       inference:
         - providerType: remote::vllm
           config:
             url: http://vllm-svc:8000
   EOF
   ```

8. Verify the valid CR is accepted:

   ```bash
   oc get ogxserver/test-webhook-valid -n test-ogx -o jsonpath='{.metadata.name}'
   ```

**Expected Results**:

- The cert-manager Certificate resource for the webhook is in Ready state.
- The ValidatingWebhookConfiguration is registered and references the correct webhook service.
- The `oc apply` with empty inference providers array is rejected (non-zero exit code).
- The error message is descriptive and references the MinItems or minimum-items constraint on the
  providers array.
- The rejected CR does not exist in the cluster (`oc get` returns "not found").
- A valid CR with at least one provider is accepted by the webhook without errors.

**Test Data**:

Invalid CR (empty providers):

```yaml
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: test-webhook-empty-providers
  namespace: test-ogx
spec:
  distribution:
      name: rh-dev
  providers:
    inference: []
```

**Notes**: To be filled later in the process.
