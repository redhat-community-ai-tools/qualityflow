---
name: stp-reviewer
description: Semantic QE review of STP documents against domain rules, Jira source data, and quality standards
model: claude-opus-4-6
version: 1.1.0
---

# STP Reviewer Skill

**Phase:** Post-Generation Review · **User-Invocable:** false
Invoked by the **review-stp** command after `/stp-builder` generates an STP.

## Purpose

A comprehensive **semantic QE review** of a generated STP — the quality, accuracy, and
completeness judgment a human QE reviewer would apply. NOT structural validation:
output-validator owns section counts, table row counts, and markdown formatting. This
skill owns Rule A–Q compliance, coverage gaps, scenario quality, risk accuracy,
cross-section contradictions, and source-data comparison.

**Zero-trust principle:** never trust the STP's own claims. Verify every requirement
summary, scope item, and metadata field against the fetched Jira source data.
"Requirements reviewed: Done" with acceptance criteria missing from Section III is a
CRITICAL finding.

## Two-Layer Review Architecture

- **Layer 1 (General):** shared pipeline rules embedded in this file — always active.
- **Layer 2 (Project-specific):** examples, component lists, and mappings from
  `{project_context.config_dir}/review_rules.yaml`, passed as context by review-stp.

Loaded `stp_rules.*` keys refine individual rules (component lists, term mappings,
thresholds, version sources). The full key→rule mapping table is in
**`reference/key-maps.md`** in this skill directory — Read it only when review_rules is
actually loaded and you need to resolve a key. **Graceful degradation:** with no
`review_rules.yaml`, all rules still apply using the built-in defaults below; config adds
precision, never coverage.

## Input

```yaml
stp_file_path: "outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md"
jira_data:
  main_issue: <fetched Jira issue data>
  linked_issues: <linked issues array>
  subtasks: <subtasks array>
project_context: <from project-resolver, includes repo_rules>
review_rules: <from review_rules.yaml, if available>
```

### repo_rules Integration

When `project_context.repo_rules` is available:
- **`stp_template`** — authoritative template for Rule B; compare against the fetched
  template, not the local copy.
- **`stp_guide`** — context for testing goals (SMART criteria, P0/P1/P2), risk
  categories, entry/exit criteria, STP lifecycle.
- **`testing_tiers`** — defines Tier 1 vs Tier 2 for this project; use for Rule J and
  Dimension 3 tier-distribution checks.

## Output

Review report written to `outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md`.

---

## Review Dimensions

7 dimensions; every finding is classified:

| Severity | Meaning | Impact on Verdict |
|:---------|:--------|:------------------|
| **CRITICAL** | Factual error, missing coverage, or rule violation making the STP unusable | Blocks approval |
| **MAJOR** | Significant quality issue to address | Flags for attention |
| **MINOR** | Improvement suggestion / stylistic | Informational only |

---

### Dimension 1: Domain Judgment Rule Compliance (Rules A–Q)

Check each rule A through Q against the STP, sampling the relevant sections.

#### Rule A — Abstraction Level

Check every Scope item (II.1), Testing Goal, Section III scenario, and Requirement
Summary. Litmus test: *"Would this sentence appear in customer-facing release notes?"*
YES → PASS; NO → flag and suggest a rewrite. Requirement Summaries must use user-story
format ("As a [role], I want...").

**Allowlist (never flag):** API, CRD, CustomResource, RBAC, webhook, operator (as
deployed software), feature gate (as availability control), pod, namespace, node,
cluster, CLI tools from `project.yaml` `scope_boundaries.cli_tools`, plus config
`abstraction.qe_terms_allowed`. Apply the litmus test only to genuinely borderline terms.

