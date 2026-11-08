---
feature: agent_catalog
source_key: RHOAIENG-70680
status: Open
gap_count: 12
last_updated: '2026-07-07'
---
# Gaps -- Agent Catalog

## Scope & Endpoints

- **Error response specifications** -- HTTP status codes, error payloads, and error
  handling behavior for GitHub fetch failures, malformed YAML, invalid sourceLabel,
  nonexistent agent IDs not fully specified. Would be resolved by: API spec or ADR
- **Pagination implementation details** -- nextPageToken generation/validation,
  maximum pageSize limits, default values not specified. Would be resolved by: API spec
- **filterQuery syntax grammar** -- Operators enumerated but precedence rules and
  escaping not defined. Would be resolved by: API spec or design doc
- **Authentication and authorization** -- Whether endpoints require authentication or
  role-based restrictions not specified. Would be resolved by: ADR or design doc
- **Template artifact payload format** -- agent.yaml content stored "as JSON" but JSON
  schema not specified. Would be resolved by: API spec

## Test Strategy & Risks

- **RBAC requirements not specified** -- Who can access agent catalog endpoints, whether
  source management requires admin privileges. Would be resolved by: ADR or security spec
- **Performance targets not defined** -- No latency or throughput requirements for API
  endpoints. Would be resolved by: ADR with performance requirements
- **Metadata extraction schedule/trigger** -- How often catalogs are refreshed not
  specified. Would be resolved by: ADR

## Environment & Infrastructure

- **OpenShift and RHOAI version compatibility matrix** -- Specific version requirements
  not specified. Would be resolved by: ADR or design doc
- **Environment variables for agent plugin** -- Not specified. Would be resolved by:
  API spec or design doc
- **Detailed RBAC roles and permissions** -- Service accounts and test users not fully
  defined. Would be resolved by: ADR or design doc

## Test Case Coverage Gaps

- **No RBAC test cases** -- RBAC requirements are TBD (Section 7.4), so no
  authentication or authorization test cases were generated. Once RBAC
  requirements are specified, TC-NEG should be extended with unauthorized
  access scenarios
