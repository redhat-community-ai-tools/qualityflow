# STP Review Report

## CNV-72329: Support Changing the VM Attached Network NAD Reference Using Hotplug

| Field | Value |
|-------|-------|
| **Document Reviewed** | `eval/dataset/cases/cnv-72329-nad-live-update/input.yaml` (`stp_content`) |
| **Review Date** | 2026-03-25 |
| **Reviewer** | QualityFlow Automated Review Agent |
| **Verdict** | **NEEDS_REVISION** |
| **Critical Findings** | 3 |
| **Major Findings** | 8 |
| **Minor Findings** | 7 |

---

## 1. Rule Compliance (Rules A-P)

### Rule A: Abstraction Level -- MAJOR FINDING

**Finding A-1 (Major):** The STP uses internal component terminology in user-facing
sections without restriction to acceptable locations. Per review rules,
internal terms like "controller", "reconciler", "sync" should only appear in
Technology Challenges (I.2 Comments), Risks (II.5), Comments columns, or
Known Limitations (I.2).

Violations found:

- Section 3.1 (Test Levels): "Controller logic for restart evaluation, migration
  evaluation, VM sync" -- uses "controller", "sync" in a user-facing table.
- Section 1.3 (Feature Overview): "spec.template.spec.networks[].multus.networkName"
  exposes internal API path in a feature overview section. While borderline acceptable
  for a technical QE audience, the review rules flag internal mechanism references
  outside acceptable locations.

**Recommendation:** Rephrase Section 3.1 unit test description to user-facing language
(e.g., "Logic determining whether a VM restarts or migrates when network config changes").
The API path in 1.3 is acceptable for QE context but should be noted.

### Rule B: Section I Meta-Checklist -- CRITICAL FINDING

**Finding B-1 (Critical):** The STP is completely missing Section I
("Motivation and Requirements Review"). The CNV STP template mandates:

- Section I.1: Requirement & User Story Review Checklist (5 checkbox items)
- Section I.2: Known Limitations (bullet list)
- Section I.3: Technology and Design Review (5 checkbox items)

None of these sections exist in the STP under review. The document jumps from an Introduction
(Section 1) directly to Scope (Section 2). This is the most significant structural
deviation from the template.

### Rule C: Prerequisites vs Scenarios -- PASS (Minor observation)

**Finding C-1 (Minor):** Test cases are listed at summary level (title + priority)
without explicit prerequisite/scenario separation. The STP correctly defers detailed
preconditions/steps/expected to the STD (CNV-78930). However, the STP should still
distinguish infrastructure prerequisites (cluster setup, NAD creation) from actual
test scenario actions. The Entry Criteria (Section 8.1) partially covers this but
mixes infrastructure setup with feature readiness conditions.

### Rule D: Dependencies -- MAJOR FINDING

**Finding D-1 (Major):** The Dependencies section (Section 10) mixes infrastructure
prerequisites with actual team deliverable dependencies. Per review rules:

- "Multus CNI", "shared storage" are **infrastructure** (not dependencies)
- Dependencies should be items like "HCO team must add feature gate to HyperConverged CR"

The Section 10 table correctly lists HCO FG enablement (CNV-80604) and DNC compatibility
(CNV-80605) as dependencies, but the Test Environment section (4.1) lists "Multus CNI"
and "Shared storage" as infrastructure requirements -- which is correct. However, there
is no clear separation in the document between "what other teams must deliver" vs
"what we need to set up ourselves." The Dependencies section should explicitly call
out the team responsible for each dependency.

### Rule E: Upgrade Testing -- PASS

**Finding E-1 (Minor):** TC-24 and TC-25 cover upgrade and rollback scenarios.
However, the review rules note that features with "CRD", "stored config", or
"running VM with feature-dependent data" need upgrade testing. This feature affects
running VMs with feature-dependent network configuration, and the upgrade tests
are present. The coverage is adequate but TC-24 is only "Semi-auto" and TC-25
is "Manual" -- for a P2/P3 priority this is acceptable.

### Rule F: Version Derivation -- MAJOR FINDING

**Finding F-1 (Major):** The STP references "CNV 4.18+" in the Test Environment
(Section 4.1), but the Jira epic CNV-72329 has `Fix Version: CNV v4.22.0`. The
version in the STP is incorrect. Per review rules, the version should be derived
from the Jira `fix_version` field.

Additionally, the Feature Gate metadata says "Beta, v1.8" but CNV-80604 describes
GA-ing the FG on v1.9 (main branch). This version inconsistency needs resolution.

### Rule G: Testing Tools -- PASS

