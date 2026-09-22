---
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Check whether this test plan is structurally complete before we send it for review:

```markdown
# Software Test Plan: PROJ-12345

**I. Motivation & Requirements Review**

Users need to attach storage to a running instance.

**II. Software Test Plan**

1. Scope of Testing: disk attach and detach on running instances.
2. Testing Goals
   - [x] **Functional**
   - [ ] **Performance**
3. Test Environment: OpenShift 4.20, Ceph RBD.

**III. Test Scenarios & Traceability**

| Requirement ID | Requirement Summary | Test Scenario(s) | Tier | Priority |
|:---|:---|:---|:---|:---|
| REQ-ATTACH-01 | Disk attaches to a running instance | Verify the guest sees the new disk | Tier 1 | P0 |
| REQ-ATTACH-02 | Duplicate attach is rejected | | Tier 1 | P1 |
```
