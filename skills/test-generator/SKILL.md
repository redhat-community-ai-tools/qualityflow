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

- `checkout`: path of the tests repo checkout (from `/generate-tests` Step 2.2)
- `vocabulary`: `repo_context.py context` output per target directory
  (`/generate-tests` Step 3.5)

**Prerequisites:**
- STD YAML at `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`
- At least one language config file in `{project_context.config_dir}/`, or an
  STD `code_generation_config` (auto mode)
- A checkout of the tests repo. No checkout: stop and say which env var to set;
  never generate against a guessed suite.

---

## Output

```
outputs/{JIRA_ID}/go-tests/           (if Go enabled)
├── qf_{feature}_test.go
└── summary.yaml

outputs/{JIRA_ID}/python-tests/       (if Python enabled)
├── test_qf_{feature}.py
└── summary.yaml

outputs/tests/{JIRA_ID}/{language}/   (any other language)
└── ...
```

Each test file is also written into the checkout at its `target_path`: the
repo-relative path where it belongs (`{target_dir}/{file}`), so it is
verified with the suite's real conftest chain and a push can place it there.
`summary.yaml` records it:

```yaml
jira_id: PROJ-123
language: python
framework: pytest
test_count: 4
qf_test_id_marker: false        # the repo does not register qf_test_id
files:
  - name: test_qf_login.py
    target_path: tests/api/test_qf_login.py
    scenarios: [1, 2, 3, 4]     # STD scenario numbers, in test order
new_fixtures:                   # only fixtures the generator had to add
  - {name: locked_user, file: tests/api/test_qf_login.py, why: "no existing fixture creates a locked user"}
verification: passed            # passed | failed | skipped (repo_context.py verify)
verification_reason: "collected; no test was run"
```

A `conftest.py` appears only when the generator added one under the rules
below; it gets a `target_path` too.

Test file names start with the STD's `code_generation_config.filename_prefix`:
`qf_` for Go, `test_qf_` for Python. Never name a Python test `qf_{feature}.py`
or `qf_test_{feature}.py`. pytest's default `python_files` is
`test_*.py *_test.py`, so such a file is collected only when named on the
command line, and the target repo's CI never runs it.

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
- `document_metadata.stp_reference.url` (fall back to `.file`) — `{STP_URL}`,
  emitted in the file header and in every test's docstring/comment. When the STD
  has no `stp_reference` (bug fixes and other non-STP inputs), emit
  `Jira: {JIRA_URL}` instead — every test carries exactly one of the two, never an
  `STP:` line with an empty value. `{JIRA_URL}` is `document_metadata.jira_url`,
  and a test whose scenario has its own `jira_url` links that one instead. A
  case migrated from Polarion links its own requirement.
- Each scenario's `polarion_id`, if any. See the Python rules below.

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

### Step 2.7: Use Only the Suite's Vocabulary

The `vocabulary` input is the suite as it is. Generated code may use:

- **Fixtures:** those listed in `fixtures` (by their listed name), pytest's
  built-ins (`request`, `tmp_path`, `monkeypatch`...), those of pytest plugins
  the repo already depends on, or one the STD explicitly defines as new.
- **Imports:** standard library, the test framework, packages the repo already
  depends on, and the `helpers` modules (and names) sibling tests import. Any
  other project import must resolve to a file in the checkout; open it and use
  what it really defines.
- **Markers:** those in `markers.registered`. Under `strict: true` any other
  marker fails collection.
- **Style:** follow the `siblings` (read them): class vs function tests,
  fixture use, assertion and wait helpers, docstring layout.

Never:

- write a `conftest.py` that redefines a fixture the vocabulary lists, or edit
  an existing `conftest.py`;
- fake, stub or re-implement a suite utility, client or fixture ("harness"
  fakes, local stand-ins): a test that passes against its own fakes proves
  nothing about the team's environment.

A fixture the vocabulary lacks and the scenario needs goes **in the test
module**. Only when the target directory has no `conftest.py`
(`existing_conftest: null`) and more than one generated file needs it, put it
in a new `conftest.py` there. Either way list it under `new_fixtures` in
`summary.yaml` with the reason, and in the report.

### Step 3: Load Pattern Rules

**If config_dir is null:** Skip config-based pattern loading. Use only LSP patterns
(if available) and the `code_generation_config` from the STD YAML.

**If config_dir is available:** For each scenario, read the pattern library for
the scenario's tier from:
- `{project_context.config_dir}/patterns/tier{N}_patterns.yaml`
  (e.g., `tier1_patterns.yaml` for Tier 1 scenarios, `tier2_patterns.yaml` for Tier 2)
- Fresh LSP patterns if available

**Precedence:** fresh LSP-derived patterns take priority over the config
pattern library when both cover the same symbol.

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

    // STP: {STP_URL}
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
- `// STP: {STP_URL}` comment above every `t.Run(`

**Validation:**
- Count `t.Run(` calls = count of STD scenarios
- All imports resolve (no unused imports)
- Build tag line present if `build_tags` configured
- Every `t.Run(` preceded by an `STP:` comment

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
        // STP: {STP_URL}
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
- `// STP: {STP_URL}` comment above every `It()`
- `BeforeEach` for shared setup
- `Expect().To()` / `Expect().NotTo()` for assertions

