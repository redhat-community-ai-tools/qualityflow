---
name: template-engine
description: Apply the official STP template structure to generated content
---

# Template Engine Skill

**Phase:** Utility
**User-Invocable:** false

## Purpose

Apply the official STP template structure to generated content.

## When to Use

Invoked by the **stp-generator** subagent to structure the final document.

## Template Location

**Priority order (use the first available):**

1. **repo_rules.stp_template** — from `project_context.repo_rules.stp_template` (fetched at
   runtime from the project's design docs repo via project-resolver Step 9). This is the
   **source of truth** — the team owns and maintains the template in their repo.
2. **Local config fallback** — `{project_context.config_dir}/templates/stp/stp-template.md`
   (used only if repo_rules.stp_template is null, meaning the fetch failed or was disabled).
3. **Skill-relative fallback** — `templates/stp-template.md` (relative to this skill directory).

Section requirements: `{project_context.config_dir}/templates/stp/section-requirements.md`
with fallback to `references/section-requirements.md` (relative to this skill).

**Important:** When `repo_rules.stp_template` is available, the template may use a different
format than the local copy (e.g., tables vs checkboxes for Section I). Always follow the
fetched template's format — it represents the team's current standard.

## Document Structure

**When the team has its own template** (`repo_rules.stp_template`, or
`{project_context.config_dir}/templates/stp/stp-template.md`): follow its exact structure,
section ordering, labels and formatting (tables vs checkboxes). That template is the authority,
and output-validator checks the STP against it: its sections, block labels, fixed item labels,
and the sub-fields its example items carry. The bundled structure below does not apply.

Whichever template is used, strip every `<!-- ... -->` comment and replace every example item
(a bracketed label such as `- **[Known Limitation]**`, or a `- **Risk:** [The risk]` entry)
with real items that keep its sub-fields, or with the block's "None" line. Example items are
guidance for the author, and reviewers reject STPs that keep them.

**When using the bundled template** (`templates/stp-template.md`, the last resort): the STP
MUST contain sections in this EXACT order:

```
1. Document Header: `{project_context.stp_header}` (from project config)
2. Feature Title: ## **[Title] - Quality Engineering Plan**
3. Metadata & Tracking (bullet list, 7 items; Feature Maturity has DP/TP/GA sub-items)
4. Document Conventions (bulleted, one term per line; omit terms every reviewer knows)
5. Feature Overview (2-8 sentences)
6. ---
7. Section I.1 - Requirement & User Story Review Checklist (5 checkbox items)
8. Section I.2 - Known Limitations (one bullet per limitation, each with a Sign-off line)
9. Section I.3 - Technology and Design Review (5 checkbox items)
10. Section II.1 - Scope of Testing + Testing Goals + Out of Scope + Test Limitations
11. Section II.2 - Test Strategy (14 checkboxes in 4 groups)
12. Section II.3 - Test Environment (bullet list, 10 items)
13. Section II.3.1 - Testing Tools & Frameworks (only NEW/SPECIAL tools)
14. Section II.4 - Entry Criteria (checkbox format)
15. Section II.5 - Risks (6 bold category labels + optional Other)
16. ---
17. Section III.1 - Requirements-to-Tests Mapping (bullet-based)
18. Section III.2 - Source Constants (table, optional — only when STP Builder extracted constants)
19. ---
20. Section IV - Sign-off and Approval (role-labelled reviewers and approvers)
```

## Key Design Rules

### Readability: one fact per line

Reviewers read these documents in a browser and on GitHub. Every list field is a
**nested bullet list** — one item per line, 2-space indents — never a paragraph
of `;`-joined clauses. A checklist item holds its template prompt lines
(`*List the key D/S requirements reviewed:*`, ...) with the answers as bullets
under each prompt. If a sub-item runs past two sentences, split it.

### Placeholders are for humans, and they stay visible

Anything only a person can supply — a sign-off, an agreement, a named owner, a
kickoff date — is left as the template's placeholder (`[Name/Date]`,
`[Name / @github-handle]`), never filled with "Pending", "TBD", "not recorded",
or a sentence explaining why it is missing. The placeholder is what tells the
reviewer where their input is needed.

