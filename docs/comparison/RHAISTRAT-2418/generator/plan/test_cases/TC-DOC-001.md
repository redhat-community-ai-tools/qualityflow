---
test_case_id: TC-DOC-001
source_key: RHAISTRAT-2418
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DOC-001: Verify metrics catalog documentation completeness

**Objective**: Confirm that auth decision metrics are documented
in the RHOAI metrics catalog with all required fields.

**Test Steps**:

1. Locate the metrics documentation in
   `docs/content/observability/metrics-and-dashboards.md` (or the
   RHOAI metrics catalog location if different).
2. Verify documentation exists for each metric:
   - `auth_server_authconfig_response_status`
   - `auth_server_authconfig_duration_seconds`
   - `auth_server_evaluator_total`
   - `auth_server_evaluator_duration_seconds`
   - `maas:auth_decisions:rate5m`
   - `maas:auth_deny_ratio:rate5m`
   - `maas:auth_latency_p95:5m`
   - `MaaSHighAuthDenyRate` alert
3. For each metric, verify these fields are present:
   - Metric name
   - Metric type (counter, histogram, recording rule, alert)
   - Label schema with all label names and value domains
   - Source component (Authorino)
   - Scrape endpoint (`/server-metrics`)
   - Scrape interval (30s)
4. Verify at least two operator questions with example PromQL
   queries are provided.

**Expected Results**:

- All 8 metrics/rules/alerts are documented
- Each entry includes metric name, type, label schema, source
  component, scrape endpoint, and scrape interval
- At least 2 example PromQL queries are provided with
  descriptions of what operator questions they answer
- Documentation mentions the `authconfig` SHA-256 hash mapping
  and how to correlate hashes to policy names

**Notes**: To be filled later in the process.
