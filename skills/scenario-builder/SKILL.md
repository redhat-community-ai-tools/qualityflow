---
name: scenario-builder
description: Build concise test scenario descriptions for STP requirements mapping
model: claude-opus-4-6
---

# Scenario Builder Skill

**Phase:** Core Processing
**User-Invocable:** false

## Purpose

Build concise test scenario descriptions for the STP Requirements-to-Tests Mapping.

## When to Use

Invoked by the **stp-generator** subagent for each validated requirement.

## Input

```yaml
requirement:
  requirement_id: PROJ-12345
  requirement_summary: Users can reset their password via email
  source: regression_analysis
  evidence: HandlePasswordReset entry point added
  coverage_status: NEW          # NEW (default), PARTIAL_COVERAGE, or EXISTING_COVERAGE
  existing_coverage:            # present only when coverage_status is not NEW
    - test_function: TestPasswordReset_Success
      test_file: pkg/auth/reset_test.go
      behavior_tested: "Password reset succeeds for valid email"
  coverage_gap:                 # present only for PARTIAL_COVERAGE
    - "Error handling for invalid email format not tested"
```

## Output Format

```yaml
scenario:
  requirement_id: PROJ-12345
  requirement_summary: Users can reset their password via email
  test_scenarios:
    - description: Verify password reset email is sent for valid user
      type: positive
    - description: Verify error for invalid email format
      type: negative
  suggested_tier: Tier 1 (Functional)
  suggested_priority: P0
```

## Pre-Generation Coverage Check

Before generating scenarios, check `coverage_status` on the input requirement:

| Coverage Status | Action |
|:----------------|:-------|
| `EXISTING_COVERAGE` | Return empty scenarios with `covered_by` metadata. Do NOT generate test scenarios. |
| `PARTIAL_COVERAGE` | Generate scenarios ONLY for behaviors listed in `coverage_gap`. Skip behaviors already in `existing_coverage`. |
| `NEW` or absent | Generate scenarios normally (full set, existing behavior). |

**EXISTING_COVERAGE output:**

```yaml
scenario:
  requirement_id: PROJ-12345
  requirement_summary: Users can reset their password via email
  coverage_status: EXISTING_COVERAGE
  test_scenarios: []
  covered_by:
    - test_function: TestCPUHotplug_Success
      test_file: pkg/compute/cpu_test.go
      behavior_tested: "CPU hot-add succeeds for running VM"
```

**PARTIAL_COVERAGE output:** Generate scenarios only for uncovered gaps. Include
`covered_by` metadata for the already-covered behaviors so Section III can reference them.

When `coverage_status` is absent (backward compatibility), treat as `NEW`.

## Scenario Description Rules

### Keep It Brief

| GOOD (Brief) | BAD (Verbose) |
|:-------------|:--------------|
| Verify password reset via email | Verify that when a user requests a password reset, the system sends a reset email to the registered address |
| Test API backward compatibility | Test that the API maintains backward compatibility with previous versions |
| Validate RBAC permissions | Validate that RBAC permissions are properly enforced for the operation |

### Format

- Start with action verb: Verify, Test, Validate, Confirm
- One short phrase (5-10 words)
- NO test steps, preconditions, or expected results
- NO specific commands, API calls, or values
- Describes WHAT is tested, not HOW

### Positive Scenarios

Cover:

- Primary functionality (happy path)
- All supported operations
- Configuration variations
- State transitions

### Negative Scenarios

Every requirement should have at least one negative scenario:

| Positive Scenario | Corresponding Negative |
|:------------------|:-----------------------|
| Verify password reset succeeds | Verify error for invalid email format |
| Verify data export completes | Verify graceful failure when service unavailable |
| Verify backup creation | Verify error when insufficient storage |
| Verify API accepts valid input | Verify API rejects malformed request |

### Scenario Categories

For each requirement, consider:

| Category | Example |
|:---------|:--------|
| **Basic Operation** | Verify password reset email is sent |
| **Error Handling** | Verify error for expired reset token |
| **State Validation** | Verify account status after password change |
| **Permission Check** | Verify non-admin cannot reset other users |
| **Recovery** | Verify cleanup after failed password change |
| **Persistence** | Verify new password persists after session expiry |

## Exclusions

DO NOT include:

| Exclude | Why |
|:--------|:----|
| Generic meta-tests | "Verify tests pass in CI" is not a feature test |
| Platform-level tests | Using scope_boundaries from project config |
| Trivial atomic steps | "Start service" is a prerequisite, not a test |
| Detailed procedures | Steps belong in STD, not STP |
| Irrelevant topologies | No environment-specific tests unless feature requires |

## Priority Assignment

| Priority | Criteria |
|:---------|:---------|
| P0 | Core functionality, data integrity, security |
| P1 | Important functionality, error handling, API validation |
| P2 | Edge cases, minor features, optimization |

