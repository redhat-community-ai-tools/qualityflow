---
test_case_id: TC-POLICY-001
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-POLICY-001: MaaSAuthPolicy created — Kuadrant AuthPolicy generated on shared Gateway

**Objective**: Verify that creating a MaaSAuthPolicy in a
tenant namespace causes the maas-controller to generate a
corresponding Kuadrant AuthPolicy attached to the shared
Gateway.

**Preconditions**:

- Tenant namespace `tenant-a` exists with label `maas.opendatahub.io/tenant=tenant-a`
- Kuadrant operator is deployed
- Shared Gateway exists

**Test Steps**:

1. Apply a MaaSAuthPolicy CR in namespace `tenant-a`
2. Wait for controller reconciliation
3. Run `kubectl get authpolicy -A` and look for a policy referencing `tenant-a`
4. Inspect the generated AuthPolicy to verify it is attached to the shared Gateway

**Expected Results**:

- A Kuadrant AuthPolicy named after or referencing `tenant-a` exists in the cluster
- The AuthPolicy spec references the shared Gateway (not a per-tenant Gateway)
- MaaSAuthPolicy status condition reflects successful propagation

**Notes**: To be filled later in the process.
