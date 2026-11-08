---
test_case_id: TC-TMPL-004
source_key: RHAISTRAT-2493
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-004: Verify 3-probe architecture: startupProbe, readinessProbe, and livenessProbe

**Objective**: Confirm that the vLLM-Omni ServingRuntime template defines all three probes
with the correct values from the actual template: startupProbe (failureThreshold:40,
periodSeconds:30), readinessProbe (periodSeconds:10, failureThreshold:3), livenessProbe
(periodSeconds:15, failureThreshold:3), all with no initialDelaySeconds.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster

**Test Steps**:

1. Via `ServingRuntime.get()`, retrieve the vLLM-Omni ServingRuntime object.
2. Access `.instance.spec.containers[0].startupProbe` and assert:
   - `failureThreshold == 40`
   - `periodSeconds == 30`
3. Access `.instance.spec.containers[0].readinessProbe` and assert:
   - `periodSeconds == 10`
   - `failureThreshold == 3`
4. Access `.instance.spec.containers[0].livenessProbe` and assert:
   - `periodSeconds == 15`
   - `failureThreshold == 3`
5. Assert that none of the three probes (startupProbe, readinessProbe, livenessProbe)
   has `initialDelaySeconds` set.

**Expected Results**:

- All 3 probes are present with exact values from the actual template
- startupProbe gates pod startup (max 1200s window = 40×30s)
- readinessProbe and livenessProbe activate only after startupProbe succeeds
- No `initialDelaySeconds` is set on any of the three probes

**Notes**: To be filled later in the process.
