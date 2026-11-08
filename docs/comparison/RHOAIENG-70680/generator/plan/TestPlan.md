---
feature: agent_catalog
source_key: RHOAIENG-70680
source_type: issue
status: Draft
author: ai-hub
components:
- AI Hub
additional_docs: []
last_updated: '2026-07-07'
version: 1.0.0
reviewers: []
---
# Agent Catalog Test Plan

**AI Hub – Agent Catalog Backend**

**Strategy**: [RHOAIENG-70680](https://redhat.atlassian.net/browse/RHOAIENG-70680)

---

## 1. Executive Summary

### 1.1 Purpose

The Agent Catalog feature extends the RHOAI catalog infrastructure to support
AI agent starter kits alongside existing models and MCP servers. This test plan
covers the backend components: a metadata extraction pipeline that discovers
agent starter kits from GitHub repositories and produces structured YAML
catalogs, a new catalog service plugin with REST API endpoints for listing,
filtering, searching, and retrieving agent details, and operator integration
for automatic deployment and configuration of agent catalog sources.

The feature is scoped as Dev Preview — browse-only, with no agent execution
or versioning. Testing focuses on verifying API correctness, data integrity,
operator wiring, and compatibility with existing catalog plugins.

### 1.2 Scope

#### In Scope (AI Hub Responsibilities)

- Agent catalog REST API endpoints (list, get, filter options, artifacts)
- Agent metadata schema validation (required and optional fields)
- filterQuery with operators (=, !=, LIKE, ILIKE, IN, AND, OR)
- Keyword search (`q` parameter) and name filter (`name` LIKE)
- sourceLabel filtering and sourceLabel-to-sourceID resolution
- Pagination (pageSize, nextPageToken, orderBy, sortOrder)
- Unified `/sources?assetType=agents` endpoint integration
- Agent plugin registration and health (`/readyz`)
- Operator-managed ConfigMap creation and volume mounting
- User-editable agent sources via ConfigMap patching
- Custom properties forwarding from upstream YAML
- Artifacts endpoint with type filtering (image-artifact, template-artifact)
- Metadata extraction pipeline (`make process-agents`)

#### Out of Scope (Other Teams)

- UI implementation (BFF proxy and frontend pages)
- Agent deployment or execution from the catalog
- Agent versioning or lifecycle management
- Custom agent registration by end users
- Agent runtime orchestration

### 1.3 Test Objectives

1. Verify catalog API endpoints return accurate agent data with correct
   filtering, search, and pagination behavior
2. Verify the operator successfully deploys and configures agent catalog
   sources from ConfigMaps with correct volume mounts and `--catalogs-path`
3. Verify sourceLabel resolution correctly maps to sourceID for multi-source
   catalog scenarios
4. Verify filterQuery parser supports all specified operators and correctly
   filters results
5. Verify the artifacts endpoint returns correct artifact types with proper
   pagination and 404 for nonexistent agents
6. Verify the agent plugin registers correctly and reports healthy via `/readyz`
7. Verify existing model and MCP catalog plugins remain functional after
   agent plugin deployment

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — Primary focus, testing REST endpoints against
  the shared PostgreSQL database
- **Data Validation Testing** — Agent schema compliance, YAML catalog
  structure, custom properties forwarding
- **Functional Testing** — Filtering, search, pagination, source management,
  plugin lifecycle
- **Operator Integration Testing** — ConfigMap creation, volume mounting,
  catalog path wiring, init container loading

### 2.2 Test Types

- **Positive Testing** — Valid API requests with expected filters, search
  terms, pagination parameters; successful agent listing and detail retrieval
- **Negative Testing** — Invalid filterQuery syntax, nonexistent agent IDs,
  malformed YAML sources, unauthorized access attempts
- **Boundary Testing** — Large catalogs, complex filterQuery combinations
  (nested AND/OR), maximum pageSize limits, agents with minimal vs complete
  metadata
- **Regression Testing** — Existing model and MCP plugins remain functional,
  unified /sources endpoint returns all asset types, shared database integrity

### 2.3 Test Priorities

- **P0 (Critical)** — Core browsing: list agents, get agent detail, basic
  filtering/search succeed; operator deployment creates ConfigMap and loads
  agents; plugin registers and reports healthy
- **P1 (High)** — Advanced filtering (all operators), source management,
  pagination, metadata extraction pipeline, artifacts endpoint, custom
  properties
- **P2 (Medium)** — Edge cases in filter combinations, performance with
  large catalogs, graceful handling of incomplete metadata, disabled sources

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- OpenShift cluster with RHOAI operator installed
- Model catalog service running with agent plugin enabled
- Shared PostgreSQL database (MLMD schema)
- `model-catalog-sources` ConfigMap for user-editable agent catalog sources
- `default-catalog-sources` ConfigMap with Red Hat starter kits (operator-managed)

### 3.2 Test Data Requirements

- Custom agent catalog YAML with 7 agents across frameworks (langgraph,
  crewai, autogen, claude-code, langflow, minimal) injected via ConfigMap
  patch
- Agents with varying completeness: full metadata, missing framework,
  custom properties
- Red Hat starter kits catalog (15 agents, loaded by operator default)

### 3.3 Test Users

- Admin user with permissions to create/patch ConfigMaps and access catalog
  API
- Service account with database access for catalog service

---

## 4. API Endpoints Under Test

| Endpoint | Method | Purpose | Priority |
| ---------- | -------- | --------- | ---------- |
| /api/agent_catalog/v1alpha1/agents | GET | List agents with filtering, search, pagination | P0 |
| /api/agent_catalog/v1alpha1/agents/{agent_id} | GET | Retrieve a single agent by ID | P0 |
| /api/agent_catalog/v1alpha1/agents/filter_options | GET | List available filter fields and values | P1 |
| /api/agent_catalog/v1alpha1/agents/{id}/artifacts | GET | Retrieve agent artifacts with type filtering | P1 |
| /api/model_catalog/v1alpha1/sources?assetType=agents | GET | List agent catalog sources | P0 |
| /readyz | GET | Verify agent plugin health | P0 |
| /healthz | GET | Verify catalog service health | P0 |

### Query Parameters (GET /agents)

| Parameter | Purpose | Priority |
| ----------- | --------- | ---------- |
| name | SQL LIKE search on agent name | P1 |
| q | Keyword search across agent fields | P1 |
| sourceLabel | Filter by source label | P1 |
| filterQuery | Complex filtering (framework, agentType, tags) | P1 |
| pageSize | Control pagination size | P1 |
| orderBy | Specify sort field (NAME, ID, CREATE_TIME) | P2 |
| sortOrder | Specify sort direction (ASC, DESC) | P2 |
| nextPageToken | Retrieve next page of results | P1 |

### Query Parameters (GET /agents/{id}/artifacts)

| Parameter | Purpose | Priority |
| ----------- | --------- | ---------- |
| artifactType | Filter by type (image-artifact, template-artifact) | P1 |
| pageSize | Control pagination size | P1 |
| nextPageToken | Retrieve next page of results | P1 |

---

## 5. Test Cases

> **Note**: 47 test cases generated across 11 categories. See the
> complete index at [test_cases/INDEX.md](test_cases/INDEX.md).

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
| ---------- | ------------ | ---------------------- |
| TC-API | 6 | 5×P0, 1×P1, 0×P2 |
| TC-FILTER | 9 | 0×P0, 8×P1, 1×P2 |
| TC-SEARCH | 4 | 0×P0, 4×P1, 0×P2 |
| TC-PAGE | 4 | 0×P0, 2×P1, 2×P2 |
| TC-SRC | 4 | 0×P0, 3×P1, 1×P2 |
| TC-SCHEMA | 3 | 0×P0, 3×P1, 0×P2 |
| TC-ARTIFACT | 4 | 0×P0, 4×P1, 0×P2 |
| TC-OPS | 1 | 0×P0, 1×P1, 0×P2 |
| TC-NEG | 5 | 1×P0, 2×P1, 2×P2 |
| TC-E2E | 4 | 4×P0, 0×P1, 0×P2 |
| TC-UPGRADE | 3 | 2×P0, 1×P1, 0×P2 |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- `TC-API` — API endpoint functionality (list, get, filter options)
- `TC-FILTER` — filterQuery operators and parameter filtering
- `TC-SEARCH` — Keyword search and name LIKE matching
- `TC-PAGE` — Pagination and ordering
- `TC-SRC` — Source management (sourceLabel, multi-source, disabled)
- `TC-SCHEMA` — Agent schema validation (required fields, custom properties)
- `TC-ARTIFACT` — Artifacts endpoint and type filtering
- `TC-OPS` — Operator integration (ConfigMap, volumes, health)
- `TC-NEG` — Negative and error handling scenarios
- `TC-E2E` — End-to-end scenarios

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for each
> P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
| ---- | ---------- | ------------------- | ---------- |
| TC-E2E-001 | Browse and inspect agent from default catalog | /healthz, /readyz, /agents, /agents/{id}, /agents/{id}/artifacts | P0 |
| TC-E2E-002 | Add custom agent source and browse combined catalog | /agents, /sources?assetType=agents, /readyz | P0 |
| TC-E2E-003 | Filter, search, and paginate through agent catalog | /agents, /agents/filter_options | P0 |
| TC-E2E-004 | Operator deployment wires agent catalog end-to-end | /healthz, /readyz, /agents, /sources?assetType=agents | P0 |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
| ---------------------------- | --------------- |
| GET /api/agent_catalog/v1alpha1/agents | TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-004 |
| GET /api/agent_catalog/v1alpha1/agents/{agent_id} | TC-E2E-001 |
| GET /api/agent_catalog/v1alpha1/agents/filter_options | TC-E2E-003 |
| GET /api/agent_catalog/v1alpha1/agents/{id}/artifacts | TC-E2E-001 |
| GET /api/model_catalog/v1alpha1/sources?assetType=agents | TC-E2E-002, TC-E2E-004 |
| GET /readyz | TC-E2E-001, TC-E2E-002, TC-E2E-004 |
| GET /healthz | TC-E2E-001, TC-E2E-004 |

---

## 7. Non-Functional Requirements

### 7.1 Disconnected/Air-Gapped

The metadata extraction pipeline fetches agent starter kits from GitHub.
In disconnected environments:

- Pre-loaded YAML catalogs must be bundled with the operator installation
  without requiring external GitHub access
- Custom agent catalog sources configured via ConfigMap pointing to
  internal registries or mirrors
- Operator deployment succeeds with offline catalog loading
  (agents-catalog.yaml in init container)
- Error handling when GitHub sources are unavailable, with fallback to
  cached catalogs
- `--skip-github-fetch` flag enables offline pipeline execution

### 7.2 Upgrade/Migration

The feature introduces a new plugin and operator-managed ConfigMaps:

- Operator upgrade from versions without agent catalog to versions with
  agent plugin (ConfigMap creation, volume mount addition, catalog path)
- Database schema compatibility for new MLMD context types alongside
  existing model/MCP contexts
- Backwards compatibility of the unified /sources endpoint (existing
  model/MCP queries must continue working)
- Rollback scenarios if agent plugin initialization fails

### 7.3 Performance/Scalability

Pagination and filtering imply large-scale catalog scenarios:

- API response time for listing agents with 100+ entries
- Search and filterQuery performance with complex operators over large
  datasets
- Pagination behavior (nextPageToken generation, consistent ordering)
- Concurrent API requests from multiple users

### 7.4 RBAC/Authorization

TBD — The strategy does not specify RBAC requirements for agent catalog
endpoints. If following existing catalog patterns (model/MCP), agent
endpoints should enforce the same permission model. Clarification needed
via ADR or security specification.

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
| ------ | -------- | ------------- | ------------ |
| GitHub API unavailability during metadata extraction | High | Medium | Pre-bundle default catalog in operator, support offline YAML loading |
| Integration with existing plugins breaks shared infrastructure | Medium | Medium | Regression test model and MCP plugins after agent deployment |
| Operator upgrade adds new ConfigMap/volumes to existing deployments | High | Low | Test upgrade scenarios, verify ConfigMap creation idempotency |
| filterQuery complexity produces incorrect results | Medium | Medium | Comprehensive test matrix for operator combinations |
| Metadata quality varies across GitHub repository structures | Medium | Medium | Schema validation for extracted YAML, default values for optional fields |
| Database schema evolution causes migration failures | High | Low | Test MLMD schema migration, verify context type registration |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- OpenShift cluster with RHOAI operator deployed
- Model registry operator deployed
- PostgreSQL database instance (shared MLMD schema)
- GitHub access for metadata pipeline testing (or offline mode)

### 9.2 Configuration

- `default-catalog-sources` ConfigMap (operator-managed, includes
  agent_catalogs section with Red Hat starter kits)
- `model-catalog-sources` ConfigMap (user-editable, for custom agent
  sources)
- `catalog-agent-configmap.yaml.tmpl` (operator template)
- `--catalogs-path` argument for agent sources file
- Shared-data volume with agents-catalog.yaml from init container

### 9.3 Test Tools

- `oc` CLI for ConfigMap creation, patching, and verification
- `curl` or `httpie` for API endpoint testing
- `psql` for PostgreSQL database verification
- `pytest` with `opendatahub-tests` framework for automated test execution
- `jq` for parsing API responses

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
| ---------- | ------- | ---- | ---- | ----- |
| TC-API | 6 | 5 | 1 | 0 |
| TC-FILTER | 9 | 0 | 8 | 1 |
| TC-SEARCH | 4 | 0 | 4 | 0 |
| TC-PAGE | 4 | 0 | 2 | 2 |
| TC-SRC | 4 | 0 | 3 | 1 |
| TC-SCHEMA | 3 | 0 | 3 | 0 |
| TC-ARTIFACT | 4 | 0 | 4 | 0 |
| TC-OPS | 1 | 0 | 1 | 0 |
| TC-NEG | 5 | 1 | 2 | 2 |
| TC-E2E | 4 | 4 | 0 | 0 |
| TC-UPGRADE | 3 | 2 | 1 | 0 |
| **Total** | **47** | **12** | **29** | **6** |

### 10.2 Endpoint Coverage

| Endpoint | Test Cases | Coverage |
| ---------- | ------------ | ---------- |
| GET /api/agent_catalog/v1alpha1/agents | TC-API-001, TC-FILTER-001–009, TC-SEARCH-001–004, TC-PAGE-001–004, TC-E2E-001–003 | |
| GET /api/agent_catalog/v1alpha1/agents/{agent_id} | TC-API-002, TC-SCHEMA-001–003, TC-NEG-001, TC-E2E-001 | |
| GET /api/agent_catalog/v1alpha1/agents/filter_options | TC-API-003, TC-E2E-003 | |
| GET /api/agent_catalog/v1alpha1/agents/{id}/artifacts | TC-ARTIFACT-001–004, TC-NEG-002, TC-E2E-001 | |
| GET /api/model_catalog/v1alpha1/sources?assetType=agents | TC-API-006, TC-SRC-001–004, TC-E2E-002, TC-E2E-004, TC-UPGRADE-003 | |
| GET /readyz | TC-API-004, TC-OPS-003–004, TC-E2E-001–002, TC-E2E-004, TC-UPGRADE-001 | |
| GET /healthz | TC-API-005, TC-OPS-004, TC-E2E-001, TC-E2E-004 | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-07-07 | Initial test plan |
| 1.1.0 | 2026-07-07 | Generated 47 test cases across 11 categories |

---

**End of Test Plan**
