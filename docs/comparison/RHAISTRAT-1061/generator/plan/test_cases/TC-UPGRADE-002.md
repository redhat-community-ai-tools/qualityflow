---
test_case_id: TC-UPGRADE-002
strat_key: RHAISTRAT-1061
priority: P0
status: Draft
automation_status: Not Started
last_updated: '2026-06-16'
---

# TC-UPGRADE-002: Workload continuity during upgrade

**Objective**: Verify the existing LlamaStack server pod continues serving traffic without
interruption during the RHOAI 3.4 to 3.5 upgrade, maintaining health and inference availability
throughout.

**Preconditions**:

- RHOAI 3.4 installed and healthy
- A running LlamaStackDistribution CR (`llama-stack-upgrade-test`) serving inference traffic
- A working VLLM endpoint accessible via the inference secret
- RHOAI 3.5 upgrade available via the operator catalog
- `oc` CLI authenticated with cluster-admin privileges
- A monitoring/polling script ready to run (see Test Data)

**Test Steps**:

1. Verify the LLSD pod is running and healthy on RHOAI 3.4:

   ```bash
   LLSD_POD=$(oc get pod -l app.kubernetes.io/instance=llama-stack-upgrade-test -o jsonpath='{.items[0].metadata.name}')
   oc exec "$LLSD_POD" -- curl -s http://localhost:8321/v1/health
   ```

2. Record the pod name and UID before upgrade:

   ```bash
   oc get pod -l app.kubernetes.io/instance=llama-stack-upgrade-test \
     -o jsonpath='{.items[0].metadata.name},{.items[0].metadata.uid}' > /tmp/pre-upgrade-pod-id.txt
   cat /tmp/pre-upgrade-pod-id.txt
   ```

3. Start a background health check loop that polls the LLSD server every 5 seconds during the
   upgrade:

   ```bash
   LLSD_ROUTE=$(oc get route llama-stack-upgrade-test -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
   nohup bash -c '
     echo "Health check started at $(date)"
     FAILURES=0
     SUCCESSES=0
     while true; do
       TIMESTAMP=$(date +"%Y-%m-%dT%H:%M:%S")
       if oc exec '"$LLSD_POD"' -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8321/v1/health 2>/dev/null | grep -q "200"; then
         echo "${TIMESTAMP} HEALTH=OK"
         SUCCESSES=$((SUCCESSES + 1))
       else
         echo "${TIMESTAMP} HEALTH=FAIL"
         FAILURES=$((FAILURES + 1))
       fi
       sleep 5
     done
   ' > /tmp/health-check.log 2>&1 &
   HEALTH_PID=$!
   echo "Health check PID: $HEALTH_PID"
   ```

4. Start a background inference check loop that sends a simple request every 15 seconds:

   ```bash
   nohup bash -c '
     echo "Inference check started at $(date)"
     while true; do
       TIMESTAMP=$(date +"%Y-%m-%dT%H:%M:%S")
       RESPONSE=$(oc exec '"$LLSD_POD"' -- curl -s -w "\n%{http_code}" http://localhost:8321/v1/inference/chat-completion \
         -H "Content-Type: application/json" \
         -d "{\"model_id\": \"test-model\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}]}" 2>/dev/null)
       HTTP_CODE=$(echo "$RESPONSE" | tail -1)
       if [ "$HTTP_CODE" = "200" ]; then
         echo "${TIMESTAMP} INFERENCE=OK"
       else
         echo "${TIMESTAMP} INFERENCE=FAIL (HTTP ${HTTP_CODE})"
       fi
       sleep 15
     done
   ' > /tmp/inference-check.log 2>&1 &
   INFERENCE_PID=$!
   echo "Inference check PID: $INFERENCE_PID"
   ```

5. Initiate the RHOAI 3.4 to 3.5 upgrade:

   ```bash
   # The upgrade method depends on the installation channel
   # Monitor upgrade progress
   oc get csv -n redhat-ods-operator -w
   ```

