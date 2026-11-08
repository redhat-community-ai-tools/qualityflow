---
test_case_id: TC-RULES-001
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-RULES-001: Verify auth decision rate recording rule

**Objective**: Confirm that `maas:auth_decisions:rate5m` computes
per-authconfig, per-status 5-minute rates correctly from raw
`auth_server_authconfig_response_status` counters.

**Preconditions**:

- PrometheusRule with `maas.authorino.auth-decisions` rule group
  applied
- Auth traffic generated for at least 5 minutes to populate the
  rate window

**Test Steps**:

1. Generate sustained auth traffic (60 requests/minute for 6
   minutes) using grpcurl:

   ```bash
   for i in $(seq 1 360); do
     grpcurl -plaintext -d '{"attributes": {"request": {"http": \
       {"method": "GET", "path": "/test"}}}}' \
       <authorino-service>:50051 \
       envoy.service.auth.v3.Authorization/Check
     sleep 1
   done
   ```

2. Query the recording rule output:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     maas:auth_decisions:rate5m" | jq '.data.result[]'
   ```

3. Verify the result contains labels `authconfig`, `namespace`,
   and `status`.
4. Verify the rate value is approximately 1.0 requests/second
   (60 requests per minute).

**Expected Results**:

- `maas:auth_decisions:rate5m` returns non-empty results
- Each result has labels `{authconfig, namespace, status}`
- Rate values are positive and approximately match the generated
  traffic rate (within 20% tolerance)
- Results are filtered to namespaces matching
  `rh-connectivity-link|kuadrant-system`

**Notes**: To be filled later in the process.
