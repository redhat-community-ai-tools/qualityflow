---
max_turns: 6
timeout_seconds: 240
allowed_tools: [Skill]
runs: 3
---
Normalise this Jira issue into the structured form our test-planning pipeline consumes:

```
Key: PROJ-12345
Type: Story   Status: In Progress   Priority: Major
Summary: Allow users to attach a second disk to a running instance
Components: storage, api
Labels: customer-request, 4.20
Fix Version: 4.20.0
Reporter: [reporter] <reporter@example.com>
Assignee: [assignee] <assignee@example.com>
Created: 2026-02-03T09:12:00.000+0000
Updated: 2026-02-27T16:40:00.000+0000

Description:
Users need to add storage to an instance without restarting it.

Acceptance Criteria:
- A disk can be attached to a running instance and appears in the guest
- Attaching a disk does not interrupt running workloads
- Detaching a disk while the instance runs releases the volume

Implementation PR: https://github.com/example-org/example-repo/pull/4412
Feature: https://issues.example.com/browse/PROJ-9000
```