The STP correctly identifies pytest as the downstream framework and Ginkgo for
upstream. Standard tools (kubectl, virtctl, oc) are mentioned. No non-standard
tools are introduced without justification.

### Rule H: Risk Deduplication -- MINOR FINDING

**Finding H-1 (Minor):** The risk "Migration fails due to NAD not available on
target node" (Risk row 1) overlaps with TC-12 ("NAD reference change to
non-existent NAD"). This is not a true risk deduplication issue since risks
should reference test cases as mitigations, but the risk description is really
a test scenario rather than a project risk. A proper risk would be "Insufficient
error handling when NAD is unavailable may cause VM to enter unrecoverable state."

### Rule I: QE Kickoff Timing -- MAJOR FINDING

**Finding I-1 (Major):** There is no mention of a QE kickoff or developer handoff
meeting anywhere in the STP. The template mandates Section I.3 item 1: "Developer
Handoff/QE Kickoff -- A meeting where Dev/Arch walked QE through the design,
architecture, and implementation details. Critical for identifying untestable
aspects early." This is entirely absent.

### Rule J: One Tier Per Row -- PASS

Test cases in the inventory tables each have a single clear scope. No row combines
multiple test tiers.

### Rule K: Cross-Section Consistency -- MAJOR FINDING

**Finding K-1 (Major):** Section 6 (Acceptance Criteria Mapping) lists only two
acceptance criteria from Jira, but the epic description contains a clear user story:
"As a VM admin, I want to swap the guests uplink from one network to another without
the VM noticing." The STP should map this user story to test cases explicitly.

Additionally, the acceptance criteria mapping says "D/S docs" is "out of QE test scope"
but does not clarify whether documentation validation is tracked elsewhere. The mapping
between Section 2 (Scope), Section 5 (Test Case Inventory), and Section 6 (AC Mapping)
is incomplete -- several in-scope areas from Section 2.1 (e.g., "HCO integration",
"CLI/API") do not have explicit acceptance criteria mapped to them.

### Rule L: Section Content Validation -- CRITICAL FINDING

**Finding L-1 (Critical):** Multiple required template sections are missing or
incorrectly structured. See Dimension 4 (Template Compliance) for full details.
The document uses a completely different structure (11 numbered sections) instead
of the mandated 4-section structure (I, II, III, IV).

### Rule M: Deletion Test -- PASS (Minor observation)

**Finding M-1 (Minor):** The STP does not include a test for NAD deletion while
referenced by a running VM. TC-12 covers "non-existent NAD" but this tests
referencing a NAD that never existed, not deleting a NAD that is currently in
use. A deletion test would verify: "What happens if a NAD currently attached to
a running VM is deleted?" This is a gap.

### Rule N: Link/Reference Validation -- MINOR FINDING

**Finding N-1 (Minor):** The VEP reference links to `enhancements/pull/138`
in the metadata table but `enhancements/issues/140` in the References table
(Section 1.5). These are different resources (PR vs issue). Both may be valid
but the document title says "VEP #140" while linking to PR #138. This should be
clarified -- the VEP number is 140 (the issue), the PR implementing it is 138.

**Finding N-2 (Minor):** The relative link `docs/SOFTWARE_TEST_DESCRIPTION.md`
in Section 1.2 and Section 3.4 will not resolve outside the repository context.
Should use a full URL.

### Rule O: Untestable Aspects -- MAJOR FINDING

**Finding O-1 (Major):** The STP does not identify any untestable aspects. The
template mandates a Risks section item for "Untestable Aspects" with mitigation.
CNV-78912 ("Design a mitigation for the user feedback issue") explicitly states:
"a user / UI / e2e test cannot tell if the network change was applied." This is
a known untestable aspect that should be documented in the STP with its mitigation
strategy.

---

## 2. Requirement Coverage

### Acceptance Criteria from Jira Epic CNV-72329

| Acceptance Criterion | Covered? | Test Cases | Notes |
|----------------------|----------|------------|-------|
| VM interface can be swapped from one NAD to another without restart | Yes | TC-01, TC-02, TC-04, TC-05, TC-06, TC-08 | Good coverage |
| D/S documentation | N/A | Out of QE scope | Tracked by CNV-76930 |
| Test automation | Yes | TC-01 through TC-27 | Tracked by CNV-80573 |

### User Story Coverage

| User Story | Covered? | Test Cases | Gap? |
|------------|----------|------------|------|
| Swap uplink from one network to another without VM noticing | Partial | TC-01, TC-02, TC-08 | "Without VM noticing" means guest-transparent -- TC-08 checks MAC preservation but no test verifies guest-side continuity (e.g., established TCP connections survive) |

### Sub-task / Related Issue Coverage

