---
max_turns: 40
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Agent]
runs: 3
---
Review the Software Test Description for CNV-68916 before it goes to design review.

- STP: `outputs/CNV-68916/stp/CNV-68916_test_plan.md`
- STD YAML: `outputs/CNV-68916/std/CNV-68916_test_description.yaml`
- Test stubs: `outputs/CNV-68916/std/python-tests/`

Write the review report to `outputs/CNV-68916/reviews/CNV-68916_std_review.md`. It must state
a verdict of exactly one of APPROVED, APPROVED_WITH_FINDINGS, or NEEDS_REVISION, and end
with a YAML block giving `verdict`, `critical_count`, `major_count`, and `minor_count`.
