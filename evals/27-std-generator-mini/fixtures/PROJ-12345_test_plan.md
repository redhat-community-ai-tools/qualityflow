# Software Test Plan: PROJ-12345

**I. Motivation & Requirements Review**

Customers cannot add storage to an instance without restarting it.

**II. Software Test Plan**

1. Scope of Testing: attaching and detaching disks on running instances.
2. Testing Goals
   - [x] **Functional**
3. Test Environment: OpenShift 4.20, Ceph RBD, RHEL 9.4 guests.

**III. Test Scenarios & Traceability**

| Requirement ID | Requirement Summary | Test Scenario(s) | Tier | Priority |
|:---|:---|:---|:---|:---|
| REQ-ATTACH-01 | A disk attaches to a running instance and appears in the guest | Verify a second disk attached to a running instance is visible in the guest and workloads continue | Tier 1 | P0 |
| REQ-ATTACH-02 | Attaching a disk that is already attached is rejected | Verify a duplicate attach is rejected with a clear error and the instance keeps one copy | Tier 1 | P1 |
| REQ-DETACH-01 | Detaching a disk from a running instance releases the volume | Verify detaching removes the disk from the guest and releases the volume | Tier 1 | P1 |

**IV. Sign-off & Approval**

- [ ] QE Lead
