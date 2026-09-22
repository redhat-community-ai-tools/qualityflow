---
max_turns: 25
timeout_seconds: 900
allowed_tools: [Skill, Read, Glob, Grep, Agent]
runs: 3
---
Build the Software Test Description for PROJ-12345 from its approved test plan at
`outputs/PROJ-12345/stp/PROJ-12345_test_plan.md`: the STD YAML at
`outputs/PROJ-12345/std/PROJ-12345_test_description.yaml`, plus test stubs carrying
Preconditions / Steps / Expected docstrings. The repository under test is the current
working directory.
