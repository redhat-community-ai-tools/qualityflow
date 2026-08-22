---
name: test-generator
description: Generate working test code from STD YAML — language and framework driven by project config
model: claude-opus-4-6
---

# Test Generator Skill

## Purpose

Generates **working test code** from STD YAML specifications. Reads
project config to determine which languages and frameworks to target.
Not limited to Go and Python — any language declared in config.

**Output:** Working test files that compile/pass collection for each
configured language/framework.

**Note:** For test stubs (design review), use stub-generator skills instead.

---

## Input Required

- `jira_id`: Jira ticket ID (e.g., "MYPROJ-12345")
- `priority_filter`: (Optional) Priority level to generate tests for
  ("P0", "P1", or "P2")

**Prerequisites:**
- STD YAML at `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`
- At least one language config file in `{project_context.config_dir}/`

---

## Output

```
outputs/{JIRA_ID}/go-tests/           (if Go enabled)
├── {feature}_test.go
└── summary.yaml

outputs/{JIRA_ID}/python-tests/       (if Python enabled)
├── test_{feature}.py
├── conftest.py
└── summary.yaml

outputs/tests/{JIRA_ID}/{language}/   (any other language)
└── ...
```

---

## CRITICAL REQUIREMENT

**Generate ONE test case per STD scenario. No exceptions.**

- 19 STD scenarios → 19 generated test functions/blocks
- Pattern-based file grouping is allowed, but EVERY scenario gets a test

---

## Workflow

### Step 1: Discover Language Targets

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
- `imports` — organized by category (standard, framework, project)
- `build_command` — validation command
- `test_patterns` — naming conventions

### Step 2: Read STD YAML

Load `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`

Extract:
- Total scenario count
- Scenarios grouped by tier/type
- Test objectives, steps, assertions

### Step 2.5: Filter by Coverage Status and Priority

**Coverage filtering (existing behavior):**

Remove scenarios with `coverage_status: EXISTING_COVERAGE` from the working
set — no test code is generated for them. For each skipped scenario, emit a
reference comment in the output file:

```go
// Scenario {scenario_id}: covered by existing test {covered_by.test_function}
```

**Priority filtering (new):**

If `priority_filter` is provided:

1. Remove scenarios where `priority != priority_filter` from working set
2. Scenarios missing the `priority` field are included (backwards compatible)
3. Log the filtering result:

   ```text
   Generating tests for priority {priority_filter}: {N} scenarios
   Skipping {M} scenarios with different priorities
   ```

If `priority_filter` is null, all scenarios proceed (default behavior).

**Final working set:** Scenarios with (`coverage_status` != EXISTING_COVERAGE)
AND (`priority` == priority_filter OR priority_filter is null OR priority
field missing)

**Coverage targets (optional):**

When a scenario carries `coverage_targets`, the generated test exists to make
those specific lines execute. Two obligations:

1. **Generate it first.** Order the working set so scenarios with
   `coverage_targets` come before those without. If generation is truncated
   for any reason, the gap-closing tests are the ones that survive.
2. **Record the target in the test.** Emit the target as a comment on the
   generated test function so a reviewer can verify the claim:

   ```go
   // Coverage target: internal/harness/compose.go:45-47 (ResolveOverlays)
   ```

Do not assert on coverage numbers inside the test — the test must fail for
behavioral reasons, not coverage reasons. `coverage_targets` documents intent
and drives ordering; it is not a test oracle.

A scenario whose `coverage_status_source` is `measured` must never be dropped
as a duplicate on static grounds — a measurement already disagreed with static
analysis once for this scenario.

### Step 3: Load Pattern Rules

**If config_dir is null:** Skip config-based pattern loading. Use only LSP patterns
(if available) and the `code_generation_config` from the STD YAML.

**If config_dir is available:** For each enabled language, read patterns from:
- `{project_context.config_dir}/patterns/{language}_patterns.yaml`
- Fresh LSP patterns if available

### Step 4: Generate Tests Per Language

For each enabled language config, generate test files using the
appropriate framework section below.

---

## Framework: Go `testing` (standard library + testify)

When `framework: "testing"` in the language config:

