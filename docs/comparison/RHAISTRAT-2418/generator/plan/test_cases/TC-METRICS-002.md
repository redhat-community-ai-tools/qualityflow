---
test_case_id: TC-METRICS-002
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-METRICS-002: Verify auth decision latency histogram metric

**Objective**: Confirm that `auth_server_authconfig_duration_seconds`
histogram is exposed on `/server-metrics` with labels `{authconfig,
namespace}` and standard histogram buckets.

**Preconditions**:

- Auth traffic previously generated (TC-METRICS-001 preconditions met)

**Test Steps**:

1. Query the `/server-metrics` endpoint:

   ```bash
   kubectl exec -n <authorino-namespace> <authorino-pod> -- \
     curl -s http://localhost:8080/server-metrics | \
     grep auth_server_authconfig_duration_seconds
   ```

2. Verify `_bucket`, `_count`, and `_sum` suffixes are present
   (standard histogram exposition).
3. Verify labels `authconfig` and `namespace` are present on each
   line.
4. Confirm bucket boundaries (`le` label) include standard values.

**Expected Results**:

- `auth_server_authconfig_duration_seconds_bucket` lines present
  with `le` boundaries
- `auth_server_authconfig_duration_seconds_count` present with
  non-zero value
- `auth_server_authconfig_duration_seconds_sum` present with
  non-zero value
- Labels include `authconfig="<sha256-hash>"` and
  `namespace="<authorino-namespace>"`

**Notes**: To be filled later in the process.
