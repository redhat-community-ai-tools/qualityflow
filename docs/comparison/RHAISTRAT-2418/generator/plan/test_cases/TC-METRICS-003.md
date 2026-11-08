---
test_case_id: TC-METRICS-003
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-METRICS-003: Verify evaluator invocation metrics

**Objective**: Confirm that `auth_server_evaluator_total` counter and
`auth_server_evaluator_duration_seconds` histogram are exposed with
labels `{evaluator_name, evaluator_type}`.

**Preconditions**:

- Auth traffic previously generated (TC-METRICS-001 preconditions met)

**Test Steps**:

1. Query the `/server-metrics` endpoint:

   ```bash
   kubectl exec -n <authorino-namespace> <authorino-pod> -- \
     curl -s http://localhost:8080/server-metrics | \
     grep -E 'auth_server_evaluator_(total|duration_seconds)'
   ```

2. Verify `auth_server_evaluator_total` has labels
   `evaluator_name` and `evaluator_type`.
3. Verify `auth_server_evaluator_duration_seconds` has histogram
   suffixes (`_bucket`, `_count`, `_sum`) with the same label
   schema.

**Expected Results**:

- `auth_server_evaluator_total` lines present with
  `evaluator_name` and `evaluator_type` labels
- `auth_server_evaluator_duration_seconds_bucket` lines present
  with histogram boundaries
- Counter and histogram values are non-zero after auth traffic

**Notes**: To be filled later in the process.
