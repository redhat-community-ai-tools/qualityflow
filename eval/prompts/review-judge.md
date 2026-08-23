# Judge: finding alignment against the exemplar review

You are grading one STP review produced by the `stp-reviewer` skill against the
reference review shipped with the same eval case (`reference.md` in the case
directory). Both documents review the *same* Software Test Plan.

You are not grading whether the review is good in the abstract. You are grading
whether it found what the reference found. The reference is the exemplar: it is
either the verbatim output of a real pipeline run on this exact input
(`annotations.reference_type: captured`), or, for a deliberately degraded input, a
checklist of the findings the skill's own rules require
(`annotations.reference_type: derived`). Check `annotations.yaml` for which.

## What counts as a match

Two findings match when they name the same defect in the same place. They match
even when:

- the rule letter or dimension number differs, or the produced review files a
  finding under a rule the reference filed elsewhere;
- the wording, ordering, or section layout differs;
- the produced review merges two reference findings into one, or splits one into
  two, provided the underlying defects are all named;
- severity differs by one level in either direction — note it, do not treat it as
  a miss.

They do not match when the produced review names a different section, a different
rule violation, or a defect the reference did not identify at all.

## What to weight

1. **Critical findings dominate.** Every critical in the reference must appear in
   the produced review at critical or major severity. A missed critical is the
   failure this suite exists to catch.
2. **Major findings next.** Most should appear. Losing a few is drift; losing most
   is a change in sensitivity.
3. **Minor findings are informational.** Do not penalise a review for finding
   fewer minors, and do not reward it for finding more.
4. **New findings are not automatically wrong.** A defect the reference missed but
   that is genuinely present, and that you can point at in the STP, is a neutral
   observation — say so in your rationale. A finding you cannot ground in the STP
   text is a hallucination and costs a point.
5. **Format drift is not a finding gap.** Some references predate the current
   output format in `skills/stp-reviewer/SKILL.md`. Judge substance.

## Scale

| Score | Meaning |
|:---|:---|
| 5 | Every reference critical and essentially every major found. No ungrounded findings. |
| 4 | Every reference critical found; a minority of majors missing or merged. No ungrounded findings. |
| 3 | Every reference critical found, but major coverage is visibly thinner, or one finding is not grounded in the STP text. |
| 2 | A reference critical is missing, or several findings are ungrounded. |
| 1 | Multiple reference criticals missing, or the review is largely unrelated to the document. |

Score 3 is the floor for "the same reviewer, slightly different day". Anything at or
below 2 means the reviewer's judgement changed, and the change should be understood
before the new model is adopted.

## Output

Return the integer score, then a short rationale that states explicitly:

- which reference criticals were found and which were missed, by name;
- roughly how many reference majors were found;
- any finding in the produced review you could not ground in the STP text.

Name the findings. "Good coverage" is not a rationale.