### Section I is a Meta-Checklist

Section I items confirm the QE review PROCESS was followed. Each item is a checkbox
with the **verbatim label from the template**; the answers go under the
template's italic prompt lines beneath it:

```markdown
- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Incremental backup of stopped resources via the existing backup API (feature gate)
    - Backup status reports offline mode
```

Do NOT replace checkbox labels or prompt lines with feature content, and do not
collapse the answers into a `Comments:` paragraph. Mark `[x]` when the item is
answered; leave `[ ]` only with a stated reason under it.

### Metadata: Feature Maturity

`Feature Maturity` is three sub-items and nothing else:

```markdown
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: v5.1.0
```

Each value is a version or `N/A`. When Jira does not settle it (fix version and
target version disagree, no maturity label), write the most likely value from
the fix version followed by `[confirm]` — e.g. `GA: v5.1.0 [confirm]` — and
record the conflict once as an Entry Criteria item. Never nest maturity under
another field and never explain it in prose here.

### Section I.2 Known Limitations

Confirmed product constraints only (not test constraints — those are Test
Limitations in II.1; not scope decisions — those are Out of Scope):

```markdown
- **Only one offline incremental backup between resource starts**
  - A second incremental while the resource stays stopped is rejected
  - *Sign-off:* [Name/Date]
```

If there are none: `None — reviewed and confirmed with [Name/Date] that no feature limitations apply for this release.`

### Section I.3 is Technology and Design Review

5 checkboxes, same pattern as I.1: template label, then the template's italic
prompt lines with answers beneath.

### Section II.1: Scope, Goals, Out of Scope, Test Limitations

1. A short scope paragraph (what is tested, which maturity phase)
2. **Testing Goals** — one line each, ordered P0 → P1 → P2, in the template's
   format: `- **[P0]** As a backup provider, verify ...`. No goal ids, no
   scenario-id lists, no "(TS-01, TS-03)" suffixes. One goal per distinct user
   outcome — see scenario-builder "Goals and scenarios are not duplicated".
3. **Out of Scope** — each item:
   ```markdown
   - **Running resource backup scenarios**
     - *Rationale:* Covered by the existing CBT STP
     - *PM/Lead Agreement:* [Name/Date]
   ```
4. **Test Limitations** — constraints imposed on QE (no hardware, no partner
   environment), each with `  - *Sign-off:* [Name/Date]`; or
   `None — reviewed and confirmed that no test limitations apply for this release.`

### Section II.2 Uses Categorized Checkboxes

14 items in four groups, labels verbatim from the template:

**Functional:** Functional Testing, Automation Testing, Regression Testing, Self-Validation Testing
**Non-Functional:** Performance Testing, Scale Testing, Security Testing, Usability Testing, Monitoring
**Integration & Compatibility:** Compatibility Testing, Upgrade Testing, Dependencies, Cross Integrations
**Infrastructure:** Cloud Testing

Each has one `*Details:*` line. Unchecked items still need a justification.

### Section II.3.1 Lists Only New/Special Tools

