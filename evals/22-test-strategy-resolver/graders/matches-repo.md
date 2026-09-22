---
type: llm
focus: last_message
---
The repository uses pytest on Python 3.11+, tests under tests/<area>/test_*.py, test
functions named test_*, classes named Test*, fixtures passed as arguments (running_vm,
dv_source, nad), and pytest markers polarion and gating.

PASS if the answer reports python + pytest, the tests/<area>/test_*.py placement, the
test_* naming, and the polarion/gating markers.

FAIL if it reports a different language or framework (Go, unittest, Ginkgo), or invents
conventions the repository does not use.
