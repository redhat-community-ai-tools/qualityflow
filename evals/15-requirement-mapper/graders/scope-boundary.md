---
type: llm
focus: last_message
---
Three acceptance criteria belong to this feature. The Kubernetes scheduler
(schedulePodToNode) and the etcd storage backend (etcdWriteQuorum) are platform components
owned by other teams and were not changed.

PASS if all three acceptance criteria are mapped to test scenarios, AND the scheduler and
etcd items are excluded/rejected as out of scope (or simply never proposed as scenarios),
AND every requirement keeps the real ID PROJ-12345 rather than an invented one.

FAIL if it proposes testing the Kubernetes scheduler or etcd quorum, drops one of the three
criteria, or invents requirement IDs that were not given.
