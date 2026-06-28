---
name: ticket-assessor
description: Assess Jira ticket data completeness and readiness for STP generation
model: claude-opus-4-6
---

# Ticket Assessor Skill

**Phase:** Pre-Processing (Post-collection)
**User-Invocable:** false

## Purpose

Assess whether the aggregated Jira data collected by jira-collector is
sufficient to produce a high-quality STP. Returns a readiness verdict with
actionable recommendations for the ticket owner.

## When to Use

Invoked by the **stp-orchestrator** agent after jira-collector returns. The
orchestrator passes the complete jira-collector output to this skill. The
assessment uses the already-collected data — it makes no external calls of its own.

## Tools Required

None. This skill operates entirely on the data passed to it.

## Input

The complete aggregated output of jira-collector.

## Output Format

**You MUST produce a markdown report in exactly this structure.** The
stp-orchestrator saves this to
`outputs/stp/{JIRA_ID}/{JIRA_ID}_ticket_assessment.md` and reads the verdict
from the `**Verdict:**` line.

```markdown
# Ticket Assessment: {JIRA_ID}

**Project:** {display_name}
**Verdict:** READY/PARTIAL/INSUFFICIENT
**Summary:** {one-line summary}

## Is the WHAT clear?

**Status:** PASS/WARN/FAIL

{Explain what technical entities were found in summary, description, and
comments. Be specific about what the pipeline can extract.}

## Is the WHAT TO TEST clear?

**Status:** PASS/WARN/FAIL

{Explain what behavioral expectations were found and where — acceptance
criteria, reproduction steps, expected results, test scenarios in comments,
etc. Be specific about what the pipeline can derive test scenarios from.}

## Can the pipeline trace the relevant code?

| Dimension | Status | Detail |
|:----------|:-------|:-------|
| Components | PASS/FAIL | {list components found or note none} |
| PR URLs | PASS/FAIL | {count found, list sources, or note none} |

## Supporting Fields

| Field | Status | Detail |
|:------|:-------|:-------|
| Linked Issues | PASS/FAIL | {count and relationship types} |
| Labels | PASS/FAIL | {list or note none} |
| Fix Version | PASS/FAIL | {value or note none} |
| Priority | PASS/FAIL | {value or note none} |
| Issue Type | PASS/FAIL | {value or note none} |
| Feature Link | PASS/FAIL | {parent/epic or note none} |

## Recommendations

{List only when there are WARN or FAIL results. Each recommendation should
tell the ticket owner what to add to the Jira ticket. If all PASS, write
"No recommendations — ticket data is sufficient for STP generation."}
```

## Assessment Approach

The assessment answers three questions about the aggregated data. Each question
maps to a dimension of STP quality. All three questions draw from the full
aggregated picture — summary, description, comments, linked issues, epic
children, subtasks, and feature candidates.

### Question 1: Is the WHAT clear?

*Can the pipeline understand what this ticket is about?*

The pipeline needs to extract technical entities (resources, APIs, operations,
behaviors) to feed into feature-finder and requirement-mapper. If the
aggregated data lacks technical specificity, the pipeline has nothing to work
with.

**Assessed from:** `main_issue.summary`, `main_issue.description`,
`main_issue.comments`, `linked_issues[].summary`,
`linked_issues[].description`, `linked_issues[].comments`

| Verdict | Signal |
|:--------|:-------|
| PASS | The aggregated data names specific technical entities and provides context — technical details, behavioral descriptions, reproduction steps, root cause analysis, user stories, design rationale, or engineering discussion in comments |
| WARN | Summary is specific but the description is thin and comments do not add meaningful technical context |
| FAIL | No technical specificity found across summary, description, and comments — the pipeline cannot determine what this ticket is about |

**If FAIL:** Verdict is **INSUFFICIENT**. The pipeline cannot generate
meaningful test scenarios without understanding what the ticket is about.

**Recommendation when not PASS:** Add a detailed description to the Jira
ticket explaining what the feature does or what the bug is, including
specific resource types, operations, and expected behaviors.

### Question 2: Is the WHAT TO TEST clear?

