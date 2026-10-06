---
max_turns: 15
timeout_seconds: 600
allowed_tools: [Skill]
runs: 3
---
Review this Software Test Description (STD) YAML for me. Are the test scenarios
traceable back to their requirements, are the Preconditions/Steps/Expected
docstrings complete, and is anything missing before we hand it to code generation?

```yaml
std_version: "2.1"
jira_id: PROJ-70012
feature: "Volume snapshot restore for running workloads"
test_scenarios:
  - id: TS-01
    requirement: REQ-PROJ-70012-01
    tier: 1
    title: "Restore a snapshot to a running workload"
    preconditions: "Running workload with a completed VolumeSnapshot"
    steps:
      - "Issue a restore request referencing the snapshot"
      - "Wait for the restore to reach Completed"
    expected: "Workload volume reflects the snapshot contents; workload stays running"
  - id: TS-02
    requirement: REQ-PROJ-70012-02
    tier: 2
    title: "Restore fails cleanly when the snapshot is missing"
    preconditions: "Running workload; referenced snapshot deleted"
    steps:
      - "Issue a restore request referencing the deleted snapshot"
    expected: ""
  - id: TS-03
    requirement: ""
    tier: 1
    title: "Concurrent restores on the same volume are serialized"
    preconditions: "Running workload with two pending restore requests"
    steps:
      - "Submit both restore requests within one second"
    expected: "One restore completes; the other is rejected or queued"
```
