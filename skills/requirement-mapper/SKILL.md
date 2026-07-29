---
name: requirement-mapper
description: Map Jira requirements to testable scenarios with validation gates
---

# Requirement Mapper Skill

**Phase:** Core Processing
**User-Invocable:** false

## Purpose

Map Jira requirements to testable scenarios, applying validation gates and project scope boundaries.

## When to Use

Invoked by the **stp-generator** subagent to transform regression analysis into validated requirements.

## Input

```yaml
jira_data:
  main_issue:
    key: PROJ-12345
    summary: Add CPU hot-plug support
    description: ...
    acceptance_criteria: ...
  linked_issues: [...]

regression_data:
  impacted_features:
    - feature_name: Live Migration
      relationship: Direct caller
      why_might_break: ...
    - ...
  recommended_tests:
    - requirement: Live migration works with CPU changes
      test_scenario: Verify VM migration succeeds after CPU hot-plug
      priority: P1
    - ...
```

## Output Format

```yaml
validated_requirements:
  - requirement_id: PROJ-12345  # Jira issue key — NEVER invent IDs
    requirement_summary: Live migration completes successfully after CPU hot-plug
    source: regression_analysis
    evidence: MigrateInstance calls UpdateSpec which was modified
    validation_passed: true
    test_scenario: Verify VM migration succeeds after CPU hot-plug
    priority: P1
  - requirement_id: ""  # Leave blank for subsequent rows under the same epic
    requirement_summary: CPU can be hot-added to running VM
    source: regression_analysis
    evidence: HandleCPUHotplug is new entry point
    validation_passed: true
    test_scenario: Verify CPU addition to running VM
    priority: P0
  - ...

rejected_requirements:
  - requirement_summary: Kubernetes scheduler places VM pods correctly
    reason: Platform-level test - Kubernetes scheduler is tested by platform team
    gate_failed: Requirement Level Validation
  - requirement_summary: PVC binds to PV correctly
    reason: Platform-level test - CSI/storage tested by storage team
    gate_failed: Requirement Level Validation
  - ...

ac_quality:
  ac_rewrites:
    - original: "snapcontent.sourceVolumeMode is preserved"
      rewritten: "Volume mode is preserved during snapshot restore"
      technical_context: "snapcontent.sourceVolumeMode API field"
  ac_augmentations:
    - original: "Users can restore from snapshot"
      augmented: "Restored VM boots successfully and target files match pre-snapshot state"
  measurability_warnings: 0

coverage_summary:
  total_from_regression: 15
  validated: 12
  rejected: 3
  tier1_count: 8
  tier2_count: 4
```

## Requirement Level Validation Gate

### Step 1: Read Scope Boundaries from Config

Read `{project_context.config_dir}/project.yaml` `scope_boundaries` for all validation data:

- **`testing_levels`**: Lists which testing levels to ACCEPT and which to REJECT.
  Classify each requirement by its testing level, then look up the action.
- **`team_ownership`**: Lists which teams' scope to ACCEPT and which to REJECT.
  Ask "Who tests this?" and look up the action.
- **`in_scope_resources`**: Resources that the project tests (ACCEPT if involved).
- **`out_of_scope_if_only`**: Resources that are out of scope when they are the
  ONLY resource involved (REJECT if no in-scope resources are present).

### Step 2: Resource Scope Check

For each requirement, check which resources it involves:

- **Accept** if the requirement involves any resource listed in `scope_boundaries.in_scope_resources`
- **Reject** if the requirement involves ONLY resources listed in `scope_boundaries.out_of_scope_if_only`

### Step 3: Final Check

Read the `scope_boundaries.validation_gate` question from `{project_context.config_dir}/project.yaml`.

- YES → ACCEPT
- NO → REJECT

## Acceptance Criteria Quality Gate

Before mapping requirements to scenarios, validate each acceptance criterion
from Jira for quality. This gate catches issues that would otherwise produce
CRITICAL review findings downstream.

### Step A: Abstraction Level Check

For each acceptance criterion text, apply the "Release Notes" litmus test
from Rule A:

> "Would this sentence appear in customer-facing release notes?"

Scan for these red-flag patterns:

- API field names used as nouns (e.g., `spec.fieldName`, `status.condition`,
  `resource.metadata.annotations`)
- CRD spec paths (e.g., `snapcontent.sourceVolumeMode`, `vm.spec.domain.cpu`)
- Internal component references (controller, reconciler, evaluator, sync handler)
- Implementation verbs (reconcile, sync, propagate, trigger, annotate)
- Go/Python/API struct field names used in place of user-observable descriptions

When a red-flag pattern is found:

1. **Rewrite** the acceptance criterion in user-observable language before
   passing it to scenario-builder
