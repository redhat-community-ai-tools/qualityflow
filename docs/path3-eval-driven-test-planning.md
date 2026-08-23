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
depends on, so the repo ships the eval that guards it: `eval/`, three
exemplars in [agent-eval-harness](https://github.com/opendatahub-io/agent-eval-harness)
layout.

The exemplars are real. Two of them are STPs that went through the pipeline,
paired with the verbatim review the reviewer produced for them — one landing
`APPROVED_WITH_FINDINGS` with zero criticals, one landing `NEEDS_REVISION` with
three. The third is the first STP with five itemised degradations applied
(coverage stripped for two acceptance criteria, internal-mechanism language
pushed into the scope and goals, a prerequisite dressed up as a test scenario, a
row given two tiers), so its critical findings are known by construction rather
than by recollection. Every edit is listed in that case's `annotations.yaml`.

When a new model ships:

```bash
/eval-run --config eval/eval.yaml --model claude-opus-4-6   # baseline
/eval-run --config eval/eval.yaml --model <new-model>       # candidate
/eval-compare <baseline-run-id> <candidate-run-id>
```

Two judges are deterministic — the produced verdict must equal
`annotations.expected_verdict`, and the critical finding count must sit inside
the case's tolerance. A third is an LLM rubric that scores the produced findings
against the reference review. Ship when all three verdicts still agree and the
critical counts hold.

The interesting failure is the quiet one. If critical findings *drop* while the
verdict survives, the new model is more lenient and the next STP may be the one
where the last critical disappears too — investigate before adopting. If
criticals *rise* on the clean STP, it has become trigger-happy, which is how a
review gate gets switched off by the people it is supposed to help.

This is eval-before-switch. No guessing. See `eval/README.md` for the runbook and
for how to promote a new real run into an exemplar.

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
