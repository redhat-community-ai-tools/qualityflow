---
test_case_id: TC-RULES-003
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-RULES-003: Verify P95 auth latency recording rule

**Objective**: Confirm that `maas:auth_latency_p95:5m` produces
valid 95th percentile auth decision latency values per authconfig.

**Preconditions**:

- PrometheusRule with `maas.authorino.auth-decisions` rule group
  applied
- Auth traffic generated for at least 5 minutes

**Test Steps**:

1. Generate sustained auth traffic for 6 minutes (reuse traffic
   from TC-RULES-001 if already running).
2. Query the P95 latency recording rule:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     maas:auth_latency_p95:5m" | jq '.data.result[]'
   ```

3. Verify results contain labels `{authconfig, namespace}`.
4. Verify the P95 value is a positive number in seconds (typical
   auth decision latency is sub-second).

**Expected Results**:

- `maas:auth_latency_p95:5m` returns non-empty results
- Each result has labels `{authconfig, namespace}`
- Latency values are positive numbers (expected range: 0.001 to
  1.0 seconds for typical auth decisions)
- Values are computed from
  `auth_server_authconfig_duration_seconds_bucket` histogram

**Notes**: To be filled later in the process.
