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

**Prerequisites:**

- STD YAML at `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`
- At least one of:
  - Language config file in `{project_context.config_dir}/` (tier mode)
  - `code_generation_config` in STD YAML (auto mode — `config_dir` may be null)

---

## Output

Test files are **always** written directly into source package directories
with `qf_` filename prefix, co-located with production code:

```
{resolved_package}/qf_{feature}_test.go      (Go)
{resolved_package}/qf_test_{feature}.py       (Python)
outputs/go-tests/{JIRA_ID}/summary.yaml       (metadata only)
outputs/python-tests/{JIRA_ID}/summary.yaml   (metadata only)
```

**Per-scenario package resolution:** Each test file is placed in the
source package that contains the code it tests. When the STD YAML
provides `target_test_directories` (plural), use it as the candidate
list. When only `target_test_directory` (singular) is provided, use it
as the default but still resolve per-scenario if scenarios reference
functions in other packages.

**Resolution order for each scenario's target package:**

1. The scenario's `code_under_test` or referenced function → find its
   package in `SOURCE_REPO_PATH`
2. The scenario's imports (`imports.project` entries) → derive the
   filesystem path from the import path
3. `target_test_directory` from `code_generation_config` (default)
4. If `SOURCE_REPO_PATH` is unavailable → **error**: report
   `"reason": "no-source-repo"` and do not generate tests. Never write
   tests to `outputs/` or `qf-tests/` — they won't compile.

The `qf_` filename prefix makes QF-generated tests discoverable via
`find . -name 'qf_*'`.

---

## CRITICAL REQUIREMENT

**Generate ONE test case per STD scenario with `coverage_status: NEW` or
`PARTIAL_COVERAGE`. Skip `EXISTING_COVERAGE` — emit a reference comment instead.**

- 19 STD scenarios (12 NEW + 1 PARTIAL + 6 EXISTING) → 13 test functions + 6 reference comments
- Pattern-based file grouping is allowed, but EVERY non-EXISTING scenario gets a test
- For `EXISTING_COVERAGE` scenarios, emit a comment referencing the existing test:

  ```go
  // Covered by existing test: TestComparePathPresence_AllPresent
  // in internal/scaffold/pathpresence_test.go
  ```

When `coverage_status` is absent on a scenario, treat it as `NEW` (backward compatible).

---

## Workflow

### Step 1: Discover Language Targets

**Tier mode** (`config_dir` is not null):

Scan `{project_context.config_dir}/` for YAML files with
`enabled: true` and a `language:` field:

```bash
for f in {project_context.config_dir}/*.yaml; do
  # Skip non-language files (project.yaml, repositories.yaml, etc.)
  # A language config has: enabled, language, framework fields
done
```

Known file names: `go.yaml`, `python.yaml`, `tier1.yaml`, `tier2.yaml`

Each language config provides:

- `language` — "go", "python", etc.
- `framework` — "testing", "ginkgo-v2", "pytest", etc.
- `imports` — organized by category (standard, framework, project)
- `build_command` — validation command
- `test_patterns` — naming conventions

**Auto mode** (`config_dir` is null):

Read `code_generation_config` directly from the STD YAML. The STD YAML IS the config
in auto mode — it contains the detected language, framework, imports, and package name
from the test-strategy-resolver.

```yaml
# From STD YAML code_generation_config:
language: "go"
framework: "testing"
assertion_library: "testify"
package_name: "cli"
imports:
  standard: ["context", "testing"]
  framework: ["github.com/stretchr/testify/assert"]
  project: ["github.com/org/repo/internal/cli"]
```

No config directory scanning needed — generate for the single detected language.

### Step 2: Read STD YAML

Load `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`

Extract:

- Total scenario count
- Scenarios grouped by tier/type
- Test objectives, steps, assertions

### Step 3: Load Pattern Rules

**Tier mode:** For each enabled language, read patterns from:

- `{project_context.config_dir}/patterns/{language}_patterns.yaml`
- Fresh LSP patterns if available

**Auto mode:** Skip pattern loading (no pattern library exists for auto-detected
projects). Instead, read existing test files in `SOURCE_REPO_PATH` to learn
conventions (indentation, assertion style, helper patterns) directly from the repo.

### Step 3.5: Scan Existing Tests in Target Packages

For each resolved target package directory (from `target_test_directories`
or `target_test_directory`), scan existing tests when `SOURCE_REPO_PATH`
is available:

```bash
ls $SOURCE_REPO_PATH/{target_test_directory}/*_test.go 2>/dev/null
```

Read these files to extract:

