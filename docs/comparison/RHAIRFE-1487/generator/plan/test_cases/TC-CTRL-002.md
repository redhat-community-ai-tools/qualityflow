---
test_case_id: TC-CTRL-002
source_key: RHAIRFE-1487
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CTRL-002: maas-controller ignores namespace without tenant label

**Objective**: Verify that the maas-controller does not
reconcile MaaSSubscription or MaaSAuthPolicy resources in a
namespace that lacks the `maas.opendatahub.io/tenant` label.

**Preconditions**:

- maas-controller is running
- An unlabeled namespace `no-label-ns` exists

**Test Steps**:

1. Confirm `no-label-ns` has no `maas.opendatahub.io/tenant` label
2. Directly apply a MaaSSubscription in `no-label-ns` (bypassing webhook if needed for this test)
3. Wait 60 seconds
4. Check controller logs for any reconciliation event referencing `no-label-ns`
5. Check MaaSSubscription status in `no-label-ns`

**Expected Results**:

- Controller logs contain no reconciliation events for `no-label-ns`
- MaaSSubscription in `no-label-ns` remains unreconciled (no `Ready` status condition)

**Notes**: To be filled later in the process.
