---
test_case_id: TC-INFRA-002
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-INFRA-002: config.yaml Memories and Compaction provider registration

**Objective**: Validate that OGX's config.yaml correctly
registers the Memories API and Compaction API providers and that both
are active after deployment.

**Preconditions**:

- OGX deployed via LlamaStackDistribution CR with config.yaml
  containing Memories and Compaction provider entries
- OGX pod in Running/Ready state on port 8321

**Test Steps**:

1. Deploy OGX with a config.yaml that includes Memories and
   Compaction provider registrations (see TC-INFRA-001 for CR
   example).
2. Verify the mounted config contains memory and compaction provider
   entries.
3. Verify the service provider listing includes both registered
   providers.
4. Verify startup logs show provider registration messages with no
   error-level entries.

**Expected Results**:

- config.yaml contains entries for both `memory` and `compaction`
  providers
- Provider listing endpoint returns JSON array including both
  provider types with status indicating active/healthy
- OGX startup logs show successful registration of both
  providers (no ERROR or WARNING related to provider init)
- No stack traces or connection failures in logs related to
  provider registration

**Notes**: To be filled later in the process.
