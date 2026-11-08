# update_db_migration_cli_for_praxis_state_ownership_schema_changes

Test plan for the OGX database migration CLI changes in RHAIENG-7604. The plan verifies
mapping from OGX source rows to the Praxis state-ownership schema, CLI fallback values,
fixed ownership issuer assignment, and required missing-value errors.

- Strategy: [RHAIENG-7604](https://redhat.atlassian.net/browse/RHAIENG-7604)
- Version: 1.1.0
- Last modified: 2026-09-25
- Test plan: [TestPlan.md](TestPlan.md)
- Additional documents: None supplied
- Automated tests: [opendatahub-tests](https://github.com/opendatahub-io/opendatahub-tests);
  destination to be finalized during test-case implementation

## Test Cases

[Test case index](test_cases/INDEX.md) — 4 total: 2 P0, 2 P1, and 0 P2.

## Changelog

### v1.1.0

- Added the cluster-admin test identity, permissions, resources, and namespace scope.
