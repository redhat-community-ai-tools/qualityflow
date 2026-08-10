---
name: comment-classifier
description: >-
  Classify PR review comments on STP/STD documents into auto-fixable vs
  needs-human categories. Maps free-text feedback to QualityFlow domain
  rules for automated fix routing.
model: claude-opus-4-6
---

# Comment Classifier Skill

**Phase:** Pre-Fix Analysis
**User-Invocable:** false

## Purpose

Classify PR review comments into actionable categories so the pr-fix-agent knows
which comments it can fix automatically and which require human input. This skill
bridges the gap between free-text review feedback (from humans or bots like
CodeRabbit) and QualityFlow's structured domain rules (A-P).

## When to Use

Invoked by the **pr-fix-agent** after fetching review comments from a PR.
Runs once per fix cycle before any edits are applied.

## Input

```yaml
comments:
  - id: 12345
    author: "reviewer-username"
    body: "This scenario references internal reconciler logic"
    path: "stps/storage/remove-hooks-stp.md"  # or outputs/PROJ-12345/stp/...
    line: 142
    section: "III"
    in_reply_to: null
  - id: 12346
    author: "coderabbitai[bot]"
    body: "Missing negative test scenario for this operation"
    path: "outputs/stp/PROJ-12345/PROJ-12345_test_plan.md"
    line: 155
    section: "III"
    in_reply_to: null
  - id: 12347
    author: "team-lead"
    body: "This requirement is out of scope for this release"
    path: "outputs/stp/PROJ-12345/PROJ-12345_test_plan.md"
    line: 98
    section: "III"
    in_reply_to: null
document_type: "stp"  # or "std"
project_context: <from project-resolver, or null if resolution failed>
target_repo_rules: <content of AGENTS.md from target repo, or null>
target_repo: "RedHatQE/openshift-virtualization-tests-design-docs"  # or null
```

### Target Repo Review Rules