**File structure:**
```go
//go:build {build_tags}

package {package_name}

import (
    "testing"
    // standard imports from config
    // framework imports from config
    // project imports from config
)

func TestFeatureName(t *testing.T) {
    // shared setup

    t.Run("scenario description", func(t *testing.T) {
        // test implementation
        // use assert.Equal(t, expected, actual)
        // use require.NoError(t, err) for fatal checks
    })
}
```

**Rules:**
- Function prefix from `test_patterns.function_prefix` (default: "Test")
- Subtest style from `test_patterns.subtest_style` (default: "t.Run")
- Assertion style from `test_patterns.assertion_style` (default: "testify")
- Build tags from `build_tags` array → `//go:build tag1 && tag2`
- Import paths from `imports.standard`, `imports.test_framework`, `imports.project`
- Package name from `default_package` or derived from test file location

**Validation:**
- Count `t.Run(` calls = count of STD scenarios
- All imports resolve (no unused imports)
- Build tag line present if `build_tags` configured

---

## Framework: Go `ginkgo-v2` (Ginkgo v2 + Gomega)

When `framework: "ginkgo-v2"` in the language config:

**File structure:**
```go
package {package_name}

import (
    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    // other imports from config
)

var _ = Describe("[JIRA-ID] Feature", func() {
    Context("scenario group", func() {
        It("[test_id:TS-XXX] should do X", func() {
            // test implementation
        })
    })
})
```

**Rules:**
- Dot imports for ginkgo and gomega
- `Describe/Context/It` hierarchy
- `[test_id:TS-XXX]` labels in `It()` descriptions
- `BeforeEach` for shared setup
- `Expect().To()` / `Expect().NotTo()` for assertions

**Validation:**
- Count `It(` blocks = count of STD Functional scenarios
- All `[test_id:TS-XXX]` present

---

## Framework: Python `pytest`

When `framework: "pytest"` in the language config:

**File structure:**
```python
"""Tests for {feature} — {JIRA_ID}."""
import pytest
# imports from config

class TestFeature:
    """Tests for feature X.

    Markers:
        - {markers}

    Preconditions:
        - {preconditions}
    """

    def test_scenario_name(self, fixture1, fixture2):
        """Scenario: {description} [TS-XXX]."""
        # test implementation
        assert result == expected
```

**Rules:**
- `def test_*()` naming convention
- Scenario ID in docstring for traceability
- `conftest.py` for shared fixtures (if multiple test files)
- Fixture naming: nouns, not verbs
- Context managers for resources
- No `time.sleep()` — use polling utilities

**Validation:**
- Count `def test_*` functions = count of STD End-to-End scenarios
- All scenario IDs in docstrings
- `pytest --collect-only` passes (if pytest available)

---

## Polarion Toggle

If `project_context.feature_toggles.polarion` is false, omit Polarion
test case ID markers from generated test code.

## Repo Rules Integration

When `project_context.repo_rules` is available (e.g., AGENTS.md rules),
apply those coding standards to all generated test code. Common rules:
- Implicit markers (don't add explicitly)
- Forbidden patterns (skip/skipif, etc.)
- Fixture guidelines
- Import conventions

---

## Step 5: Validate Complete Coverage

**CRITICAL VALIDATION — MANDATORY**

After all files generated:

1. Count STD scenarios per tier/type
2. Count generated test cases per language
3. Verify 1:1 mapping: every scenario has a test
4. Report missing scenario IDs

**Priority filter applied:** If `priority_filter` was provided, validation
counts should match filtered scenarios only, not total STD scenarios. Report:

- Total STD scenarios: {total}
- Filtered to priority {priority_filter}: {filtered_count}
- Generated test cases: {generated_count}
- Coverage: {generated_count}/{filtered_count} scenarios

---

## Step 6: Report Results

Generate summary per language:
- Language, framework
- Files generated, line counts
- Test count, scenario coverage
- LSP patterns used (true/false)
- Any errors or warnings

---

## Error Handling

**STD not found:** Error + suggest running `/std-builder` first.

**No language configs:** Error + suggest creating language YAML in config.

**Pattern not recognized:** Warning + fall back to direct STD-to-test generation.

**Validation fails:** Save to `.invalid` extension, show errors, continue.

---

**End of Test Generator Skill**
