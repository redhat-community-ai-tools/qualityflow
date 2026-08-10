---
name: tier-classifier
description: Classify test scenarios into project-defined tiers
model: claude-opus-4-6
---

# Tier Classifier Skill

**Phase:** Core Processing
**User-Invocable:** false

## Purpose

Classify test scenarios into the tiers defined by the project's `tier*.yaml` config files.
The classifier reads the project's tier configs to discover available tiers and their
`description` fields, then assigns each scenario to the appropriate tier.

## When to Use

Invoked by the **stp-generator** subagent for each test scenario.

## Input

```yaml
scenario:
  requirement_id: PROJ-12345
  requirement_summary: Users can reset their password via email
  test_description: Verify password reset email is sent
  type: positive
  priority: P0
  fix_scope:                          # optional, from github_data
    files_changed: 1
    functions_changed: ["sendResetEmail"]
    packages_changed: ["pkg/auth/reset"]
    requires_cluster_interaction: false
    issue_type: bug                   # bug vs feature

# Available tiers (from project's tier*.yaml configs)
available_tiers:
  - tier: "Tier 1"
    display_name: "Functional"
    description: "Single feature in isolation; API contracts; basic workflows"
  - tier: "Tier 2"
    display_name: "End-to-End"
    description: "Complete user workflows; multi-feature integrations"
```

## Output Format

```yaml
classification:
  requirement_id: PROJ-12345
  test_description: Verify password reset email is sent
  test_type: Tier 1 (Functional)
  reasoning: Tests single feature (password reset) in isolation
```

## Valid Test Types

Valid values are derived from the project's `tier*.yaml` configs. `Unit Tests` is
always available as a built-in tier (developer-responsibility, no auto-generation).

**Built-in tier (always available):**

| Test Type | Description |
|:----------|:------------|
| `Unit Tests` | Isolated components with mocks; validates individual functions/modules. **Note:** Unit tests are classified for tracking in the STP but are developer-responsibility -- no auto-generation pipeline exists for this tier. |

**Project-defined tiers (from `tier*.yaml` configs):**

Each tier config's `tier` and `display_name` fields produce the test type label.
For example, a config with `tier: "Tier 1"` and `display_name: "Functional"` produces
`Tier 1 (Functional)`. The `description` field guides classification decisions.

**Default tiers** (used when no tier configs are available or as reference):

| Test Type | Description |
|:----------|:------------|
| `Tier 1 (Functional)` | Single feature in real cluster; API contracts; basic workflows |
| `Tier 2 (End-to-End)` | Complete user workflows; multi-feature integrations; **user-scenario focused** |

## Key Principle: User-Scenario Focus for Tier 2

**Tier 2 tests are strictly user-scenario focused.** They validate what end users experience and interact with, not internal system behavior, implementation details, or diagnostic information.

**Key Principle:** Tests should only verify observable user outcomes, not internal system state or logs.

## Decision Matrix

| Question | Unit | Tier 1 | Tier 2 |
|:---------|:-----|:-------|:-------|
| Tests isolated functions with mocks? | YES | no | no |
| Tests single feature in a real environment? | no | YES | no |
| Requires multiple features working together? | no | no | YES |
| Tests basic API or component functionality? | no | YES | no |
| Validates complete user workflow? | no | no | YES |
| Can run without infrastructure (mocked dependencies)? | YES | no | no |
| Requires minimal test environment? | no | YES | no |
| Requires production-like environment? | no | no | YES |
| Tests upgrade or migration paths? | no | no | YES |
| Tests at scale (100+ resources)? | no | no | YES |
| Involves multiple services interacting? | no | no | YES |
| Tests data persistence across operations? | no | no | YES |

## Classification Flow (Updated)

```
0. Fix-Scope Demotion Check (optional)
   SKIP if fix_scope is absent OR issue_type is feature/enhancement.
   ONLY activate when fix_scope is present AND issue_type is bug/customer_case/defect.

   a. Single function changed AND requires_cluster_interaction is false?
      YES -> Unit Tests
             reasoning: "Fix modifies single function {name} with no cluster
             interaction. Unit test provides equivalent coverage at lower cost."
      NO  -> Continue

   b. Single package changed AND single resource/entity type?
      YES -> Tier 1 (Functional)
             reasoning: "Fix is scoped to {package}, single resource operation.
             Tier 1 provides equivalent coverage."
      NO  -> Continue to Step 1 (no demotion)

1. Does it require a cluster?
   NO  -> Unit Tests
   YES -> Continue

2. Check Tier 2 PROMOTION triggers first (see below)
   ANY trigger matches -> Tier 2 (End-to-End)
   NO triggers match -> Continue

3. Does it test a single feature in isolation?
   YES -> Tier 1 (Functional)
   NO  -> Tier 2 (End-to-End)
```

**IMPORTANT:** Check Tier 2 triggers BEFORE defaulting to Tier 1.

## Tier 2 Promotion Triggers

**Qualifying Rule:** A trigger matches only when the **test itself** exercises that
workflow as its primary action — not when the feature merely uses that mechanism
internally. Classify based on what the **test** does, not what the **feature** does
under the hood.

Example: A feature that uses database failover internally to apply a config change does NOT
make a test "Failover with active connections" — unless the test's primary
action is to perform and validate a failover. If the test calls an API endpoint and
checks a response, it's Tier 1 regardless of whether failover happens behind
the scenes.