6. Wait for the upgrade to complete:

   ```bash
   # Wait for the new CSV to reach Succeeded phase
   oc get csv -n redhat-ods-operator | grep rhods-operator
   ```

7. Stop the health and inference check loops:

   ```bash
   kill $HEALTH_PID $INFERENCE_PID 2>/dev/null || true
   ```

8. Analyze the health check results:

   ```bash
   echo "=== Health Check Summary ==="
   TOTAL=$(grep -c "HEALTH=" /tmp/health-check.log)
   OK=$(grep -c "HEALTH=OK" /tmp/health-check.log)
   FAIL=$(grep -c "HEALTH=FAIL" /tmp/health-check.log)
   echo "Total checks: $TOTAL, OK: $OK, Failures: $FAIL"
   echo ""
   echo "=== Any failures ==="
   grep "HEALTH=FAIL" /tmp/health-check.log || echo "No failures"
   ```

9. Analyze the inference check results:

   ```bash
   echo "=== Inference Check Summary ==="
   TOTAL=$(grep -c "INFERENCE=" /tmp/inference-check.log)
   OK=$(grep -c "INFERENCE=OK" /tmp/inference-check.log)
   FAIL=$(grep -c "INFERENCE=FAIL" /tmp/inference-check.log)
   echo "Total checks: $TOTAL, OK: $OK, Failures: $FAIL"
   echo ""
   echo "=== Any failures ==="
   grep "INFERENCE=FAIL" /tmp/inference-check.log || echo "No failures"
   ```

10. Verify the pod was not restarted during upgrade (same UID):

    ```bash
    POST_POD_INFO=$(oc get pod -l app.kubernetes.io/instance=llama-stack-upgrade-test \
      -o jsonpath='{.items[0].metadata.name},{.items[0].metadata.uid}')
    PRE_POD_INFO=$(cat /tmp/pre-upgrade-pod-id.txt)
    echo "Pre-upgrade: $PRE_POD_INFO"
    echo "Post-upgrade: $POST_POD_INFO"
    if [ "$PRE_POD_INFO" = "$POST_POD_INFO" ]; then
      echo "PASS: Pod was not restarted"
    else
      echo "WARN: Pod was restarted or replaced"
    fi
    ```

11. Final health and inference verification after upgrade:

    ```bash
    LLSD_POD=$(oc get pod -l app.kubernetes.io/instance=llama-stack-upgrade-test -o jsonpath='{.items[0].metadata.name}')
    oc exec "$LLSD_POD" -- curl -s http://localhost:8321/v1/health
    oc exec "$LLSD_POD" -- curl -s http://localhost:8321/v1/inference/chat-completion \
      -H "Content-Type: application/json" \
      -d '{"model_id": "test-model", "messages": [{"role": "user", "content": "Hello"}]}'
    ```

**Expected Results**:

- The LLSD server pod continues running throughout the entire upgrade process
- Health endpoint (`/v1/health`) returns HTTP 200 on every check during the upgrade (zero failures)
- Inference endpoint responds successfully during the upgrade (zero failures)
- The pod UID remains the same before and after upgrade (pod was not restarted)
- After upgrade completes, both health and inference endpoints still respond normally

**Test Data**:

```yaml
# No new resources needed — this test uses the LLSD CR from TC-UPGRADE-001 step 1
# Monitoring is done via inline bash scripts in the test steps
```

```bash
# Quick one-liner to check results after test
echo "Health: $(grep -c 'HEALTH=OK' /tmp/health-check.log) OK, $(grep -c 'HEALTH=FAIL' /tmp/health-check.log) FAIL"
echo "Inference: $(grep -c 'INFERENCE=OK' /tmp/inference-check.log) OK, $(grep -c 'INFERENCE=FAIL' /tmp/inference-check.log) FAIL"
```

**Notes**: To be filled later in the process.
