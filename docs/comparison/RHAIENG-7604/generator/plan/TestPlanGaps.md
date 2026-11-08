---
feature: update_db_migration_cli_for_praxis_state_ownership_schema_changes
source_key: RHAIENG-7604
status: Open
gap_count: 15
last_updated: '2026-09-25'
---
# Gaps — update_db_migration_cli_for_praxis_state_ownership_schema_changes

## Resolved Gaps

### Environment & Infrastructure

- Required test identity, concrete resources, RBAC role, and permissions for running or
  observing the migration Job and inspecting data are resolved by the user clarification:
  a cluster-admin identity with full OGX, Praxis, and associated-object access across all
  namespaces, including create/get/list/watch/update/patch/delete permissions.

## Unresolved Gaps

### Scope & Endpoints

- The strategy references an ADR for full context, but no ADR was provided.
- The CLI executable name, command/subcommand, and complete invocation syntax are unspecified.
- The source and target datastore interfaces and target-row verification method are unspecified.
- Exact error text and failure signaling are unspecified.

### Test Strategy & Risks

- The strategy references an ADR for full context, but no ADR was supplied.
- Treatment of explicitly empty source values is not stated consistently for fallback selection.
- The observable error contract is not defined.

### Unresolved Environment & Infrastructure

- The linked ADR, including deployment decisions and architectural context, was not supplied.
- Required OpenShift, RHOAI, OGX operator, and dependent-service versions, cluster topology,
  and resource requirements are unspecified.
- The database engine, source and target schema/table details, and supported method for
  querying migrated Praxis rows are unspecified.
- Migration Job trigger, CLI wiring, completion signal, exit behavior, and error
  location/format are unspecified.
- Configuration source, precedence, and wiring for fallback values are unspecified.
- The exact meaning of “not present,” “missing,” and “empty” remains unspecified,
  including null, empty, and whitespace handling.
- Supported QE tools and procedures for invocation, log collection, datastore querying,
  and fixture cleanup are unspecified.
- Exact fixture schema, minimum source-row set, and test-data isolation or cleanup
  requirements are unspecified.

## New Gaps Identified

No new gaps identified.

## Advisory Actionability Gaps

- OpenShift version
- RHOAI version
- unresolved TBD visibility
- test-data formats and examples

## Test Case Coverage Gaps

- All seven Section 1.3 objectives and the OGX DB migration CLI interface are covered by the
  generated test cases. No new objective or interface coverage gap was identified.
- Explicitly empty or whitespace-only `tenant_id` and `owner_principal` values are not covered
  because the expected fallback behavior remains unspecified. Add boundary cases after the
  missing-value semantics are clarified.
- The generated cases remain execution-dependent on the existing unresolved details for CLI
  invocation, datastore inspection, fixture schema and cleanup, and the observable error
  contract. These are carried forward prerequisites, not new coverage gaps.
