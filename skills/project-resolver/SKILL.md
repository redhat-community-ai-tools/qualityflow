---
name: project-resolver
description: Resolve Jira ID to project configuration and load project context
---

# Project Resolver Skill

**Phase:** Pre-Processing (Step 0)
**User-Invocable:** false

## Purpose

Central config loader for QualityFlow's multi-project architecture. Every command
invokes this skill as Step 0 to resolve the Jira ID to a project and load its
configuration.

## When to Use

Invoked as the **first step** of every command (`stp-builder`, `std-builder`,
`generate-tests`) before any other processing.

## Tools Required

- Read
- mcp__github__get_file_contents (for repo_files fetch)

## Input

```yaml
jira_input: "PROJ-66855"  # or "https://your-jira.example.com/browse/PROJ-66855"
```

## Workflow

### Step 1: Parse Jira ID

Extract the Jira ID from the input. Handle both formats:

- Direct ID: `PROJ-12345` → extract prefix `PROJ`, ID `PROJ-12345`
- URL: `https://your-jira.example.com/browse/PROJ-12345` → extract prefix `PROJ`, ID `PROJ-12345`

The prefix is the text before the first hyphen in the Jira key.

### Step 2: Read Routing Configuration

Read `config/routing.yaml` from the project root.

Extract the `routes` array and `default_project` value.

### Step 3: Resolve Project

Match the extracted prefix against `routes[].prefix`:

```
For each route in routes:
  if route.prefix == extracted_prefix:
    project_id = route.project
    break
```

If no match found:

- If `default_project` is not null: use `default_project`
- If `default_project` is null: go to **Step 3.5** (Auto-Discovery Fallback)

### Step 3.5: Auto-Discovery Fallback (Unconfigured Projects)

**Trigger:** Routing lookup failed AND no `default_project` configured.

