---
test_case_id: TC-CTRL-001
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-CTRL-001: maas-controller discovers namespace with maas.opendatahub.io/tenant label

**Objective**: Verify that the maas-controller automatically
discovers and begins reconciling a namespace when the
`maas.opendatahub.io/tenant` label is added.

**Preconditions**:

- maas-controller is running
- An unlabeled namespace `tenant-b` exists

**Test Steps**:

1. Confirm `tenant-b` namespace has no `maas.opendatahub.io/tenant` label
2. Add label: `kubectl label namespace tenant-b maas.opendatahub.io/tenant=tenant-b`
3. Monitor controller logs for discovery event
4. Create a MaaSSubscription in `tenant-b` and verify it is reconciled

**Expected Results**:

- Controller logs contain a discovery or watch event referencing `tenant-b` within 30 seconds of labeling
- MaaSSubscription created in `tenant-b` reaches `Ready` status
- No manual controller restart required

**Notes**: To be filled later in the process.
