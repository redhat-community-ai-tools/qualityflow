# STP Section Requirements Reference

Section-by-section requirements for the bundled fallback template
(`../templates/stp-template.md`), aligned with the upstream CNV template
(`RedHatQE/openshift-virtualization-tests-design-docs`, `stps/stp-template/stp.md`).
When a project fetches its own template (`repo_rules.stp_template`), that
template wins. The formatting rules — one fact per line, visible placeholders,
Feature Maturity, sign-offs — are in `../SKILL.md` → Key Design Rules.

## Section Overview

| Section | Required | Format | Notes |
|:--------|:---------|:-------|:------|
| Document Header | Yes | Heading | Must be exact text |
| Feature Title | Yes | Heading | Must include "Quality Engineering Plan" |
| Metadata & Tracking | Yes | Bullet list, 7 items | Feature Maturity has DP/TP/GA sub-items; no "Current Status" |
| Document Conventions | If needed | Bullet list | One term per line; feature-specific terms only |
| Feature Overview | Yes | Prose | 2-8 sentences, user perspective, states the maturity phase covered |
| Section I.1 | Yes | Checkbox list, 5 items | Template prompt lines, answers as bullets |
| Section I.2 | Yes | Bullet list | Known Limitations, each with `*Sign-off:* [Name/Date]` |
| Section I.3 | Yes | Checkbox list, 5 items | Technology and Design Review |
| Section II.1 | Yes | Mixed | Scope + Testing Goals + Out of Scope + Test Limitations |
| Section II.2 | Yes | Checkbox list, grouped | 14 items: 4 + 5 + 4 + 1 |
| Section II.3 | Yes | Bullet list, 10 items | All components required |
| Section II.3.1 | Yes | Bullet list, 3 items | Only NEW/SPECIAL tools |
| Section II.4 | Yes | Checkbox list | 2 standard + feature-specific |
| Section II.5 | Yes | Bold category labels | 6 categories (+ Other when needed) |
| Section III | Yes | Bullet list | Requirements-to-Tests Mapping |
| Section IV | Yes | Bullet list | Role-labelled reviewers and approvers |

## Sections NOT in Template

Do NOT include:

- Related GitHub Pull Requests table (not in upstream template)
- Appendix, Summary, Glossary, References
- Sub-tables (A, B) under Test Strategy
- Section II.6 (Known Limitations is I.2)

## Detailed Requirements

### Metadata & Tracking (7 items)

- **Enhancement(s)** — VEP / design doc links
- **Feature Tracking** — feature-level Jira
- **Epic Tracking** — the feature's tracking epic (not the QE Jira)
- **Feature Maturity** — exactly three sub-items: `DP:`, `TP:`, `GA:` (version or `N/A`;
  an unsettled value carries `[confirm]`)
- **QE Owner(s)** — name and contact
- **Owning SIG**
- **Participating SIGs**

A parent STP of a multi-SIG feature adds **Child STPs**; single-SIG STPs omit it.

### Section I.1 — Requirement & User Story Review Checklist (5 checkboxes)

| Checkbox | Prompt lines (verbatim, italic) |
|:---------|:--------------------------------|
| Review Requirements | *List the key D/S requirements reviewed:* |
| Understand Value and Customer Use Cases | *Describe the feature's value to customers:* / *List the customer use cases identified:* |
| Testability | *Note any requirements that are unclear or untestable:* |
| Acceptance Criteria | *List the acceptance criteria:* / *Note any gaps or missing criteria:* |
| Non-Functional Requirements (NFRs) | *List applicable NFRs and their targets:* / *Note any NFRs not covered and why:* |

Answers are bullets beneath each prompt line; use cases in user-story form;
each acceptance criterion its own bullet.

### Section I.2 — Known Limitations

One bold bullet per confirmed product constraint, a detail line if needed, and
`*Sign-off:* [Name/Date]`. Or the "None — reviewed and confirmed with [Name/Date]" line.

### Section I.3 — Technology and Design Review (5 checkboxes)

