---
type: llm
focus: last_message
---
The requirement has a happy path (attach a disk to a running instance, visible in the
guest, workloads uninterrupted) and an error path (attaching a disk already attached must
be rejected with a clear error).

PASS if the scenarios cover both: at least one verifying the successful attach and at least
one verifying the duplicate attach is rejected, each phrased as something a tester can
observe, and each carrying a priority.

FAIL if only the happy path is covered, if a scenario merely restates the requirement with
no observable outcome, or if it invents requirements not in the text (detach, resize,
migration, performance).
