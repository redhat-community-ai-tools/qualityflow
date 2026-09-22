---
max_turns: 12
timeout_seconds: 360
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Ticket PROJ-12345 says only: "Users need to attach a second disk to a running instance
without restarting it." There is no pull request and no file list.

Find where this behaviour lives in this repository — the entry points our tests would go
through — and say what is already covered by existing tests.
