# Reference: expected findings for the DEMO-1104 malformed-STP probe

> **This is not a captured reviewer run.** This case is fully synthetic
> (`source.type: synthetic`); this file is *derived* from
> `skills/stp-reviewer/SKILL.md`'s own rule definitions. Judges that compare
> produced prose against this file should score coverage of the listed findings,
> not stylistic resemblance.

---

## Verdict: NEEDS_REVISION

Follows deterministically from SKILL.md's verdict table: 1+ critical finding
blocks approval. An STP with an empty traceability matrix is unusable regardless
of how tidy its prose is.

## Expected critical findings (3)

### C1 — Rule B, Section III is empty — from planted finding P1

The Requirements-to-Tests Mapping table has a header and zero rows. Rule B:
CRITICAL — "Section III has no items or is empty — this is the core of the STP
and must be filled."

### C2 — Rule B, checked checkbox with empty sub-items — from planted finding P2

Section I.1's Acceptance Criteria item is checked with no sub-bullets. Rule B:
CRITICAL — "a checkbox is checked but its sub-items are empty."

### C3 — Rule B, placeholder text remaining — from planted finding P3

Test Environment (II.3) contains only "[TODO: describe the required test
environment before review]". Rule B: CRITICAL — "any required section has
unfilled placeholder text still present."

A reviewer may merge these into fewer structural findings, or additionally raise
the Rule K fallout (Scope, Testing Goals and the Monitoring strategy row all
promise coverage that the empty Section III does not provide) as CRITICAL; the
tolerance in `annotations.yaml` accommodates both directions.

## Expected non-critical findings

Not scored deterministically. Plausible: Rule K contradictions between
Scope/Goals/Strategy and the empty Section III if not already raised as
critical (MAJOR); Rule G.2 environment specificity is unassessable behind the
placeholder; content-only review notes (Jira data unavailable) in the
Confidence section, with Dimensions 2 and 4 skipped per Error Handling.
