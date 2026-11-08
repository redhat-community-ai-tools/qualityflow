---
test_case_id: TC-POLICY-002
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-POLICY-002: MaaSAuthPolicy updated — Kuadrant AuthPolicy updated

**Objective**: Verify that updating a MaaSAuthPolicy causes
the corresponding Kuadrant AuthPolicy to be updated
accordingly.

**Preconditions**:

- MaaSAuthPolicy for `tenant-a` exists and Kuadrant AuthPolicy has been generated (see TC-POLICY-001)

**Test Steps**:

1. Patch the MaaSAuthPolicy in `tenant-a` to change an auth rule (e.g., add a new audience or claim)
2. Wait for controller reconciliation
3. Inspect the Kuadrant AuthPolicy for `tenant-a` and verify the change is reflected

**Expected Results**:

- Kuadrant AuthPolicy for `tenant-a` reflects the updated MaaSAuthPolicy configuration
- No stale or duplicate AuthPolicy resources exist for `tenant-a`
- MaaSAuthPolicy status condition remains `Ready` after update

**Notes**: To be filled later in the process.