**Validation:**
- Count `It(` blocks = count of STD Functional scenarios
- All `[test_id:TS-XXX]` present
- Every `It(` preceded by an `STP:` comment

---

## Framework: Python `pytest`

When `framework: "pytest"` in the language config:

**File structure:**
```python
"""Tests for {feature} — {JIRA_ID}.

STP: {STP_URL}
"""
import pytest
# imports from config

class TestFeature:
    """Tests for feature X.

    Markers:
        - {markers}

    Preconditions:
        - {preconditions}
    """

    @pytest.mark.qf_test_id("TS-XXX")   # only when the repo registers it
    def test_scenario_name(self, fixture1, fixture2):
        """Scenario: {description} [TS-XXX].

        STP: {STP_URL}
        """
        # test implementation
        assert result == expected
```

**Rules:**
- `def test_*()` naming convention
- Scenario ID in docstring for traceability (unchanged)
- `STP: {STP_URL}` (`Jira: {JIRA_URL}` when the STD has no STP) in the module
  docstring AND in every test docstring — a file-level reference does not
  survive a test being moved to another module
- **`@pytest.mark.qf_test_id("{test_id}")` on every generated test function
  when the repo registers `qf_test_id`** (it is in `markers.registered`), in
  addition to the docstring tag. It shows up in `pytest --collect-only` and
  JUnit XML. It is a **QualityFlow marker, not a Polarion one**, independent of
  the Polarion Toggle below. When the repo does not register it, omit it (an
  unregistered mark fails collection under `--strict-markers`), never register
  it from a generated `conftest.py`, and set `qf_test_id_marker: false` in
  `summary.yaml`: the `[TS-…]` docstring tag plus each file's `scenarios` list
  keep the traceability (scripts/qf_record_ci.py reads both).
- A scenario with a `polarion_id` (a case migrated from Polarion) gets
  `@pytest.mark.polarion("{polarion_id}")` with its real id, whatever the
  Polarion Toggle says, stacked above `qf_test_id`. Its stub listed the id under
  `Markers:`; now the test is implemented, the real decorator is right (a
  repo's sync job may then mark the case Automated).
- Every marker the stub lists under `Markers:`, and the scenario's STD `marker`
  (e.g. `tier3` from `scenario_tiers`), becomes a real `@pytest.mark.{name}`
  decorator on the test, stacked above `qf_test_id`. The target suite registers
  its own markers (under `--strict-markers` any other one fails collection);
  never invent one it does not register.
- Fixtures and helpers only from the vocabulary (Step 2.7); a new fixture is
  named as a noun, not a verb
- Context managers for resources
- No `time.sleep()` — use the suite's polling utilities

**Validation:**
- Count `def test_*` functions = count of STD End-to-End scenarios
- All scenario IDs in docstrings
- Every test docstring contains an `STP:` line, or a `Jira:` line when the STD has
  no STP. That line is the scenario's own `jira_url` when it has one.
- Every scenario with a `polarion_id` has `@pytest.mark.polarion("{polarion_id}")`
- When the repo registers `qf_test_id`, every `def test_*` has a matching
  `@pytest.mark.qf_test_id(...)` decorator
- Every scenario with an STD `marker` has that `@pytest.mark.{marker}` decorator
- Every fixture argument and project import is in the vocabulary or listed
  under `new_fixtures`; no generated `conftest.py` redefines a listed fixture

---

## Polarion Toggle

If `project_context.feature_toggles.polarion` is false, omit Polarion
test case ID markers from generated test code. This does NOT affect
`@pytest.mark.qf_test_id(...)` — that marker is QualityFlow's own scenario
id, independent of Polarion, and is always generated for Python tests. Nor
does it affect a scenario's real `polarion_id` marker, which is always generated.

## Repo Rules Integration

When `project_context.repo_rules` is available (e.g., AGENTS.md rules),
apply those coding standards to all generated test code, on top of the
vocabulary (the rules say how to write; the vocabulary says what exists).
Common rules:
- Implicit markers (don't add explicitly)
- Forbidden patterns (skip/skipif, etc.)
- Fixture guidelines
- Import conventions

---

## Step 4.5: Verify in the Checkout

`/generate-tests` Step 4.5 runs
`python3 skills/test-generator/repo_context.py verify <checkout> <target_path>... --repos-yaml <repositories.yaml>`
on the files written to the checkout: `uv run pytest --setup-plan -q` (with
`uv.lock`) or `python -m pytest --setup-plan -q` for Python — collection plus
every fixture resolved, with the repo entry's `verify: {env, args}` applied — `go vet` plus
`go test -run xxx -count=0` per package for Go. Record its `verification` and
`reason` in `summary.yaml`. Collection/compilation is the limit of this offline
check; never report a test as passing.

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
- Files generated with their `target_path`, line counts
- New fixtures added, and why
- Verification result and reason ("collected/compiled, not run")
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
