---
type: llm
focus: last_message
---
The ticket says only "attaching disks doesn't work properly", with no acceptance criteria,
no reproduction steps, no expected behaviour, no components, no linked PR.

PASS if the answer judges the ticket not ready (or only partly ready) for test planning AND
names concretely what is missing — for example no expected behaviour or acceptance criteria,
no reproduction steps, no affected component or version.

FAIL if it treats the ticket as ready to plan from, or if it invents requirements, disk
sizes, versions or error messages that the ticket does not contain.