## Example Transformations

Input:

```yaml
requirement_summary: Data export works with concurrent writes
evidence: ExportData calls modified WriteBuffer
```

Output:

```yaml
test_scenarios:
  - description: Verify export after concurrent write
    type: positive
  - description: Verify export with pending write operation
    type: positive
  - description: Verify error for export during active write
    type: negative
```

Input:

```yaml
requirement_summary: API rejects invalid quota specifications
evidence: ValidateQuotaChange added to API path
```

Output:

```yaml
test_scenarios:
  - description: Verify API rejects zero quota value
    type: negative
  - description: Verify API rejects negative quota value
    type: negative
  - description: Verify API rejects exceeding max quota
    type: negative
  - description: Verify descriptive error message returned
    type: negative
```

## Consolidation

After generating scenarios, verify no overlap with `existing_test_coverage` data
(if provided). Remove any generated scenario whose behavior is semantically equivalent
to an existing test function's `behavior_tested` summary.

If multiple similar scenarios, consolidate:

| Before (Fragmented) | After (Consolidated) |
|:--------------------|:---------------------|
| Test add 1 item, Test add 2 items, Test add 4 items | Verify batch add with various counts |
| Check status after add, Check events after add | Verify status and events after add operation |

## End-to-End Workflow Scenarios (Tier 2)

**IMPORTANT:** For each requirement, also consider if an end-to-end workflow scenario is appropriate.

### When to Generate E2E Scenarios

Generate a Tier 2 (E2E) scenario if the feature:

- Interacts with other features (auth, storage, messaging)
- Has state that should persist across operations
- Is part of a larger user workflow
- Could be affected by upgrades or version changes

### E2E Scenario Patterns

| Feature Type | E2E Scenario to Add |
|:-------------|:--------------------|
| Config changes | Verify config state preserved through failover |
| Storage operations | Verify storage lifecycle (create -> backup -> restore) |
| Network/API changes | Verify connectivity survives service restart |
| Any resource modification | Verify modification persists through restart/failover |
| API changes | Verify backward compatibility across upgrade |

### E2E Scenario Examples

| Atomic (Tier 1) | E2E Workflow (Tier 2) |
|:----------------|:----------------------|
| Verify config update succeeds | Verify config preserved after failover |
| Verify backup creation | Verify backup -> restore -> verify data workflow |
| Verify endpoint registration | Verify connectivity after service restart |
| Verify attachment upload | Verify attachment data persists through restart |
| Verify API accepts input | Verify API behavior consistent after upgrade |

## Output per Requirement

For each requirement, produce 2-7 test scenarios:

- 1 primary positive scenario (Tier 1 - always)
- 1-2 additional positive variations (Tier 1 - if applicable)
- 1 negative scenario (Tier 1 - always)
- 1 end-to-end workflow scenario (Tier 2 - when applicable, see above)
- 0-2 dimensional probing scenarios (from the 12-dimension system below, when applicable)

Bias toward the lower end (2-3) for simple features and the upper end (5-7) for complex
features with many applicable dimensions.

## Negative Scenario Proportion Guardrail

After generating all scenarios for all requirements, validate the negative scenario
proportion across the entire scenario set.

**Minimum threshold:** At least 20% of all scenarios must be negative (type: `negative`).

**Validation gate:**
```
total_scenarios = count of all generated scenarios across all requirements
negative_scenarios = count of scenarios with type: negative
negative_ratio = negative_scenarios / total_scenarios

IF negative_ratio < 0.20:
  Generate additional negative scenarios until the ratio reaches 0.20
  Prioritize requirements that have zero negative scenarios
  Use the Acceptance Criteria Error Conditions technique (below) first
```

**Acceptance Criteria Error Conditions:**
When the Jira acceptance criteria mention error handling, failure modes, invalid input,
or boundary conditions, each such mention MUST produce at least one negative scenario.

Scan acceptance criteria for these patterns:
- "error", "fail", "invalid", "reject", "deny", "timeout", "exceed", "corrupt"
- "should not", "must not", "cannot", "prevent"
- "when X is missing", "when X is unavailable", "when X fails"
- "insufficient", "unauthorized", "forbidden"

For each matched pattern, generate a negative scenario that tests the described failure
mode. These scenarios count toward the negative ratio.

**Remediation order when below threshold:**
1. Generate scenarios from unmatched AC error conditions (highest value)
2. Add error/failure scenarios for requirements with zero negatives
3. Probe the Error (dim 2) and Edge Case (dim 3) dimensions for remaining requirements
4. Add permission/RBAC denial scenarios if the feature has access controls

## NFR-Driven Scenario Generation

When the input includes NFR claims (from Section I.1 Non-Functional Requirements
or from Test Strategy Section II.2 checked items), generate corresponding test
scenarios to ensure NFR claims are backed by testable scenarios in Section III.

