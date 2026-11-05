---
feature: remote_gemini_provider
source_key: RHAISTRAT-1245
status: Open
gap_count: 26
last_updated: '2026-06-05'
---
# Gaps — Remote Gemini Provider

## Scope & Endpoints

- **google-genai package availability in AIPCC wheel pipeline not
  confirmed** — would be resolved by: AIPCC wheel release
  documentation or confirmation from AIPCC team
- **Specific Gemini API endpoints (base URL, authentication endpoint
  paths) not documented** — would be resolved by: API specification
  document or Gemini API integration guide
- **Expected format/structure of x-ogx-provider-data header payload
  with gemini_api_key field** — would be resolved by: API
  specification or ADR describing header-based authentication
  override mechanism
- **/v1/responses API compatibility status with remote::gemini
  provider unclear** — would be resolved by: Technical investigation
  findings or ADR with API compatibility matrix
- **Error handling specifications for Gemini-specific API error
  codes/formats** — would be resolved by: API specification or
  integration guide documenting Gemini error response handling
- **TLS version and certificate validation requirements for Gemini
  API egress** — would be resolved by: Security requirements document
  or ADR (strategy mentions TLS 1.2+ but lacks implementation
  details)
- **JSON schema transformation rules for filtering
  Gemini-incompatible fields** — would be resolved by: Technical
  design document or code implementation specification for schema
  filtering logic
- **ConfigMap injection patterns for GEMINI_API_KEY via OGX K8s
  Operator** — would be resolved by: Operator configuration guide
  or ADR describing environment variable injection for provider
  credentials

## Test Strategy & Risks

- **Gemini API version compatibility matrix not defined** — would be
  resolved by: ADR or design doc specifying supported Gemini API
  versions
- **Supported Gemini model list for pre-registration not
  specified** — would be resolved by: PM decision or ADR listing
  default models (open question in strategy)
- **JSON schema field filtering behavior for tool definitions not
  fully specified** — would be resolved by: Technical design document
  or upstream code review documenting filtering rules
- **MCP server integration patterns with Gemini models not
  detailed** — would be resolved by: Integration guide or design doc
  for MCP+Gemini connectivity
- **Backwards compatibility test scenarios for remote::openai to
  remote::gemini migration not enumerated** — would be resolved by:
  Migration guide or ADR describing upgrade path
- **Performance baselines and SLOs for Gemini provider not
  defined** — would be resolved by: Performance requirements document
  or NFR specification
- **Gemini-specific error handling test cases not enumerated** —
  would be resolved by: Error handling specification or Gemini API
  error code reference

## Environment & Infrastructure

- **OpenShift version compatibility not specified** — would be
  resolved by: RHOAI 3.5 compatibility matrix or release notes
- **Gemini model list for pre-registration unclear** — would be
  resolved by: PM decision (open question in strategy)
- **/v1/responses API tool calling expected behavior with native
  remote::gemini provider unknown** — would be resolved by:
  Technical investigation or ADR
- **AIPCC wheel availability for google-genai package
  unconfirmed** — would be resolved by: AIPCC team confirmation
  (blocks Konflux build)
- **Network policy/proxy configuration details for Gemini API
  egress missing** — would be resolved by: Network architecture
  document or cluster configuration guide
- **Resource limits for OGX pod sizing with google-genai dependency
  not provided** — would be resolved by: Performance testing or
  resource requirements document
- **ConfigMap schema for Gemini provider configuration
  undocumented** — would be resolved by: Operator documentation or
  ADR
- **Per-request API key override example payloads needed** — would be
  resolved by: API specification or integration guide
- **MCP server test setup and configuration undefined** — would be
  resolved by: MCP integration guide or test harness documentation
- **Backwards compatibility test scenarios for distribution upgrade
  not specified** — would be resolved by: Upgrade guide or ADR
- **Gemini-specific error handling test cases not enumerated** —
  would be resolved by: Error handling specification
