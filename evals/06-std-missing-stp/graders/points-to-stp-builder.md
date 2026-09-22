---
type: llm
focus: last_message
---
There is no STP for CNV-70001, and an STD can only be derived from an STP.

PASS if the reply says the STP is missing and tells the user to create it first
(for example by running /stp-builder CNV-70001), without presenting any invented
STD content or test scenarios.

FAIL if the reply produces STD YAML, test stubs, or test scenarios anyway, or
does not tell the user that the STP must exist first.
