---
type: llm
focus: last_message
---
PASS if the dependency graph puts each link in the right place: PROJ-11100 as something
that blocks PROJ-12345 (a blocker, must land first), PROJ-13000 as something PROJ-12345
blocks, PROJ-9000 as the epic/feature it implements, and PROJ-12346 recognised as a clone
or backport rather than a blocker. FAIL if a blocker and a blocked item are swapped, or if
PROJ-12000 (a related, already-done bug) is presented as a blocker.
