---
test_case_id: TC-NEG-002
source_key: RHAIENG-7604
objectives: [7]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-09-25"
upgrade_phase: both
---

# TC-NEG-002: Missing owner principal without a fallback fails clearly

**Objective**: Verify that migration fails with a clear owner-subject error when a source
row lacks `owner_principal` and no fallback owner subject is provided.

**Preconditions**:

- A cluster-admin test identity can invoke the migration CLI or Job and collect its output.
- The supported CLI executable, command or subcommand, fixture schema, completion signal, and
  exact error-output location have been confirmed for the test environment.
- The source fixture contains a row with a present `tenant_id` and an absent
  `owner_principal`, so owner-subject handling is the missing-value condition under test.
- No `--fallback-owner-subject` value is supplied. The target datastore is isolated from prior
  runs.
- The same fixture and assertions are executed against the selected pre-upgrade and
  post-upgrade deployments; exact versions remain an open plan gap.

**Test Steps**:

1. Create the missing-owner-principal source row using the supported fixture mechanism.
2. Run the supported OGX DB migration CLI command or Job without
   `--fallback-owner-subject`.
3. Wait for the command or Job to finish, and collect both its completion status and migration
   output from the supported location.
4. Inspect the target datastore for a target row corresponding to the failed fixture, if the
   supported inspection method exposes partial results.

**Expected Results**:

- The command returns a failure status or the migration Job reaches its documented failed
  state.
- The displayed error identifies the missing `owner_principal` and indicates that no fallback
  owner subject was provided.
- The migration is not reported as a successful completion for the fixture.

**Test Data**:

```yaml
fixture_label: missing-owner-no-fallback
tenant_id: tenant-analytics-02
owner_principal: absent
fallback_owner_subject: not-provided
```

Map these logical fields to the supported source-fixture schema once the fixture contract is
confirmed. Validate the error against the supported observable error contract once it is
defined; do not require an unconfirmed literal message.

**Notes**: To be filled later in the process.