### NFR-to-Scenario Cross-Reference

For each NFR category claimed in the input, verify at least one scenario exists
that tests it. If not, generate one.

| NFR Category | Required Scenario Type | Generation Trigger |
|:-------------|:-----------------------|:-------------------|
| Security | At least one security-negative scenario | No scenario tests rejection, unauthorized access, or input validation |
| Performance | At least one measurable performance scenario | No scenario includes a quantifiable threshold or latency check |
| Scalability | At least one scale-boundary scenario | No scenario tests behavior at scale limits or concurrency bounds |
| Monitoring | At least one observability scenario | No scenario tests metrics, alerts, or health endpoints |
| Usability | At least one user-workflow scenario | No scenario tests end-user interaction path |

When generating an NFR-driven scenario, tag it with `nfr_source` metadata so
downstream tools can trace it back to the NFR claim:

```yaml
- description: Verify API rejects malformed resource name
  type: negative
  nfr_source: Security
```

### Security-Specific Scenario Probing

When the feature involves any of these indicators, probe for security scenarios
even if Security Testing is not explicitly checked in the strategy:

- User input accepted via API (names, paths, configurations)
- File paths or resource paths in specifications
- External data sources consumed
- User-provided strings used in operations

Generate scenarios for these security patterns when applicable:

| Security Pattern | Scenario to Generate | When Applicable |
|:-----------------|:---------------------|:----------------|
| Input validation | Verify API rejects malformed input | Any API that accepts user input |
| Injection prevention | Verify special characters in input are handled safely | Any user-provided string used in commands or queries |
| Path traversal | Verify path traversal attempts are rejected | Any feature accepting file or resource paths |
| Authorization boundary | Verify unauthorized users cannot perform the operation | Any operation with RBAC implications |

**IMPORTANT for path traversal:** When a feature accepts path inputs, scenarios
for path traversal attempts (`../`, absolute paths outside allowed scope) MUST
expect **rejection/failure**, not success. A path normalization scenario should
verify that invalid paths are blocked, not that they resolve correctly.

### Continuous vs End-State Verification

When a requirement or acceptance criterion uses language implying ongoing
verification ("continuous", "throughout", "during the entire", "while running",
"sustained", "persists over time", "uninterrupted"), generate scenarios that
distinguish between:

| Verification Type | Scenario Pattern | Example |
|:------------------|:-----------------|:--------|
| End-state check | Verify final state after operation | Verify service is healthy after restore |
| Continuous verification | Verify condition holds throughout operation | Verify service remains reachable during restore |

If the AC says "continuous verification" or "throughout the operation", the
scenario MUST describe checking an intermediate state or monitoring during the
operation, not just checking the final state. Use patterns like:

- "Verify [metric/condition] remains stable during [operation]"
- "Verify [workload/service] is uninterrupted throughout [operation]"
- "Verify no [failures/errors] occur during [operation window]"

Do NOT generate an end-state-only scenario when the AC requires continuous
verification. This is a semantic mismatch that reviewers flag as a WARNING.

---

## Dimensional Probing (Comprehensive)

The 6 categories above (Basic Operation through Persistence) serve as a quick reference.
The following 12-dimension system provides comprehensive probing for systematic edge
case discovery. Use it after generating scenarios from the quick-reference categories.

### 12 Exploration Dimensions

| # | Dimension | Probing Question | Example Scenario |
|:--|:----------|:-----------------|:-----------------|
| 1 | Happy Path | Does the primary operation succeed? | Verify password reset via email |
| 2 | Error | What happens when the operation fails? | Verify error for invalid email format |
| 3 | Edge Case | What happens at boundaries (0, 1, max, empty, nil)? | Verify behavior with maximum allowed resource count |
| 4 | Abuse | What if input is malicious or wildly unexpected? | Verify rejection of injection in resource name |
| 5 | Scale | What happens with many resources or large payloads? | Verify operation with 100+ concurrent resources |
| 6 | Concurrent | What if two operations happen simultaneously? | Verify conflict handling for parallel modifications |
| 7 | Temporal | What if timing or ordering matters? | Verify operation during ongoing failover |
| 8 | Data Variation | What if data format or encoding varies? | Verify handling of unicode in resource names |
| 9 | Permission | Who can and cannot perform this? | Verify non-admin cannot modify resource |
| 10 | Integration | How does this interact with other features? | Verify feature works after failover |
| 11 | Recovery | What happens after failure or crash? | Verify state restored after service crash |
| 12 | State Transition | What happens across lifecycle transitions? | Verify state preserved through restart |

### Mapping to Quick-Reference Categories