| Checkbox | Prompt lines (verbatim, italic) |
|:---------|:--------------------------------|
| Developer Handoff/QE Kickoff | *Key takeaways and concerns:* |
| Technology Challenges | *List identified challenges:* / *Impact on testing approach:* |
| API Extensions | *List new or modified APIs:* / *Testing impact:* |
| Test Environment Needs | *See environment requirements in Section II.3 and testing tools in Section II.3.1* |
| Topology Considerations | *Describe topology requirements:* / *Impact on test design:* |

### Section II.1 — Scope of Testing

1. **Scope paragraph** — what is tested, which maturity phase.
2. **Testing Goals** — `- **[P0]** <goal>`, one per line, P0 → P1 → P2, user
   perspective, at least one negative/failure-path goal per P0 functional goal.
3. **Out of Scope** — `- **Item**` / `  - *Rationale:*` / `  - *PM/Lead Agreement:* [Name/Date]`.
4. **Test Limitations** — `- **Item**` / `  - *Sign-off:* [Name/Date]`, or the "None" line.

### Section II.2 — Test Strategy (14 checkboxes)

**Functional:** Functional Testing, Automation Testing, Regression Testing, Self-Validation Testing
**Non-Functional:** Performance Testing, Scale Testing, Security Testing, Usability Testing, Monitoring
**Integration & Compatibility:** Compatibility Testing, Upgrade Testing, Dependencies, Cross Integrations
**Infrastructure:** Cloud Testing

Each has a `*Details:*` line; unchecked items state why.

### Section II.3 — Test Environment (10 items)

Cluster Topology, Platform & Product Version(s), CPU Virtualization, Compute
Resources, Special Hardware, Storage, Network, Required Operators, Platform,
Special Configurations. "N/A" means explicitly not applicable; none left empty.

### Section II.3.1 — Testing Tools & Frameworks (3 items)

Test Framework, CI/CD, Other Tools — only tools that are new or different from
the standard infrastructure.

### Section II.4 — Entry Criteria

The two standard checkboxes plus feature-specific ones, `[x]` only when done
and consistent with Dependencies and Test Limitations.

### Section II.5 — Risks (6 categories + Other)

Bold labels in order: Timeline/Schedule, Test Coverage, Test Environment,
Untestable Aspects, Resource Constraints, Dependencies. Under each: either a
full entry (`**Risk:**`, `**Mitigation:**`, the category's supplemental line,
`*Sign-off:* [Name/Date]`) or one `**Mitigation:** No risk identified — <reason>.`
line. Add **Other** only for a risk no category fits.

### Section III — Requirements-to-Tests Mapping

**No minimum item requirement.** Bullet-based:

```markdown
- **[PROJ-72329]** — As a user, I want to hotplug a network interface to a running VM
  - *Test Scenario:* **TS-01**: [Tier 1] Verify hotplug attaches the interface and traffic flows
    - *Priority:* P0
```

Each requirement: ID in bold brackets, user-story summary, and per scenario a
`TS-{NN}` id (sequential in document order — see SKILL.md Scenario IDs), the
inline classification tag (`[Tier N]` in tier mode, `[functional]` /
`[integration]` / `[e2e]` / `[unit]` in auto mode — std-orchestrator parses it
from this line, so never move it to a separate `*Test Type:*` line) and the
priority. No two scenarios verify the
same outcome (scenario-builder "Goals and scenarios are not duplicated").

### Section IV — Sign-off and Approval

Reviewers (QE, Development) and approvers (QE Lead, Dev Lead, Product Manager),
each `Role: [Name / @github-handle]` until a person fills it.

## Horizontal Rules

Place `---` in these locations:

1. After Feature Overview (before Section I)
2. After Section II.5 Risks (before Section III)
3. After Section III (before Section IV)

## Prohibited Sections

Do NOT add:

- Related GitHub Pull Requests table
- Appendix
- Summary
- Glossary
- References
- Any sections after Section IV
- Section II.6