*Can the pipeline derive test scenarios from the aggregated data?*

Somewhere in the aggregated data there must be behavioral expectations — what
should happen, what should not happen, or what went wrong. These can come from
many places: an explicit acceptance criteria field, bug reproduction steps,
expected/actual results, user stories, or behavioral details found in comments
(QE-written test scenarios, engineer descriptions of expected fix behavior,
verification results). The jira-collector also extracts acceptance criteria
into `feature_candidates.acceptance_criteria` from linked issues and subtasks.

**Assessed from:** `main_issue.acceptance_criteria`,
`main_issue.description` (reproduction steps, expected/actual results, user
stories), `main_issue.comments` (test scenarios, expected behavior
discussions, verification details), `feature_candidates.acceptance_criteria`,
`linked_issues[].acceptance_criteria`, `linked_issues[].description`,
`linked_issues[].comments`

| Verdict | Signal |
|:--------|:-------|
| PASS | Behavioral expectations exist somewhere in the aggregated data — describing specific outcomes tied to concrete operations or conditions |
| WARN | Some behavioral context exists but it is vague or lacks concrete outcomes |
| FAIL | No behavioral expectations found anywhere in the aggregated data |

**If FAIL:** Does not block generation but significantly reduces STP quality.
Test scenarios will be inferred from the description alone.

**Recommendation when not PASS:** Add acceptance criteria or expected outcomes
to the Jira ticket describing what the correct behavior looks like.

### Question 3: Can the pipeline trace the relevant code?

*Are there code references the pipeline can use for regression analysis?*

The pipeline produces stronger STPs when it can trace code changes — analyzing
PR diffs, building call graphs, and mapping impacted features. This requires
PR URLs and components in the aggregated data. Without either, the STP is
generated purely from Jira text, which still works but produces weaker
code-level coverage.

This question is evaluated across two sub-dimensions:

#### 3a: Components

**Assessed from:** `main_issue.components`,
`linked_issues[].components`, `feature_candidates.component_hints`

| Verdict | Signal |
|:--------|:-------|
| PASS | At least one component is set on the main issue or linked issues |
| FAIL | No components set anywhere |

**Recommendation when FAIL:** Set the relevant component(s) on the Jira ticket
so the pipeline can map the work to the correct code area.

#### 3b: PR URLs

**Assessed from:** `pr_urls` (the aggregated, deduplicated list from all
sources — main issue description, custom fields, comments, linked issue
descriptions, linked issue custom fields, linked issue comments, subtasks,
remote links)

| Verdict | Signal |
|:--------|:-------|
| PASS | 1+ PR URLs found in the aggregated list |
| FAIL | No PR URLs found across any source |

**Recommendation when FAIL:** Link relevant pull requests to the Jira ticket
or its related issues. PRs can be added in the Git Pull Request field, in
comments, or in linked issues. Without PRs, the STP will not include
code-level regression analysis.

## Supporting Fields

These fields do not affect the three main questions but improve the overall
STP quality. Each is simply PASS or FAIL.

| Field | PASS | FAIL | Impact when FAIL |
|:------|:-----|:-----|:-----------------|
| **Linked Issues** | 1+ linked issues or epic children exist | No linked issues | Incomplete dependency graph; may miss PRs and broader context |
| **Labels** | 1+ labels set | No labels | Tier classification relies on heuristics only |
| **Fix Version** | Fix version set | No fix version | Version field left as placeholder in STP |
| **Priority** | Priority set | No priority | Test priority assignment uses defaults |
| **Issue Type** | Issue type set | No issue type | Pipeline cannot distinguish bug vs feature behavior |
| **Feature Link** | Parent issue, feature/epic link, or integration points exist | None | Cannot trace to parent epic for broader context |

## Verdict Rules

| Verdict | Condition |
|:--------|:----------|
| **READY** | Question 1 is PASS, Question 2 is PASS, and both 3a and 3b are PASS |
| **PARTIAL** | Question 1 is at least WARN, and no more than 2 fields across Questions 2, 3a, 3b are FAIL |
| **INSUFFICIENT** | Question 1 is FAIL |
