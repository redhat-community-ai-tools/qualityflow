---
test_case_id: TC-NETPOL-001
strat_key: RHAISTRAT-1061
priority: P1
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-NETPOL-001: NetworkPolicy per-CR toggle

**Objective**: Verify that enabling `spec.network.networkPolicy.enabled` on an OGXServer CR creates
a NetworkPolicy resource, and disabling it removes the NetworkPolicy.

**Preconditions**:

- OpenShift cluster with OGX operator installed
- `oc` CLI authenticated with cluster-admin privileges
- A namespace for the test (e.g., `netpol-test`)
- Network plugin supports NetworkPolicy enforcement (default on OpenShift)

**Test Steps**:

1. Create the test namespace:

   ```bash
   oc new-project netpol-test
   ```

2. Verify no NetworkPolicy resources exist initially:

   ```bash
   oc get networkpolicies -n netpol-test
   ```

3. Apply an OGXServer CR with NetworkPolicy enabled:

   ```bash
   oc apply -f - <<EOF
   apiVersion: ogx.io/v1beta1
   kind: OGXServer
   metadata:
     name: ogx-netpol-test
     namespace: netpol-test
   spec:
     replicas: 1
     distribution:
       name: rh-dev
     network:
       networkPolicy:
         enabled: true
   EOF
   ```

4. Wait for the operator to reconcile:

   ```bash
   oc wait --for=condition=Ready pod -l app=ogx-netpol-test -n netpol-test --timeout=120s
   ```

5. Verify that a NetworkPolicy resource was created:

   ```bash
   oc get networkpolicies -n netpol-test
   ```

6. Verify ownership via ownerReferences:

   ```bash
   oc get networkpolicy -n netpol-test \
     -o jsonpath='{.items[0].metadata.ownerReferences}' | \
     python3 -c "
   import json, sys
   refs = json.load(sys.stdin)
   assert any(
     r['kind'] == 'OGXServer' and r['name'] == 'ogx-netpol-test'
     for r in refs
   ), f'Expected OGXServer owner, got {refs}'
   print('PASS: NetworkPolicy owned by OGXServer CR')
   "
   ```

7. Inspect the NetworkPolicy rules:

   ```bash
   oc get networkpolicy -n netpol-test -o yaml
   ```

8. Update the CR to disable NetworkPolicy:

   ```bash
   oc patch ogxserver ogx-netpol-test -n netpol-test --type=merge -p '
   spec:
     network:
       networkPolicy:
         enabled: false
   '
   ```

9. Wait for the operator to reconcile (allow a few seconds):

   ```bash
   sleep 10
   ```

10. Verify that the NetworkPolicy resource has been removed:

   ```bash
   oc get networkpolicies -n netpol-test
   ```

**Expected Results**:

- After step 2: no NetworkPolicy resources exist in the namespace
- After step 5: exactly one NetworkPolicy resource exists, owned by the OGXServer CR
- After step 6: the NetworkPolicy has ownerReferences
  pointing to the OGXServer CR
- After step 7: the NetworkPolicy has appropriate ingress/egress rules scoped to the OGXServer
  workload
- After step 10: zero NetworkPolicy resources exist in the namespace (the operator deleted it)

**Test Data**:

```yaml
# CR with NetworkPolicy enabled
apiVersion: ogx.io/v1beta1
kind: OGXServer
metadata:
  name: ogx-netpol-test
  namespace: netpol-test
spec:
  replicas: 1
  distribution:
    name: rh-dev
  network:
    networkPolicy:
      enabled: true
```

```yaml
# Patch to disable NetworkPolicy
spec:
  network:
    networkPolicy:
      enabled: false
```

**Notes**: To be filled later in the process.
