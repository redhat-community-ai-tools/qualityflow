---
test_case_id: TC-UPG-002
source_key: RHAISTRAT-1246
objectives: [7]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-UPG-002: Migration from remote::openai workaround to native provider

**Objective**: Verify that a user can migrate from the `remote::openai`
workaround to the native `remote::anthropic` provider without breaking
existing inference requests.

**Preconditions**:

- RHOAI 3.5 cluster with both providers available
- Anthropic models initially configured using `remote::openai`
  workaround with `network.headers`

**Test Steps**:

1. Confirm inference works with `remote::openai` workaround config
2. Update the provider configuration from `provider_type: remote::openai`
   with `network.headers` to `provider_type: remote::anthropic` with
   `ANTHROPIC_API_KEY` environment variable
3. Remove the `network.headers` workaround from the config
4. Restart the OGX distribution pod to apply the new config
5. Send the same inference request as step 1
6. Verify per-request API key override now works (was blocked by
   the workaround)

**Expected Results**:

- Post-migration inference returns HTTP 200 with a valid completion
- Per-request API key override via `x-ogx-provider-data` succeeds
  (previously impossible with workaround)
- No data loss or configuration corruption during migration

**Notes**: To be filled later in the process.
