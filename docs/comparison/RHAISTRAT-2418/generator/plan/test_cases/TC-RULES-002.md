---
test_case_id: TC-RULES-002
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-RULES-002: Verify deny ratio recording rule computation

**Objective**: Confirm that `maas:auth_deny_ratio:rate5m` correctly
computes the ratio of denied auth decisions to total decisions.

**Preconditions**:

- PrometheusRule with `maas.authorino.auth-decisions` rule group
  applied
- Ability to generate both allowed and denied auth requests

**Test Steps**:

1. Generate mixed auth traffic for 6 minutes: approximately
   75% allowed (OK) and 25% denied (UNAUTHENTICATED) requests.
   Use valid credentials for allowed requests and invalid/missing
   credentials for denied requests.
2. Wait for the 5-minute rate window to stabilize (at least 6
   minutes of traffic).
3. Query the deny ratio:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     maas:auth_deny_ratio:rate5m" | jq '.data.result[]'
   ```

4. Verify the ratio is approximately 0.25 (25% denied).

**Expected Results**:

- `maas:auth_deny_ratio:rate5m` returns non-empty results
- Each result has labels `{authconfig, namespace}`
- The ratio value is approximately 0.25 (within 0.05 tolerance)
- The zero fallback (`or 0 * group by ...`) produces a 0 value
  for authconfigs with only OK traffic

**Notes**: To be filled later in the process.
