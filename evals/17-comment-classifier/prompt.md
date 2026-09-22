---
max_turns: 6
timeout_seconds: 240
allowed_tools: [Skill]
runs: 3
---
Four review comments came back on the test plan PR for PROJ-12345. Sort out which ones we
can fix automatically and which need a human:

```
#12345 (reviewer): Section III scenario 4 says "verify the reconciler syncs the volume
        annotation" — that's internal mechanism language, rewrite it as user-observable.
#12346 (reviewer): The table in Section II.3 is missing the alignment row, it renders
        wrong in the docs site.
#12347 (reviewer): Do we even want to support attaching disks to paused instances? Product
        hasn't decided; ask Dana before adding scenarios for it.
#12348 (bot): Trailing whitespace on line 212.
```
