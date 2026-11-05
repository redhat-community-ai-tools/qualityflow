---
test_case_id: TC-UPG-001
source_key: RHAISTRAT-1246
objectives: [7]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-UPG-001: Existing remote::openai workaround survives upgrade

**Objective**: Verify that existing `remote::openai` workaround
configurations with Anthropic endpoints continue to work after
upgrading to a RHOAI version with native `remote::anthropic` support.

**Preconditions**:

- RHOAI cluster at a version WITHOUT `remote::anthropic` provider
- Anthropic models configured using the `remote::openai` workaround
  with `network.headers`:

  ```yaml
  network:
    headers:
      x-api-key: ${env.EXTERNAL_MODEL_PROVIDER_API_KEY:=placeholder}
      anthropic-version: "2023-06-01"
  ```

- Inference verified working with the workaround configuration

**Test Steps**:

1. Confirm inference to Anthropic models works on the pre-upgrade
   version using the `remote::openai` workaround
2. Upgrade RHOAI to 3.5 (which includes `remote::anthropic`)
3. Verify the existing `remote::openai` workaround configuration
   was NOT modified by the upgrade
4. Send the same inference request as step 1
5. Verify the request still succeeds with HTTP 200

**Expected Results**:

- Pre-upgrade inference request succeeds (baseline)
- Upgrade completes without modifying existing provider configs
- Post-upgrade inference using `remote::openai` workaround returns
  HTTP 200 with a valid completion
- Both `remote::openai` and `remote::anthropic` providers can
  coexist in the same deployment

**Notes**: To be filled later in the process.
