# Reference: expected findings for the DEMO-1103 PR-null bug probe

> **This is not a captured reviewer run.** This case is fully synthetic
> (`source.type: synthetic`); this file is *derived* from
> `skills/stp-reviewer/SKILL.md`'s own rule definitions. Judges that compare
> produced prose against this file should score coverage of the listed findings,
> not stylistic resemblance.

---

## Verdict: APPROVED_WITH_FINDINGS

No critical violation exists; the planted major tail rules out APPROVED.

## Expected degrade-path handling

- **Rule P skipped, explicitly.** The ticket is a Bug but `fix_scope` is null.
  SKILL.md's activation guard requires both conditions; the rule table should
  carry PASS with "N/A — not a bug ticket or no PR data available" (or
  equivalent). Any tier-efficiency finding derived from an imagined fix scope is
  a failure of this case.
- **Dimension 2 runs and finds full coverage.** Both acceptance criteria map to
  scenarios: the tie-break criterion to REQ-DEMO-1103-01 (and -02), the
  unchanged-behaviour criterion to REQ-DEMO-1103-03. Coverage should be reported
  as 2/2 with no gap.
- **Confidence Notes** should record "PR data referenced in STP: NO" (or
  equivalent) without lowering the verdict for it.

## Expected major findings (3)

### M1 — Rule D, infrastructure listed as a dependency — from planted finding P1

The Dependencies strategy row lists the CSI snapshot provisioner and the default
StorageClass. Both are pre-existing platform infrastructure and belong in Test
Environment (II.3); Rule D reserves Dependencies for another team's delivery.
MAJOR.

### M2 — Dimension 6, Performance Testing marked Y without a performance requirement — from planted finding P2

"Validate pruning completes within an acceptable time" is functional phrasing
with no SLA or benchmark target. MAJOR per the N/A-vs-Y challenge.

### M3 — Rule A, Requirement Summary format — from planted finding P3

Section III Requirement Summaries are plain phrases rather than "As a [role]..."
user-story format. MAJOR; may be reported once across all rows.

## Expected minor findings

Small unplanted minors (verbosity, bare unchecked strategy entries, generic
environment phrasing) are plausible and covered by the advisory tolerances.
