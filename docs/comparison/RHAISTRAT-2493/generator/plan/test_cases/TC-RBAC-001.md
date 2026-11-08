---
test_case_id: TC-RBAC-001
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-RBAC-001: Verify Cluster Admin can manage ServingRuntime and InferenceService

**Objective**: Confirm that a Cluster Admin role can create, modify, and delete
vLLM-Omni ServingRuntime and InferenceService resources across namespaces.

**Preconditions**:

- A test user with Cluster Admin role is available
- vLLM-Omni ServingRuntime template is deployed in the cluster
- Two test namespaces are available (Namespace-A for ServingRuntime, Namespace-B
  for InferenceService)
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Authenticate as the Cluster Admin test user via
   `DynamicClient.authenticate(role="cluster-admin")`.
2. Via `ServingRuntime.create()`, create a vLLM-Omni ServingRuntime in
   Namespace-A. Assert the operation returns HTTP 201.
3. Via `InferenceService.create()`, create an InferenceService referencing the
   vLLM-Omni runtime in Namespace-B. Assert the operation returns HTTP 201.
4. Via `ServingRuntime.patch()`, modify the ServingRuntime in Namespace-A. Assert
   the patch operation succeeds (HTTP 200).
5. Via `InferenceService.delete()`, delete the InferenceService in Namespace-B.
   Assert the delete operation succeeds (HTTP 200).
6. Via `ServingRuntime.delete()`, delete the ServingRuntime in Namespace-A. Assert
   the delete operation succeeds (HTTP 200).

**Expected Results**:

- Cluster Admin can perform all CRUD operations (create, read, patch, delete) on
  ServingRuntime in any namespace without permission errors
- Cluster Admin can perform all CRUD operations on InferenceService in any
  namespace without permission errors
- No 403 Forbidden responses occur during any operation

**Notes**: This test validates RBAC behavior specifically for the new vLLM-Omni
ServingRuntime. The same RBAC rules apply generically to all RHOAI serving runtimes;
this TC confirms the new runtime integrates correctly with existing RBAC enforcement.
