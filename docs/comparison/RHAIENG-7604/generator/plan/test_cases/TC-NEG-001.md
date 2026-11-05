---
test_case_id: TC-NEG-001
source_key: RHAIENG-7604
objectives: [3]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-09-25"
upgrade_phase: both
---

# TC-NEG-001: Missing tenant without a fallback fails clearly

**Objective**: Verify that migration fails with a clear tenant-related error when a source
row lacks `tenant_id` and no fallback tenant is provided.

**Preconditions**:

- A cluster-admin test identity can invoke the migration CLI or Job and collect its output.
- The supported CLI executable, command or subcommand, fixture schema, completion signal, and
  exact error-output location have been confirmed for the test environment.
- The source fixture contains a row with an absent `tenant_id` and a present
  `owner_principal`, so tenant handling is the first missing-value condition under test.
- No `--fallback-tenant` value is supplied. The target datastore is isolated from prior runs.
- The same fixture and assertions are executed against the selected pre-upgrade and
  post-upgrade deployments; exact versions remain an open plan gap.

**Test Steps**:

1. Create the missing-tenant source row using the supported fixture mechanism.
2. Run the supported OGX DB migration CLI command or Job without `--fallback-tenant`.
3. Wait for the command or Job to finish, and collect both its completion status and migration
   output from the supported location.
4. Inspect the target datastore for a target row corresponding to the failed fixture, if the
   supported inspection method exposes partial results.

**Expected Results**:

- The command returns a failure status or the migration Job reaches its documented failed
  state.
- The displayed error identifies the missing `tenant_id` and indicates that no fallback tenant
  was provided.
- The migration is not reported as a successful completion for the fixture.

**Test Data**:

```yaml
fixture_label: missing-tenant-no-fallback
tenant_id: absent
owner_principal: principal-batch-02
fallback_tenant: not-provided
```

Map these logical fields to the supported source-fixture schema once the fixture contract is
confirmed. Validate the error against the supported observable error contract once it is
defined; do not require an unconfirmed literal message.

**Notes**: To be filled later in the process.