2. Record the original AC text and the rewrite in `ac_rewrites` metadata
3. Move the original technical term to a `technical_context` field that
   scenario-builder can reference for precision without leaking it into
   user-facing text

**Rewrite examples:**

| Original AC (implementation language) | Rewritten AC (user-observable) |
|:---------------------------------------|:-------------------------------|
| snapcontent.sourceVolumeMode is preserved | Volume mode is preserved during snapshot restore |
| RestartRequired condition is not set | VM continues running without restart |
| controller reconciles the CR status | Feature status is updated correctly |
| annotation key X is set on the pod | Feature metadata is visible via API |

### Step B: Measurability Check

For each acceptance criterion, verify it contains an observable pass/fail
condition. Apply this test:

> "Can a test automation framework determine PASS or FAIL from this criterion
> alone, without human judgment?"

Red-flag patterns (non-measurable):

- "Users can [verb]" without specifying what observable state proves success
- "Works correctly" / "functions properly" / "behaves as expected"
- "Is supported" without defining what support means observably
- "Should be able to" without an assertion target

When a non-measurable AC is found:

1. **Augment** the AC with an explicit observable condition derived from the
   Jira description, linked issues, or the feature's technical context
2. Record the augmentation in `ac_augmentations` metadata
3. If no observable condition can be derived, flag the requirement with
   `measurability_warning: true` so the STP includes a note

**Augmentation examples:**

| Original AC (non-measurable) | Augmented AC (measurable) |
|:------------------------------|:--------------------------|
| Users can restore from snapshot | Restored VM boots successfully and target files match pre-snapshot state |
| Hot-plug is supported | CPU count increases without VM restart and guest OS reports new CPUs |
| Feature works in Dev Preview | Feature is accessible when Dev Preview feature gate is enabled |

## Requirement ID Rules

### Jira Issue Keys Only

Requirement IDs MUST be Jira issue keys (e.g., `PROJ-72329`). Never invent IDs
like `REQ-xxx-001`, `REQ-NAD-001`, or any other synthetic ID format.

- Use the **epic key** for the first row under that epic
- Leave the Requirement ID **blank** for subsequent rows under the same epic
  (avoids redundant repetition of the same key)
- If a linked sub-issue has its own Jira key, use that key instead

| BAD (Invented) | GOOD (Jira Key) |
|:----------------|:-----------------|
| REQ-NAD-001 | PROJ-72329 |
| REQ-CPU-001 | PROJ-12345 |
| REQ-MIG-001 | PROJ-67890 |

## Requirement Quality Rules

### STP Level Requirements

Requirements must be HIGH-LEVEL capabilities:

| BAD (Too Low-Level) | GOOD (STP Level) |
|:--------------------|:-----------------|
| Create VM with 2 CPUs, start it, add 2 more | CPU can be hot-added to running VM |
| Run `{cli_tool} get resource` and check status | Resource status is accurately reported via API |
| Create PVC, attach, write file, verify | Data persists across disk attach/detach |

### Avoid Trivial Atomic Requirements

Consolidate into feature capabilities:

| BAD (Fragmented) | GOOD (Consolidated) |
|:-----------------|:--------------------|
| Start VM, Stop VM, Restart VM | VM lifecycle operations function correctly |
| Create disk, Attach, Detach, Delete | Disk hot-plug operations complete successfully |
| Add CPU, Remove CPU, Add memory | Resource hot-plug preserves VM stability |

### Target Count

**5-15 high-level requirements per feature** - not 30-50 trivial operations.

## Source Priority

**EXCLUSIVE source for test scenarios:** Regression Analysis

DO NOT derive test scenarios from:

- Jira ticket descriptions
- Acceptance criteria
- PR descriptions or review comments
- Web search results
- General assumptions

## Negative Scenario Coverage

Include negative test scenarios for:

- Invalid input handling
- Resource constraints
- Permission denied
- Invalid state
- Conflict handling
- Recovery/interruption
- Boundary conditions
- Missing dependencies

## Example Mapping

Input (from regression analysis):

```yaml
impacted_features:
  - feature_name: Live Migration
    relationship: Direct caller
    why_might_break: Migration calls instance update which was modified
```

Output:

```yaml
validated_requirements:
  - requirement_id: PROJ-12345
    requirement_summary: Live migration completes successfully after CPU configuration changes
    source: regression_analysis
    evidence: MigrateInstance → UpdateSpec (modified)
    validation_passed: true
    test_scenario: Verify VM migration succeeds with modified CPU config
    priority: P1
```

## Coverage Checklist

Before finalizing, verify:

- [ ] All operations covered (every action the feature supports)
- [ ] All configuration options covered
- [ ] All API fields covered
- [ ] All states covered
- [ ] All integration points covered
- [ ] Positive AND negative scenarios included
- [ ] No gaps between regression findings and test scenarios