Check if the `SOURCE_REPO_PATH` environment variable is set (points to a local checkout
of the PR's repository, set by the GitHub workflow).

**If `SOURCE_REPO_PATH` is NOT set:** **FAIL** with error:

```
Unknown Jira prefix "{prefix}". No project configured for this prefix.
Check config/routing.yaml for configured prefixes.
To add a new project, create config/projects/{name}/ and add a route in config/routing.yaml.
```

**If `SOURCE_REPO_PATH` IS set:** Scan the repo to synthesize a project context.

#### 3.5.1 Detect Language

Scan `SOURCE_REPO_PATH` for language markers (check in order, use first match):

| File Present | Language Detected |
|:-------------|:------------------|
| `go.mod` | go |
| `Cargo.toml` | rust |
| `pyproject.toml` or `requirements.txt` or `setup.py` | python |
| `package.json` | typescript/javascript |

If no marker found: default to the most common file extension in the repo.

#### 3.5.2 Detect Test Framework

Scan for existing test files near production code:

**Go:**

- Glob `*_test.go` files in `SOURCE_REPO_PATH`
- Read the first 3-5 test files found
- Grep imports for framework detection:
  - `"github.com/onsi/ginkgo"` → framework: `ginkgo-v2`
  - `"github.com/stretchr/testify"` → assertion_library: `testify`
  - `"testing"` (stdlib only) → framework: `testing`
- Read `package` declaration → package_convention: `same-package` or `external`

**Python:**

- Glob `test_*.py` or `*_test.py` files
- Grep imports: `pytest`, `unittest`
- framework: `pytest` or `unittest`

**Fallback:** If no test files found, use safe defaults:

- Go → `framework: "testing"`, `assertion_library: "testify"`, `package_convention: "same-package"`
- Python → `framework: "pytest"`

#### 3.5.3 Build Discovery Block

```yaml
discovery:
  language: "{detected language}"
  framework: "{detected framework}"
  assertion_library: "{detected assertion lib or null}"
  package_convention: "{same-package or external}"
  test_file_pattern: "{glob pattern for test files}"
  source_repo_path: "{SOURCE_REPO_PATH}"
```

#### 3.5.4 Return Synthesized Project Context

Skip Steps 4-9 entirely (no config directory to validate, no defaults to merge,
no repo files to fetch). Go directly to Step 10 with:

```yaml
project_context:
  project_id: "auto-detected"
  display_name: "{repo directory name}"
  jira_id: "{original input ID, e.g., GH-42}"
  config_dir: null
  discovery:
    language: "{detected}"
    framework: "{detected}"
    assertion_library: "{detected or null}"
    package_convention: "{detected}"
    test_file_pattern: "{detected}"
    source_repo_path: "{SOURCE_REPO_PATH}"
  feature_toggles:
    test_strategy: "auto"
    tier1_tests: false
    tier2_tests: false
    test_case_markers: false
    unit_tests: false
    stp_generation: true
    std_generation: true
    stp_review: true
    std_review: true
    lsp_analysis: true
    pii_sanitization: false
    repo_files_fetch: false
  stp_header: "Test Plan"
  versioning:
    product_name: "{repo directory name}"
    platform_name: "N/A"
    current_version: "N/A"
  repo_rules: {}
```

**Key:** `config_dir: null` signals to ALL downstream skills that they are in
auto-discovery mode. Skills MUST check for `config_dir: null` before attempting
to read tier1.yaml, tier2.yaml, or any other project config files.

### Step 4: Validate Project Directory

Check that `config/projects/{project_id}/` exists and contains the required files.

Read `config/_schema.yaml` to get the `required_files` list.

For each required file, verify it exists at `config/projects/{project_id}/{file}`.

If any required file is missing: **FAIL** with error:

```
Project "{project_id}" is missing required config file: {file}
Expected at: config/projects/{project_id}/{file}
```

### Step 5: Load Defaults

Read `config/_defaults.yaml` and extract the `feature_toggles` defaults.

### Step 6: Load Project Config

Read `config/projects/{project_id}/project.yaml` and extract:

- `project_id`
- `display_name`
- `feature_toggles` (project-specific overrides)
- `stp_document.header`
- `versioning`

### Step 7: Merge Feature Toggles

Deep-merge project toggles over defaults:

```
merged_toggles = defaults.feature_toggles
for key, value in project.feature_toggles:
  merged_toggles[key] = value
```

### Step 8: Validate Toggle Consistency

Read `config/_schema.yaml` `toggle_consistency` rules.

For each rule:

- If `merged_toggles[rule.toggle]` is true, verify `config/projects/{project_id}/{rule.requires_file}` exists
- If the required file is missing: **WARN** (not fail):

  ```
  Warning: {rule.toggle} is enabled but {rule.requires_file} not found.
  ```

### Step 9: Fetch Repo Files (repo_rules)

**Guard:** Skip this step if `merged_toggles.repo_files_fetch` is false.

Read `config/projects/{project_id}/repositories.yaml` and check for a `repo_files` section.

If `repo_files` exists, fetch each declared file from its source repository:

```
repo_rules = {}

For each entry in repo_files:
  # Resolve the repo reference
  repo_ref = entry.repo  # e.g., "tier2_repo" or "design_docs_repo"
  repo_config = repositories_yaml[repo_ref]  # get org + name from the repo section

  # Fetch via GitHub MCP
  Try:
    content = mcp__github__get_file_contents(
      owner=repo_config.org,
      repo=repo_config.name,
      path=entry.path,
      branch=repo_config.default_branch  # optional, defaults to main
    )
    repo_rules[entry_name] = content  # attach raw content
    Log: "Fetched {entry_name} from {repo_config.org}/{repo_config.name}/{entry.path}"

  On failure:
    If entry.fallback is not null:
      # Read local fallback from config_dir
      fallback_path = "{config_dir}/{entry.fallback}"
      content = Read(fallback_path)
      repo_rules[entry_name] = content
      Log: "Fallback: loaded {entry_name} from {fallback_path}"
    Else:
      repo_rules[entry_name] = null
      Log: "Warning: Could not fetch {entry_name}, no fallback configured"
```

**Parallel fetching:** All repo_files entries are independent — fetch them in parallel
(multiple `mcp__github__get_file_contents` calls in one message) for performance.

**Result:** `repo_rules` dictionary with raw file contents keyed by logical name.

### Step 10: Return Project Context

Return the resolved context:

```yaml
project_context:
  project_id: "{project_id}"
  display_name: "{display_name}"
  jira_id: "{JIRA_ID}"
  config_dir: "config/projects/{project_id}"
  feature_toggles:
    test_case_markers: true/false
    unit_tests: true/false
    tier1_tests: true/false
    tier2_tests: true/false
    stp_generation: true/false
    std_generation: true/false
    lsp_analysis: true/false
    pii_sanitization: true/false
    repo_files_fetch: true/false
  stp_header: "{stp_document.header}"
  versioning:
    product_name: "{product_name}"
    platform_name: "{platform_name}"
    current_version: "{current_version}"
  repo_rules:
    agents_rules: "{raw content of AGENTS.md or null}"
    std_format: "{raw content of SOFTWARE_TEST_DESCRIPTION.md or null}"
    stp_template: "{raw content of STP template or null}"
    stp_guide: "{raw content of STP guide or null}"
    testing_tiers: "{raw content of testing tiers guide or null}"
```

## Output Format

### Configured Project (routing match found)

```yaml
project_context:
  project_id: "{project_id}"
  display_name: "{display_name}"
  jira_id: "PROJ-12345"
  config_dir: "config/projects/{project_id}"
  feature_toggles:
    test_case_markers: true
    unit_tests: false
    test_strategy: "tier"
    tier1_tests: true
    tier2_tests: true
    stp_generation: true
    std_generation: true
    lsp_analysis: true
    pii_sanitization: true
    repo_files_fetch: true
  stp_header: "{from project.yaml stp_document.header}"
  versioning:
    product_name: "{from project.yaml versioning.product_name}"
    platform_name: "{from project.yaml versioning.platform_name}"
    current_version: "{from project.yaml versioning.current_version}"
  repo_rules:
    agents_rules: "{fetched from repo or null}"
    std_format: "{fetched from repo or null}"
    stp_template: "{fetched from repo or null}"
    stp_guide: "{fetched from repo or null}"
    testing_tiers: "{fetched from repo or null}"
```

### Auto-Detected Project (routing miss + SOURCE_REPO_PATH)

```yaml
project_context:
  project_id: "auto-detected"
  display_name: "fullsend"
  jira_id: "GH-42"
  config_dir: null
  discovery:
    language: "go"
    framework: "testing"
    assertion_library: "testify"
    package_convention: "same-package"
    test_file_pattern: "*_test.go"
    source_repo_path: "/home/runner/work/fullsend/fullsend"
  feature_toggles:
    test_strategy: "auto"
    tier1_tests: false
    tier2_tests: false
    test_case_markers: false
    unit_tests: false
    stp_generation: true
    std_generation: true
    stp_review: true
    std_review: true
    lsp_analysis: true
    pii_sanitization: false
    repo_files_fetch: false
  stp_header: "Test Plan"
  versioning:
    product_name: "fullsend"
    platform_name: "N/A"
    current_version: "N/A"
  repo_rules: {}
```

### repo_rules Usage by Skills

| Skill | Uses from repo_rules |
|:------|:--------------------|
| template-engine | `stp_template` — official STP template structure |
| stp-generator | `stp_template`, `stp_guide` — template + guide for generation |
| stp-reviewer | `stp_template`, `stp_guide`, `testing_tiers` — review against official docs |
| std-generator | `std_format`, `agents_rules` — STD format rules + coding standards |
| stub-generator | `std_format`, `agents_rules` — PSE format + stub conventions |
| test-generator | `agents_rules` — fixture, marker, and code pattern rules |
| std-reviewer | `std_format`, `agents_rules` — validate stubs against repo rules |

## Error Handling

**Unknown prefix (no SOURCE_REPO_PATH):**

- Error: "Unknown Jira prefix. No project configured and no source repo available for auto-detection."
- Action: List known prefixes and suggest adding a route
- Exit command

**Unknown prefix (with SOURCE_REPO_PATH):**

- Not an error — triggers auto-discovery fallback (Step 3.5)
- Returns synthesized project_context with `config_dir: null`

**Missing project directory:**

- Error: "Project config directory not found"
- Action: Suggest creating the directory structure
- Exit command

**Missing required config file:**

- Error: "Required config file missing"
- Action: List the missing file and expected location
- Exit command

**Malformed YAML:**

- Error: "Cannot parse config file"
- Action: Show the file path and suggest checking YAML syntax
- Exit command

## Usage by Commands

Each command uses project_context differently:

| Command | Uses from project_context |
|:--------|:--------------------------|
| stp-builder | Passes to stp-orchestrator for all subagents |
| std-builder | Checks tier1_tests/tier2_tests to decide which stubs to generate |
| generate-tests | Checks tier1_tests/tier2_tests; blocks if both false |

## Usage by Agents

Each agent reads additional config files on-demand from `config_dir`:

| Agent | Reads from config_dir |
|:------|:----------------------|
| jira-collector | `jira.yaml`, `components.yaml` |
| github-pr-fetcher | `repositories.yaml` (optional) |
| regression-analyzer | `repositories.yaml`, `components.yaml` |
| stp-generator | `project.yaml`, `environment.yaml`, `tier1.yaml`, `tier2.yaml` |
| document-formatter | `pii_exceptions.yaml` |
| ticket-context-analyzer | `repositories.yaml` |

## Feature Toggle Notes

The `unit_tests` toggle is informational only. It signals whether unit tests are in scope for a project configuration, but no QualityFlow command or skill gates on it. All other toggles (`test_case_markers`, `tier1_tests`, `tier2_tests`, `stp_generation`, `std_generation`, `lsp_analysis`, `pii_sanitization`) are actively gated by commands, agents, or skills.

The `test_strategy` toggle controls how test classification and code generation work:

- `"auto"` (default): detect framework, package, imports from the target repo's existing tests. Uses `test-strategy-resolver` skill instead of `tier-classifier`. Does not require tier1.yaml/tier2.yaml.
- `"tier"`: use the traditional tier classification system with tier1.yaml (Go/Ginkgo) and tier2.yaml (Python/pytest). Uses `tier-classifier` skill. Required for configured projects with tier-based classification.

When `config_dir` is `null` (auto-detected project), `test_strategy` is always `"auto"` and `tier1_tests`/`tier2_tests` are both `false`.
