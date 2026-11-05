---
test_case_id: TC-INIT-005
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-INIT-005: Verify liveness probe detects pod health failure

**Objective**: Confirm that the liveness probe restarts the pod
when the `/health` endpoint stops responding after successful
initialization.

**Preconditions**:

- vLLM-Omni InferenceService is deployed and pod is in Ready state
- Liveness probe is configured with `httpGet` on `/health` port
  8080

**Test Steps**:

1. Via `pod_is_ready(pod=omni_pod_resource)`, verify the pod is Running
   and Ready.
2. Simulate a health check failure by observing the pod's behavior when
   the vLLM-Omni process becomes unresponsive (e.g., under extreme memory
   pressure or by observing a natural failure).
3. Via `Pod.get_events()`, monitor pod events for liveness probe failures.
4. Via `get_restart_counts(pod=omni_pod_resource)`, observe whether the
   kubelet restarts the container after the configured failure threshold
   is reached (3 failures at 15s intervals = ~45 seconds).

**Expected Results**:

- The liveness probe issues `httpGet` requests to `/health` on
  port 8080 at 15-second intervals (no `initialDelaySeconds`)
- If `/health` returns non-200 for 3 consecutive probes, the
  kubelet restarts the container
- Pod events show `Unhealthy` events followed by a container
  restart

**Notes**: To be filled later in the process.