**CRITICAL (in Scope/Goals/Scenarios):** non-allowlisted internal components
(controller, reconciler, evaluator, sync, annotation, label, trigger, condition; plus
config `internal_components`); implementation verbs (reconcile, sync, trigger,
propagate); low-level API verbs as test descriptions ("deletecollection", "PATCH the
CR"); how-to-run-tests references ("run pytest with...", "execute via CI"); internal
code paths ("pkg/storage/handler.go"); test framework constructs (decorators, markers,
fixtures — STD material); cross-document leaks ("the STD will describe..." — each
document is self-contained at its abstraction level); internal infrastructure names
where user-level concepts exist (config `internal_to_user_mappings`).

**MAJOR (Requirement Summary):** missing "As a [role]" format; technical subject instead
of user role ("The controller..." vs "As an admin...").

**Acceptable locations for internal mechanisms** (or config `acceptable_locations`):
Technology Challenges (I.3 sub-items), Risks (II.5), checkbox sub-items, Known
Limitations (I.2).

#### Rule A.2 — Language Precision

Check Scope items, Goals, Scenarios.
**MAJOR:** anthropomorphizing infrastructure ("without the service noticing"); colloquial
phrasing ("works fine", "basically"); hedging ("should probably").
**MINOR:** vague qualifiers ("properly", "as expected") lacking measurable criteria.
**Acceptable:** "with minimal service disruption"; "within 30 seconds"; standard QE
vocabulary (verify/validate/confirm/assert).

#### Rule B — Section I Meta-Checklist

Verify Section I structure/format (tables vs checkboxes, columns, ordering) against the
template from `repo_rules.stp_template` (preferred) or
`{project_context.config_dir}/templates/stp/stp-template.md`. Expected: I.1 = 5 checkbox
items (Review Requirements; Understand Value and Customer Use Cases; Testability;
Acceptance Criteria; NFRs), sub-bullets indented; I.2 Known Limitations (moved from
II.6); I.3 = 5 checkbox items (Developer Handoff; Technology Challenges; API Extensions;
Test Environment Needs; Topology), sub-bullets indented.

**CRITICAL — empty required fields:** Section III empty (the core of the STP); a checked
checkbox with empty sub-items; unfilled placeholder text.
**MAJOR:** sub-items holding acceptance-criteria lists or feature-specific technical
detail belonging elsewhere; value propositions instead of review observations; STP not on
the current template version (stale sections, wrong checkbox/table format).

#### Rule C — Prerequisites vs Test Scenarios

Section III rows must describe **testable behavior**, not configuration. Prerequisite
patterns: "X must be set/enabled/configured", "cluster needs X", "requires X deployed",
"feature gate must be enabled" (unless the scenario is "verify the feature gate controls
availability"). Prerequisites belong in Test Environment (II.3), Entry Criteria (II.4),
or Special Configurations.
**CRITICAL:** a prerequisite as a Section III scenario with no corresponding behavioral
verification.

#### Rule D — Dependencies = Team Delivery

Dependencies checkbox (II.2), if checked, must list **another team's delivery** — a
change merged/delivered/released before this can be tested (config
`dependency_examples`) — not pre-existing infrastructure.
**MAJOR:** infrastructure listed as a dependency (config
`infrastructure_not_dependency`) — that is a test environment requirement.

#### Rule E — Upgrade Testing Applicability

Criterion: "If a cluster upgrades N→N+1, must data/state created by this feature be
preserved or converted?" YES → checked; NO → N/A. Indicators: config
`persistent_state_indicators`.
**MAJOR:** checked for a one-time operation (e.g. patching a spec field); unchecked for a
feature storing configuration in persistent resources.

#### Rule F — Version Derivation

Compare version rows in II.3 against the Jira version field (config
`metadata.version_source`, e.g. `fix_version`) and `project_context.versioning`.
**MAJOR:** hardcoded older versions; missing version when Jira has one.
**Acceptable:** "TBD" when the Jira field is unset.

#### Rule G — Testing Tools Section

II.3.1 lists only NON-standard tools (standard lists: config `standard_tools` /
`standard_frameworks`; general principle — infrastructure-standard tools don't belong).
**MINOR:** standard framework/CLI/CI-CD tools listed (unless feature-specific).
**Acceptable:** empty list; genuinely non-standard tools.

#### Rule G.2 — Environment Specificity

**MINOR:** II.3 entries that are generic boilerplate — identical for any unrelated
feature, no feature-specific reason stated.

#### Rule H — Risk Deduplication

**MAJOR:** a II.5 risk duplicating information already in Test Environment (II.3). Risks
should describe: timeline uncertainties, coverage gaps, untestable aspects, team resource
constraints, external dependencies, unknown failure modes.

#### Rule I — QE Kickoff Timing

Developer Handoff (I.3) must place kickoff in the **design phase**, before implementation.
**MAJOR:** "after PR is merged", "after implementation", "post-merge review".
**Acceptable:** design-phase kickoff; "kickoff scheduled/completed" (with date).

#### Rule J — One Tier Per Row

**CRITICAL:** any Section III item with more than one tier ("Tier 1 / Tier 2", tiers
joined by comma or "and"). Exactly ONE tier per item.

#### Rule K — Cross-Section Consistency

| Check | Sections | Must be true |
|:------|:---------|:-------------|
| 1 | Scope ↔ Out of Scope (II.1) | No item in both |
| 2 | Goals (II.1) ↔ Limitations (I.2) | Goals don't promise what limitations exclude |
| 3 | Section I sub-items ↔ Limitations | Sub-items don't claim excluded capabilities |
| 4 | Strategy (II.2) ↔ Section III | Unchecked strategy ⇒ no scenarios of that type |
| 5 | Entry Criteria (II.4) ↔ Environment (II.3) | Environment references consistent |
| 6 | Scope ↔ Section III | Every scope item has ≥1 scenario |
| 7 | Out of Scope ↔ Section III | No scenarios test out-of-scope items |

**Severity:** CRITICAL for Scope↔Out-of-Scope or Goals↔Limitations contradictions;
MAJOR otherwise.

#### Rule L — Section Content Validation (Misplaced Content)

| Section | Contains | NOT |
|:--------|:---------|:----|
| Scope (II.1) | Testable capabilities (checkboxes) | Implementation detail, how to run tests |
| Out of Scope (II.1) | Exclusions + rationale + PM ack | Limitations (→ I.2) |
| Goals (II.1) | User-observable outcomes | Internal mechanism validations |
| Strategy (II.2) | Checkboxes + feature-specific sub-items | Detailed scenarios (→ III) |
| Dependencies (II.2) | Other-team deliveries + Jira refs | Infrastructure (→ II.3) |
| Environment (II.3) | Infrastructure/platform needs | Risks (→ II.5) |
| Tools (II.3.1) | Non-standard tools only | Standard tools |
| Risks (II.5) | Genuine uncertainties + mitigations | Environment requirements (→ II.3) |
| Limitations (I.2) | Feature boundaries/restrictions | Out-of-scope items (→ II.1) |
| Section III | Testable behaviors + requirement mapping | Prerequisites, setup instructions |

**MAJOR:** content in the wrong section — scenarios in Scope; infrastructure as
Dependencies; environment requirements as Risks; test-execution instructions in
Scope/Goals; user stories in Technology Challenges (I.3) instead of I.1; Testability
describing specific test cases (Testability = *whether* testable, not *what* to test);
step-level detail in the general description. **MINOR:** borderline cases.

**Limitation vs Out-of-Scope:** Limitation (I.2) = a constraint *prevents* testing ("not
supported by the product"); Out of Scope (II.1) = a deliberate *decision* not to test
("follow-up cycle"). **MAJOR:** item misfiled per this distinction, either direction.
**MINOR:** out-of-scope item with risk implications but no II.5 entry acknowledging the
gap with a mitigation.

#### Rule M — Deletion Test (ISTQB)

Per section: "If removed, would the Go/No-Go decision be hindered?" Content not informing
that decision is excess.
**MAJOR:** background duplicating Jira/VEP (reference, don't duplicate); implementation
description beyond what's needed to know what to test; Section III material in Section I;
CI-job-granularity environment detail. **MINOR:** correct but verbose.

#### Rule N — Link/Reference Validation

Extract all URLs (VEP, Jira, PR, enhancement, docs). Check: valid syntax; correct domain
for the content type; not a personal fork (`github.com/username/...`).
**CRITICAL:** link to a completely wrong resource (wrong Jira project, different SIG's
VEP). **MAJOR:** VEP/enhancement on the wrong domain for the feature type; stale
references (resolved bug refs, deprecated technologies, outdated identifiers); Jira
reference ≠ input Jira ID; PR URLs to unrelated repos. **MINOR:** personal-fork links
(prefer upstream); valid links unverifiable offline.
ALL link/reference findings report under this rule (consolidates former Dim 5/7 checks).

#### Rule O — Untestable Aspects Documentation

Any item marked "not testable at this stage"/"cannot be verified"/"deferred" requires:
(1) a reason, (2) a timeline/condition for testability, (3) a II.5 risk entry.
**CRITICAL — priority-testability contradiction:** a P0/GA-blocking item documented as
untestable — cannot be both highest-priority and untestable. Resolutions: downgrade to
P2, add a timeline, move to a follow-up STP, or resolve the blocker.
**MAJOR:** missing reason, timeline, or risk entry. **MINOR:** all three present but
timeline vague ("sometime in the future").

#### Rule P — Testing Pyramid Efficiency (Fix-Scope Awareness)

**Activation guard:** ONLY when issue type is Bug/Customer Case/Defect AND PR data exists
(`fix_scope` not null). Otherwise PASS: "N/A — not a bug ticket or no PR data available."

**Step 1 — classify fix scope (deterministic).** From `fix_scope.key_changes` /
`fix_scope.files_changed`: count distinct top-level packages (test files excluded); count
modified functions (excluding tests); check whether any modified file's package path has
cluster-facing indicators (`client-go`, `controller-runtime`, `k8s.io/api`, or cluster
packages from `components.yaml`).

| Packages | Functions | Cluster | Classification |
|:---------|:----------|:--------|:---------------|
| 1 | 1 | No | `single-function-isolated` |
| 1 | 1 | Yes | `single-function-cluster` |
| 1 | 2+ | Any | `single-package` |
| 2+ | Any | Any | `multi-package` |
| Any | Any | PR mentions "user workflow"/"end-to-end" | `multi-step-workflow` |

`files_changed: "large"` (>5k lines) → `multi-package`.

**Step 2 — tier efficiency.** Per scenario, is the tier the minimum with equivalent
coverage?

| Classification | Minimum Viable Tier |
|:---------------|:--------------------|
| `single-function-isolated` | Unit Tests (mocked test validates the fix) |
| `single-function-cluster` | Tier 1 (single operation in cluster) |
| `single-package` | Tier 1 (single feature verification) |
| `multi-package` | Tier 2 (cross-component interaction) |
| `multi-step-workflow` | Tier 2 (full workflow verification) |

**MAJOR:** all scenarios for a single-function fix are Tier 2; customer case with a
1-file fix and no Unit/Tier 1 scenario. **MINOR:** Tier 2 for a small fix — fine for
regression confidence, but a lower-tier test should also exist. **NOT a finding:** Tier 1
(verify fix) + Tier 2 (verify workflow) together (ideal); feature tickets or
multi-package bugs at Tier 2. Recommend the minimum viable tier AND keeping the
higher-tier test.

#### Rule Q — Requirement ID Format

**MAJOR:** bare `REQ-{NN}` or `REQ-{WORD}-{NN}` where `{WORD}` is not the Jira ticket's
actual key (e.g. `REQ-01`, `REQ-NAD-001`) — collides across tickets, untraceable.
**Acceptable:** a Jira key verbatim (`PROJ-72329`) or `REQ-{JIRA_KEY}-{NN}`
(`REQ-PROJ-72329-01`).

---

### Dimension 2: Requirement Coverage

Compare Section III against Jira: read the main issue's acceptance criteria and each
linked issue; check every criterion/user story has a corresponding scenario.

- **CRITICAL:** acceptance criterion with no scenario.
- **CRITICAL:** coverage below threshold — `review_rules.stp_rules.coverage_threshold`
  (default 0.70). If `covered/total` is below it: "Acceptance criteria coverage is {X}%
  ({covered}/{total}). Minimum threshold is {threshold}%. {uncovered list}." Blocks
  approval regardless of individual findings so incomplete STPs don't reach STD.
- **CRITICAL:** any uncovered P0/GA-blocking criterion — sufficient even above threshold.
- **MAJOR:** linked issue's use case in no scenario; Jira mentions error handling / edge
  cases but no negative scenarios exist.
- **MINOR:** feature-overview capability not tested.

**Metrics to report:**
```
acceptance_criteria_covered: X/Y
acceptance_criteria_coverage_rate: X/Y (percent%)
p0_criteria_covered: X/Y
linked_issues_reflected: X/Y
negative_scenarios_present: true/false
edge_cases_identified: X (from Jira) / Y (in STP)
```

**Value Proposition & Use Case Quality** — must be customer-facing, accurate, actionable.
**MAJOR:** internal audience framing — QE/Dev/SRE listed as "users" (BAD: "For QE —
internal benchmarking"; GOOD: "Provides users with published performance thresholds");
use cases describing test activities instead of user scenarios; stated value not matching
the actual capability per Jira/VEP; value duplicated from a parent feature without what
this feature adds. **MINOR:** empty/generic use case section.

**Proactive Scope Completeness Probing** — actively ask "what about X?" (the most common
human-review feedback):
- **UI — MAJOR:** user-facing component exists (linked UI Jira, "UI" in description,
  Usability checked) but UI testing is in neither Scope nor Out of Scope with rationale
  + PM ack.
- **Negative/edge — MAJOR:** <2 negative scenarios among 10+ total. Suggest by type —
  network: connectivity loss, conflicting configs; storage: insufficient storage,
  concurrent ops on one volume; RBAC: unauthorized users, escalation attempts.
- **OS/platform — MINOR:** one OS only; if acceptable, Out of Scope with PM sign-off.
- **Monitoring — MAJOR:** Monitoring checked in II.2 but no monitoring/alerting scenario
  in III — add scenarios or uncheck.
- **Regression — MINOR:** checked but vague — which tests must pass, which behaviors
  must not change?
- **Cross-SIG — MAJOR:** 2+ Participating SIGs but a SIG's area has no scenarios — add
  cross-team scenarios or explain why not needed.
- **Out-of-scope ack — MINOR:** exclusion lacking rationale / PM sign-off.
- **Invalid scope exclusion (subtractive) — MAJOR:** a scenario tests behavior the
  feature explicitly does not support (VEP non-goals / user stories) — remove or
  reclassify; undefined behavior cannot be validated.
- **Layered-product ownership** (only if config `scope.layered_product` defined; the
  product assumes platform features work) — **MAJOR:** scenario exercising only
  platform-level functionality with no product-specific involvement — may belong to the
  platform team; verify or justify. With 2+ SIGs, per-scenario ownership must be clear.
- **Epic-anchored — MAJOR:** each major epic requirement must be covered by a scenario
  or explicitly excluded with justification; neither → flag it.

---

### Dimension 3: Scenario Quality

| Criterion | Good | Bad |
|:----------|:-----|:----|
| Specificity | "Verify service reachable after config change" | "Verify feature works" |
| User perspective | "Verify user sees updated resource after edit" | "Verify internal sync succeeds" |
| Brevity | 5-10 words, single phrase | Multi-sentence |
| Actionability | Clear what to test | Vague/ambiguous |
| Uniqueness | Distinct behavior per scenario | Duplicates/overlap |

**CRITICAL:** generic scenario ("Verify feature works correctly"). **MAJOR:**
internal-mechanism language; duplicate scenarios. **MINOR:** >15 words.

**Distribution:** positive AND negative present; reasonable P0/P1/P2 spread (P0 for
core, not everything); appropriate Tier 1/2 split (complex workflows Tier 2); ≥2
scenarios per distinct requirement.

**Priority heuristics:** primary capability's first positive scenario / core happy path
→ P0; error handling & negative → P1/P2; regression & backward compat → P1; edge cases
→ P2; integration → P1/P2.
**MAJOR:** primary positive scenario not P0; ALL scenarios P0 (inflation); error handling
above core. **MINOR:** >50% P0; no P2 at all (under-differentiation).

---

### Dimension 4: Risk & Limitation Accuracy

Evaluate against Jira/PR data. Per risk: genuine uncertainty or a known environment
requirement (Rule H overlap)? Actionable mitigation? Status tracked? Per limitation:
matches Jira/PR feature boundaries? Jira limitations missing from the STP? STP
limitations contradicting Jira?
**MAJOR:** Jira-mentioned limitation absent from I.2; vague mitigation ("Monitor the
situation"). **MINOR:** all risk statuses unchecked (expected for draft — note it).

---

### Dimension 5: Scope Boundary Assessment

Extract what the feature does from Jira; compare against Scope and Out of Scope (II.1).
**CRITICAL:** scope claims capabilities the feature doesn't provide; scope includes
unsupported/invalid user behavior (VEP/user-story non-goals — undefined results can't be
validated). **MAJOR:** important capability missing from scope; out-of-scope item that
should be tested; scope not traceable to epic goals / linked user stories.
**MINOR:** scope too broad for the ticket.

---

### Dimension 6: Test Strategy Appropriateness

Per II.2 checkbox: correct checked state? Substantive, feature-specific sub-items?

**Classification** — config `strategy.always_y` (always checked) and
`strategy.requires_justification_for_y`; general defaults: Functional and Automation
always checked (QualityFlow generates automated tests); Performance only with
latency/throughput requirements; Security only when RBAC/auth/security boundaries change;
Usability only with a UI component; Upgrade per Rule E; Dependencies per Rule D.

**MAJOR:** Functional unchecked; checked item with generic sub-items ("Will be tested").
**MINOR:** unchecked item without justification.

**N/A vs Y challenge** — question checked states proactively:
- **MAJOR (should be unchecked):** Performance checked but sub-items only say "completes
  within acceptable time", no SLA/benchmark (that's functional); Security checked citing
  only standard RBAC; Usability checked with no UI/UX impact (API-only).
- **MAJOR (should be checked):** Upgrade unchecked despite persistent state (Rule E);
  Monitoring unchecked despite new metrics/alerts; Regression unchecked for a GA feature.
- **MINOR — Technology Challenges misuse (I.3):** item that is a test requirement, not a
  genuine challenge ("need to configure storage backend" = requirement; "backend behavior
  differs across vendors" = challenge).
- **MAJOR — unchecked cross-referencing:** rationale must be consistent with
  Out-of-Scope; infrastructure type alone is insufficient; if another team covers it,
  name the team ("{team} covers {area} testing", not "covered elsewhere").
- **MINOR:** unchecked checkbox with no rationale at all.

---

### Dimension 7: Metadata Accuracy

| Field | Validation |
|:------|:-----------|
| Enhancement(s) | Resolve to actual enhancement proposals |
| Feature Tracking | Correct parent/feature issue (Jira Feature Link) |
| Epic Tracking | Matches input Jira ID (Epic + Parent keys) |
| QE Owner(s) | TBD acceptable for draft |
| Owning SIG | Matches Jira labels/components (config `metadata.sig_field`) |
| Participating SIGs | Reasonable for scope |

**MAJOR:** Owning SIG ≠ Jira component/label; Feature Tracking → wrong issue;
cross-artifact naming inconsistency (STP title vs Jira summary vs STD file name — one
name across STP/STD/code/Jira); approver/role assignments without actual authority.
Link/stale-reference checks report under Rule N.

---

## Review Report Format

Markdown with these sections, in order:

1. `# STP Review Report: {JIRA_ID}` + header lines: Reviewed (STP path), Date,
   Reviewer `QualityFlow Automated Review (v1.1.0)`, Review Rules Schema
   (`review_rules._extraction_metadata.schema_version` or "N/A").
2. `## Verdict: {APPROVED | APPROVED_WITH_FINDINGS | NEEDS_REVISION}` — human-readable.
3. `## Summary` — table: Dimensions reviewed (N/7), Critical/Major/Minor finding counts,
   Confidence (HIGH/MEDIUM/LOW).
4. `## Findings by Dimension` — one subsection per dimension. Dim 1 (`Rule Compliance
   (Rules A–Q)`): table, one row per rule A…Q — `Rule | Status (PASS/WARN/FAIL) |
   Finding`. Dim 2: coverage metrics table + uncovered criteria list. Dim 3: counts
   table (total, per tier, per priority, positive/negative) + per-scenario findings.
   Dims 4–7: findings prose.
5. `## Recommendations` — numbered, severity-ordered, each prefixed
   **[CRITICAL]**/**[MAJOR]**/**[MINOR]**.
6. `## Confidence Notes` — factor table (Jira data available; linked issues fetched; PR
   data referenced; all sections present; template comparison possible; review rules
   loaded — YES/NO each) + confidence rationale.
7. The machine-readable verdict block — the very last content in the file.

Abbreviated example:

````markdown
# STP Review Report: PROJ-123
## Verdict: APPROVED_WITH_FINDINGS
## Summary
...
## Findings by Dimension
### Dimension 1: Rule Compliance (Rules A–Q)
| A — Abstraction Level | PASS | — |
## Recommendations
## Confidence Notes
```yaml
verdict: APPROVED_WITH_FINDINGS
critical_count: 0
major_count: 2
minor_count: 1
```
````

## Machine-Readable Verdict Block (required)

The report MUST end with exactly one fenced yaml block as its final content:

```yaml
verdict: APPROVED | APPROVED_WITH_FINDINGS | NEEDS_REVISION
critical_count: N
major_count: N
minor_count: N
```

Exactly these four keys; `verdict` is one of the three values; counts are integers
matching the Summary table. This block supplements — never replaces — the human-readable
`## Verdict:` line and does not change verdict semantics.

---

## Verdict Criteria

| Verdict | Criteria |
|:--------|:---------|
| `APPROVED` | 0 critical findings, 0 major findings |
| `APPROVED_WITH_FINDINGS` | 0 critical findings, 1+ major or minor findings |
| `NEEDS_REVISION` | 1+ critical findings |

---

## Confidence Scoring

| Level | Criteria |
|:------|:---------|
| `HIGH` | Jira data available, all sections present, template comparison done, review rules `default_ratio <= 0.30` |
| `MEDIUM` | Jira data incomplete, OR template unavailable, OR review rules `default_ratio <= 0.60` |
| `LOW` | Jira data unavailable (content-only review), OR review rules `default_ratio > 0.60` |

When `review_rules._extraction_metadata.default_ratio > 0.50`, add to Confidence Notes:
"Review precision reduced: {X}% of rules using generic defaults. Consider adding
project-specific `review_rules.yaml` or enabling `repo_files_fetch`."

---

## Error Handling

- **STP file not found:** return error, no review report.
- **Jira data unavailable:** content-only review (Dimensions 1, 3, 5, 6); confidence LOW;
  skip Dimensions 2 and 4 (need source comparison); note skipped dimensions.
- **Template not found:** skip Rule B; note in report.
- **project_context unavailable:** skip Rules F, G; note in report.
- **review_rules.yaml not found:** general rules only (all rules still apply, reduced
  precision); note in Confidence Notes.

---

**End of STP Reviewer Skill**
