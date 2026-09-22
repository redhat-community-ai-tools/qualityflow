---
max_turns: 6
timeout_seconds: 240
allowed_tools: [Skill]
runs: 3
---
Decide what we should actually test for PROJ-12345, and what belongs to someone else.

Ticket PROJ-12345 "Attach a second disk to a running instance". Acceptance criteria:
1. A disk can be attached to a running instance and appears in the guest.
2. Attaching a disk does not interrupt running workloads.
3. Attaching a disk that is already attached is rejected with a clear error.

Code analysis found: `AttachVolume` (new entry point), `validateVolumeRequest` (modified),
`schedulePodToNode` (unchanged — Kubernetes scheduler library), and `etcdWriteQuorum`
(unchanged — platform storage backend).
