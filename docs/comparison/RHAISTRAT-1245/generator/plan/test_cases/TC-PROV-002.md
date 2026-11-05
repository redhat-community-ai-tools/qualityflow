---
test_case_id: TC-PROV-002
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_providers.py
automation_function: TestGeminiProviders::test_gemini_provider_no_network_headers_workaround
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-PROV-002: Verify provider configuration without network.headers workaround

**Objective**: Confirm that Gemini models can be configured using
`provider_type: remote::gemini` without requiring `network.headers`
workarounds in the distribution config.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` in `config.yaml`
- No `network.headers` overrides configured for Gemini

**Test Steps**:

1. Inspect the deployed distribution's `config.yaml` and verify
   it uses `provider_type: remote::gemini` with the conditional
   activation pattern `${env.GEMINI_API_KEY:+gemini-inference}`
2. Verify the `remote::gemini` provider stanza does not require
   custom `network.headers` overrides (ignore unrelated providers)
3. Send a chat completion request to `/v1/chat/completions`
   using the configured Gemini model

**Expected Results**:

- The `config.yaml` uses `provider_type: remote::gemini`
- No `network.headers` workaround is present in the config
- The chat completion request returns HTTP 200 with a valid
  response from the Gemini model

**Notes**: To be filled later in the process.