Only list tools that are **new** or **different** from standard testing infrastructure.
The project's standard-tool list comes from
`project_context.review_rules.stp_rules.testing_tools.standard_tools` — tools on
that list (e.g., the project's default test framework or CLI) should NOT be listed.
Leave empty if using only standard tools.

### Section II.5 Risks

Six category labels, always present, in this order: Timeline/Schedule, Test
Coverage, Test Environment, Untestable Aspects, Resource Constraints,
Dependencies (plus **Other** only for a risk that fits none of them). A category
with a real risk gets the full entry:

```markdown
**Timeline/Schedule**

- **Risk:** The downstream implementation may land after code freeze
  - **Mitigation:** Prioritize P0 scenarios; align with the automation epic
  - *Estimated impact on schedule:* 2-4 weeks
  - *Sign-off:* [Name/Date]
```

The supplemental line is category-specific: *Estimated impact on schedule*,
*Areas with reduced coverage*, *Missing resources or infrastructure* (Test
Environment), *Alternative validation approach* (Untestable Aspects), *Current
capacity gaps*, *Dependent teams or components*. A category with no risk gets
one line: `- **Mitigation:** No risk identified — <one-sentence reason>.`

### No Related GitHub PRs Table

The upstream template does not include a Related GitHub Pull Requests table.
Do not add this section.

## Required Structure Counts

These are the bundled template's; a team's own template sets its own.

| Section | Format | Required Items |
|:--------|:-------|:---------------|
| Metadata | Bullet list | 7 (Enhancement, Feature Tracking, Epic Tracking, Feature Maturity with DP/TP/GA, QE Owner, Owning SIG, Participating SIGs) |
| I.1 Requirement Review | Checkbox list | 5 (Review Requirements, Understand Value and Customer Use Cases, Testability, Acceptance Criteria, NFRs) |
| I.2 Known Limitations | Bullets, each with Sign-off | 1+ items, or the "None — reviewed and confirmed" line |
| I.3 Technology Review | Checkbox list | 5 (Developer Handoff, Technology Challenges, API Extensions, Test Environment Needs, Topology) |
| II.1 Out of Scope | Bold bullets with Rationale + PM/Lead Agreement | 1+ items or "None" |
| II.1 Test Limitations | Bold bullets with Sign-off | 1+ items or "None" |
| II.2 Test Strategy | Categorized checkboxes | 14 items (4 + 5 + 4 + 1) |
| II.3 Test Environment | Bullet list | 10 (Cluster Topology, Platform Version, CPU Virtualization, Compute, Special Hardware, Storage, Network, Operators, Platform, Special Configs) |
| II.5 Risks | Bold category labels | 6 categories (+ optional Other); each has a Mitigation, and a Sign-off when a Risk is stated |
| III.1 Requirements Mapping | Bullet-based | No minimum; comprehensive coverage |
| III.2 Source Constants | Table | Optional; present only when STP Builder extracted constants from source code |

## Bullet and Checkbox Formatting

- Metadata uses `- **Field:** Value` format
- Checkbox items use `- [ ] **Label**` with the template's italic prompt lines as sub-items
- Risk categories are bold labels; entries under them use `- **Risk:**` / `- **Mitigation:**`
- Test environment uses `- **Component:** configuration details`
- Section III uses bullet items with requirement ID, summary, scenarios, tier, and priority

### Scenario IDs

Each scenario listed under a Section III.1 item carries a heading id
`TS-{NN}` (two-digit, sequential across the whole of Section III in document
order — e.g. `TS-01`, `TS-02`, ... `TS-12`, not reset per requirement row).
Format: `**TS-{NN}**: {scenario description}`. std-generator copies it verbatim
into the STD scenario's `stp_scenario_id`, so:

- **No STD yet** (`outputs/{JIRA_ID}/std/` has no STD YAML): any edit that adds,
  removes, merges or reorders scenarios renumbers them all, so the ids stay
  sequential in document order. Out-of-order ids (`TS-15`, `TS-47`, `TS-16`)
  read as missing scenarios to a reviewer.
- **STD exists**: ids are frozen. New scenarios take the next unused number;
  removed ids are not reused.

## Section Headers

Use exact markdown header levels:

- `#` for document title
- `##` for feature title
- `###` for major sections (Metadata, Feature Overview, I, II, III, IV)
- `####` for subsections (1, 2, 3...)

## Horizontal Rules

Place `---` horizontal rules:

- After Feature Overview (before Section I)
- After Section II.5 (before Section III) -- note: II.6 no longer exists
- After Section III (before Section IV)

## Input

```yaml
content:
  metadata:
    enhancement: <link>
    feature_in_jira: <link>
    jira_tracking: <link>
    feature_maturity: {dp: <version|N/A>, tp: <version|N/A>, ga: <version>}
    qe_owner: <name>
    owning_sig: <sig>
    participating_sigs: [...]
    document_conventions: [<term: definition>, ...]   # or [] to omit

  feature_overview: <2-8 sentence description>

  section_i:
    requirement_review:
      - check: Review Requirements
        done: "[ ]"
        details: <feature-specific observations as sub-items>
      - check: Understand Value and Customer Use Cases
        done: "[ ]"
        details: <feature-specific observations as sub-items>
      - check: Testability
        done: "[ ]"
        details: <feature-specific observations as sub-items>
      - check: Acceptance Criteria
        done: "[ ]"
        details: <feature-specific observations as sub-items>
      - check: Non-Functional Requirements (NFRs)
        done: "[ ]"
        details: <feature-specific observations as sub-items>
    known_limitations:
      - limitation: <confirmed product constraint>
        detail: <one line, optional>
        sign_off: "[Name/Date]"
      - ...
    technology_review:
      - check: Developer Handoff
        done: "[ ]"
        details: <feature-specific observations as sub-items>
      - ...

  section_ii:
    scope: <text>
    testing_goals: <prioritized P0/P1/P2 list>
    out_of_scope:
      - item: <item>
        rationale: <rationale>
        agreement: "[Name/Date]"
      - ...
    test_limitations:
      - limitation: <constraint imposed on QE>
        sign_off: "[Name/Date]"
      - ...
    test_strategy:
      - category: Core Testing
        items:
          - item: Functional Testing
            applicable: Y
            description: <description>
          - item: Automation Testing
            applicable: Y
            description: <description>
          - ...
      - category: Extended Testing
        items:
          - ...
      - category: Integration & Operations
        items:
          - ...
    environment:
      - component: Cluster Topology
        config: <configuration details>
      - ...
    tools:
      - category: Test Framework
        tools: <only NEW/SPECIAL tools or empty>
      - ...
    entry_criteria:
      - <extra feature-specific criteria>
      - ...
    risks:
      - category: Timeline/Schedule   # all 6 categories, Other only if needed
        risk: <risk, or null when none>
        mitigation: <mitigation, or "No risk identified — <reason>">
        supplemental: <category-specific line, when a risk is stated>
        sign_off: "[Name/Date]"       # when a risk is stated
      - ...

  section_iii:
    requirements_mapping:
      - requirement_id: <Jira issue key, or REQ-{JIRA_KEY}-{NN} for a fine-grained sub-requirement — never a ticket-less id>
        requirement_summary: <summary>
        test_scenarios: <scenarios, each with a stable TS-{NN} heading id — see Scenario IDs>
        tier: <Tier 1 or Tier 2>
        priority: <priority>
      - ...

  section_iv:
    reviewers: [...]
    approvers: [...]
```

## Output

Complete STP markdown document following the exact template structure.

## Validation Before Output

- [ ] Document starts with: `{project_context.stp_header}` (read from project config)
- [ ] Feature title format: `## **[Title] - Quality Engineering Plan**`
- [ ] Feature Overview section present (2-4 sentences)
- [ ] Document Conventions line present
- [ ] No Related GitHub PRs table
- [ ] Metadata is a bullet list with 7 items; Feature Maturity has exactly DP/TP/GA sub-items (no "Current Status" field)
- [ ] Section I.1 has 5 checkbox items (merged "Understand Value and Customer Use Cases")
- [ ] Section I.1/I.3 checkbox labels and italic prompt lines are **verbatim** template text; answers are bullets beneath the prompts
- [ ] Section I.2 is Known Limitations; every limitation has `*Sign-off:* [Name/Date]`
- [ ] Section I.3 is Technology and Design Review with 5 checkbox items
- [ ] Section II.1 contains Scope + Testing Goals + Out of Scope + Test Limitations
- [ ] Every Out of Scope item has `*Rationale:*` and `*PM/Lead Agreement:*`; every Test Limitation has `*Sign-off:*`
- [ ] Testing Goals use `- **[P0]** ...`, ordered by priority, no goal/scenario ids
- [ ] Test Strategy has 14 checkboxes (4 Functional, 5 Non-Functional, 4 Integration & Compatibility, 1 Infrastructure)
- [ ] Test Environment is a bullet list with 10 items
- [ ] Testing Tools lists only NEW/SPECIAL tools
- [ ] Entry Criteria uses checkbox format
- [ ] Risks: the 6 category labels are present; each has a Mitigation; each stated Risk has its supplemental line and `*Sign-off:* [Name/Date]`
- [ ] Human-only fields keep the template placeholder (`[Name/Date]`), never "Pending"/"TBD" prose
- [ ] Section II.6 does NOT exist (Known Limitations moved to I.2)
- [ ] Section III.1 uses bullet-based format (not table)
- [ ] Each Section III.1 item has exactly one tier
- [ ] Section III.2 (Source Constants) present only if STP Builder extracted constants
- [ ] Source Constants values are backtick-wrapped and verbatim from source code
- [ ] Requirement IDs are Jira issue keys, or `REQ-{JIRA_KEY}-{NN}` for a fine-grained
  sub-requirement — never a ticket-less id (bare `REQ-{NN}` or `REQ-{WORD}-{NN}` where
  `{WORD}` is not the ticket's actual key)
- [ ] Each Section III.1 scenario has a stable `TS-{NN}` heading id (see Scenario IDs)
- [ ] Horizontal rules in correct positions (after Overview, after II.5, after III)
- [ ] No extra sections added

## Abstraction Level Enforcement

All STP content must be written from the **user/QE perspective**, not the developer/implementation perspective:

- **Replace** API field names, CRD spec fields, and internal struct names with user-observable descriptions
- **Replace** internal component references (controller, reconciler, handler) with feature-level behavior descriptions
- **Acceptance criteria** must describe user-observable outcomes ("Resource starts successfully") not internal behavior ("controller reconciles resource status")
- If `project_context.review_rules.stp_rules.abstraction` is available, use `internal_to_user_mappings` for project-specific translations

### Regression Scenarios

Regression testing belongs in the **Test Strategy (II.2)** Regression Testing checkbox, NOT as individual scenarios in Section III. Reference existing regression test suites in the Regression Testing details. Do not generate regression-specific scenarios for Section III.

## Source Constants Section (III.2) — Optional

This section is present ONLY when the STP Builder's Step 3.5 extracted
literal constants from the source code. It provides verbatim values
that downstream STD generation must use without modification.

**Format:**

```markdown
#### Section III.2 — Source Constants

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|----------|-------|------------|------|
| SENTINEL | `# --- managed section - do not edit ---` | pkg/scripts/sync.sh | 14 |
| SCRIPT_PATH | `pkg/scripts/sync.sh` | PR diff header | — |
```

**Rules:**

- Values MUST be wrapped in backticks to preserve exact content
- Each row must have a Source File and Line (use `—` for PR-derived paths)
- If a constant was not found, its Value cell is `[NOT FOUND]`
- This section is consumed verbatim by the STD Generator — never summarize or paraphrase the values
- Omit this section entirely if no constants were extracted

## Prohibited Content

- Related GitHub Pull Requests table
- Appendix sections
- Summary sections at end
- Glossary sections
- References sections
- Sub-tables A/B under Test Strategy
- Decision/Justification blocks
- YAML/JSON configuration blocks
- Shell command examples
- Code snippets
- Standard tools in Testing Tools section (list only tools NOT in `stp_rules.testing_tools.standard_tools`; if feature uses only standard tools, write "Standard tooling — no additional tools required")
- Section II.6 (Known Limitations is now I.2)
- "Current Status" in Metadata
- API field names, CRD names, or internal component names in acceptance criteria or scenario descriptions
- Regression-specific scenarios in Section III (regression belongs in Test Strategy II.2)
