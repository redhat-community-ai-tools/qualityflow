---
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Lay this out as a proper test plan document for PROJ-12345:

- Why: customers cannot add storage to an instance without restarting it.
- What we will test: attaching and detaching disks on running instances, including
  rejecting a duplicate attach.
- Not testing: the storage backend itself, or the Kubernetes scheduler.
- Environment: OpenShift 4.20 on bare metal, Ceph RBD, RHEL 9.4 guests.
- Risk: live attach may interrupt workloads under heavy I/O.
- Scenarios: attach visible in guest (P0), duplicate attach rejected (P1), detach releases
  the volume (P1).
