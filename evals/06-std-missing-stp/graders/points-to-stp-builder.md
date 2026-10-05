---
type: llm
focus: last_message
---
There is no STP for CNV-70001 and no scenario list
(`outputs/CNV-70001/input/CNV-70001_scenarios.yaml`) — the two inputs an STD can be
derived from.

PASS if the reply says the input is missing and tells the user how to provide one —
for example by running /stp-builder CNV-70001, or by adding a scenario list — without
presenting any invented STD content or test scenarios.

FAIL if the reply produces STD YAML, test stubs, or test scenarios anyway, or does
not tell the user that an STP (or a scenario list) must exist first.
