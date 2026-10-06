# Eval-Driven Test Planning with QualityFlow

*~4 min read — Path 3: Evals & Quality*

## The Problem

Test plans are judgment-heavy documents. A human QE engineer reads a Jira
ticket, decides what to test, classifies priority and tier, and writes
scenarios in user-facing language. When an AI agent generates that same
document, how do you know the output is good enough?

You run an eval.

## Structured Verdicts as Quality Gates

QualityFlow generates Software Test Plans (STPs) from Jira tickets and
GitHub issues. Every generated STP passes through an automated review
skill (`stp-reviewer`) that evaluates 7 dimensions:

1. **Rule Compliance** — 16 domain rules (abstraction level, cross-section
   consistency, prerequisite detection, testing pyramid efficiency)
2. **Requirement Coverage** — every Jira acceptance criterion mapped to a
   test scenario
3. **Scenario Quality** — specificity, user perspective, priority distribution
4. **Risk & Limitation Accuracy** — cross-referenced against source data
5. **Scope Boundary** — does the scope match what the feature actually does
6. **Strategy Appropriateness** — are the right test types selected
7. **Metadata Accuracy** — versions, SIG ownership, links

Each dimension produces findings classified as CRITICAL, MAJOR, or MINOR.
The verdict follows deterministic rules:

| Verdict | Criteria |
|---------|---------|
| `APPROVED` | 0 critical, 0 major |
| `APPROVED_WITH_FINDINGS` | 0 critical, 1+ major/minor |
| `NEEDS_REVISION` | 1+ critical |

This is already eval-shaped. The review skill IS an eval — it defines what
"good" looks like and produces a structured score.

## Eval-Before-Switch in Practice

QualityFlow's `stp-reviewer` skill specifies `model: claude-opus-4-6` in its
frontmatter. Changing that pin changes the quality gate the whole pipeline
depends on, so the repo ships the eval that guards it: cases 01–03 in
`evals/`, a `claude plugin eval` suite.

The exemplars are real. Two of them are STPs that went through the pipeline,
one written to the wrong structure and one with implementation language leaking
into its goals and scenarios. The third is the first STP with five itemised degradations applied
(coverage stripped for two acceptance criteria, internal-mechanism language
pushed into the scope and goals, a prerequisite dressed up as a test scenario, a
row given two tiers), so its critical findings are known by construction rather
than by recollection. Every edit is listed in that case's `graders/planted-defects.md`.

When a new model ships:

```bash
claude plugin eval . -j 8 --scaffold --no-publish --judge-model sonnet --allow-tools Write Edit
```

Run it on the current pin, then again with the candidate model. Each case's
regex graders check the verdict and that the critical-finding count sits in the
case's range; an LLM grader checks that the findings name the defects the case
was built around. Ship when the verdicts still agree and the critical counts hold.

The interesting failure is the quiet one. If critical findings *drop* while the
verdict survives, the new model is more lenient and the next STP may be the one
where the last critical disappears too — investigate before adopting. If
criticals *rise* on the clean STP, it has become trigger-happy, which is how a
review gate gets switched off by the people it is supposed to help.

This is eval-before-switch. No guessing. See `evals/README.md` for the runbook.

## From Review Skill to Eval Pipeline

The pattern generalizes. Any agent output with a structured quality
assessment can become an eval:

- **Input:** a known-good (or known-bad) artifact
- **Expected:** the correct quality judgment
- **Assertion:** the agent's actual output matches

QualityFlow applies this at two levels:

1. The STP/STD *content* is evaluated by review skills (quality of the
   generated document)
2. The review skills *themselves* can be evaluated by running them against
   known inputs and checking verdicts (quality of the quality judgment)

The second level is what makes the system trustworthy. You're not just
checking if the agent produces output — you're checking if the agent's
quality gate catches what it should.
