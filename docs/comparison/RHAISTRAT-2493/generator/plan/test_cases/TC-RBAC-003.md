---
test_case_id: TC-RBAC-003
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-RBAC-003: Verify Namespace-Scoped User has read-only InferenceService access

**Objective**: Confirm that a Namespace-Scoped User can view InferenceService status
in their namespace but cannot create, modify, or delete resources.

**Preconditions**:

- A test user with Namespace-Scoped (read-only) role is available
- An InferenceService using vLLM-Omni runtime is already deployed in the
  namespace accessible to the test user
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Authenticate as the Namespace-Scoped User via
   `DynamicClient.authenticate(role="namespace-scoped-user")`.
2. Via `InferenceService.get()`, retrieve the InferenceService in the user's
   namespace. Assert the operation returns HTTP 200 with InferenceService details.
3. Via `InferenceService.create()`, attempt to create a new InferenceService in
   the same namespace. Assert the operation returns HTTP 403.
4. Via `InferenceService.delete()`, attempt to delete the existing InferenceService.
   Assert the operation returns HTTP 403.

**Expected Results**:

- `GET InferenceService` returns HTTP 200 with InferenceService details visible
- `POST InferenceService` (create) returns HTTP 403 Forbidden
- `DELETE InferenceService` returns HTTP 403 Forbidden
- The Namespace-Scoped User can observe but not modify serving resources

**Notes**: This test validates RBAC behavior specifically for the new vLLM-Omni
ServingRuntime. The same RBAC rules apply generically to all RHOAI serving runtimes;
this TC confirms the new runtime integrates correctly with existing RBAC enforcement.
