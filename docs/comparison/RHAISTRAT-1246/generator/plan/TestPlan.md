---
feature: remote_anthropic_provider
source_key: RHAISTRAT-1246
source_type: strat
status: In Review
author: OGX Core Team
components:
- Documentation
- OGX Core
additional_docs:
- '["https://docs.google.com/document/d/1SEmWmym9XLs8_krHLdaItq7dUX6LmZtkrPik57mZeGo/edit?tab=t.3mrf1syv46a"]'
last_updated: '2026-08-17'
version: 1.0.1
reviewers: []
---
# Remote Anthropic Provider Test Plan

OGX Core Team -- E2E System Testing

**Strategy**: [RHAISTRAT-1246](https://redhat.atlassian.net/browse/RHAISTRAT-1246)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan covers the inclusion of the native `remote::anthropic`
provider in the RHOAI OGX (formerly Llama Stack) distribution. The
feature enables proper Claude model integration with Anthropic-specific
authentication headers (`x-api-key` and `anthropic-version`),
per-request API key override via provider data headers, and correct
model listing using the AsyncAnthropic SDK.

Testing validates that the native provider replaces the existing
`remote::openai` workaround, which blocks multi-tenant scenarios by
preventing per-request API key overrides and creates technical debt
requiring custom `network.headers` configuration for each deployment.

### 1.2 Scope

#### In Scope (OGX Core Team Responsibilities)

- Including the `remote::anthropic` provider in the downstream RHOAI
  OGX distribution image
- Native Anthropic authentication using `x-api-key` and
  `anthropic-version` headers without `network.headers` workarounds
- Per-request API key override via `x-ogx-provider-data` header with
  `anthropic_api_key` field
- Model listing functionality using the AsyncAnthropic SDK to handle
  Anthropic's `/v1/models` format differences
- Chat completions API with streaming and temperature parameter support
- Tool calling via chat completions and responses APIs
- MCP server integration with Anthropic models
- Provider listing in the `/v1/providers` endpoint
- Documentation updates with Anthropic configuration examples and
  embedding model guidance (Voyage AI recommendations)
- End-to-end validation against Anthropic's API
- Distribution configuration updates (`build.yaml`, `config.yaml`)
  with conditional environment variable activation pattern
- Konflux build integration with `anthropic` Python SDK dependency

#### Out of Scope (Other Teams)

- Anthropic-specific UI in Gen AI Studio (handled by dashboard team
  separately)
- Per-user API token management through the Dashboard UI (future
  release)
- Anthropic embedding model support (Anthropic does not provide
  embedding models; RFE notes guidance on Voyage AI for embeddings)
- Claude thinking/reasoning capabilities (provider-level feature; may
  work natively without additional strategy work)

### 1.3 Test Objectives

1. Verify that inference requests to Claude models return valid
   responses when a user configures `provider_type: remote::anthropic`
   with a valid Anthropic API key on a deployed RHOAI OGX distribution
   via end-to-end API requests
   (AC: #1 — valid API key configuration produces successful inference)
2. Verify that authentication succeeds without `network.headers`
   configuration when the `remote::anthropic` provider sends requests
   using `x-api-key` and `anthropic-version` headers via measuring
   HTTP 200 responses in end-to-end tests
   (AC: #2 — native authentication headers work without workaround)
3. Verify that per-request API key override functionality works when a
   user sets `anthropic_api_key` in the `x-ogx-provider-data` header
   via measuring successful authentication with a different key than
   the config-level key
   (AC: #3 — per-request key override mechanism functions correctly)
4. Verify that Anthropic models are listed correctly in the
   AsyncAnthropic SDK format when a user requests model listing via
   `/v1/models` with the Anthropic provider configured
   (AC: #4 — model listing returns correct Anthropic-specific format)
5. Verify that the `remote::anthropic` provider appears in the output
   when querying the `/v1/providers` endpoint on a deployed OGX
   distribution via REST API calls
   (AC: #5 — provider registration is visible)
6. Verify that Anthropic API keys are handled through Kubernetes
   Secrets injected as environment variables, per-request key override
   uses the `x-ogx-provider-data` header mechanism, and TLS 1.2+ is
   enforced for egress to Anthropic API endpoints via security-focused
   e2e tests
   (NFR: Security — secure credential handling and transport)
7. Verify that existing `remote::openai` workaround configurations
   continue to work after the `remote::anthropic` provider is added
   via regression testing
   (NFR: Backwards Compatibility — additive change preserves configs)

---

## 2. Test Strategy

### 2.1 Test Levels

- **E2E System Testing** -- End-to-end workflows exercising the
  deployed OGX distribution through external interfaces: provider
  configuration via YAML/environment variables, inference requests to
  Claude models through chat completions and responses APIs, model
  listing via `/v1/models` endpoint, provider listing via
  `/v1/providers` endpoint, tool calling, MCP server integration, and
  per-request API key override via `x-ogx-provider-data` headers.
  Testing validates the complete flow from provider activation
  (environment variable injection) through Kubernetes operator to
  successful Anthropic API calls.

### 2.2 Test Types

- **Positive Testing** -- Valid Anthropic API keys, successful chat
  completions with and without streaming, temperature and sampling
  parameters, tool calling via chat completions and responses APIs,
  model listing using AsyncAnthropic SDK, MCP server integration,
  per-request API key override, provider activation via environment
  variables, correct authentication headers
- **Negative Testing** -- Invalid or missing API keys, authentication
  failures, missing `anthropic-version` header, Anthropic API error
  responses, network failures to external Anthropic endpoints,
  malformed per-request API key override, provider activation without
  required environment variables, concurrent requests with invalid
  keys in multi-tenant scenarios

### 2.3 Test Priorities

- **P0 (Critical)** -- Core provider functionality that blocks basic
  Anthropic model usage: provider included in distribution image,
  provider configurable without `network.headers` workarounds, chat
  completions API working with streaming and parameters, tool calling
  functional
- **P1 (High)** -- Features enabling production multi-tenant scenarios
  and operational readiness: per-request API key override via
  `x-ogx-provider-data` header, model listing using AsyncAnthropic
  SDK, MCP server compatibility, documentation with configuration
  examples
- **P2 (Medium)** -- Full validation and edge cases: comprehensive
  testing against Anthropic's API for all parameter combinations,
  error handling for Anthropic-specific responses, validation of
  embedding model guidance documentation

---

## 3. Test Environment

### 3.1 Infrastructure & Configuration

- RHOAI 3.5 cluster with OGX distribution (formerly Llama Stack)
  deployed
- OGX K8s Operator installed and operational
- OpenShift/Kubernetes cluster with egress access to Anthropic API
  endpoints
- Minimum OpenShift version: TBD (strategy specifies RHOAI 3.5 but
  does not state minimum OCP version; confirm with platform team)
- TLS 1.2+ support for external API calls to Anthropic
- Kubernetes Secrets capability for storing API keys
- Environment variable injection mechanism (`ANTHROPIC_API_KEY`) for
  provider activation
- Python runtime: TBD -- strategy assumption states "anthropic Python
  SDK is compatible with Python 3.12 on the AIPCC base image -- needs
  validation"; confirm supported Python version from AIPCC wheel
  pipeline before provisioning test environment
- AIPCC wheel pipeline with `anthropic` Python SDK available
  (dependency for Konflux builds)

### 3.2 Test Data Requirements

- Valid Anthropic API keys (minimum 2 keys for per-request override
  testing in multi-tenant scenarios)
- Native provider YAML configuration (`provider_type: remote::anthropic`
  without `network.headers` workarounds). Example activation pattern
  from strategy: `${env.ANTHROPIC_API_KEY:+anthropic-inference}` in
  `config.yaml`
- Legacy workaround YAML configuration for backwards compatibility
  validation. Example from strategy:

  ```yaml
  network:
    headers:
      x-api-key: ${env.EXTERNAL_MODEL_PROVIDER_API_KEY:=placeholder}
      anthropic-version: "2023-06-01"
  ```

- Per-request API key override header example:

  ```http
  x-ogx-provider-data: {"anthropic_api_key": "<second-api-key>"}
  ```

- Chat completion request payloads with streaming enabled/disabled and
  temperature/sampling parameters. Example:

  ```json
  {
    "model": "<anthropic-model-id>",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true,
    "temperature": 0.7
  }
  ```

- Tool calling test payloads for chat completions API and responses API
- MCP server configurations compatible with Anthropic models
- Sample model listing responses in Anthropic's `/v1/models` format
  (differs from OpenAI format)

### 3.3 Test Users

Strategy does not define explicit RBAC requirements (Section 7.4 notes
RBAC is N/A for this feature). The following roles are inferred from
the deployment and testing operations described in the strategy:

- **Cluster administrator**: Permissions to install the OGX K8s
  Operator, deploy the OGX distribution, and manage Kubernetes Secrets
  containing `ANTHROPIC_API_KEY`. Required for initial environment
  setup.
- **Namespace-scoped user**: Permissions to create/update ConfigMaps
  and CR specs for provider activation via environment variables.
  Required for provider configuration tests.
- **API consumer (unauthenticated at cluster level)**: Sends inference
  requests with per-request API key override via `x-ogx-provider-data`
  header. Required for multi-tenant scenario tests. Minimum 2
  identities with separate Anthropic API keys needed.
- **Service account**: TBD -- confirm whether a dedicated service
  account is required for the operator's environment variable injection
  mechanism (strategy references "user's ConfigMap or CR spec" but
  does not specify service account requirements)

### 3.4 Test Tools

- `oc` CLI (OpenShift) or `kubectl` for cluster operations: deploying
  the OGX distribution, managing ConfigMaps/Secrets, inspecting pod
  logs (`oc logs`), and verifying environment variable injection
- `curl` for REST API endpoint testing: `/v1/models`, `/v1/providers`,
  chat completions, and responses endpoints. Example:

  ```bash
  curl -X POST <ogx-route>/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "x-ogx-provider-data: {\"anthropic_api_key\": \"<key>\"}" \
    -d '{"model": "<model>", "messages": [{"role": "user", "content": "test"}]}'
  ```

- `jq` for JSON response validation (comparing Anthropic `/v1/models`
  format against expected AsyncAnthropic SDK output structure)
- `openssl s_client` or equivalent for TLS version verification on
  egress connections to Anthropic API endpoints
- pytest with RHOAI test framework for automated E2E test execution

---

## 4. Interfaces Under Test

| Interface | Type | Purpose |
|-----------|------|---------|
| `/v1/models` | REST | List Anthropic models using AsyncAnthropic SDK format |
| `/v1/providers` | REST | List available providers including `remote::anthropic` |
| Chat completions API | REST | Inference requests to Claude models with streaming and parameters |
| Responses API | REST | Inference requests via responses endpoint with tool calling |
| `x-ogx-provider-data` header | REST | Per-request API key override with `anthropic_api_key` field |
| OGX K8s Operator CR spec | CRD | Setting environment variables for provider activation |
| `kubectl`/`oc` CLI | CLI | Deploy and manage OGX distribution with Anthropic provider *(inferred from deployment context; strategy implies cluster operations but does not name CLI tooling as a testable interface)* |

---

## 5. Test Cases

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| TC-E2E | 9 | 5 P0, 4 P1 |
| TC-NEG | 3 | 1 P0, 2 P1 |
| TC-NFR | 2 | 2 P1 |
| TC-UPG | 2 | 2 P1 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

Only the following category prefixes are allowed -- feature areas go in the
test case name after the prefix, not as a separate category:

| Prefix | Meaning |
|--------|---------|
| TC-E2E | End-to-end user journey flows |
| TC-NEG | Negative and error path journeys |
| TC-NFR | Non-functional requirement validation (performance, disconnected, RBAC) |
| TC-UPG | Upgrade path validation |

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each interface in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Interfaces Covered | Priority |
|----|----------|-------------------|----------|
| TC-E2E-001 | Basic inference with native provider | Chat completions API, `x-ogx-provider-data` header | P0 |
| TC-E2E-002 | Streaming with temperature parameters | Chat completions API | P0 |
| TC-E2E-003 | Per-request API key override | Chat completions API, `x-ogx-provider-data` header | P1 |
| TC-E2E-004 | Anthropic model listing | `/v1/models` | P1 |
| TC-E2E-005 | Provider listing includes Anthropic | `/v1/providers` | P1 |
| TC-E2E-006 | Tool calling via chat completions | Chat completions API | P0 |
| TC-E2E-007 | Tool calling via responses API | Responses API | P0 |
| TC-E2E-008 | MCP server integration | Chat completions API, Responses API | P1 |
| TC-E2E-009 | Provider activation via env var | OGX K8s Operator CR spec, `/v1/providers` | P0 |

### 6.2 E2E Coverage Matrix

| Interface (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| `/v1/models` | TC-E2E-004 |
| `/v1/providers` | TC-E2E-005, TC-E2E-009 |
| Chat completions API | TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-006, TC-E2E-008 |
| Responses API | TC-E2E-007, TC-E2E-008 |
| `x-ogx-provider-data` header | TC-E2E-001, TC-E2E-003 |
| OGX K8s Operator CR spec | TC-E2E-009 |
| `kubectl`/`oc` CLI | TC-E2E-009 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

The `remote::anthropic` provider requires external network connectivity
to Anthropic's API endpoints. Disconnected testing must verify:

- The `anthropic` Python SDK package is bundled in the OGX distribution
  image via AIPCC wheels (no runtime download required)
- Provider configuration fails gracefully with clear error messages
  when Anthropic API endpoints are unreachable
- Network failure handling returns appropriate error responses to
  clients
- TLS 1.2+ enforcement for egress traffic is validated (cannot
  downgrade to insecure connections)

Note: This provider cannot function in fully air-gapped environments
as it requires real-time API calls to Anthropic's cloud service.
Disconnected testing focuses on build-time dependency packaging and
runtime error handling for network failures.

### 7.2 Upgrade/Migration

The strategy explicitly states this is an **additive change**. Testing
must verify:

- Existing `remote::openai` workaround configurations with Anthropic
  endpoints (using `network.headers` for `x-api-key`) continue to
  function after upgrade to a version with native `remote::anthropic`
  provider
- Side-by-side operation: both `remote::openai` and
  `remote::anthropic` providers work concurrently in the same
  deployment
- Migration path: configurations can be converted from
  `provider_type: remote::openai` with `network.headers` to
  `provider_type: remote::anthropic` without breaking existing
  inference requests
- Upgrade from RHOAI version without Anthropic provider to version
  with it does not disrupt existing provider configurations (OpenAI,
  Bedrock, etc.)
- Documentation provides clear migration guidance from the workaround
  to native provider

### 7.3 Performance/Scalability

The strategy highlights **multi-tenant scenarios** where different
users need different API keys. Testing must verify:

- API response latency with streaming enabled remains within
  acceptable bounds (baseline: comparable to OpenAI provider streaming
  performance)
- Concurrent inference requests with different per-request API keys
  (via `x-ogx-provider-data` header) do not cause key leakage,
  authentication failures, or cross-tenant data exposure
- Large response handling (Claude models can generate long outputs)
  does not cause memory issues or timeouts
- Tool calling overhead (request transformation for Anthropic's
  format) does not significantly degrade response time
- MCP server integration performance under load (multiple concurrent
  MCP requests)

### 7.4 RBAC/Authorization

**Not Applicable** -- The strategy does not define RBAC requirements
for access control within RHOAI. The per-request API key override
mechanism (`x-ogx-provider-data` header with `anthropic_api_key`
field) is for multi-tenant authentication to Anthropic's external
API, not for authorization boundaries between users within the OGX
distribution. Provider configuration is controlled via Kubernetes
environment variables and ConfigMaps, following existing OGX operator
patterns. No new role-based access control policies are introduced.

### 7.5 Security

Anthropic API keys must be handled securely through Kubernetes Secrets
injected as environment variables (`ANTHROPIC_API_KEY`), consistent
with existing provider secret management. Testing must verify:

- API keys are never logged in plain text (container logs, operator
  logs, audit logs)
- Per-request key override via `x-ogx-provider-data` header correctly
  replaces config-level keys without exposing either key in responses
- TLS 1.2+ is enforced for all egress traffic to Anthropic API
  endpoints (reject TLS 1.1 or lower)
- Authentication headers (`x-api-key` + `anthropic-version`) are
  transmitted securely and not cached in insecure locations
- Invalid or expired API keys result in clear authentication failures
  without leaking key material in error messages

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| `anthropic` Python SDK not available in AIPCC wheel pipeline | High | Medium | Engage AIPCC team early to confirm wheel availability; if not available, prioritize SDK onboarding alongside transitive dependencies before Konflux build |
| Anthropic API version changes between RHOAI releases | Medium | Low | Pin the upstream OGX version for RHOAI 3.5; monitor upstream repository for Anthropic-related changes; document the `anthropic-version` header value in release notes |
| Users on RHOAI 3.4 with `remote::openai` workaround need migration path | Medium | High | Document migration from `remote::openai` + `network.headers` to `remote::anthropic` in release notes; provide configuration examples and validation steps |
| Anthropic API access for testing unavailable | Medium | Low | Ensure QE team has valid Anthropic API keys for end-to-end validation; coordinate with PM for API key provisioning |
| Upstream OGX `remote::anthropic` provider stability unvalidated | Medium | Medium | Validate that the provider at the pinned upstream version is stable and functionally complete before integration; run upstream provider tests if available |
| `anthropic` Python SDK incompatible with Python 3.12 on AIPCC base image | Medium | Low | Validate SDK compatibility with Python 3.12 before Konflux build; check for known compatibility issues in SDK changelog |
| Coordination dependency with RHAISTRAT-1245 (Gemini provider) | Low | High | Determine sequencing or parallel delivery with Gemini provider; coordinate shared AIPCC wheel onboarding work to avoid duplication |

---

## 9. Appendix

### 9.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| TC-E2E | 9 | 5 | 4 | 0 |
| TC-NEG | 3 | 1 | 2 | 0 |
| TC-NFR | 2 | 0 | 2 | 0 |
| TC-UPG | 2 | 0 | 2 | 0 |
| **Total** | **16** | **6** | **10** | **0** |

### 9.2 Interface Coverage

| Interface | Test Cases | Coverage |
|-----------|------------|----------|
| `/v1/models` | TC-E2E-004 | |
| `/v1/providers` | TC-E2E-005, TC-E2E-009, TC-NEG-003 | |
| Chat completions API | TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-006, TC-E2E-008, TC-NEG-001, TC-NEG-002 | |
| Responses API | TC-E2E-007, TC-E2E-008 | |
| `x-ogx-provider-data` header | TC-E2E-001, TC-E2E-003, TC-NEG-002 | |
| OGX K8s Operator CR spec | TC-E2E-009 | |
| `kubectl`/`oc` CLI | TC-E2E-009 | |

### 9.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-13 | Initial test plan |
| 1.0.1 | 2026-08-14 | Auto-revision: grounding and actionability improvements |

---

## End of Test Plan
