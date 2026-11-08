---
test_case_id: TC-RULES-004
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-RULES-004: Verify promtool unit tests pass

**Objective**: Confirm that all 9 promtool unit tests for recording
rules and alert definitions pass successfully.

**Test Steps**:

1. Clone or access the models-as-a-service repository (branch
   with PR #1363 merged).
2. Run promtool unit tests:

   ```bash
   cd deployment/base/observability
   promtool test rules maas-auth-alerting.unit-tests.yaml
   ```

3. Verify all test cases pass.

**Expected Results**:

- `promtool test rules` exits with code 0
- Output shows 9 test cases evaluated
- All tests report `SUCCESS` — no failures or errors
- Tests cover: auth decision rate, deny ratio (25% denied and
  0% denied), P95 latency, alert firing (>10%), alert suppression
  (<=10%), alert timing (before 10m), negligible traffic guard,
  and namespace filtering

**Test Data**:

```bash
# Unit test file location
deployment/base/observability/maas-auth-alerting.unit-tests.yaml

# Rules file location
deployment/base/observability/maas-auth-alerting.rules.yaml
```

**Notes**: To be filled later in the process.