**If ANY of these are true for what the test exercises, classify as Tier 2:**

| Trigger | Example |
|:--------|:--------|
| Involves multiple services interacting | Multi-tier app deployment |
| Tests complete user story/workflow | Register -> Configure -> Use -> Verify state |
| Resources must survive across operations | Data preserved through failover |
| Validates data/state persistence across operations | Backup -> Restore -> Verify data |
| Tests upgrade or version compatibility | Upgrade from v2.0 to v3.0 |
| Requires external systems | External cache, message queue, load balancer |
| Simulates production deployment | Full application stack |
| Tests disaster recovery or failover | Node failure recovery |
| RBAC across multiple resources/operations | User permissions through resource lifecycle |
| Data lifecycle with multiple steps | Create -> Transform -> Archive -> Restore |
| Rolling update with active workload | Update while requests flowing, verify continuity |

## What's NOT in Tier 1

**Classify as Tier 2 (not Tier 1) if the scenario involves:**

- Multi-feature integration scenarios
- Complex end-to-end user workflows and user stories
- Performance and scale testing
- Upgrade scenarios
- Disaster recovery scenarios
- Multi-step workflows (create -> operate -> verify persistence)
- Cross-component interactions

## What Tier 2 Does NOT Test

**Do NOT classify as Tier 2 if testing:**

- Internal debug logs validation (not user-facing)
- Internal component implementation details
- Code-level unit behaviors
- Low-level API internals not exposed to users
- Developer debugging workflows
- Platform-level features outside the project's scope boundaries
- System metrics users don't interact with
- Internal error messages or stack traces

**Note:** Tests may verify user-observable events (user-facing APIs, webhooks) but should not parse internal service logs.

## Tier 1 (Functional) Indicators

Classify as Tier 1 if:

- Tests a single feature in isolation
- Validates API contracts
- Basic CRUD operations
- Single resource lifecycle
- Error handling for single feature
- Basic configuration validation
- **AND** no Tier 2 promotion triggers apply

**Examples:**

- Create resource via API
- Update configuration via REST endpoint
- Create a single backup (single operation)
- Stop a running service
- Attach a single storage volume

## Tier 2 (End-to-End) Indicators

Classify as Tier 2 if:

- Requires multiple features working together
- Tests complete user workflow
- Involves cross-component interaction
- Requires production-like environment
- Tests upgrade/migration paths
- Tests at scale (100+ resources)
- Involves multi-step scenarios with state verification

**Examples:**

- Deploy multi-tier application stack
- Rolling update with active traffic validation
- Create -> Backup -> Restore -> Verify workflow
- Upgrade from version X to Y
- RBAC workflow across resource lifecycle
- Data lifecycle (create -> transform -> archive -> restore)
- Multi-service network communication
- Config change followed by failover and state verification

## Unit Test Indicators

Classify as Unit Tests if:

- Tests individual function/method
- Uses mocks for dependencies
- No cluster required
- Developer responsibility typically

**Examples:**

- Validate input parsing function
- Test error message formatting
- Test configuration parsing

## Common Misclassifications

| Scenario | Wrong | Correct | Reason |
|:---------|:------|:--------|:-------|
| Deploy 3-tier app | Tier 1 | Tier 2 | Multi-service workflow |
| Single failover (one service) | Tier 2 | Tier 1 | Single feature operation |
| API validation | Unit | Tier 1 | Requires real environment |
| Upgrade with active users | Tier 1 | Tier 2 | Multi-step, cross-version |
| Attach single volume | Tier 2 | Tier 1 | Single feature |
| Failover then verify data | Tier 1 | Tier 2 | Multi-step with state verification |
| Backup and restore | Tier 1 | Tier 2 | Multi-step workflow |
| Service survives node drain | Tier 1 | Tier 2 | Cross-component, DR scenario |
| Scale test with 100 instances | Tier 1 | Tier 2 | Scale testing |
| Config change + failover | Tier 1 | Tier 2 | Multi-feature integration |

## Priority Influence

Priority doesn't determine tier:

- P0 can be Tier 1 or Tier 2
- P2 can be Tier 1 or Tier 2

Tier is based on **scope and complexity**, not importance.

## Output Examples

Input:

```yaml
test_description: Verify user can reset password via email
```

Output:

```yaml
test_type: Tier 1 (Functional)
reasoning: Tests single feature (password reset) in isolation, no multi-step workflow
```

Input:

```yaml
test_description: Verify user data preserved through backup and restore
```

Output:

```yaml
test_type: Tier 2 (End-to-End)
reasoning: Multi-step workflow (create -> backup -> restore -> verify data)
```

Input:

```yaml
test_description: Verify upgrade preserves user configuration
```

Output:

```yaml
test_type: Tier 2 (End-to-End)
reasoning: Cross-version testing, requires upgrade scenario
```

Input:

```yaml
test_description: Verify config change followed by failover preserves settings
```

Output:

```yaml
test_type: Tier 2 (End-to-End)
reasoning: Multi-feature integration (config change + failover), state verification across operations
```

Input:

```yaml
test_description: Verify resource can be created with high replica count
```

Output:

```yaml
test_type: Tier 1 (Functional)
reasoning: Single feature (resource creation), single operation, no multi-step workflow
```
