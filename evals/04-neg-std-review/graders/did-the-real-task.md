---
type: llm
focus: last_message
weight: 1
---
The user asked for a review of a Software Test Description (STD) YAML — a
different artifact from a Software Test Plan (STP). The response should review
the STD on its own terms and must NOT mistakenly apply the STP review framework.

The response PASSES only if BOTH hold:

1. **It reviews the STD substantively.** It addresses the actual questions asked —
   requirement traceability of the scenarios, completeness of the
   Preconditions/Steps/Expected docstrings, and readiness gaps. It should notice
   the concrete problems in this YAML: TS-02 has an empty `expected`, and TS-03
   has an empty `requirement` (no traceability). Catching at least one of these
   is required.
2. **It does NOT run the STP review machinery.** It must not produce an "STP
   Review Report", must not evaluate the document against the STP's 7 dimensions
   or Rules A–Q, and must not treat this YAML as if it were a Software Test Plan.
   Applying the STP reviewer's rubric to an STD is the over-trigger failure this
   case exists to catch.

Return whether the response passes and a one-line rationale.
