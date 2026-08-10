---
name: stub-generator
description: Generate test stubs with PSE docstrings from STD YAML — language and framework driven by project config
model: claude-opus-4-6
---

# Stub Generator Skill

## Purpose

Generates **test stubs with PSE docstrings** from STD YAML for design review (Phase 1).
Reads project config to determine which languages and frameworks to target.

**Output:** Test stubs excluded from execution, containing PSE
documentation (Preconditions/Steps/Expected) as the deliverable for
human review.

**Key Principle:** The STD = the docstrings/comments in the test files
(no separate document needed for review).

---

## Input Required

- `jira_id`: Jira ticket ID (e.g., "MYPROJ-12345", "GH-2247")
- `priority_filter`: (Optional) Priority level to generate stubs for
  ("P0", "P1", or "P2")

**Prerequisites:**

- STD YAML at `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`
- At least one language config file in `{project_context.config_dir}/`

---

## Output

```
outputs/std/{JIRA_ID}/
├── {JIRA_ID}_test_description.yaml        (STD YAML — already exists)
├── go-tests/                              (if Go config enabled)
│   └── {feature}_stubs_test.go
└── python-tests/                          (if Python config enabled)
    └── test_{feature}_stubs.py
```

For other languages: `outputs/std/{JIRA_ID}/{language}-tests/`

---

## CRITICAL REQUIREMENT

**Generate ONE test stub per STD scenario. No exceptions.**

- CORRECT: 12 STD scenarios, 1 Go config enabled → 12 stub functions
- CORRECT: 12 STD scenarios (9 Tier 1, 3 Tier 2), Go + Python configs → 9 Go + 3 Python stubs
- WRONG: 12 STD scenarios → 5 test files with some scenarios omitted

**Pattern-based file grouping is allowed**, but **EVERY scenario must get
a test stub in at least one language.**

---

## Workflow

### Step 1: Read STD YAML

Load `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`

**Extract:**

- Total scenario count: `len(scenarios)`
- Each scenario's tier field (if present)
- Test objectives, preconditions, steps, assertions

### Step 2: Discover Language Targets

**Auto-discovery guard:** If `project_context.config_dir` is null (auto-discovered
project), read the `code_generation_config` section from the STD YAML instead of
scanning config files. The STD YAML already contains language, framework, and import
information populated by the test-strategy-resolver during STD generation. Skip the
config file scan entirely and build the language target map from STD metadata.

**When config_dir is available:** Scan `{project_context.config_dir}/` for YAML files with
`enabled: true` and a `language:` field:

```bash
for f in {project_context.config_dir}/tier*.yaml; do
  # Each tier config has: enabled, tier, language, framework fields
  # Teams create one file per tier: tier1.yaml, tier2.yaml, tier3.yaml, etc.
done
```

Each tier config provides:

- `tier` — tier label for routing (e.g., "Tier 1", "Tier 2", "Tier 3")
- `language` — "go", "python", etc.
- `framework` — "testing", "ginkgo-v2", "pytest", etc.
- `reference_guide` (optional) — URL to team's testing guide for this tier
- `reference_tests` (optional) — URLs to example test files
- `imports` — organized by category
- `default_package` — package name for Go files

### Step 2.5: Filter by Coverage Status and Priority

**Coverage filtering (existing behavior):**

Remove scenarios with `coverage_status: EXISTING_COVERAGE` from the working
set. These represent behaviors already covered by existing tests and do not
need stubs generated.

Log the count: `"Skipping {N} scenarios with existing coverage"`

**Priority filtering (new):**

If `priority_filter` is provided:

1. Remove scenarios where `priority != priority_filter` from working set
2. Scenarios missing the `priority` field are included (backwards compatible)
3. Log the filtering result:

   ```text
   Generating stubs for priority {priority_filter}: {N} scenarios
   Skipping {M} scenarios with different priorities
   ```

If `priority_filter` is null, all scenarios proceed (default behavior).

**Final working set:** Scenarios with (`coverage_status` != EXISTING_COVERAGE)
AND (`priority` == priority_filter OR priority_filter is null OR priority
field missing)

Scenarios from the final working set proceed to Step 3.

### Step 3: Map Scenarios to Language Targets

**For each enabled language config:**

1. **If the config declares a `tier:` field:**
   Filter STD scenarios to ONLY those matching that tier.
   Matching is prefix-based: scenario tier "Tier 2 (End-to-End)" matches
   config tier "Tier 2".

2. **If the config has NO `tier:` field:**
   Generate stubs for ALL STD scenarios in this language.
   This is the full-coverage mode — used by projects where there is a
   single language and tiers are not relevant.

