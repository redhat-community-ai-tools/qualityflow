---
test_case_id: TC-DEP-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_deployment.py
automation_function: TestGeminiDeployment::test_build_includes_gemini_and_google_genai
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-DEP-001: build.yaml includes remote::gemini provider

**Objective**: Verify that the OGX distribution's `build.yaml`
declares the `remote::gemini` provider as a build-time dependency.

**Preconditions**:

- Access to the OGX distribution image or its build artifacts

**Test Steps**:

1. Inspect the distribution's `build.yaml` file (from the image
   or source repository)
2. Verify that `remote::gemini` appears in the list of providers
3. Verify that the `google-genai` Python package dependency is
   included

**Expected Results**:

- `build.yaml` contains an entry for the `remote::gemini`
  provider
- The `google-genai` package is listed as a dependency
  (directly or transitively)
- The distribution image builds successfully with these
  dependencies via the Konflux pipeline

**Notes**: To be filled later in the process.
