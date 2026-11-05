---
test_case_id: TC-DEP-002
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_deployment.py
automation_function: TestGeminiDeployment::test_config_conditional_activation_pattern
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-DEP-002: config.yaml conditional activation pattern

**Objective**: Verify that the distribution's `config.yaml`
uses the correct conditional activation pattern for the Gemini
provider.

**Preconditions**:

- Access to the OGX distribution's `config.yaml`

**Test Steps**:

1. Inspect the distribution's `config.yaml` file
2. Locate the Gemini provider configuration section
3. Verify the conditional activation pattern matches
   `${env.GEMINI_API_KEY:+gemini-inference}`
4. Verify this follows the same pattern used by other cloud
   providers (Bedrock, WatsonX, Azure, OpenAI)

**Expected Results**:

- `config.yaml` contains a provider entry that activates
  conditionally based on `GEMINI_API_KEY`
- The activation pattern is
  `${env.GEMINI_API_KEY:+gemini-inference}`
- The pattern is consistent with how other cloud providers
  are configured in the distribution

**Notes**: To be filled later in the process.
