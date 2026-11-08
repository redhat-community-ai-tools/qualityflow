# Agent Catalog — Test Case Index

**Parent Test Plan**: [TestPlan.md](../TestPlan.md)
**Source**: [RHOAIENG-70680](https://redhat.atlassian.net/browse/RHOAIENG-70680)

---

## Quick Stats

| Metric | Count |
| -------- | ------- |
| Total Test Cases | 47 |
| P0 (Critical) | 12 |
| P1 (High) | 29 |
| P2 (Medium) | 6 |

---

## API Endpoint Functionality (TC-API)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-API-001](TC-API-001.md) | List all agents returns populated response | P0 |
| [TC-API-002](TC-API-002.md) | Get agent by ID returns correct agent details | P0 |
| [TC-API-003](TC-API-003.md) | Get filter options returns available filter fields and values | P1 |
| [TC-API-004](TC-API-004.md) | Agent plugin readiness check reports healthy | P0 |
| [TC-API-005](TC-API-005.md) | Catalog service health check reports healthy | P0 |
| [TC-API-006](TC-API-006.md) | List agent sources returns agent catalog sources | P0 |

## Filter Query and Parameter Filtering (TC-FILTER)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-FILTER-001](TC-FILTER-001.md) | filterQuery with equals operator filters by framework | P1 |
| [TC-FILTER-002](TC-FILTER-002.md) | filterQuery with not-equals operator excludes framework | P1 |
| [TC-FILTER-003](TC-FILTER-003.md) | filterQuery with LIKE operator performs partial matching | P1 |
| [TC-FILTER-004](TC-FILTER-004.md) | filterQuery with ILIKE operator performs case-insensitive matching | P1 |
| [TC-FILTER-005](TC-FILTER-005.md) | filterQuery with IN operator matches multiple values | P1 |
| [TC-FILTER-006](TC-FILTER-006.md) | filterQuery with AND combines multiple conditions | P1 |
| [TC-FILTER-007](TC-FILTER-007.md) | filterQuery with OR matches either condition | P1 |
| [TC-FILTER-008](TC-FILTER-008.md) | sourceLabel parameter filters agents by source | P1 |
| [TC-FILTER-009](TC-FILTER-009.md) | filterQuery with nested AND/OR combinations | P2 |

## Keyword Search and Name Matching (TC-SEARCH)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-SEARCH-001](TC-SEARCH-001.md) | Keyword search with q parameter matches across fields | P1 |
| [TC-SEARCH-002](TC-SEARCH-002.md) | Name filter with LIKE matching | P1 |
| [TC-SEARCH-003](TC-SEARCH-003.md) | Keyword search with no matches returns empty results | P1 |
| [TC-SEARCH-004](TC-SEARCH-004.md) | Combined search and filter narrows results | P1 |

## Pagination and Ordering (TC-PAGE)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-PAGE-001](TC-PAGE-001.md) | Pagination with pageSize limits results per page | P1 |
| [TC-PAGE-002](TC-PAGE-002.md) | Order by NAME ascending sorts agents alphabetically | P2 |
| [TC-PAGE-003](TC-PAGE-003.md) | Order by CREATE_TIME descending sorts newest first | P2 |
| [TC-PAGE-004](TC-PAGE-004.md) | Pagination with filter maintains consistent ordering | P1 |

## Source Management (TC-SRC)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-SRC-001](TC-SRC-001.md) | sourceLabel resolves to correct sourceID for filtering | P1 |
| [TC-SRC-002](TC-SRC-002.md) | Custom agent source added via ConfigMap patch loads agents | P1 |
| [TC-SRC-003](TC-SRC-003.md) | Disabled agent source excludes agents from listing | P2 |
| [TC-SRC-004](TC-SRC-004.md) | Unified sources endpoint returns all asset types | P1 |

## Agent Schema Validation (TC-SCHEMA)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-SCHEMA-001](TC-SCHEMA-001.md) | Agent with complete metadata returns all fields | P1 |
| [TC-SCHEMA-002](TC-SCHEMA-002.md) | Agent with minimal metadata uses defaults for optional fields | P1 |
| [TC-SCHEMA-003](TC-SCHEMA-003.md) | Custom properties forwarded from upstream YAML | P1 |

## Artifacts Endpoint (TC-ARTIFACT)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-ARTIFACT-001](TC-ARTIFACT-001.md) | List all artifacts for an agent | P1 |
| [TC-ARTIFACT-002](TC-ARTIFACT-002.md) | Filter artifacts by type image-artifact | P1 |
| [TC-ARTIFACT-003](TC-ARTIFACT-003.md) | Filter artifacts by type template-artifact | P1 |
| [TC-ARTIFACT-004](TC-ARTIFACT-004.md) | Artifacts endpoint pagination | P1 |

## Operator Integration (TC-OPS)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-OPS-004](TC-OPS-004.md) | Existing model and MCP plugins remain functional after agent deployment | P1 |

> TC-OPS-001, 002, 003 removed — covered by [TC-E2E-004](TC-E2E-004.md).

## Negative and Error Handling (TC-NEG)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-NEG-001](TC-NEG-001.md) | Get nonexistent agent ID returns 404 | P0 |
| [TC-NEG-002](TC-NEG-002.md) | Artifacts for nonexistent agent returns 404 | P1 |
| [TC-NEG-003](TC-NEG-003.md) | Invalid filterQuery syntax returns error | P1 |
| [TC-NEG-004](TC-NEG-004.md) | Invalid nextPageToken returns error or empty results | P2 |
| [TC-NEG-005](TC-NEG-005.md) | Invalid sourceLabel returns empty results | P2 |

## End-to-End Scenarios (TC-E2E)

| Test Case ID | Title | Priority |
| ------------- | ------- | ---------- |
| [TC-E2E-001](TC-E2E-001.md) | Browse and inspect agent from default catalog | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Add custom agent source and browse combined catalog | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Filter, search, and paginate through agent catalog | P0 |
| [TC-E2E-004](TC-E2E-004.md) | Operator deployment wires agent catalog end-to-end | P0 |

## Upgrade Testing (TC-UPGRADE)

| Test Case ID | Title | Priority | Phase |
| ------------- | ------- | ---------- | ------- |
| [TC-UPGRADE-001](TC-UPGRADE-001.md) | Operator upgrade creates agent ConfigMap and volume mounts | P0 | post |
| [TC-UPGRADE-002](TC-UPGRADE-002.md) | Database schema compatibility after upgrade | P0 | both |
| [TC-UPGRADE-003](TC-UPGRADE-003.md) | Unified sources endpoint backwards compatibility | P1 | both |