| Quick-Reference Category | Maps to Dimension(s) |
|:-------------------------|:---------------------|
| Basic Operation | 1 (Happy Path) |
| Error Handling | 2 (Error) |
| State Validation | 12 (State Transition) — expanded to cover full lifecycle |
| Permission Check | 9 (Permission) |
| Recovery | 11 (Recovery) |
| Persistence | 12 (State Transition) — subsumed |
| *(new)* | 3 (Edge Case), 4 (Abuse), 5 (Scale), 6 (Concurrent), 7 (Temporal), 8 (Data Variation), 10 (Integration) |

### Feature-Type Weighting

Not all dimensions apply equally. Use this lookup table to determine which dimensions
to probe heavily based on feature keywords from the Jira component, labels, or
requirement description.

| Feature Keywords | Probe Heavily | Probe Lightly |
|:-----------------|:--------------|:--------------|
| network, connectivity, endpoint, gateway | Concurrent, Scale, Integration, Temporal | Abuse, Data Variation |
| storage, volume, backup, snapshot, cache | Recovery, State Transition, Scale, Edge Case | Abuse, Temporal |
| failover, replication, ha, recovery | Temporal, Concurrent, State Transition, Integration | Abuse, Data Variation |
| API, RBAC, auth, permission, webhook | Abuse, Permission, Edge Case, Data Variation | Scale, Temporal |
| upgrade, update, version, lifecycle | State Transition, Integration, Recovery, Edge Case | Abuse, Concurrent |
| config, settings, resource, allocation | Concurrent, Edge Case, State Transition | Abuse, Data Variation |
| UI, dashboard, console | Data Variation, Permission, Edge Case | Scale, Concurrent |

The weighting table is a heuristic guide, not a hard gate. If a "probe lightly"
dimension yields a clearly valuable scenario, include it.

### Probing Execution Flow

For each requirement:

1. **Generate base scenarios** using the existing quick-reference categories
   (positive, negative, E2E) as described above
2. **Determine feature keywords** from `requirement_summary` and `evidence`
3. **Look up high-priority dimensions** from the weighting table
4. **Probe each high-priority dimension** not already covered by step 1:
   - Ask the probing question against this specific requirement
   - If the answer yields a meaningful, non-duplicate scenario: add it
   - If redundant with an existing scenario: skip
5. **Apply consolidation rules** (existing — no duplicates, no platform-level tests)
6. **Cap total scenarios** at 2-7 per requirement (bias toward lower end for simple
   features, upper end for complex features with many applicable dimensions)

Probed scenarios follow all existing format rules:

- 5-10 word descriptions
- Action verb prefix (Verify, Test, Validate, Confirm)
- No test steps, preconditions, or expected results
- No specific commands, API calls, or values
- Describes WHAT is tested, not HOW

Do NOT generate scenarios for dimensions that produce trivial or platform-level tests
(existing exclusion rules still apply).

### Probing Examples

These examples show how dimensional probing produces scenarios the quick-reference
categories alone would miss.

#### Example 1: Webhook Registration Feature

**Requirement:** Webhook endpoint can be registered for event notifications

**Base scenarios (from quick-reference categories):**

- Verify webhook registration succeeds (Happy Path)
- Verify error for invalid endpoint URL (Error)
- Verify webhook state after service restart (State Transition)
- Verify non-admin cannot register webhooks (Permission)

**Feature keywords:** API, webhook, endpoint

**High-priority dimensions:** Abuse, Permission, Edge Case, Data Variation

**Dimensional probing adds:**

- Verify behavior when two webhooks registered simultaneously (Concurrent)
- Verify registration during ongoing failover (Temporal)
- Verify registration with maximum webhooks already registered (Edge Case/Scale)

#### Example 2: Data Backup Feature

**Requirement:** Backup can be created from active database

**Base scenarios (from quick-reference categories):**

- Verify backup creation from active database (Happy Path)
- Verify error on insufficient storage (Error)
- Verify backup data integrity after restore (Recovery)
- Verify non-admin cannot create backup (Permission)

**Feature keywords:** storage, backup, data

**High-priority dimensions:** Recovery, State Transition, Scale, Edge Case

**Dimensional probing adds:**

- Verify backup during active write workload (Concurrent)
- Verify backup of maximum-size dataset (Scale)
- Verify backup restore after service crash (Recovery + State Transition)

#### Example 3: RBAC Authorization Feature

**Requirement:** Authorization validates RBAC permissions for API operations

**Base scenarios (from quick-reference categories):**

- Verify webhook permits authorized operation (Happy Path)
- Verify webhook rejects unauthorized operation (Error)
- Verify webhook state after API server restart (Recovery)

**Feature keywords:** RBAC, webhook, permission

**High-priority dimensions:** Abuse, Permission, Edge Case, Data Variation

**Dimensional probing adds:**

- Verify webhook rejects malformed permission payload (Abuse)
- Verify behavior with empty role binding list (Edge Case)
- Verify handling of special characters in role names (Data Variation)