**Result:** A map of `{language_config: [scenario1, scenario2, ...]}`

**Validation after mapping:**
Every STD scenario must be assigned to at least one language. If any
scenario is unassigned (e.g., a Tier 2 scenario exists but no config
maps to Tier 2), log a warning listing the unmapped scenarios.

### Step 4: Generate Stubs Per Language

For each enabled language config and its assigned scenarios, generate
stub files using the appropriate framework section below.

**For each scenario:**

1. Extract PSE information from STD YAML (see Transformation Rules below)
2. Generate stub with PSE documentation
3. Apply the framework-specific exclusion mechanism

**After all scenarios processed:**

4. Assemble into file(s) grouped by feature pattern
5. Save to `outputs/std/{JIRA_ID}/{language}-tests/`

### Step 5: Validate Complete Coverage

**CRITICAL VALIDATION — MANDATORY**

After all files generated:

1. Count STD scenarios assigned to each language: `N_assigned`
2. Count generated stubs per language: `N_stubs`
3. Verify: `N_stubs == N_assigned` for each language
4. Verify: every STD scenario appears in at least one language's stubs
5. If any scenario is missing: ERROR + list missing scenario IDs

**Priority filter applied:** If `priority_filter` was provided, validation
counts should match filtered scenarios only, not total STD scenarios. Report:

- Total STD scenarios: {total}
- Filtered to priority {priority_filter}: {filtered_count}
- Generated stubs: {generated_count}
- Coverage: {generated_count}/{filtered_count} scenarios

### Step 6: Report Results

Generate summary per language:

- Language, framework
- Scenarios assigned, stub files generated
- Total lines
- Coverage validation result (PASS/FAIL)

---

## Phase 1 Prohibitions (All Languages)

Phase 1 stubs are **design-only**. The following MUST NOT appear:

- No fixture/helper definitions
- No framework-specific decorators or annotations
  **Exception:** `@pytest.mark.polarion("PLACEHOLDER")` when `polarion: true`
- No fixture/helper parameters in test signatures
- No framework imports beyond the minimum needed for the stub pattern
  **Exception:** `import pytest` when `polarion: true` (needed for the decorator)
- No PR references (PRs are STP-level context, not STD)
- No block comments above tests (all info in docstrings/PSE comments)
- No fixture names in Preconditions (use descriptive requirements)
  - GOOD: "Running application with standard image"
  - BAD: "Running resource (resource_to_restart fixture)"

---

## Framework: Go `ginkgo-v2`

When `framework: "ginkgo-v2"` in the language config:

### File Structure

```go
package {default_package}  // from config

import (
    . "github.com/onsi/ginkgo/v2"  // from config dot_imports
)

/*
{Feature} Tests

STP: {STP_URL}
Jira: {JIRA_ID}
*/

var _ = Describe("[{JIRA_ID}] {Feature}", {domain_decorator}, func() {
    /*
    Markers:
        - tier1

    Preconditions:
        - {shared preconditions}
    */

    Context("{context name}", func() {
        /*
        Preconditions:
            - {test-specific precondition}

        Steps:
            1. {step 1}
            2. {step 2}

        Expected:
            - {expected outcome}
        */
        PendingIt("[test_id:TS-{ID}-001] should {description}", func() {
            Skip("Phase 1: Design only - awaiting implementation")
        })
    })
})
```

**Rules:**

- Package name from config `default_package`
- Imports: ONLY dot-import of ginkgo/v2 (from config `dot_imports`)
- No gomega import (not needed for stubs)
- `PendingIt()` with `Skip()` inside — excluded from execution
- PSE as block comments (`/* */`) ABOVE each `PendingIt`
- `[test_id:TS-{JIRA_ID_SHORT}-{NNN}]` label in description
- Shared preconditions in `Describe` block comment
- Decorators from config (e.g., `decorators.SigNetwork`)

**Output:** `outputs/std/{JIRA_ID}/go-tests/{feature}_stubs_test.go`

---

## Framework: Go `testing`

When `framework: "testing"` in the language config:

### File Structure

```go
//go:build {build_tags}

package {default_package}  // from config

import "testing"

/*
{Feature} Tests

STP: {STP_URL}
Jira: {JIRA_ID}
*/

func TestFeatureName(t *testing.T) {
    /*
    Preconditions:
        - {shared preconditions}
    */

    /*
    Preconditions:
        - {test-specific precondition}

    Steps:
        1. {step 1}
        2. {step 2}

    Expected:
        - {expected outcome}
    */
    t.Run("should {description}", func(t *testing.T) {
        t.Skip("Phase 1: Design only - awaiting implementation")
    })
}
```

