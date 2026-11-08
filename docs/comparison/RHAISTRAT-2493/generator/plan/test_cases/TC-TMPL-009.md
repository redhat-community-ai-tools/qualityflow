---
test_case_id: TC-TMPL-009
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-TMPL-009: Verify securityContext in ServingRuntime template

**Objective**: Confirm that the vLLM-Omni ServingRuntime template's container
defines the expected security hardening via securityContext, preventing
privilege escalation and ensuring non-root execution.

**Preconditions**:

- vLLM-Omni ServingRuntime template is deployed in the cluster

**Test Steps**:

1. Get the vLLM-Omni ServingRuntime via `ServingRuntime.get()` and access
   `instance.spec.containers[0].securityContext`.
2. Assert `securityContext.allowPrivilegeEscalation == False`.
3. Assert `securityContext.privileged == False`.
4. Assert `securityContext.runAsNonRoot == True`.
5. Assert `"ALL"` is in `securityContext.capabilities.drop`.

**Expected Results**:

- `allowPrivilegeEscalation` is `False`
- `privileged` is `False`
- `runAsNonRoot` is `True`
- `capabilities.drop` contains `"ALL"`

**Notes**: To be filled later in the process.
pytest.param id: `test_omni_security_context`
