---
test_case_id: TC-NFR-001
source_key: RHAISTRAT-1246
objectives: [6]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-NFR-001: API keys not leaked in logs or error responses

**Objective**: Verify that Anthropic API keys are never logged in
plain text in container logs, operator logs, or returned in error
response bodies.

**Preconditions**:

- RHOAI 3.5 cluster with `remote::anthropic` provider activated
- `ANTHROPIC_API_KEY` set via Kubernetes Secret

**Test Steps**:

1. Send several inference requests (both successful and failing)
2. Retrieve pod logs for the OGX distribution container:

   ```bash
   oc logs deployment/ogx-distribution -n <namespace> | \
     grep -i "anthropic_api_key\|x-api-key\|<actual-key-prefix>"
   ```

3. Verify no API key values appear in the logs
4. Send a request with an invalid key via `x-ogx-provider-data`
   and inspect the error response body for key material
5. Check operator logs for any key leakage:

   ```bash
   oc logs deployment/ogx-k8s-operator -n <namespace> | \
     grep -i "api.key\|secret"
   ```

**Expected Results**:

- No API key values appear in container logs
- No API key values appear in operator logs
- Error responses reference "authentication failed" or similar
  without including the actual key string

**Notes**: To be filled later in the process.
