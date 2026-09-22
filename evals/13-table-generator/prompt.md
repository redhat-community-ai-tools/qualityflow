---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Turn this into the environment table for a test plan document:

- Platform: OpenShift 4.20 on bare metal
- Storage: Ceph RBD with dynamic provisioning
- Guest OS: RHEL 9.4, Windows Server 2022
- Network: OVN-Kubernetes, single stack IPv4
- Minimum nodes: 3 worker nodes with 16 GiB RAM each
