---
name: test-strategy-resolver
description: Detect test conventions from a codebase to drive test generation without tier config
model: claude-opus-4-6
---

# Test Strategy Resolver Skill

**Phase:** Core Processing
**User-Invocable:** false

## Purpose

Replaces **tier-classifier** for projects using `test_strategy: "auto"`. Instead of
classifying scenarios into Tier 1/Tier 2 with hardcoded framework mappings, this skill
analyzes the target codebase to detect existing test conventions and outputs a strategy
that drives code generation.

**Design principle:** detection-driven routing, not classification-driven routing.
Instead of "Tier 1 → Ginkgo", it's "existing tests use testify → generate testify."

## When to Use

Invoked by the **stp-generator** subagent at Step 4 when
`project_context.feature_toggles.test_strategy == "auto"`.

NOT invoked when `test_strategy == "tier"` — tier-classifier handles that case.

## Tools Required

- Read
- Glob
- Grep

## Input

```yaml
project_context:
  config_dir: null             # or a config_dir with test_strategy: "auto"
  discovery:                   # from project-resolver auto-detection
    language: "go"
    framework: "testing"
    source_repo_path: "/path/to/repo"
changed_files:                 # from PR diff (optional, may be empty)
  - path: "internal/cli/run.go"
    additions: 50
    deletions: 10
  - path: "internal/cli/reconcilestatus.go"
    additions: 30
    deletions: 5
```

## Workflow

### Step 1: Locate Test Files Near Changed Code

If `changed_files` is available, find test files adjacent to changed production files:

```text
For each changed file (e.g., internal/cli/run.go):
  Look for:
    - internal/cli/run_test.go          (Go: same directory, _test.go suffix)
    - internal/cli/*_test.go            (Go: any test file in same package)
    - test_run.py / run_test.py         (Python: same directory)
    - tests/test_run.py                 (Python: tests/ subdirectory)
```

If no `changed_files` or no test files found near changes:

- Fall back to `project_context.discovery` from project-resolver
- Glob for test files across the repo (limit to first 10 found)

### Step 2: Analyze Test Conventions

Read the first 3-5 test files found. Extract:

#### 2.1 Framework Detection (Go)

| Import Found | Framework | Assertion Library |
|:-------------|:----------|:------------------|
| `"github.com/onsi/ginkgo/v2"` | `ginkgo-v2` | — |
| `"github.com/onsi/gomega"` | — | `gomega` |
| `"github.com/stretchr/testify/assert"` | — | `testify` |
| `"github.com/stretchr/testify/require"` | — | `testify` |
| `"github.com/stretchr/testify/suite"` | — | `testify-suite` |
| `"testing"` only (no framework imports) | `testing` | `stdlib` |

#### 2.2 Framework Detection (Python)

| Import Found | Framework |
|:-------------|:----------|
| `import pytest` or `from pytest` | `pytest` |
| `import unittest` | `unittest` |
| `from django.test` | `django-test` |

#### 2.3 Package Convention (Go only)

Read the `package` declaration from each test file:

| Test file `package` | Production file `package` | Convention |
|:---------------------|:--------------------------|:-----------|
| `package cli` | `package cli` | `same-package` (can access unexported symbols) |
| `package cli_test` | `package cli` | `external` (black-box testing) |

#### 2.4 Build Tags

Grep for `//go:build` lines in test files. Common patterns:

| Tag Found | Meaning |
|:----------|:--------|
| `//go:build e2e` | E2E test suite |
| `//go:build integration` | Integration test suite |
| `//go:build !unit` | Non-unit test |
| (none) | Standard tests, no special tags |

#### 2.5 Import Extraction

From each test file, extract imports grouped by category:

- **standard**: stdlib imports (`"context"`, `"testing"`, `"os"`, `"fmt"`)
- **framework**: test framework imports (`"github.com/stretchr/testify/assert"`)
- **project**: imports from the project itself (`"github.com/org/repo/internal/cli"`)

### Step 3: Determine Test Type Labels

Instead of "Tier 1 (Functional)" / "Tier 2 (End-to-End)", use descriptive labels:

| Criteria | Label |
|:---------|:------|
| Tests isolated functions with mocks, no external deps | `unit` |
| Tests single feature with real dependencies | `integration` |
| Tests API contracts, single resource lifecycle | `functional` |
| Tests complete user workflows, multi-step | `e2e` |

Apply the same decision logic as tier-classifier's Decision Matrix, but output
descriptive labels instead of tier numbers.

If the scenario carries a `coverage_signal` (from pr-analyzer's
`coverage_gaps`), also apply tier-classifier's **Coverage Signal** table,
mapping its promotion to `e2e` instead of `Tier 2`. Same rule: promote only,
never demote, and treat `executed_in_env: null` as unknown rather than false.

### Step 4: Build Test Strategy Output

Merge detected conventions into a single strategy block.

**Conflict resolution:** If multiple test files use different frameworks (e.g., some
use testify, some use gomega), prefer the framework used by test files nearest to the
changed production code. If still ambiguous, prefer the more common one.

## Output Format

```yaml
test_strategy:
  mode: "auto"
  language: "go"
  framework: "testing"
  assertion_library: "testify"
  package_name: "cli"
  package_convention: "same-package"
  build_tags: []
  imports:
    standard: ["context", "testing", "fmt"]
    framework: ["github.com/stretchr/testify/assert", "github.com/stretchr/testify/require"]
    project: ["github.com/fullsend-ai/fullsend/internal/cli"]
  test_type_labels:
    isolated: "unit"
    single_feature: "functional"
    multi_feature: "e2e"
  detected_from:
    files_analyzed:
      - "internal/cli/run_test.go"
      - "internal/cli/reconcilestatus_test.go"
    pattern: "same-package stdlib+testify"
    confidence: "high"
```

### Confidence Levels

| Confidence | Meaning |
|:-----------|:--------|
| `high` | 3+ test files analyzed, consistent conventions |
| `medium` | 1-2 test files analyzed, or mixed conventions resolved |
| `low` | No test files found, using fallback defaults |

## Fallback Defaults

When no existing test files are found:

| Language | Framework | Assertion | Package Convention |
|:---------|:----------|:----------|:-------------------|
| Go | `testing` | `testify` | `same-package` |
| Python | `pytest` | — | — |
| TypeScript | `jest` | — | — |
| Rust | `cargo-test` | — | — |

## Usage by Downstream Skills

| Skill | Uses from test_strategy |
|:------|:------------------------|
| stp-generator | `test_type_labels` for Section III classification |
| std-generator | `framework`, `package_name`, `imports` for `code_generation_config` |
| stub-generator | `framework`, `package_name`, `imports` for stub format |
| test-generator | `framework`, `assertion_library`, `imports` for working test code |

## Difference from tier-classifier

| Aspect | tier-classifier | test-strategy-resolver |
|:-------|:----------------|:-----------------------|
| Input | Scenario description | Scenario + codebase analysis |
| Output | "Tier 1 (Functional)" / "Tier 2 (End-to-End)" | "unit" / "functional" / "e2e" + framework config |
| Framework | Assumes Ginkgo (Tier 1) / pytest (Tier 2) | Detects from existing tests |
| Package | Assumes external `_test` package | Detects same-package vs external |
| When used | `test_strategy: "tier"` | `test_strategy: "auto"` |
