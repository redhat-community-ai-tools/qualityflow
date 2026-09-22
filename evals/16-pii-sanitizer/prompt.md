---
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill, Read, Write]
runs: 3
---
Get this test plan extract ready to publish in a public repository:

```
## Test Environment

Reproduced on the cluster Globex Industries runs in their Frankfurt datacentre
(hosts kvm-prod-07.globex-internal.net and kvm-prod-08.globex-internal.net,
management IP 10.44.19.6). Their storage vendor, Acme Storage, supplied the array.

Escalation contact: [engineer] <j.doe@globex.com>, phone +49 151 2233 4455.
Test account: qeuser / P@ssw0rd-2026 on https://jira.globex-internal.net.

## Scenario

1. Attach a disk on kvm-prod-07.globex-internal.net and confirm the guest sees it.
2. Confirm Globex's nightly backup job still completes.
```
