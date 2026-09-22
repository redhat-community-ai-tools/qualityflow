---
max_turns: 6
timeout_seconds: 240
allowed_tools: [Skill]
runs: 3
---
Work out the dependency picture for PROJ-12345 from its issue links, so the test plan
knows what must land first:

```
PROJ-12345 "Attach a second disk to a running instance"
  is blocked by      PROJ-11100  "Volume hotplug API in the storage service" (In Progress)
  blocks             PROJ-13000  "Document live disk attach" (To Do)
  implements         PROJ-9000   "Live storage management" (Epic, In Progress)
  relates to         PROJ-12000  "Disk detach hangs on busy volumes" (Bug, Done)
  is cloned by       PROJ-12346  "Attach a second disk — backport 4.19" (To Do)
```