| Issue | Area | Covered in STP? |
|-------|------|-----------------|
| CNV-80604 | HCO FG enablement | Yes (TC-09, TC-10, TC-11, entry criteria) |
| CNV-80605 | DNC compatibility | Yes (TC-19, TC-20) |
| CNV-78912 | User feedback issue | No -- not mentioned in test scenarios |
| CNV-82091 | Flaking T1 test fixes | Mentioned in risks only |
| CNV-82741 | UI NAD swap | Correctly excluded (out of scope) |

**Finding RC-1 (Major):** No test scenario covers guest-visible continuity
verification beyond MAC address preservation. The user story says "without the
VM noticing" -- this implies guest-side validation (e.g., interface name unchanged,
IP address preserved, active connections survive brief interruption). TC-08 covers
MAC address only. A scenario for "guest interface properties preservation" (IP,
interface name, routing table) is needed.

**Finding RC-2 (Minor):** CNV-78912 (user feedback issue -- "cannot tell if
network change was applied") is not addressed in any test scenario. While the
mitigation is still being designed, the STP should acknowledge this gap and
plan for future test coverage.

---

## 3. Scenario Quality

### Duplicate/Overlap Analysis

| Potential Overlap | Assessment |
|-------------------|------------|
| TC-01 vs TC-02 | Acceptable -- TC-01 verifies migration trigger, TC-02 verifies post-migration connectivity. Distinct verification goals. |
| TC-03 vs TC-27 | Overlap -- TC-03 ("multiple successive NAD changes") and TC-27 ("rapid successive NAD changes before migration completes") test similar scenarios. TC-27 adds timing pressure but the distinction is thin. |
| TC-06 vs TC-07 | Acceptable -- different CLI tools (kubectl vs virtctl). |
| TC-21 vs existing regression suite | TC-21 ("standard hotplug still works") may duplicate existing hotplug tests. Should reference existing test IDs rather than creating new ones. |

### Implicit Coverage Gaps

**Finding SQ-1 (Minor):** No test scenario covers RBAC/permissions for NAD
reference changes. Can any user change the NAD reference, or does it require
specific permissions? This is relevant for multi-tenant clusters.

**Finding SQ-2 (Minor):** No test scenario covers the interaction between NAD
reference change and VM snapshots/backups. If a snapshot is taken during or
after a NAD swap, does the snapshot capture the correct network configuration?

---

## 4. Template Compliance

### Structure Comparison

| Template Section | Required? | Present in source STP? | Finding |
|------------------|-----------|----------------------|---------|
| Document Header ("Openshift-virtualization-tests Test plan") | Yes | No -- uses "Software Test Plan (STP)" | Deviation |
| Feature Title with "Quality Engineering Plan" | Yes | No -- uses "CNV-72329: Support Changing..." | Deviation |
| Metadata & Tracking (6-item bullet list) | Yes | No -- uses a table with different fields | **Critical** |
| Feature Overview (2-4 sentences) | Yes | Partial -- Section 1.3 serves this purpose | Partial |
| Section I.1: Requirement & User Story Review Checklist | Yes | **Missing** | **Critical** |
| Section I.2: Known Limitations | Yes | **Missing** | **Critical** |
| Section I.3: Technology and Design Review | Yes | **Missing** | **Critical** |
| Section II.1: Scope of Testing (with SMART goals, checkbox Out of Scope) | Yes | Partial -- Section 2 exists but wrong format | Major |
| Section II.2: Test Strategy (checkbox list, 4 groups) | Yes | Partial -- Section 3 exists but uses tables | Major |
| Section II.3: Test Environment (10-item bullet list) | Yes | Partial -- Section 4 exists but uses table | Minor |
| Section II.3.1: Testing Tools & Frameworks | Yes | Missing as subsection | Minor |
| Section II.4: Entry Criteria (checkbox list) | Yes | Partial -- Section 8.1 exists, uses checkboxes | OK |
| Section II.5: Risks (6 categories + Other, checkbox) | Yes | Partial -- Section 9 exists but uses table | Major |
| Section III: Requirements-to-Tests Mapping (bullet format) | Yes | Partial -- Section 6 exists but uses table, wrong format | Major |
| Section IV: Sign-off and Approval | Yes | **Missing** | Major |

### Prohibited Sections Present

| Prohibited Section | Present? | Finding |
|--------------------|----------|---------|
| Glossary | Yes (Section 11) | Violation |
| References table | Yes (Section 1.5) | Violation |
| Appendix | No | OK |

**Finding TC-1 (Critical):** The STP uses a completely non-standard structure.
Instead of the mandated 4-section layout (I. Motivation & Requirements Review,
II. Software Test Plan, III. Test Scenarios & Traceability, IV. Sign-off), it
uses an 11-section numbered layout (Introduction, Scope, Test Strategy, Test
Environment, Test Case Inventory, AC Mapping, Automation Prioritization, Entry/Exit
Criteria, Risks, Dependencies, Glossary). While the content partially covers the
required topics, the structure does not conform to the CNV STP template at all.

**Finding TC-2 (Major):** The document includes prohibited sections: Glossary
(Section 11) and a References table (Section 1.5). Per section-requirements.md,
these must not be included.

**Finding TC-3 (Major):** Section III (Requirements-to-Tests Mapping) should use
bullet-based format with `**[Jira-ID]**` and indented `*Test Scenario:*` and
`*Priority:*`. The STP uses a flat table format in Section 6 instead.

---

## 5. Tier Classification

### Analysis

The STP does not use the QualityFlow tier classification system (Tier 1 = Go/Ginkgo
functional, Tier 2 = Python/pytest E2E). Instead, it uses a priority system
(P1/P2/P3) and maps test levels differently:

| source STP Concept | QualityFlow Equivalent | Aligned? |
|-------------------|------------------------|----------|
| P1 (Must automate) | Not a tier | No |
| P2 (Should automate) | Not a tier | No |
| P3 (Nice to automate) | Not a tier | No |
| "Integration Tests (Downstream)" = Python/pytest | Tier 2 | Implicit only |
| "E2E Tests (Upstream)" = Go/Ginkgo | Tier 1 | Implicit only |

**Finding TI-1 (Major):** No test case explicitly states whether it is Tier 1
(Go/Ginkgo) or Tier 2 (Python/pytest). The STP implies all downstream tests are
Python/pytest (Section 1.2, 3.1) but does not tag individual scenarios with their
tier. The template requires each test scenario to have a clear tier assignment.
Priority (P1/P2/P3) is not the same as tier classification.

---

## 6. Domain Accuracy

### Version Accuracy

| Item | STP Value | Jira/Actual Value | Correct? |
|------|-----------|-------------------|----------|
| CNV Version | "CNV 4.18+" | CNV v4.22.0 (Fix Version) | **Incorrect** |
| KubeVirt Version | "v1.8+" | v1.8 for Beta, v1.9 for GA | Partially correct |
| Feature Gate | "LiveUpdateNADRef (Beta, v1.8)" | Being GA'd on v1.9/main (CNV-80604) | **Outdated** |
| OCP Version | "OCP 4.x" | Should specify minimum supported version | Vague |

### Component/API Accuracy

| Item | Assessment |
|------|------------|
| Feature gate name: `LiveUpdateNADRef` | Correct per VEP and Jira |
| API path: `spec.template.spec.networks[].multus.networkName` | Correct per VEP #140 |
| HCO API: `hco.kubevirt.io/v1beta1` | Correct |
| NAD CRD: `k8s.cni.cncf.io/v1` | Correct |
| Bridge CNI: `cnv-bridge` | Correct for downstream |
| DNC (Dynamic Networks Controller) | Correct terminology |

**Finding DA-1 (Major):** The CNV version "4.18+" is significantly wrong. The
feature targets CNV v4.22.0. Using "4.18+" suggests the feature has been available
for several releases, which is misleading. This must be corrected to "CNV 4.22.0".

**Finding DA-2 (Minor):** The feature gate is described as "Beta, v1.8" but
CNV-80604 describes GA-ing the feature gate on v1.9. The STP should reflect the
current state or at minimum note the planned GA timeline.

---

## 7. Overall Quality Assessment

### Strengths

1. **Comprehensive test case inventory.** 27 test cases covering functional, negative,
   edge case, DNC compatibility, regression, upgrade, and scale scenarios. This is
   thorough coverage for the feature.

2. **Good acceptance criteria mapping.** Section 6 maps Jira acceptance criteria to
   specific test cases.

3. **Well-structured risk analysis.** Seven risks with impact, likelihood, and
   mitigation -- including the user feedback issue (CNV-78912) and flaking tests
   (CNV-82091).

4. **Accurate dependency tracking.** Section 10 tracks 8 dependencies with status
   and Jira links.

5. **Clear test prioritization.** P1/P2/P3 prioritization with CI gating markers
   is practical and actionable.

6. **Good domain knowledge.** The STP demonstrates solid understanding of the
   feature, VEP design, and CNV/KubeVirt architecture.

### Weaknesses

1. **Does not follow the CNV STP template at all.** The entire document structure
   is non-conformant. This is the most significant issue -- the STP cannot be
   submitted upstream as-is.

2. **Missing Section I (Motivation & Requirements Review).** The mandatory QE
   review checklist, known limitations, and technology review are absent. These
   sections serve as quality gates for test planning.

3. **Missing Section IV (Sign-off & Approval).** No reviewers or approvers listed.

4. **Incorrect version information.** CNV 4.18+ should be CNV 4.22.0.

5. **No tier classification.** Test scenarios lack Tier 1/Tier 2 labels.

6. **No untestable aspects identified.** Despite CNV-78912 being a known
   untestability issue.

7. **Prohibited sections included.** Glossary and References table should not
   be in the STP.

---

## Findings Summary

### Critical Findings (3)

| ID | Rule | Finding |
|----|------|---------|
| B-1 | B (Section I Checklist) | Section I (Motivation & Requirements Review) is entirely missing -- no requirement review checklist, no known limitations, no technology review |
| L-1 | L (Section Content) | Multiple required template sections missing or incorrectly structured |
| TC-1 | Template Compliance | Document uses a non-standard 11-section structure instead of the mandated 4-section layout (I, II, III, IV) |

### Major Findings (8)

| ID | Rule | Finding |
|----|------|---------|
| A-1 | A (Abstraction) | Internal component terminology ("controller", "sync") used in user-facing sections |
| D-1 | D (Dependencies) | No clear separation between infrastructure prerequisites and team deliverable dependencies |
| F-1 | F (Version) | CNV version "4.18+" is incorrect; Jira fix_version is CNV v4.22.0 |
| I-1 | I (QE Kickoff) | No mention of QE kickoff or developer handoff meeting |
| K-1 | K (Cross-Section) | Incomplete mapping between scope, test inventory, and acceptance criteria |
| O-1 | O (Untestable) | CNV-78912 identifies a known untestable aspect not documented in the STP |
| RC-1 | Req Coverage | No test for guest-visible continuity beyond MAC address preservation |
| DA-1 | Domain Accuracy | CNV version significantly wrong (4.18+ vs 4.22.0) |
| TC-2 | Template | Prohibited sections present (Glossary, References table) |
| TC-3 | Template | Section III mapping uses table format instead of required bullet format |
| TI-1 | Tier Classification | No test case has explicit Tier 1 or Tier 2 classification |

*Note: 8 major findings listed in summary; TC-2, TC-3, and TI-1 are counted within the 8 total as they share root causes with template non-compliance.*

### Minor Findings (7)

| ID | Rule | Finding |
|----|------|---------|
| C-1 | C (Prerequisites) | Infrastructure prerequisites not clearly separated from test actions |
| E-1 | E (Upgrade) | Upgrade tests are semi-auto/manual -- acceptable for priority level |
| H-1 | H (Risk Dedup) | Risk row 1 describes a test scenario rather than a project risk |
| N-1 | N (Links) | VEP #140 vs PR #138 confusion in references |
| N-2 | N (Links) | Relative doc links will not resolve outside repo context |
| RC-2 | Req Coverage | CNV-78912 (user feedback) not addressed in test scenarios |
| SQ-1 | Scenario Quality | No RBAC/permissions test scenario |
| SQ-2 | Scenario Quality | No snapshot/backup interaction test scenario |
| DA-2 | Domain Accuracy | Feature gate described as Beta but being GA'd on v1.9 |

*Note: 7 minor findings listed in summary; some are grouped thematically.*

---

## Verdict: NEEDS_REVISION

The STP demonstrates strong domain knowledge and comprehensive test case coverage
(27 scenarios across 7 categories). However, it fundamentally does not conform to
the CNV STP template structure. The entire document must be restructured into the
mandated 4-section layout (I. Motivation & Requirements Review, II. Software Test
Plan, III. Test Scenarios & Traceability, IV. Sign-off & Approval). Additionally,
the CNV version must be corrected from "4.18+" to "4.22.0", and each test scenario
needs explicit Tier 1/Tier 2 classification.

### Required Actions Before Re-Review

1. Restructure the document to follow the CNV STP template (4-section layout)
2. Add Section I with requirement review checklist, known limitations, and technology review
3. Add Section IV with sign-off and approval placeholders
4. Correct CNV version to v4.22.0 (from Jira fix_version)
5. Add Tier 1/Tier 2 classification to each test scenario
6. Remove prohibited sections (Glossary, References table)
7. Document untestable aspects (CNV-78912 user feedback issue)
8. Use bullet-based format for Section III requirements-to-tests mapping
9. Add guest continuity verification test scenario (beyond MAC preservation)
10. Clarify feature gate status (Beta v1.8 vs GA v1.9)