When `target_repo_rules` is provided (content of the target repo's `AGENTS.md`),
use those rules as the **primary reference** for classifying comments. Reviewers
(both human and bot) follow the target repo's review standards, so comments will
align with those rules rather than QualityFlow's internal rules.

**Rule mapping priority:**
1. Match against target repo rules first (e.g., `AGENTS.md` section checklists)
2. Fall back to QualityFlow rules A-P for anything not covered
3. When both apply, the target repo rule takes precedence for context

**Common target repo patterns (from `AGENTS.md`):**
- "check `[x]`" / "mark as checked" → update-metadata (checkbox flip)
- "specify actual {field}" → needs-human if domain knowledge required, update-metadata if value is in the comment
- "missing section" / "section is missing" → restructure
- "PM/UX confirmation needed" / "PM/UX input" → needs-human:approval-needed
- "user-observable outcome only" / "not how it's tested" → rewrite-scenario (Rule A equivalent)
- "add something like:" with quoted text → add-scenario (reviewer provides the text)
- "same as above" / "consistency" → map to same fix as the referenced comment

## Output Format

```yaml
classification:
  total_comments: 4
  auto_fixable: 2
  propose_fix: 1
  needs_human: 1

  auto_fix:
    - comment_id: 12345
      category: "rule-violation"
      rule: "A"
      severity: "CRITICAL"
      fix_skill: "scenario-builder"
      fix_action: "rewrite-scenario"
      context:
        target_line: 142
        section: "III"
        original_text: "Verify reconciler updates annotation after hot-plug"
        guidance: "Rewrite using user-observable language per Rule A"

    - comment_id: 12346
      category: "missing-scenario"
      rule: null
      severity: "MAJOR"
      fix_skill: "scenario-builder"
      fix_action: "add-scenario"
      context:
        target_line: 155
        section: "III"
        requirement_id: "PROJ-12345"
        guidance: "Generate negative scenario for the operation"

  propose_fix:
    - comment_id: 12348
      category: "researchable"
      severity: "MAJOR"
      research_sources:
        - type: "issue"
          url: "https://github.com/my-org/my-repo/issues/14056"
        - type: "jira"
          key: "PROJ-72329"
      proposed_text: "Scale testing: validate hook removal on 10+ instances with concurrent backup operations"
      confidence: "medium"
      context:
        target_line: 180
        section: "III"
        original_comment: "What scale? How many VMs?"
        reasoning: "VEP mentions 'production workloads with multiple VMs'; Jira AC references 'multiple running VMs'. Proposed scale target based on typical test environments."

  needs_human:
    - comment_id: 12347
      category: "scope-decision"
      reason: "Scope changes require PM/lead sign-off"
      original_text: "This requirement is out of scope for 4.19"
```

## Classification Rules

### Auto-Fixable Categories

#### 1. Rule Violation (`rule-violation`)

The comment identifies a violation of a known domain rule (A-P). Map the comment
to the specific rule using these patterns:

| Rule | Trigger Patterns in Comment | Fix Skill |
|:-----|:----------------------------|:----------|
| A | "internal", "reconciler", "controller", "annotation", "implementation detail", "not user-observable", "user-observable outcome only", "not how it's tested" | scenario-builder |
| A.2 | "vague", "properly", "correctly", "as expected", "anthropomorphizing" | scenario-builder |
| B | "missing section", "template", "wrong heading", "section order", "section is missing", "Document Conventions" | template-engine |
| C | "prerequisite as scenario", "setup step", "not a test" | scenario-builder |
| D | "infrastructure not dependency", "pre-existing", "not another team" | template-engine |
| E | "upgrade testing", "persistent state", "should be N/A", "upgrade path was evaluated" | template-engine |
| F | "wrong version", "version mismatch", "outdated version" | template-engine |
| G | "standard tool listed", "Ginkgo listed", "pytest listed", "remove from tools" | template-engine |
| H | "duplicate risk", "risk already listed", "redundant risk" | template-engine |
| J | "multiple tiers", "one tier per row", "split tiers" | template-engine |
| K | "scope contradicts", "inconsistent with Section III", "regression scenario" | scenario-builder |
| L | "not SMART", "vague goal", "unmeasurable" | template-engine |
| P | "missing priority", "wrong priority", "priority should be" | tier-classifier |

**Additional patterns from external repo review rules (AGENTS.md):**

| Pattern | Trigger | Fix Category |
|:--------|:--------|:-------------|
| Checkbox consistency | "check `[x]`", "unchecked suggests", "for consistency" | checkbox-fix |
| Missing AC | "missing AC", "add something like:", "add AC for" | add-scenario |
| Placeholder text | "`[Name/Date]`", "`[TBD]`", "placeholder" | update-metadata |
| PM/UX sign-off | "PM/UX", "PM approval", "UX input", "belongs to PM" | needs-human:approval-needed |
| Specific value needed | "specify the actual", "not generic", "exact name" | needs-human (domain knowledge) OR update-metadata (if value in comment) |

#### 2. Missing Scenario (`missing-scenario`)

The comment requests additional test coverage:

**Trigger patterns:** "missing scenario", "no negative test", "need a test for",
"untested", "no coverage for", "add scenario", "what about testing"

**Fix skill:** scenario-builder
**Fix action:** add-scenario

#### 3. Structural Issue (`structural`)

The comment identifies formatting, template, or organizational problems:

**Trigger patterns:** "formatting", "wrong section", "move to", "table broken",
"markdown", "missing header", "section numbering"

**Fix skill:** template-engine
**Fix action:** restructure

#### 4. Tier Mismatch (`tier-mismatch`)

The comment identifies wrong tier classification:

**Trigger patterns:** "should be Tier", "wrong tier", "not Tier 1", "this is E2E",
"this is functional", "tier classification"

**Fix skill:** tier-classifier
**Fix action:** reclassify

#### 5. Metadata Error (`metadata-error`)

The comment identifies wrong metadata (versions, dates, component names):

**Trigger patterns:** "wrong version", "incorrect date", "component name",
"Jira field", "metadata"

**Fix skill:** template-engine
**Fix action:** update-metadata

#### 6. Checkbox Consistency (`checkbox-fix`)

The comment asks to check/uncheck a checkbox for consistency or to reflect
that an evaluation was done:

**Trigger patterns:** "check `[x]`", "mark as checked", "unchecked suggests",
"should be checked", "for consistency", "all categories should be checked"

**Fix skill:** template-engine
**Fix action:** update-metadata
**Note:** When the comment says "check [x] and state {text}", both the checkbox
flip AND the text addition are part of the same fix.

#### 7. Text Removal (`text-removal`)

The comment asks to remove specific text from the document:

**Trigger patterns:** "remove", "delete", "drop", "strip out"
**Condition:** The comment must quote or clearly identify the exact text to remove.

**Fix skill:** template-engine
**Fix action:** update-metadata (targeted text deletion)

#### 8. PR Title Update (`title-update`)

The comment asks to change the PR title:

**Trigger patterns:** "change title", "update title", "rename PR", "title should be"
**Condition:** The comment provides the new title text or clearly describes what it should be.

**Fix skill:** N/A (handled directly by fix-pr via `gh pr edit --title`)
**Fix action:** update-title

### Propose-Fix Categories

Comments where the agent doesn't have enough information for a confident auto-fix,
but *can* research available sources to propose an answer. The agent generates
proposed text with a confidence level and rationale; humans approve or reject.

**When to use propose-fix instead of needs-human:**
The comment asks a question or requests specific domain information that *might*
be answerable from available documentation — VEPs, Jira tickets, upstream code,
design docs, or the STP template itself.

**When to stay needs-human:**
The comment requires external judgment (PM sign-off, UX decision, team consensus)
that no amount of research can substitute for.

#### 1. Researchable Question (`researchable`)

The reviewer asks a question that may be answerable from available sources:

**Trigger patterns:** "what", "how many", "which", "specify", "what scale",
"what version", "which storage class", "what's the expected", "how should"

**Research sources (checked in order):**
1. VEP/enhancement linked in PR body or STP metadata
2. Jira ticket linked in STP (acceptance criteria, description, comments)
3. Target repo docs (`docs/`, `AGENTS.md`, sibling STPs)
4. Upstream code (API types, constants, defaults)
5. STP template guidance (HTML comments with examples)

**Output:** Proposed text with source citation and confidence level:
- **high** — direct quote or value from authoritative source
- **medium** — derived from multiple sources, reasonable inference
- **low** — best guess based on similar features, needs human validation

#### 2. Domain Value Needed (`domain-value`)

The reviewer says the current value is too generic and needs a specific one:

**Trigger patterns:** "specify the actual", "not generic", "exact name",
"real value", "actual storage class", "specific version"

**Research approach:** Check Jira fields, VEP spec, existing tests in the
repo for concrete values used in similar contexts.

#### 3. Missing Detail (`missing-detail`)

The reviewer indicates detail is missing but the information may exist
in available documentation:

**Trigger patterns:** "add detail about", "elaborate on", "more specific",
"what does this mean for", "how does this affect"

**Research approach:** Pull relevant context from VEP description,
Jira comments, or design documents.

### Needs-Human Categories

#### 1. Scope Decision (`scope-decision`)

The comment changes what should or shouldn't be tested:

**Trigger patterns:** "out of scope", "not in scope", "shouldn't test",
"remove this requirement", "not for this release", "descope"

**Reason:** Scope changes require PM/lead sign-off.

#### 2. Requirement Dispute (`requirement-dispute`)

The comment challenges the requirement itself, not the test plan:

**Trigger patterns:** "requirement is wrong", "acceptance criteria should be",
"Jira needs update", "feature changed", "not how it works"

**Reason:** Requirement changes must flow through Jira, not the STP.

#### 3. Stakeholder Approval (`approval-needed`)

The comment requires sign-off from a specific person or role:

**Trigger patterns:** "need PM approval", "check with", "ask the dev",
"architect should review", "sign-off needed"

**Reason:** Cannot proceed without external approval.

#### 4. Ambiguous (`ambiguous`)

The comment cannot be mapped to a specific fix action:

**Trigger patterns:** None specific — this is the fallback category.

**Reason:** Comment intent unclear. Flag for human review.

## Classification Logic

For each comment, apply this decision tree:

```text
1. Is the comment a reply to another comment?
   YES -> Skip (threaded discussion, not actionable)
   NO  -> Continue

2. Is the comment a "resolved" or "outdated" marker?
   YES -> Skip
   NO  -> Continue

3. Does the comment match any needs-human trigger pattern?
   (scope-decision, requirement-dispute, approval-needed)
   YES -> Classify as needs-human with matched category
   NO  -> Continue

4. Does the comment match any auto-fix trigger pattern?
   (rule-violation, missing-scenario, structural, tier-mismatch,
    metadata-error, checkbox-fix, text-removal)
   YES -> Classify as auto-fix with matched category and rule
   NO  -> Continue

5. Does the comment ask a question or request a specific value
   that might be answerable from available documentation?
   (researchable, domain-value, missing-detail)
   YES -> Classify as propose-fix with research sources
   NO  -> Continue

6. Does the comment contain a concrete suggestion for the document?
   YES -> Attempt to map to closest auto-fix category
   NO  -> Classify as needs-human:ambiguous
```

**Three-tier priority:**
1. **needs-human** — requires external judgment (PM sign-off, team decision)
2. **auto-fix** — agent is confident and can apply directly
3. **propose-fix** — agent can research and propose, but human approves
4. **needs-human:ambiguous** — fallback when nothing matches

When a comment could be either auto-fix or propose-fix, prefer auto-fix if the
answer is unambiguous from the comment itself or the template. Prefer propose-fix
if research is needed to determine the correct value.

When a comment could be either propose-fix or needs-human, prefer propose-fix if
any research source is available. Only classify as needs-human when the answer
genuinely requires human judgment that no document can provide.

## Section Detection

When a comment includes a file path and line number, determine which STP/STD
section it targets. Read the file and scan upward from the comment line to find
the nearest heading.

### STP Sections

Match against both QualityFlow template headings and external repo headings:

| Section | QualityFlow Pattern | External Repo Pattern |
|:--------|:-------------------|:----------------------|
| Metadata | — | "STP Metadata", "Feature Maturity" |
| Overview | "Feature Overview" | "Feature Overview" |
| I.1 | "Requirement Review" | "Requirement & User Story Review", "Acceptance Criteria", "NFRs" |
| I.2 | "Known Limitations" | "Known Limitations" |
| I.3 | "Technology Challenges" | "Technology and Design Review", "Developer Handoff" |
| II.1 | "Scope of Testing" | "Scope of Testing", "Testing Goals", "Out of Scope", "Test Limitations" |
| II.2 | "Test Strategy" | "Test Strategy" |
| II.3 | "Test Environment" | "Test Environment" |
| II.3.1 | "Testing Tools" | "Testing Tools & Frameworks" |
| II.4 | "Entry/Exit Criteria" | "Entry Criteria" |
| II.5 | "Risks" | "Risks" |
| III | "Requirements-to-Tests" or "Test Scenarios" | "Test Scenarios & Traceability" |
| IV | "Sign-off" | "Sign-off and Approval" |

### STD Sections

For STD YAML files, map comments to the YAML key path (e.g., `scenarios[0].steps`).

## Consolidation

Before returning results, consolidate related comments:

- Multiple comments about the same rule violation on different lines → single
  auto-fix entry with multiple target lines
- Multiple comments requesting similar scenarios → single add-scenario entry
- Thread replies → attach to parent comment classification

## Error Handling

- **No comments provided:** Return empty classification with `total_comments: 0`
- **Comment body empty:** Skip the comment
- **Cannot determine section:** Classify with `section: "unknown"`, still attempt
  rule matching from comment body text alone
- **Mixed auto-fix and needs-human in single comment:** Classify as needs-human
  (conservative approach)
