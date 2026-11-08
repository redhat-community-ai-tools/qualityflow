---
test_case_id: TC-RBAC-002
source_key: RHAISTRAT-2493
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-RBAC-002: Verify Data Science Project User cannot modify ServingRuntime

**Objective**: Confirm that a Data Science Project User can create InferenceService
within their own project but cannot modify the cluster-level ServingRuntime template.

**Preconditions**:

- A test user with Data Science Project User role (project-scoped access only)
  is available
- vLLM-Omni ServingRuntime template is deployed in the cluster
- A Data Science project namespace owned by the test user is available
- Model weights available in S3 models bucket accessible from the user's project namespace
- openshift-python-wrapper is available in the test environment

**Test Steps**:

1. Authenticate as the Data Science Project User via
   `DynamicClient.authenticate(role="ds-project-user")`.
2. Via `ServingRuntime.patch()`, attempt to patch the vLLM-Omni ServingRuntime
   in the RHOAI operator namespace. Assert the operation returns HTTP 403.
3. Via `InferenceService.create()`, create an InferenceService in the user's own
   project namespace. Assert the operation returns HTTP 201.

**Expected Results**:

- PATCH/PUT on the cluster-level vLLM-Omni ServingRuntime returns HTTP 403
  Forbidden
- InferenceService creation in the user's own project namespace returns HTTP 201
  Created
- The user can deploy inference services but cannot tamper with shared runtime
  templates

**Notes**: This test validates RBAC behavior specifically for the new vLLM-Omni
ServingRuntime. The same RBAC rules apply generically to all RHOAI serving runtimes;
this TC confirms the new runtime integrates correctly with existing RBAC enforcement.
