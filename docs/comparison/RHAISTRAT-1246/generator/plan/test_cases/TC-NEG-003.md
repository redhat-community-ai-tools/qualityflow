---
test_case_id: TC-NEG-003
source_key: RHAISTRAT-1246
objectives: [2]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-NEG-003: Missing ANTHROPIC_API_KEY prevents provider activation

**Objective**: Verify that the `remote::anthropic` provider is not
activated and returns appropriate errors when `ANTHROPIC_API_KEY` is
not set.

**Preconditions**:

- RHOAI 3.5 cluster with OGX distribution deployed
- `ANTHROPIC_API_KEY` environment variable NOT set

**Test Steps**:

1. Deploy the OGX distribution without `ANTHROPIC_API_KEY`
2. Query `/v1/providers` and verify `remote::anthropic` is absent
3. Attempt a chat completion request targeting an Anthropic model
4. Verify the request fails with a descriptive error

**Expected Results**:

- `/v1/providers` response does not include `remote::anthropic`
- Chat completion request returns an error indicating the Anthropic
  provider is not configured or the model is not available
- No crash or unhandled exception in the OGX distribution pod

**Notes**: To be filled later in the process.
