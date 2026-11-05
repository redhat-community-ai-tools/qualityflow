---
test_case_id: TC-REGR-002
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-REGR-002: HPA and PDB functionality preserved

**Objective**: Verify that Horizontal Pod Autoscaler (HPA) scaling and
PodDisruptionBudget (PDB) behavior remain intact after OGX
updates for Codex CLI support.

**Preconditions**:

- LlamaStackDistribution CR deployed with HPA configured
  (minReplicas=1, maxReplicas=3, targetCPUUtilization=70%)
- PodDisruptionBudget configured with maxUnavailable=1
- Load generation tool available (e.g., hey, k6, or wrk)

**Test Steps**:

1. Verify initial state: one OGX pod running, HPA active:

   ```bash
   oc get hpa -n <namespace>
   oc get pods -l app=llamastack -n <namespace>
   ```

2. Generate sustained load against OGX /v1/chat/completions
   endpoint to push CPU above 70% threshold:

   ```bash
   hey -n 1000 -c 50 -m POST \
     -H "Content-Type: application/json" \
     -d '{"model":"<model>","messages":[{"role":"user","content":"hi"}]}' \
     http://llamastack:8321/v1/chat/completions
   ```

3. Wait for HPA to detect CPU threshold breach and scale up
   (observe with `oc get hpa -w`).
4. Verify pod count increases from 1 to 2 or more.
5. Initiate a rolling update of the OGX deployment:

   ```bash
   oc rollout restart deployment/llamastack -n <namespace>
   ```

6. During rollout, verify PDB prevents all pods from being
   evicted simultaneously — at least 1 pod remains Running at
   all times.
7. Verify rollout completes successfully with no downtime.

**Expected Results**:

- HPA scales OGX pods when sustained load exceeds the configured
  threshold
- HPA reports currentReplicas matching or exceeding desiredReplicas
- During rolling update, at least one pod remains Available/Ready
  and clients see no HTTP 503 or connection-refused errors
- Rolling update completes with all pods in Running/Ready state
- No HTTP 503 or connection refused errors during rollout

**Notes**: To be filled later in the process.