- The `package` declaration (use exactly this — do not guess)
- Existing test helper functions (reuse, don't recreate)
- Import patterns (match the existing style)
- Existing test function names (avoid duplicating)

Pass this context to the framework-specific generation below.

### Step 4: Generate Tests Per Language

For each enabled language config, generate test files using the
appropriate framework section below.

**File naming (all frameworks):** Use the `qf_` prefix from
`code_generation_config.filename_prefix`:

- Go: `qf_{feature}_test.go`
- Python: `qf_test_{feature}.py`

**File placement (all frameworks):**

- Resolve the target package for each test file using the per-scenario
  resolution order (see Output section above)
- Write to `$SOURCE_REPO_PATH/{resolved_package}/`
- If `SOURCE_REPO_PATH` is unavailable → error, do not generate

---

## Co-location Rules (MANDATORY for all Go frameworks)

When writing tests co-located with production code, these rules are
**critical** for compilation:

1. **Import production types — NEVER redeclare them.** The test is in the
   same package (or module), so all types are directly importable. Do NOT
   copy struct definitions, interfaces, or constants into the test file.

2. **Match the existing package declaration exactly.** Read the `package`
   line from existing files in `target_test_directory` — use that, not
   what the STD YAML says, if they differ.

3. **Reuse existing test helpers.** If the target directory already has
   `_test.go` files with setup functions, fixtures, or utilities, import
   and use them instead of reimplementing.

4. **Import from real packages.** Use the import paths from
   `code_generation_config.imports.project` to import production types.
   These are real Go import paths that resolve within the module.

5. **No type stubs or shims.** If you need a type from `internal/foo`,
   import `internal/foo` — you can, because the test file lives inside
   the module tree.

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
    // project imports from code_generation_config.imports.project
)

func TestQF_FeatureName(t *testing.T) {
    // shared setup — use production constructors/helpers

    t.Run("scenario description", func(t *testing.T) {
        // test implementation using REAL production types
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
- Package name from existing files in `target_test_directory` (preferred)
  or `default_package`
- **MUST import production types, not redeclare them** (see Co-location Rules)

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
            // test implementation using REAL production types
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
- **MUST import production types, not redeclare them** (see Co-location Rules)

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

## Test Case Markers Toggle

If `project_context.feature_toggles.test_case_markers` is false, omit
external test case management markers from generated test code.

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

1. Count STD scenarios per tier/type, excluding `EXISTING_COVERAGE`
2. Count generated test cases per language
3. Verify 1:1 mapping: every `NEW`/`PARTIAL_COVERAGE` scenario has a test
4. Verify every `EXISTING_COVERAGE` scenario has a reference comment
5. Report missing scenario IDs

---

## Step 5.5: Compile Gate

**Purpose:** Verify generated tests compile before committing. This catches
import errors, undefined types, and package mismatches immediately.

### Go compile gate

If Go test files were generated and `SOURCE_REPO_PATH` is available:

```bash
cd $SOURCE_REPO_PATH
go test -run='^$' -count=1 ./{target_test_directory}/...
```

The `-run='^$'` flag matches no test names, so tests compile but don't
execute. `-count=1` prevents caching.

**If compilation fails:**

1. Parse the error output to identify the failure category:
   - **Missing imports:** Add the import from `code_generation_config.imports`
   - **Undefined types:** The test redeclared a type instead of importing
     it — replace with the real import
   - **Package mismatch:** The `package` line doesn't match the directory —
     fix to match existing files
   - **Unused imports:** Remove the unused import
2. Fix the generated file(s)
3. Re-run the compile check
4. **Maximum 3 retry iterations**
5. If still failing after 3 retries: log errors, rename files with
   `.invalid` extension, report in summary

### Python syntax gate

For Python test files:

```bash
python3 -m py_compile {target_test_directory}/qf_test_{feature}.py
```

If `pytest` is available, also run:

```bash
pytest --collect-only {target_test_directory}/qf_test_{feature}.py
```

### Compile gate skip conditions

Skip the compile gate when:

- The project uses a non-standard build system (e.g., `build_command`
  in config is set to something other than `go test`)

---

## Step 6: Report Results

Generate summary per language:

- Language, framework
- Files generated, line counts
- Test count, scenario coverage
- LSP patterns used (true/false)
- **Target directory** (where files were placed)
- **Compile gate result** (passed/failed/skipped)
- **Compile gate retries** (number of fix iterations needed)
- Any errors or warnings

---

## Error Handling

**STD not found:** Error + suggest running `/std-builder` first.

**No language configs (tier mode):** Error + suggest creating language YAML in config.

**No code_generation_config (auto mode):** Error + STD YAML may not have been generated
with auto mode. Suggest re-running `/std-builder`.

**Pattern not recognized:** Warning + fall back to direct STD-to-test generation.

**Validation fails:** Save to `.invalid` extension, show errors, continue.

**Compile gate fails after retries:** Save files with `.invalid` extension,
report the compilation errors in summary.yaml, continue with any files
that did compile.

---

**End of Test Generator Skill**
