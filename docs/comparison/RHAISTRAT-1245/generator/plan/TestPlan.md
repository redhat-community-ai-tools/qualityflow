---
feature: remote_gemini_provider
source_key: RHAISTRAT-1245
source_type: strat
status: In Review
author: QE Team
components:
- Llama Stack Core
additional_docs: []
last_updated: '2026-06-05'
version: 1.0.1
reviewers: []
---
# Remote Gemini Provider Test Plan

**QE Team – OGX remote::gemini Provider Validation**

**Strategy**: [RHAISTRAT-1245](https://redhat.atlassian.net/browse/RHAISTRAT-1245)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates the inclusion of the upstream `remote::gemini`
inference provider in the RHOAI OGX (formerly Llama Stack) distribution
image. The feature enables native Gemini model support with proper
authentication, embedding handling, tool calling compatibility, and
per-request API key override — replacing the current `remote::openai`
workaround that causes embedding failures, tool calling
incompatibilities via the Responses API, and blocks multi-tenant
scenarios.

The `remote::gemini` provider is essential for the Gen AI Studio
external model feature planned for RHOAI 3.5 EA2, ensuring full
feature parity between OpenAI and Gemini model providers without
custom per-provider workarounds in the distribution.

### 1.2 Scope

#### In Scope (QE Team Responsibilities)

- Verifying the `remote::gemini` provider is available in the
  downstream RHOAI OGX distribution image and listed by
  `/v1/providers`
- Validating Gemini model configuration using
  `provider_type: remote::gemini` without `network.headers`
  workarounds
- Testing Gemini embeddings API with proper handling of missing
  usage statistics
- Testing Gemini chat completions API with streaming and temperature
  parameters
- Validating tool calling via `/v1/chat/completions` endpoint
- Testing per-request API key override via `x-ogx-provider-data`
  header with `gemini_api_key` field
- Verifying MCP server functionality with Gemini models
- Validating conditional provider activation via `GEMINI_API_KEY`
  environment variable
- Verifying `build.yaml` and `config.yaml` distribution
  configuration updates
- Testing OGX K8s Operator ConfigMap-based environment variable
  injection for Gemini configuration
- Backwards compatibility with existing `remote::openai`
  configurations

#### Out of Scope (Other Teams)

- Gemini-specific UI in Gen AI Studio (Dashboard team)
- Per-user API token management through the Dashboard UI
  (future release)
- Google Vertex AI provider (already exists as a separate provider)
- Google Interactions API protocol support
  (tracked in RHAISTRAT-1509)
- Tool calling via `/v1/responses` API (known Gemini limitation)
- AIPCC wheel pipeline onboarding for `google-genai` package
  (AIPCC team)

### 1.3 Test Objectives

1. Verify that the `remote::gemini` provider is present in the
   deployed OGX distribution and listed in the `/v1/providers`
   endpoint output
2. Validate that Gemini models can be configured using
   `provider_type: remote::gemini` without requiring
   `network.headers` workarounds
3. Confirm that Gemini embeddings API requests complete
   successfully despite missing usage statistics in API responses
4. Verify that Gemini chat completions API works correctly with
   streaming and temperature parameters
5. Validate that tool calling via `/v1/chat/completions` endpoint
   succeeds and returns valid `tool_calls` output
6. Confirm that per-request API key override using
   `x-ogx-provider-data` header with `gemini_api_key` field
   successfully overrides config-level keys
7. Verify that MCP servers function correctly when connected to
   Gemini models

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — Primary focus: testing OGX REST
  endpoints (`/v1/chat/completions`, `/v1/providers`, embeddings)
  against the Gemini API backend through the `remote::gemini`
  provider
- **Data Validation Testing** — Verifying correct handling of
  Gemini-specific response formats, including missing usage
  statistics in embedding responses and JSON schema field filtering
- **Functional Testing** — Business logic validation for provider
  activation, configuration patterns, tool calling, and per-request
  API key override
- **Deployment Testing** — Distribution image build verification,
  Konflux pipeline integration, and OGX K8s Operator ConfigMap
  injection for Gemini credentials
- **Security Testing** — API key management through Kubernetes
  Secrets, per-request key isolation, and TLS 1.2+ enforcement
  for Gemini API egress

### 2.2 Test Types

- **Positive Testing** — Valid Gemini API key configuration, correct
  chat completions, successful embeddings, working tool definitions
- **Negative Testing** — Invalid API keys, missing `GEMINI_API_KEY`
  environment variable, malformed provider configuration, invalid
  tool definitions with unsupported JSON schema fields
- **Boundary Testing** — Large streaming responses, concurrent
  multi-tenant requests with different API keys, edge-case tool
  definitions
- **Regression Testing** — Existing `remote::openai` configurations
  continue to work, other providers unaffected by the addition of
  `remote::gemini`

### 2.3 Test Priorities

- **P0 (Critical)** — `remote::gemini` provider availability in the
  distribution, Gemini model configuration without workarounds,
  core chat completions and embeddings API functionality, tool
  calling via `/v1/chat/completions`
- **P1 (High)** — Per-request API key override via
  `x-ogx-provider-data` header, MCP server compatibility with
  Gemini models, documentation accuracy
- **P2 (Medium)** — Edge-case validation against Gemini's
  OpenAI-compatible API endpoint, JSON schema field filtering
  behavior, streaming performance characteristics

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- **OpenShift**: TBD (version to be confirmed per RHOAI 3.5
  compatibility matrix)
- **RHOAI**: 3.5 EA2 or later with OGX distribution including
  `remote::gemini` provider
- **OGX Distribution**: Built via Konflux pipeline with
  `google-genai` package from AIPCC wheels
- **OGX K8s Operator**: TBD — The strategy does not pin a
  specific operator version or build reference. Minimum version
  must support `LlamaStackDistribution` CRs with ConfigMap-based
  environment variable injection for `GEMINI_API_KEY`. Pin to the
  version shipped with RHOAI 3.5 EA2 once the build manifest is
  available.
- **External Connectivity**: Outbound HTTPS access to Google Gemini
  API endpoints required (TLS 1.2+)

### 3.2 Test Data Requirements

- **Gemini API Keys**: At least two valid Gemini API keys for
  testing per-request API key override
  - Primary key: configured via `GEMINI_API_KEY` environment
    variable in ConfigMap or CR spec
  - Secondary key: passed via `x-ogx-provider-data` header for
    per-request override testing
- **Gemini Model IDs**: TBD — The strategy lists "What Gemini
  models should be pre-registered in the default distribution
  config?" as an open question owned by PM / OGX Core Team.
  Update this section once model IDs are confirmed. Until then,
  use whatever model IDs appear in the distribution's
  `config.yaml` after the build is available.
- **Sample Distribution Configurations**:
  - `config.yaml` with `remote::gemini` provider using conditional
    activation pattern
    `${env.GEMINI_API_KEY:+gemini-inference}`
  - `build.yaml` with `remote::gemini` declared as a build-time
    dependency
- **Sample Request/Response Payloads**:
  - **Chat Completions (non-streaming)**:

    ```http
    POST /v1/chat/completions
    Content-Type: application/json

    {
      "model": "<TBD-GEMINI-MODEL-ID>",
      "messages": [
        {"role": "user", "content": "What is the capital of France?"}
      ],
      "temperature": 0.7
    }
    ```

  - **Chat Completions (streaming)**:

    ```http
    POST /v1/chat/completions
    Content-Type: application/json

    {
      "model": "<TBD-GEMINI-MODEL-ID>",
      "messages": [
        {"role": "user", "content": "Explain quantum computing."}
      ],
      "stream": true,
      "temperature": 0.5
    }
    ```

  - **Chat Completions (per-request API key override)**:

    ```http
    POST /v1/chat/completions
    Content-Type: application/json
    x-ogx-provider-data: {"gemini_api_key": "<SECONDARY-API-KEY>"}

    {
      "model": "<TBD-GEMINI-MODEL-ID>",
      "messages": [
        {"role": "user", "content": "Hello"}
      ]
    }
    ```

  - **Tool Calling**:

    ```http
    POST /v1/chat/completions
    Content-Type: application/json

    {
      "model": "<TBD-GEMINI-MODEL-ID>",
      "messages": [
        {"role": "user", "content": "What is the weather in Paris?"}
      ],
      "tools": [
        {
          "type": "function",
          "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
              "type": "object",
              "properties": {
                "location": {"type": "string"}
              },
              "required": ["location"]
            }
          }
        }
      ]
    }
    ```

    Expected response includes `tool_calls` array with
    `function.name` and `function.arguments`.
  - **Embeddings**:

    ```http
    POST <embeddings-endpoint>
    Content-Type: application/json

    {
      "model": "<TBD-GEMINI-MODEL-ID>",
      "input": "Sample text for embedding generation"
    }
    ```

    Expected: response contains embedding vector; note that
    Gemini may omit `usage` statistics in the response, which
    the provider must handle gracefully.
- **Tool Calling Payloads**: Sample tool definitions for
  `/v1/chat/completions` with function calling, including
  definitions that use JSON schema fields unsupported by Gemini
  (`additionalProperties`, `$schema`, `exclusiveMaximum`,
  `exclusiveMinimum`, `maxItems`, `minItems`, `propertyNames`,
  `const`, `default`)
- **Embedding Input Texts**: Sample texts for embedding generation
  requests
- **MCP Server Configuration**: TBD — The strategy confirms that
  MCP servers must work correctly with Gemini models but does not
  name a specific MCP server harness or tool for testing. Update
  once the QE team selects a harness (e.g., a reference MCP
  server that exposes tool definitions for the model to invoke).

### 3.3 Test Users

- **Cluster Admin**: For deploying OGX distribution and configuring
  `LlamaStackDistribution` CRs
- **API Consumer**: Standard user making inference requests via OGX
  REST API endpoints
- **Multi-Tenant Users**: Multiple users with distinct Gemini API
  keys for per-request override testing

---

## 4. API Endpoints Under Test

| Endpoint | Method | Purpose | Priority |
| ---------- | -------- | --------- | ---------- |
| `/v1/providers` | GET | List available providers; verify `remote::gemini` is present | P0 |
| `/v1/chat/completions` | POST | Chat completions with Gemini models (non-streaming) | P0 |
| `/v1/chat/completions` (streaming) | POST | Streaming chat completions with Gemini models | P0 |
| `/v1/chat/completions` (tool calling) | POST | Tool calling with Gemini-compatible function definitions | P0 |
| Embeddings endpoint | POST | Generate embeddings via `remote::gemini` provider | P0 |
| `GEMINI_API_KEY` env var | Config | Conditional provider activation in `config.yaml` | P0 |
| `provider_type: remote::gemini` | Config | Provider configuration without `network.headers` workarounds | P0 |
| `build.yaml` | Config | Distribution build config including `remote::gemini` | P0 |
| `config.yaml` | Config | Runtime config with conditional Gemini activation pattern | P0 |
| `x-ogx-provider-data` header | Header | Per-request API key override with `gemini_api_key` field | P1 |
| MCP server connections | Integration | MCP server functionality with Gemini models | P1 |
| Temperature parameter | Parameter | Temperature control in Gemini chat completions | P0 |

---

## 5. Test Cases

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
| ---------- | ------------ | ---------------------- |
| TC-PROV (Provider) | 3 | 3 P0 |
| TC-CHAT (Chat Completions) | 3 | 3 P0 |
| TC-EMB (Embeddings) | 2 | 2 P0 |
| TC-TOOL (Tool Calling) | 2 | 1 P0, 1 P2 |
| TC-AUTH (Authentication) | 2 | 2 P1 |
| TC-MCP (MCP Server) | 1 | 1 P1 |
| TC-DEP (Deployment) | 3 | 3 P0 |
| TC-REG (Regression) | 2 | 1 P0, 1 P1 |
| TC-SEC (Security) | 2 | 1 P1, 1 P2 |
| TC-E2E (End-to-End) | 4 | 3 P0, 1 P1 |
| **Total** | **24** | **16 P0, 6 P1, 2 P2** |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- `TC-PROV` — Provider availability and configuration
- `TC-CHAT` — Chat completions (including streaming and temperature)
- `TC-EMB` — Embeddings API
- `TC-TOOL` — Tool calling via `/v1/chat/completions`
- `TC-AUTH` — Per-request API key override and authentication
- `TC-MCP` — MCP server integration
- `TC-DEP` — Deployment and distribution configuration
- `TC-REG` — Regression (backwards compatibility)
- `TC-SEC` — Security (API key management, TLS)
- `TC-E2E` — End-to-end scenarios

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for
> each P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
| ---- | ---------- | ------------------- | ---------- |
| TC-E2E-001 | Deploy OGX with Gemini and run chat completion | `/v1/providers`, `/v1/chat/completions`, streaming, `GEMINI_API_KEY`, `provider_type: remote::gemini`, `config.yaml`, Temperature | P0 |
| TC-E2E-002 | Full tool calling workflow with Gemini | `/v1/chat/completions` (tool calling) | P0 |
| TC-E2E-003 | Embedding generation end-to-end | `/v1/providers`, Embeddings endpoint | P0 |
| TC-E2E-004 | Multi-tenant per-request API key override | `/v1/chat/completions`, `x-ogx-provider-data` header | P1 |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
| ---------------------------- | --------------- |
| `/v1/providers` | TC-E2E-001, TC-E2E-003 |
| `/v1/chat/completions` | TC-E2E-001, TC-E2E-004 |
| `/v1/chat/completions` (streaming) | TC-E2E-001 |
| `/v1/chat/completions` (tool calling) | TC-E2E-002 |
| Embeddings endpoint | TC-E2E-003 |
| `GEMINI_API_KEY` env var | TC-E2E-001 |
| `provider_type: remote::gemini` | TC-E2E-001 |
| `build.yaml` | — |
| `config.yaml` | TC-E2E-001 |
| `x-ogx-provider-data` header | TC-E2E-004 |
| MCP server connections | — |
| Temperature parameter | TC-E2E-001 |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

**Not Applicable** — The `remote::gemini` provider requires
outbound HTTPS connectivity to Google's Gemini API endpoints at
runtime. This feature cannot function in disconnected or
air-gapped environments by design. The conditional activation
pattern (`${env.GEMINI_API_KEY:+gemini-inference}`) ensures the
provider is only activated when a Gemini API key is present,
so disconnected deployments that omit the key will not attempt
to load the provider.

### 7.2 Upgrade/Migration

- **Backwards Compatibility**: The `remote::gemini` provider is
  purely additive. Existing configurations using
  `remote::openai` as a Gemini workaround continue to function
  but can be migrated to the native provider.
- **ConfigMap Migration**: Users who previously configured Gemini
  via `remote::openai` with `network.headers` can migrate to
  `provider_type: remote::gemini` with `GEMINI_API_KEY`
  environment variable injection.
- **Distribution Upgrade**: Upgrading from a distribution without
  `remote::gemini` to one that includes it should not disrupt
  existing providers. Verify that the new provider only activates
  when `GEMINI_API_KEY` is set.

### 7.3 Performance/Scalability

- **API Latency**: Measure response time for Gemini chat
  completions and embeddings requests through the
  `remote::gemini` provider to establish baseline latency.
- **Concurrent Multi-Tenant Requests**: Validate that multiple
  concurrent requests with different per-request API keys
  (via `x-ogx-provider-data`) are properly isolated and do not
  cross-contaminate authentication.
- **Streaming Performance**: Verify that streaming responses from
  Gemini models are delivered with acceptable time-to-first-token
  and chunk delivery.
- **Resource Consumption**: Monitor OGX pod resource usage
  (CPU, memory) under Gemini provider load to ensure no
  resource leaks from the `google-genai` dependency.

### 7.4 RBAC/Authorization

- **API Key Secret Management**: Gemini API keys must be injected
  via Kubernetes Secrets through the OGX K8s Operator's
  ConfigMap mechanism. Verify that keys are not exposed in
  pod specs, logs, or API responses.
- **Per-Request Key Isolation**: When using
  `x-ogx-provider-data` header for per-request API key override,
  verify that the override key is used only for that specific
  request and does not affect other concurrent requests.
- **Provider Access Control**: Verify that the
  `remote::gemini` provider respects OGX's existing access
  control mechanisms for provider endpoints.

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
| ------ | -------- | ------------- | ------------ |
| `google-genai` package not available in AIPCC wheel pipeline | High — Cannot build Konflux image for RHOAI | Medium | Engage AIPCC team early to confirm wheel availability; prioritize wheel onboarding if not available |
| Gemini API changes break provider between upstream OGX version and RHOAI release | High — Provider may fail for new Gemini API versions | Low | Pin the OGX upstream version used in the distribution; monitor upstream for Gemini-related fixes |
| Tool calling via `/v1/responses` API still fails with Gemini | Medium — Partial functionality gap for Responses API users | High | Document the limitation; users can use `/v1/chat/completions` for tool calling with Gemini |
| Per-request API key override mechanism does not properly isolate keys across concurrent requests | High — Security risk in multi-tenant scenarios | Low | Test with concurrent requests using different API keys; verify request-level isolation |
| JSON schema incompatibilities cause silent failures in tool definitions | Medium — Tool calling may fail for certain tool definitions | Medium | Test with tool definitions containing all known unsupported JSON schema fields; verify filtering behavior |
| Gemini API rate limits impact test execution reliability | Low — Flaky test results | Medium | Implement retry logic in tests; use separate API keys for parallel test execution |
| OGX K8s Operator ConfigMap injection does not propagate `GEMINI_API_KEY` correctly | High — Provider fails to activate | Low | Verify ConfigMap-based env var injection in operator integration tests |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- OpenShift cluster with RHOAI 3.5 EA2+ deployed
- OGX K8s Operator installed and managing
  `LlamaStackDistribution` CRs
- OGX distribution image built via Konflux pipeline with
  `google-genai` package from AIPCC wheels
- Outbound HTTPS connectivity to Google Gemini API
  (TLS 1.2+ enforced)

### 9.2 Configuration

- `GEMINI_API_KEY` environment variable set via Kubernetes
  Secret and injected through ConfigMap or CR spec
- Distribution `config.yaml` with conditional activation
  pattern: `${env.GEMINI_API_KEY:+gemini-inference}`
- Distribution `build.yaml` with `remote::gemini` provider
  declared as a build-time dependency
- Secondary Gemini API key available for per-request override
  testing

### 9.3 Test Tools

- **API Testing**: `curl`, `httpie`, or Postman for direct
  API endpoint testing
- **Python Testing**: `pytest` with `requests` and `openai`
  SDK for automated test execution
- **Kubernetes**: `kubectl`/`oc` for cluster management,
  log inspection, and resource monitoring
- **MCP Server**: TBD — The strategy requires MCP server
  compatibility testing with Gemini models but does not name
  a specific MCP server harness or tool. Select a reference
  MCP server implementation that exposes callable tools and
  update this section before test execution begins.
- **Monitoring**: Pod resource metrics for performance
  validation

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
| ---------- | ------- | ---- | ---- | ----- |
| TC-PROV | 3 | 3 | 0 | 0 |
| TC-CHAT | 3 | 3 | 0 | 0 |
| TC-EMB | 2 | 2 | 0 | 0 |
| TC-TOOL | 2 | 1 | 0 | 1 |
| TC-AUTH | 2 | 0 | 2 | 0 |
| TC-MCP | 1 | 0 | 1 | 0 |
| TC-DEP | 3 | 3 | 0 | 0 |
| TC-REG | 2 | 1 | 1 | 0 |
| TC-SEC | 2 | 0 | 1 | 1 |
| TC-E2E | 4 | 3 | 1 | 0 |
| **Total** | **24** | **16** | **6** | **2** |

### 10.2 Endpoint Coverage

| Endpoint | Test Cases | Coverage |
| ---------- | ------------ | ---------- |
| `/v1/providers` | TC-PROV-001, TC-PROV-003, TC-E2E-001, TC-E2E-003 | |
| `/v1/chat/completions` | TC-CHAT-001, TC-E2E-001, TC-E2E-004 | |
| `/v1/chat/completions` (streaming) | TC-CHAT-002, TC-E2E-001 | |
| `/v1/chat/completions` (tool calling) | TC-TOOL-001, TC-TOOL-002, TC-E2E-002 | |
| Embeddings endpoint | TC-EMB-001, TC-EMB-002, TC-E2E-003 | |
| `GEMINI_API_KEY` env var | TC-PROV-003, TC-DEP-003, TC-E2E-001 | |
| `provider_type: remote::gemini` | TC-PROV-002, TC-E2E-001 | |
| `build.yaml` | TC-DEP-001 | |
| `config.yaml` | TC-DEP-002, TC-E2E-001 | |
| `x-ogx-provider-data` header | TC-AUTH-001, TC-AUTH-002, TC-E2E-004 | |
| MCP server connections | TC-MCP-001 | |
| Temperature parameter | TC-CHAT-003, TC-E2E-001 | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-06-05 | Initial test plan |
| 1.0.1 | 2026-06-05 | Actionability revision: added TBD with rationale for Gemini model IDs (open question), OGX Operator version, and MCP server harness; added sample request/response payloads for chat completions, streaming, tool calling, per-request API key override, and embeddings |

---

**End of Test Plan**
