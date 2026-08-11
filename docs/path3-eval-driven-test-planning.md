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

## Writing Eval Cases for the Reviewer

The next question: how do you know the *reviewer itself* is good enough?

QualityFlow ships 3 eval cases for `stp-reviewer` in `evals/stp-reviewer/`:

| Case | Input | Expected |
|------|-------|----------|
| **Happy path** | Well-formed STP with full coverage, user-facing language, balanced distribution | `APPROVED`, 0 critical, 0 major |
| **Edge case** | STP with vague qualifiers ("works correctly"), risk duplication, performance testing checked without SLA | `APPROVED_WITH_FINDINGS`, 0 critical, 2+ major |
| **Error case** | STP with internal mechanism language, prerequisite-as-scenario, 1/4 acceptance criteria covered, generic scenario text | `NEEDS_REVISION`, 3+ critical |

Each case is a YAML file with `input` (STP content + mock Jira data) and
`expected` (verdict + specific assertions). Run them with `agent-eval-harness`:

```bash
/eval-run --dataset evals/stp-reviewer/ --skill stp-reviewer
```

If you change the review rules, the model, or the prompt — run the eval
first. If the happy path starts producing false positives (findings where
there should be none) or the error case stops catching critical violations,
you know the change broke something.

## Eval-Before-Switch in Practice

QualityFlow's `stp-reviewer` skill specifies `model: claude-opus-4-6` in its
frontmatter. When a new model ships, the upgrade path is:

1. Run the 3 eval cases on the current model — baseline
2. Change the model in the skill frontmatter
3. Run the same 3 eval cases — compare
4. If verdicts match and finding counts are within tolerance: ship it
5. If the error case drops from 3+ critical to 1: the new model is more
   lenient — investigate before adopting

This is eval-before-switch. No guessing.

## From Review Skill to Eval Pipeline

The pattern generalizes. Any agent output with a structured quality
assessment can become an eval:

- **Input:** a known-good (or known-bad) fixture
- **Expected:** the correct quality judgment
- **Assertion:** the agent's actual output matches

QualityFlow applies this at two levels:

1. The STP/STD *content* is evaluated by review skills (quality of the
   generated document)
2. The review skills *themselves* are evaluated by eval cases (quality
   of the quality judgment)

The second level is what makes the system trustworthy. You're not just
checking if the agent produces output — you're checking if the agent's
quality gate catches what it should.

## Getting Started

1. Look at `evals/stp-reviewer/` for the case format
2. Pick a skill in your own project that produces structured output
3. Write 3 cases: happy path, edge case, error case
4. Run with `agent-eval-harness`
5. Commit the cases — they're your regression suite for agent quality

The eval cases are small (one YAML file each), but they encode your
team's definition of "good enough." That definition should live in
version control, not in someone's head.