**Rules:**

- Package name from config `default_package`
- Build tags from config `build_tags` → `//go:build tag1`
- Import: ONLY `"testing"` (no testify needed for stubs)
- `t.Skip()` inside each subtest — excluded from execution
- PSE as block comments (`/* */`) ABOVE each `t.Run`
- Top-level `func TestXxx(t *testing.T)` groups related subtests
- Shared preconditions as comment block inside test function

**Output:** `outputs/std/{JIRA_ID}/go-tests/{feature}_stubs_test.go`

---

## Framework: Python `pytest`

When `framework: "pytest"` in the language config:

### File Structure

```python
"""
{Feature Name} Tests

STP: {STP_URL}
Jira: {JIRA_ID}
"""


class TestFeatureName:
    """
    Tests for {feature description}.

    Markers:
        - gating

    Parametrize:
        - storage_class: [default-storage-class, local-storage]

    Preconditions:
        - {Shared precondition 1 — resource creation}
        - {Shared precondition 2 — baseline data recorded}
    """
    __test__ = False

    def test_specific_behavior(self):
        """
        Test that {specific ONE thing being verified}.

        Preconditions:
            - {Test-specific precondition}

        Steps:
            1. {Discrete action}

        Expected:
            - {Concrete, verifiable assertion}
        """
```

**Rules:**

- Module docstring: STP link + Jira only (no PR refs, no feature gates)
  Use `STP:` as the keyword (not `STP Reference:`). Target repo CI checks
  match on this exact keyword.
- Class docstring: shared Preconditions + optional Markers + optional Parametrize
- `__test__ = False` on class level (grouped tests) or after function (standalone)
- Test methods: PSE docstring as function body (no `pass` — docstring is sufficient)
- `def test_foo(self):` — no fixture parameters in signature
- No `import pytest`, no `@pytest.fixture`, no `@pytest.mark.*` decorators
  **Exception:** `import pytest` + `@pytest.mark.polarion("PLACEHOLDER")` when
  `polarion: true` in project config
- **STP URL resolution:** When `stp_reference.url` exists in the STD YAML metadata
  (set by std-orchestrator when the STP has been merged into the design-docs repo),
  use that URL as `{STP_URL}`. Otherwise fall back to the local file path from
  `stp_reference.file`. Merged URLs are preferred because they remain valid after
  the output directory is cleaned up.
- `python` marker is implicit (NOT listed) — only list non-auto markers (e.g., `gating`, `arm64`)
- Markers documented in docstring `Markers:` section only.
  **Include ONLY markers that will become real `@pytest.mark.*` decorators in Phase 2.**
  Priority values (P0/P1/P2) are NOT markers — they are STD metadata.
  Tier classification (tier2, end_to_end) is implicit — do NOT list it.
  Team/SIG markers (storage, network, compute) are implicit — do NOT list them.
  If no non-implicit markers apply, **omit the `Markers:` section entirely**.
- Parametrize documented in docstring `Parametrize:` section only
- `[NEGATIVE]` prefix for failure scenario tests

**Standalone test (no class needed):**

```python
def test_specific_behavior():
    """
    Test that {specific ONE thing being verified}.

    Steps:
        1. {Discrete action}

    Expected:
        - {Concrete, verifiable assertion}
    """

test_specific_behavior.__test__ = False
```

**Output:** `outputs/std/{JIRA_ID}/python-tests/test_{feature}_stubs.py`

### Specialized (Tier 3) Tests

Specialized tests use the same Python/pytest framework as End-to-End tests.
The stub-generator treats Specialized scenarios identically to End-to-End
scenarios for stub generation. The distinction is documented via markers:

```python
class TestSpecializedFeature:
    """
    Tests for {feature description} (Specialized).

    Markers:
        - specialized
        - {hardware_marker}

    Preconditions:
        - {Hardware-specific precondition}
    """
    __test__ = False

    def test_specific_behavior(self):
        """
        Test that {specific ONE thing being verified}.

        Preconditions:
            - {Specialized infrastructure precondition}

        Steps:
            1. {Discrete action}

        Expected:
            - {Concrete, verifiable assertion}
        """
```

The `specialized` marker and any hardware-specific markers (`gpu`, `sriov`,
`numa`, `ceph`, etc.) are documented in the docstring `Markers:` section.

### Repo Rules Integration (Python)

When `project_context.repo_rules` is available, the following rules
from the target repository's AGENTS.md **override** defaults:

- **`python` is implicit** — Do NOT add `@pytest.mark.python`. Do NOT
  include `python` in the Markers docstring section.
- **Team markers are implicit** — project-specific team markers are added
  automatically. Do NOT add them explicitly.
