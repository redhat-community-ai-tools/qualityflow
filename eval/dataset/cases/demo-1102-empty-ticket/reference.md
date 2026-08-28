# Reference: expected findings for the DEMO-1102 empty-ticket probe

> **This is not a captured reviewer run.** This case is fully synthetic
> (`source.type: synthetic`); this file is *derived* from
> `skills/stp-reviewer/SKILL.md`'s own rule, confidence and error-handling
> definitions. Judges that compare produced prose against this file should score
> coverage of the listed findings, not stylistic resemblance.

---

## Verdict: APPROVED_WITH_FINDINGS

Zero critical findings exist in the document, and the planted major/minor tail
rules out a clean APPROVED. A NEEDS_REVISION here means the reviewer
manufactured a critical out of missing source data.

## Expected source-data handling

- **Confidence: MEDIUM.** SKILL.md's confidence table: "Jira data available but
  incomplete". The ticket supplies a summary only.
- **Dimension 2 must degrade, not accuse.** There are no Jira acceptance
  criteria to compare against; coverage metrics are not computable and should be
  reported as such. Error Handling prescribes proceeding with reduced scope —
  not inventing uncovered criteria.
- The report's Confidence Notes should record the incomplete source data as the
  reason confidence is degraded.

## Expected major findings (2)

### M1 — Dimension 6, Performance Testing marked Y without a performance requirement — from planted finding P1

The sub-item ("validate the condition is updated within an acceptable time") is
functional phrasing with no SLA or benchmark target. SKILL.md's N/A-vs-Y
challenge classifies this as MAJOR: uncheck it or state a real target.

### M2 — Rule A, Requirement Summary format — from planted finding P2

All four Section III Requirement Summaries are plain phrases rather than
"As a [role]..." user-story format. MAJOR per Rule A's Requirement Summary
red flag; a reviewer may report this as one finding across all rows.

## Expected minor findings

### m1 — Rule G, standard tools listed — from planted finding P3

II.3.1 lists pytest and the oc CLI, both standard project tooling. MINOR per
Rule G; the acceptable content of that section is non-standard tooling only.

Additional unplanted minors (verbosity, bare unchecked strategy entries) are
plausible and covered by the advisory tolerances.
