---
test_case_id: TC-ALERT-001
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-ALERT-001: Verify alert fires on high deny rate

**Objective**: Confirm that `MaaSHighAuthDenyRate` alert fires when
the deny ratio exceeds 10% and is sustained for 10 minutes.

**Preconditions**:

- PrometheusRule with `MaaSHighAuthDenyRate` alert applied
- Ability to generate denied auth requests (invalid credentials)
- Identify a unique AuthConfig for this test: record its
  `authconfig` hash and `namespace` (e.g., via
  `kubectl get authconfig -n <ns> -o name`)

**Test Steps**:

1. Record the target AuthConfig hash (`$AC_HASH`) and namespace
   (`$NS`) to use as filters throughout the test.
2. Confirm the alert is NOT currently firing for this AuthConfig:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '[.data.alerts[] | select(
       .labels.alertname == "MaaSHighAuthDenyRate" and
       .labels.authconfig == "'"$AC_HASH"'" and
       .labels.namespace == "'"$NS"'"
     )] | length'
   ```

   Expected output: `0`

3. Generate auth traffic targeting only that AuthConfig with
   approximately 20% deny rate: 80% valid requests (OK) and
   20% invalid requests (UNAUTHENTICATED). Sustain for at
   least 15 minutes.

   ```bash
   cleanup() { kill "$PID_OK" "$PID_DENY" 2>/dev/null; }
   trap cleanup EXIT INT TERM

   # Valid requests (run in background loop)
   while true; do
     grpcurl -plaintext -d '{"attributes":{"request":{"http":\
       {"method":"GET","path":"/valid"}}}}' \
       <authorino-service>:50051 \
       envoy.service.auth.v3.Authorization/Check
     sleep 0.5
   done &
   PID_OK=$!

   # Invalid requests at ~20% rate (run in background loop)
   while true; do
     grpcurl -plaintext -d '{"attributes":{"request":{"http":\
       {"method":"GET","path":"/invalid",\
       "headers":{"authorization":"Bearer EXPIRED"}}}}}' \
       <authorino-service>:50051 \
       envoy.service.auth.v3.Authorization/Check
     sleep 2
   done &
   PID_DENY=$!
   ```

4. At T+5m (before the 10-minute `for:` window), query the
   alerts API filtered by the exact AuthConfig and namespace:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '[.data.alerts[] | select(
       .labels.alertname == "MaaSHighAuthDenyRate" and
       .labels.authconfig == "'"$AC_HASH"'" and
       .labels.namespace == "'"$NS"'"
     )]'
   ```

   Verify the alert is either absent or in `pending` state
   (not `firing`).

5. At T+15m (after the 10-minute sustain period), query again
   with the same filter:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/alerts" | \
     jq '[.data.alerts[] | select(
       .labels.alertname == "MaaSHighAuthDenyRate" and
       .labels.authconfig == "'"$AC_HASH"'" and
       .labels.namespace == "'"$NS"'"
     )]'
   ```

6. Verify exactly one matching alert is returned.
7. Verify the alert state is `firing`.
8. Verify the alert labels include `severity: warning`.
9. Verify the alert annotation `summary` equals
   "High auth denial rate for an Authorino AuthConfig".
10. Verify the alert annotation `description` contains both
    `$AC_HASH` and `$NS`.
11. Stop the background traffic generators (also runs
    automatically via the trap if the test exits early):

    ```bash
    cleanup
    ```

**Expected Results**:

- At T+5m: no `firing` alert for `$AC_HASH` / `$NS`
  (absent or `pending` only)
- At T+15m: exactly 1 alert matches the filter
- Alert state is `firing`
- Alert labels: `severity: warning`,
  `authconfig: $AC_HASH`, `namespace: $NS`
- Alert annotation `summary` is "High auth denial rate
  for an Authorino AuthConfig"
- Alert annotation `description` contains both `$AC_HASH`
  and `$NS`

**Notes**: To be filled later in the process.