- **`pytest.skip/skipif` are forbidden** — Do not use in generated code.
- **`@pytest.mark.incremental`** for dependent tests within a class.
- **Fixture names must be nouns** — `resource_with_storage`, not `create_resource_with_storage`.
- **conftest.py is for fixtures only** — No helpers in conftest.
- **STP link required in module docstring.**

### Class-Level Preconditions (Python)

Class-level Preconditions include ONLY test-specific setup:
- Resource creation (application instances, network configs, pods, peer resources)
- Baseline data recording (identifiers, IP addresses, interface names)

Do NOT include:
- Test environment requirements (cluster version, node count, storage type)
- Platform prerequisites (platform version, product version, operator installations)

Tests assume the test environment described in the STP is already in place.
Tests that share the same setup MUST be grouped in one class.

**Shared Resource Repetition Rule:** When a test method's Steps or Expected
reference a resource declared in the shared (class-level) Preconditions, that
resource MUST also appear in the test method's own `Preconditions:` section.
This follows the repo convention: "When a shared resource (e.g., a VM) is
directly used by a test, it must appear in both the shared and test-level
preconditions."

Use functional language for the repeated precondition — describe the state,
not the mechanism:

- GOOD: `Preconditions:\n  - VM with Velero backup hooks disabled`
- BAD: `Preconditions:\n  - VM with per-VM opt-out annotation set`

### Precondition Abstraction Rule (Python)

All precondition text in stubs MUST describe the test state from the user's
perspective, not the implementation mechanism. Apply the same rewrite principles
as the STP Pre-Writing Abstraction Pass:

| Implementation Language | Functional Language |
|-------------------------|---------------------|
| "per-VM opt-out annotation" | "VM with backup hooks disabled" |
| "CRD with spec.sourcePartition set" | "restore request targeting a specific partition" |
| "controller reconciles the CR" | "restore request is processed" |
| "rsync connection established" | "file transfer connection ready" |
| "filerestore.sh helper deployed" | "restore helper available on target VM" |

This applies to BOTH shared (class-level) and test-specific preconditions.

### Polarion Marker (Conditional — Python)

When `polarion: true` in the project's feature toggles, every test function MUST have
a `@pytest.mark.polarion("PLACEHOLDER")` decorator. This is the **only** `@pytest.mark`
decorator allowed in Phase 1 stubs.

**When enabled**, add `import pytest` at the top of each file and decorate every test:

```python
import pytest


class TestFeatureName:
    """..."""
    __test__ = False

    @pytest.mark.polarion("PLACEHOLDER")
    def test_specific_behavior(self):
        """
        Test that {specific ONE thing being verified}.
        ...
        """
```

For standalone tests:

```python
@pytest.mark.polarion("PLACEHOLDER")
def test_standalone_behavior():
    """..."""

test_standalone_behavior.__test__ = False
```

**When `polarion: false`** (or not set): Do NOT add the marker or `import pytest`.

The `"PLACEHOLDER"` value is intentional — it will be replaced with the actual Polarion
test case ID during Phase 2 implementation or by CI tooling.

**Enforcement:** When `polarion: true`, the stub-generator MUST NOT output any
Python test stub file without `import pytest` at the top and
`@pytest.mark.polarion("PLACEHOLDER")` on every `def test_*` function. Omitting
the marker is a generation error — Polarion-integrated projects require it for
test case traceability.

### Dependent Tests (Incremental — Python)

When tests within a class depend on execution order, use `@pytest.mark.incremental`
in the class Markers docstring section:

```python
class TestSomeFeature:
    """
    Tests for feature with ordered dependencies.

    Markers:
        - incremental

    Preconditions:
        - Running resource with feature configured
    """
    __test__ = False

    def test_resource_is_created(self):
        """Test that a resource with feature can be created."""

    def test_resource_migration(self):
        """Test that a resource with feature can be migrated."""
```

---

## Polarion Toggle

If `project_context.feature_toggles.polarion` is false, omit Polarion
marker references from stubs (both Go and Python).

---

## PSE Boundary Rules (All Languages)

These rules are mandatory and apply to ALL frameworks. They define what
goes in each PSE section regardless of language.

### What goes in Preconditions (setup — before the test runs)

- ALL resource creation: application instances, network configs, pods, peer resources, storage
- ALL baseline data recording: "Record identifier", "Save IP address"
- Baseline state verification: confirming the starting state before the test action
- Any action that establishes the starting state for the test
- **Never** test environment requirements (cluster version, node count, operator version)

### What goes in Steps (actions — during the test)

