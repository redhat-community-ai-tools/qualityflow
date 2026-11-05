# OGX Praxis State Ownership Migration — Test Case Index

**Parent Test Plan**: [TestPlan.md](../TestPlan.md)
**Source**: [RHAIENG-7604](https://redhat.atlassian.net/browse/RHAIENG-7604)

## Quick Stats

| Metric | Count |
|--------|-------|
| Total Test Cases | 4 |
| P0 (Critical) | 2 |
| P1 (High) | 2 |
| P2 (Medium) | 0 |

## Negative and Error Handling (TC-NEG)

| Test Case ID | Title | Priority |
|--------------|-------|----------|
| [TC-NEG-001](TC-NEG-001.md) | Missing tenant without a fallback fails clearly | P0 |
| [TC-NEG-002](TC-NEG-002.md) | Missing owner principal without a fallback fails clearly | P0 |

## End-to-End Scenarios (TC-E2E)

| Test Case ID | Title | Priority |
|--------------|-------|----------|
| [TC-E2E-001](TC-E2E-001.md) | Direct source mappings and fixed ownership issuer | P1 |
| [TC-E2E-002](TC-E2E-002.md) | CLI fallbacks for absent source ownership fields | P1 |

## Upgrade Testing

All four cases are tagged `upgrade_phase: both` and are run against the selected pre-upgrade
and post-upgrade deployments. No separate `TC-UPG-*` case is added because the migration
assertions are already covered without duplicating their verification targets.

| Test Case ID | Title | Priority | Phase |
|--------------|-------|----------|-------|
| [TC-E2E-001](TC-E2E-001.md) | Direct source mappings and fixed ownership issuer | P1 | both |
| [TC-E2E-002](TC-E2E-002.md) | CLI fallbacks for absent source ownership fields | P1 | both |
| [TC-NEG-001](TC-NEG-001.md) | Missing tenant without a fallback fails clearly | P0 | both |
| [TC-NEG-002](TC-NEG-002.md) | Missing owner principal without a fallback fails clearly | P0 | both |
