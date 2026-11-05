---
test_case_id: TC-EDGE-004
source_key: RHAISTRAT-2418
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-EDGE-004: Verify multi-replica metric aggregation

**Objective**: Confirm that recording rules correctly aggregate
auth decision metrics across multiple Authorino replicas using
`sum by()` grouping.

**Preconditions**:

- Authorino deployment scaled to at least 2 replicas
- Auth traffic distributed across replicas

**Test Steps**:

1. Scale Authorino to 2 replicas and wait for rollout:

   ```bash
   kubectl scale deployment/authorino \
     -n <authorino-namespace> --replicas=2
   kubectl rollout status deployment/authorino \
     -n <authorino-namespace> --timeout=120s
   ```

2. Identify the ServiceMonitor job label and wait for
   Prometheus to scrape both targets. The job name comes
   from the ServiceMonitor `authorino-server-metrics`:

   ```bash
   SM_JOB="authorino-server-metrics"
   NS="<authorino-namespace>"  # kuadrant-system or rh-connectivity-link
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     up{job=\"${SM_JOB}\",namespace=\"${NS}\"}" | \
     jq '[.data.result[] | select(.value[1] == "1")] | length'
   ```

   Retry until output is `2` (may take up to 2 scrape
   intervals, ~60s at 30s interval).

3. Generate auth traffic for 6 minutes (traffic should be
   load-balanced across replicas).

4. Query per-replica rates scoped to the ServiceMonitor job
   and namespace to confirm both replicas received traffic:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum by (instance) (rate(\
     auth_server_authconfig_response_status{\
     job=\"${SM_JOB}\",namespace=\"${NS}\"}\
     [5m]))" | jq '.data.result[]'
   ```

   Verify at least 2 distinct `instance` values appear with
   non-zero rates.

5. Compute the sum of per-replica rates, scoped to the same
   job and namespace:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum(rate(auth_server_authconfig_response_status{\
     job=\"${SM_JOB}\",namespace=\"${NS}\"}\
     [5m]))" | jq '.data.result[0].value[1]'
   ```

6. Query the recording rule output:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     sum(maas:auth_decisions:rate5m)" | \
     jq '.data.result[0].value[1]'
   ```

7. Compare the values from steps 5 and 6 — they should match
   within 5% tolerance (minor differences from scrape timing
   are expected).

8. Verify the recording rule output label set contains only
   `authconfig`, `namespace`, and `status` (no `instance`,
   `pod`, or `job` labels leaked through):

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     maas:auth_decisions:rate5m" | \
     jq -e '(.data.result | length) > 0 and
       (.data.result | all(
         .metric | keys == ["__name__",
         "authconfig", "namespace", "status"]
       ))'
   ```

   The query must return `true`. It verifies at least one
   result exists AND every series has exactly the four
   expected label keys — no `instance`, `pod`, or `job`
   leaked from any replica.

**Expected Results**:

- Both replicas are scraped (`up` count = 2) before traffic
  generation begins
- Per-replica rates show at least 2 distinct `instance` values
  with non-zero rates
- Sum of per-replica raw rates matches
  `sum(maas:auth_decisions:rate5m)` within 5% tolerance
- Recording rule output labels are exactly `["__name__",
  "authconfig", "namespace", "status"]` — no `instance`,
  `pod`, or `job` labels present

**Notes**: To be filled later in the process.