- The test action itself: "Patch resource spec", "Execute ping", "Wait for completion"
- ONLY actions that are part of the test execution
- **Never** resource creation (that's a Precondition)
- **Never** verification statements (that's Expected)

### What goes in Expected (assertions — what the test verifies)

- Outcome verification: checking the RESULT of the test action
- Any "Verify/Confirm/Check/Ensure/Assert" that checks the OUTCOME belongs here
- Must be **concrete and verifiable**:
  - GOOD: "MAC address equals pre-change value"
  - GOOD: "Ping succeeds with 0% packet loss"
  - GOOD: "Resource is ready"
  - BAD: "Interfaces correctly configured" (missing the how)
  - BAD: "Everything works" (not verifiable)
- Must describe the **observable outcome**, not the internal mechanism

**Single-Expected Rule:** Each test MUST have exactly ONE `Expected:` statement
that captures the unified behavioral outcome. When the STD YAML `assertions` array
contains multiple entries, consolidate them into a single sentence describing the
overall expected result. The individual assertions inform the implementation (Phase 2),
not the design (Phase 1).

- WRONG: `Expected:\n  - Backup completes with status Completed\n  - No hooks executed`
- RIGHT: `Expected: Backup completes successfully without hook execution`

If multiple assertions test genuinely different aspects, that is a signal that the
scenario should be split into separate tests (one per aspect). Flag this during
generation and produce separate stubs.

**Baseline vs Outcome verification:**

- Baseline verification (before the test action) -> **Preconditions**
- Outcome verification (after the test action) -> **Expected**

### Quick Reference

| Action | PSE Section | Example |
|--------|-------------|---------|
| Create resource/config/pod | **Preconditions** | "Running resource with secondary interface" |
| Record baseline data | **Preconditions** | "Identifier and interface name recorded" |
| Verify baseline state | **Preconditions** | "Resource is in Ready state before test action" |
| Patch/Update resource | **Steps** | "Update resource spec to reference target config" |
| Wait for completion | **Steps** | "Wait for operation to complete" |
| Execute command | **Steps** | "Ping from resource-A to resource-B" |
| Verify/Confirm outcome | **Expected** | "Ping succeeds with 0% packet loss" |
| Assert state | **Expected** | "Resource is ready after operation" |

---

## STD YAML to PSE Transformation

### Field Mapping

| STD YAML Field | PSE Section | Transformation |
|----------------|-------------|----------------|
| `test_objective.title` | Brief description | "Test that {title}" (Python) / "should {title}" (Go) |
| `specific_preconditions[*].requirement` | Preconditions | Bullet list |
| `test_steps.setup` | Preconditions (context) | Add to preconditions |
| `test_steps.test_execution[*].action` | Steps | Numbered list — filter "Verify/Confirm" actions to Expected |
| `test_objective.acceptance_criteria[0]` | Expected | Natural language |
| `assertions[*].description` | Expected (fallback) | Natural language |
| Title contains "fail"/"error"/"negative" | [NEGATIVE] marker | Prefix in description |

### Assertion Wording Patterns (for Expected section)

| Wording Pattern | Maps To |
|-----------------|---------|
| `X equals Y` | `assert x == y` |
| `X does not equal Y` | `assert x != y` |
| `Resource is "Ready"` | `assert resource.status == Ready` |
| `File exists` / `Resource x exists` | `assert exists(x)` |
| `X contains Y` | `assert y in x` |
| `Ping succeeds` / `Operation succeeds` | `assert operation()` (no exception) |
| `Ping fails` / `Operation fails` | `assert` raises exception or returns failure |

---

## Success Criteria

Stub generation succeeds when:

- Every STD scenario has a corresponding stub function in at least one language
- Every stub has PSE documentation (Preconditions/Steps/Expected)
- Each test verifies **ONE thing** with ONE Expected
- Related tests are grouped (classes in Python, top-level funcs in Go)
- Stubs are excluded from execution (PendingIt/t.Skip/__test__=False)
- Negative tests are marked with `[NEGATIVE]`
- Valid syntax in all generated files
- Files saved to `outputs/std/{JIRA_ID}/{language}-tests/`

---

## Error Handling

**STD not found:**

- Error: "STD file not found at outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml"
- Suggestion: "Run `/std-builder {JIRA_ID}` first"
- Exit

**No language configs found:**

- Error: "No enabled language configs found in {project_context.config_dir}/"
- Suggestion: "Create a {language}.yaml config with `enabled: true`"
- Exit

**Unmapped scenarios (warning, not fatal):**

- Warning: "N scenarios have no matching language config (tier: X)"
- List scenario IDs
- Continue with mapped scenarios

---

**End of Stub Generator Skill**
