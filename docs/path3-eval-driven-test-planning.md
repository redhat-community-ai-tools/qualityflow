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
frontmatter. When a new model ships, the upgrade path is:

1. Run the reviewer on a known STP with the current model — baseline
2. Change the model in the skill frontmatter
3. Run the same STP — compare verdicts and findings
4. If verdicts match and finding counts are within tolerance: ship it
5. If critical findings drop unexpectedly: the new model is more
   lenient — investigate before adopting

This is eval-before-switch. No guessing.

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
