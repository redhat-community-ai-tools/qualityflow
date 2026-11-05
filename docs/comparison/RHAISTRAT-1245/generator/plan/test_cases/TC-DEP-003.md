---
test_case_id: TC-DEP-003
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_deployment.py
automation_function: TestGeminiDeployment::test_operator_injects_gemini_api_key
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-DEP-003: OGX K8s Operator ConfigMap injection for GEMINI_API_KEY

**Objective**: Verify that the OGX K8s Operator correctly
propagates the `GEMINI_API_KEY` environment variable from a
ConfigMap or CR spec to the OGX distribution pod.

**Preconditions**:

- OGX K8s Operator installed and managing
  `LlamaStackDistribution` CRs
- A Kubernetes Secret containing the Gemini API key

**Test Steps**:

1. Create a Kubernetes Secret with the Gemini API key:
   `kubectl create secret generic gemini-key
   --from-literal=GEMINI_API_KEY=<API-KEY>`
2. Configure the `LlamaStackDistribution` CR or ConfigMap
   to reference the secret and inject `GEMINI_API_KEY`
3. Apply the CR and wait for the OGX pod to start
4. Verify the environment variable is set in the running pod
   without exposing its value:
   `kubectl exec <pod> -- sh -c 'test -n "${GEMINI_API_KEY}" && echo "GEMINI_API_KEY is set"'`
5. Send a request to `/v1/providers` and verify
   `remote::gemini` is listed

**Expected Results**:

- The OGX pod has `GEMINI_API_KEY` set in its environment
- The `remote::gemini` provider activates based on the
  injected environment variable
- `/v1/providers` lists `remote::gemini` as active

**Notes**: To be filled later in the process.
