---
feature: remote_anthropic_provider
source_key: RHAISTRAT-1246
status: Open
gap_count: 23
last_updated: '2026-08-14'
---
# Gaps — Remote Anthropic Provider

## Scope & Endpoints

- Missing concrete API endpoint paths for chat completions and
  responses APIs — would be resolved by: ADR / API spec
- Missing request/response payload schemas for inference, model
  listing, and provider listing endpoints — would be resolved by:
  API spec / feature refinement
- Missing specification of `x-ogx-provider-data` header format (JSON
  structure, encoding) — would be resolved by: ADR / design doc
- Missing MCP server integration mechanism and configuration details
  — would be resolved by: ADR / design doc
- Missing OGX K8s Operator CR spec structure and example manifests
  — would be resolved by: ADR / design doc
- Missing definition of "valid responses" success criteria for
  inference requests (AC #1) — would be resolved by: feature
  refinement / test acceptance criteria
- Missing streaming response validation criteria — would be resolved
  by: feature refinement / API spec

## Test Strategy & Risks

- No design document created — technical implementation details for
  AIPCC wheel integration, Konflux build changes, and anthropic SDK
  dependency tree are unclear. Would be resolved by: design doc
- AIPCC wheel availability for anthropic SDK unconfirmed — blocks
  Konflux build if the anthropic Python SDK and its transitive
  dependencies are not available in the AIPCC wheel release pipeline
  (open question in strategy). Would be resolved by: AIPCC team
  confirmation or design doc
- No specification of which Anthropic models to pre-register in
  default distribution config — affects test coverage for model
  listing and out-of-box experience validation (open question in
  strategy). Would be resolved by: feature refinement or PM decision
- Anthropic API version compatibility not validated — assumption that
  "Anthropic's API remains backwards-compatible through RHOAI 3.5 GA"
  needs verification. The `anthropic-version: 2023-06-01` header
  value may need updates. Would be resolved by: API spec review or
  Anthropic API documentation audit
- Python 3.12 compatibility for anthropic SDK not validated —
  assumption that "anthropic Python SDK is compatible with Python 3.12
  on the AIPCC base image" needs verification. Would be resolved by:
  design doc with compatibility validation or AIPCC team confirmation
- ADR not created — strategy marks ADR as "To be created if needed."
  Given the backwards compatibility concerns and migration path
  complexity, an ADR would clarify long-term support strategy. Would
  be resolved by: ADR

## Environment & Infrastructure

- Specific OpenShift/Kubernetes version requirements not specified
  — would be resolved by: ADR or feature refinement
- Exact RHOAI version number and operator versions not specified
  (only "RHOAI 3.5" mentioned generically) — would be resolved by:
  ADR
- Cluster resource requirements (node count, CPU, memory, storage)
  not specified — would be resolved by: ADR
- Test user types, service accounts, and RBAC role requirements not
  detailed — would be resolved by: ADR or feature refinement
- Specific Anthropic model names to test against not identified (open
  question in strategy) — would be resolved by: feature refinement
  or API spec
- MCP server configuration details and types not specified — would be
  resolved by: feature refinement or design doc
- Detailed tool calling test scenarios not provided — would be
  resolved by: API spec or feature refinement
- Streaming response validation criteria not detailed — would be
  resolved by: API spec
- Migration test scenarios from `remote::openai` to
  `remote::anthropic` not specified — would be resolved by: feature
  refinement
- Temperature and sampling parameter ranges for validation not
  specified — would be resolved by: API spec
