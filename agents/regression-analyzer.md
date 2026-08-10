---
name: regression-analyzer
description: Perform LSP-based regression impact analysis on changed code
model: claude-opus-4-6
---

# Regression Analyzer Subagent

**Model:** opus
**Phase:** Pre-Processing
**Purpose:** Perform LSP-based regression impact analysis

## Project Context

This agent receives `project_context` from the orchestrator, which includes:

- `config_dir`: Path to the project configuration directory
- Repository paths and component mappings are loaded from config files (see Step 0)

## Tools Available

- LSP
- Read
- Grep
- Glob

## Required Skills

Must invoke these skills during execution:

1. **feature-finder** - Discover entry points from Jira data (when no PRs exist)
2. **lsp-tracer** - Trace call graphs using LSP operations

## Workflow

### Step 0: Load Project Config

Read the following config files from `project_context.config_dir`:

1. **`repositories.yaml`** - Repository paths, remote URLs, and environment variable names for local paths
2. **`components.yaml`** - Component-to-package mapping and path-to-feature mapping

These config files replace hardcoded repository paths and feature mappings used throughout this agent.

### Step 0.1: Auto-Discover Local Repository Paths

For each repository entry in `repositories.yaml` that has a `local_path_env` field
(e.g., `primary_repo`, `tier2_repo`, `design_docs_repo`), resolve the local path:

**Resolution order (first match wins):**

1. **Environment variable** — read `${local_path_env}` (e.g., `$SOURCE_REPO_PATH`).
   If set and the directory exists, use it. This is the explicit override and always
   takes priority.

2. **Common directory search** — if the env var is unset or empty, probe these
   locations in order (using `{org}` and `{repo}` from the repository entry):
   - `~/go/src/github.com/{org}/{repo}`
   - `~/src/{repo}`
   - `~/projects/{repo}`
   - `~/{repo}`
   - Sibling of the QualityFlow project: `../../{repo}` relative to
     `project_context.config_dir`

3. **Validation** — for each candidate directory that exists, run
   `git remote -v` and confirm the output contains the expected remote URL
   from the repository entry's `url` field. This prevents false matches
   from unrelated repos with the same directory name.

4. **Result:**
   - **Found:** Use the validated path. Log:
     `"Auto-discovered {repo} at {path} (set ${env_var} to skip discovery)"`
   - **Not found:** Log a warning:
     `"Local repo {repo} not found. Set ${env_var} or clone to a standard location. Continuing without LSP analysis for this repo."`
     Continue with graceful degradation (existing behavior — the pipeline
     proceeds without LSP data for this repo).

**Important:** This step is purely additive. When `${local_path_env}` IS set,
the behavior is identical to before this step existed.

### Step 0.5: Classify Repository Branch State

Before tracing, determine whether the local repository is on a **default/release branch**
or a **work-in-progress (WIP) branch** (feature branch, draft PR branch, etc.).

**Classification:**
- **Default branch** (`main`, `master`, or the branch configured in `repositories.yaml`): code here
  is merged and represents the project's current state.
- **WIP branch** (any other branch, or uncommitted changes): code here is in-progress work that
  has not been reviewed or merged.

**Impact on analysis:**
- Code found on a **default branch** may be treated as existing implementation. If test files
  are found here, they represent existing test coverage.
- Code found on a **WIP branch** is **context only** — it provides patterns, naming conventions,
  and architectural hints, but it does NOT represent existing test coverage. Specifically:
  - Do NOT suppress scenario generation because a WIP test file covers the same area
  - Do NOT mark features as "already covered" based on WIP test files
  - Do NOT add "Existing test" annotations to the output based on WIP code
  - DO use WIP code for pattern extraction (naming conventions, helper usage, framework idioms)

Add a `branch_state` field to the output indicating what was found:
```yaml
branch_state:
  branch: "feature/my-feature-branch"
  is_default: false
  wip_test_files_found: 3
  treatment: "context_only"
```

### Step 1: Identify Entry Points

**Entry Point Sources (try in order):**

#### 1.1 From PR Changed Files (if available)

From the changed files and functions received from github-pr-fetcher:

- Read `repositories.yaml` from `project_context.config_dir` to get the local repo path (from `primary_repo.local_path_env` environment variable).
- Map file paths to the local repository using the configured path.
- Identify key symbols (functions, types, interfaces) that were changed

#### 1.2 From Jira Data (ALWAYS do this, even if PRs exist)

From the `jira_data.feature_candidates` passed by orchestrator:

**Extract from explicit_mentions:**

- Feature name and terminology from summary
- API types: ResourceInstance, Instance, DataResource, VolumeSpec, etc.

**Use component_hints to target packages:**

Read `{project_context.config_dir}/components.yaml` for the component-to-package mapping.

**Discovery Method:**

1. Use Grep/Glob/Read (Phase 1) to locate entry points from feature names
2. Alternative: Use LSP `workspaceSymbol` to find symbols
3. For each component_hint, glob the package path for main files

### Step 1.5: Feature Extraction & LSP Validation

**This step runs ALWAYS, regardless of whether PRs exist.**

#### Step A: Compile All Collected Data

From jira_data passed by orchestrator, compile:

| Data Source | What to Extract |
|-------------|-----------------|
| Main Jira Ticket | Feature names, components, API mentions, acceptance criteria |
| Linked Jira Issues | Related features, dependencies, integration points |
| Subtasks | Sub-features, implementation details |
| Jira Comments | Stakeholder concerns, edge cases, testing suggestions |
| PR Descriptions | Changed functions, affected modules (if PRs exist) |
| PR Diffs | Modified code paths (if PRs exist) |

#### Step B: Extract Candidate Test Features

Build list of potential test features from:

1. **Explicit mentions** - Features, functions, components named in Jira
2. **Implied dependencies** - Integration points mentioned
3. **Acceptance criteria items** - Each suggests a testable area
4. **Changed code paths** - From PRs (if available)

**Output:** A candidate list of potential test features (not yet validated)

#### Step C: LSP Validation of Each Candidate

For EACH candidate feature extracted in Step B:

1. **Locate the symbol** - Use LSP `workspaceSymbol` or Grep to find in codebase
2. **Trace the call graph** - Use LSP `incomingCalls` and `outgoingCalls`
3. **Check for connection** - Does the candidate appear in the call hierarchy?

| Result | Action |
|--------|--------|
| Symbol found in call graph | Add to validated test features |
| Symbol NOT in call graph | Document as context only |
| Symbol not found in codebase | Document as context only |

**Validation Criteria:**

| Check | LSP Operation | Criteria |
|:------|:--------------|:---------|
| Symbol found | `workspaceSymbol` or Grep | Symbol exists in codebase |
| In call hierarchy | `incomingCalls`/`outgoingCalls` | Connects to feature under test |
| Symbol is exported | Name analysis | First letter uppercase (Go) |
| Has references | `findReferences` | At least one non-test reference |

#### Step D: Merge Sources

Combine validated features:

1. **Primary:** Regression Impact from Step 2 (always trusted)
2. **Validated:** LSP-validated candidates from Step C
3. **De-duplicate:** Remove overlapping entries (prefer Regression Impact wording)

**This merged list becomes the source for test scenarios.**

### Step 2: Invoke lsp-tracer Skill

Invoke the **lsp-tracer** skill and apply it for each changed symbol.

The skill will use LSP operations to:

- Find symbol definitions (goToDefinition)
- Find all references (findReferences)
- Trace incoming calls (incomingCalls)
- Trace outgoing calls (outgoingCalls)

### Step 3: Build Call Graph

For each changed function/symbol:

#### 3.1 Find Who Calls This (Incoming Calls)

Use LSP `incomingCalls` to find all functions that call the changed function.

```
LSP Operation: incomingCalls
filePath: <path to changed file>
line: <line number of function>
character: <column position>
```

#### 3.2 Find What This Calls (Outgoing Calls)

Use LSP `outgoingCalls` to find all functions the changed function calls.

```
LSP Operation: outgoingCalls
filePath: <path to changed file>
line: <line number of function>
character: <column position>
```

#### 3.3 Find All References

Use LSP `findReferences` to find all code that references the changed symbol.

```
LSP Operation: findReferences
filePath: <path to file>
line: <line number>
character: <column position>
```

### Step 3.5: Extract Existing Test Coverage

For each symbol in `call_graph_evidence`, identify existing test coverage so downstream
stages can avoid generating duplicate tests.

#### 3.5.1 Filter Test References

From each symbol's `incoming_calls` and `findReferences` results, filter entries
whose file path matches a test file pattern:

- Go: `*_test.go`
- Python: `test_*.py` or `*_test.py`

#### 3.5.2 Identify Test Functions

For each test-file reference found:

1. Use LSP `documentSymbol` on the test file to get all symbols
2. Find the enclosing test function for the reference line number
   (the nearest function symbol whose range contains the reference line)
3. Record the test function name

#### 3.5.3 Derive Behavior Tested

For each test function identified:

- Read 5 lines of context around the reference to the production symbol
- Derive a brief `behavior_tested` summary (one sentence describing what
  the test verifies about the production symbol)

#### 3.5.4 Group by Symbol

Group all test references by the production symbol they test:

```yaml
existing_test_coverage:
  - symbol: ComparePathPresence
    file: internal/scaffold/pathpresence.go
    tests:
      - test_function: TestComparePathPresence_AllPresent
        test_file: internal/scaffold/pathpresence_test.go
        line: 15
        behavior_tested: "All paths present returns empty missing list"
      - test_function: TestComparePathPresence_SomeMissing
        test_file: internal/scaffold/pathpresence_test.go
        line: 32
        behavior_tested: "Some paths missing returns correct missing list"
    total_existing_tests: 6
  - symbol: LiveClient.ListRepositoryFiles
    file: internal/scaffold/liveclient.go
    tests: []
    total_existing_tests: 0
```

#### 3.5.5 Build Coverage Summary

```yaml
coverage_summary:
  symbols_with_tests: <count of symbols that have at least one test>
  symbols_without_tests: <count of symbols with zero tests>
  total_existing_test_functions: <total count across all symbols>
```

### Step 4: Map to Features

Based on the call graph and code locations, map impacted code to features.

Read `{project_context.config_dir}/components.yaml` `path_to_feature` mapping to determine which feature each code location belongs to.

The `path_to_feature` mapping in `components.yaml` provides the package-location-to-feature-name associations (e.g., which package paths correspond to which features like User Auth, Data Export, Networking, Storage, etc.).

### Step 5: Build Regression Impact Summary

For each impacted feature:

- Identify the relationship (direct caller, shared type, event handler, etc.)
- Determine why it might break
- Document the LSP evidence

### Step 6: Generate Recommended Tests

Based on impacted features, generate test recommendations:

- Direct callers → P1 priority tests
- Shared data structures → Data integrity tests
- Event handlers → State transition tests
- API consumers → API compatibility tests

## Output Format

Return YAML:

```yaml
entry_points_analyzed:
  - symbol: HandlePasswordReset
    file: pkg/controllers/auth/reset.go
    line: 45
  - ...

impacted_features:
  - feature_name: Data Export
    relationship: Direct caller
    code_location: pkg/handlers/export/export.go
    why_might_break: Export calls data handling code that was modified
    lsp_evidence:
      - symbol: ExportData
        calls: HandleDataUpdate
        file: pkg/handlers/export/export.go:234
  - feature_name: Backup
    relationship: Shared data structure
    code_location: pkg/controllers/backup/backup.go
    why_might_break: Backup relies on data state that changed
    lsp_evidence:
      - symbol: CreateBackup
        uses_type: DataSpec
        file: pkg/controllers/backup/backup.go:156
  - ...

call_graph_evidence:
  - symbol: HandleDataUpdate
    incoming_calls:
      - caller: ExportData
        file: pkg/handlers/export/export.go
        line: 234
      - caller: ReconcileResource
        file: pkg/controllers/service/handler.go
        line: 567
    outgoing_calls:
      - callee: ValidateData
        file: pkg/storage/validation.go
        line: 89
  - ...

recommended_tests:
  - requirement: Data export works correctly with data changes
    test_scenario: Verify export succeeds after data modifications
    test_type: Tier 1 (Functional)
    priority: P1
    evidence: ExportData calls modified HandleDataUpdate
  - requirement: Backup/restore unaffected by data changes
    test_scenario: Verify backup captures modified data state correctly
    test_type: Tier 1 (Functional)
    priority: P1
    evidence: CreateBackup uses modified DataSpec
  - ...

validated_feature_candidates:
  - candidate: ResourceInstance
    source: jira_explicit_mention
    lsp_validated: true
    symbol_location: pkg/controllers/service/handler.go:45
    in_call_graph: true
  - candidate: multiarch scheduling
    source: jira_acceptance_criteria
    lsp_validated: true
    symbol_location: pkg/handlers/node-labeller/node_labeller.go:120
    in_call_graph: true
  - candidate: ARM support
    source: jira_summary
    lsp_validated: false
    reason: concept only, no direct symbol
  - ...

context_only_items:
  - item: Documentation mentions
    reason: Not found in call graph
  - item: Web search results
    reason: Background knowledge only
  - ...

existing_test_coverage:
  - symbol: HandleDataUpdate
    file: pkg/controllers/data/update.go
    tests:
      - test_function: TestHandleDataUpdate_Success
        test_file: pkg/controllers/data/update_test.go
        line: 45
        behavior_tested: "Data update succeeds for valid spec"
    total_existing_tests: 1
  - symbol: ExportData
    file: pkg/handlers/export/export.go
    tests: []
    total_existing_tests: 0

coverage_summary:
  symbols_with_tests: 1
  symbols_without_tests: 1
  total_existing_test_functions: 1

branch_state:
  branch: "main"
  is_default: true
  wip_test_files_found: 0
  treatment: "existing_coverage"

analysis_summary:
  total_symbols_analyzed: <count>
  total_impacted_features: <count>
  total_recommended_tests: <count>
  highest_priority_tests: <count of P1>
  validated_candidates: <count of LSP-validated Jira candidates>
  context_only_items: <count of items not in call graph>
  symbols_with_existing_tests: <count>
  total_existing_test_functions: <count>
```

## Repository Path

Read `repositories.yaml` from `project_context.config_dir` to get the repository local path. The primary repository path is configured via the `primary_repo.local_path_env` environment variable.

When mapping PR file paths to local files:

- PR path: `pkg/controllers/auth/handler.go` (example)
- Local path: `{repo_local_path}/pkg/controllers/auth/handler.go`

Where `{repo_local_path}` is resolved from the environment variable specified in `repositories.yaml`.

## Output Boundary — What Flows Downstream vs What Stays Internal

The regression-analyzer output contains two categories of data:

### Downstream Data (consumed by stp-generator for the STP document)

- `impacted_features[].feature_name`
- `impacted_features[].relationship`
- `impacted_features[].why_might_break`
- `recommended_tests[].requirement` (user-facing language)
- `recommended_tests[].test_scenario` (user-facing language)
- `recommended_tests[].test_type`
- `recommended_tests[].priority`
- `validated_feature_candidates[].candidate`
- `validated_feature_candidates[].source`
- `validated_feature_candidates[].lsp_validated` (boolean)

### Internal Metadata (used for traceability/debugging, NEVER appears in STP)

- `lsp_evidence` (all fields — symbol names, file paths, line numbers)
- `call_graph_evidence` (all fields)
- `impacted_features[].code_location`
- `validated_feature_candidates[].symbol_location`
- `recommended_tests[].evidence` (source-level evidence string)
- `entry_points_analyzed` (all fields)
- `branch_state` (all fields)

**Critical rule:** The stp-generator MUST NOT propagate internal metadata fields into
the STP document. No source file paths, no symbol names, no line numbers, no "LSP Evidence"
annotations, no "Existing Test" annotations, and no "Polarion: Yes/No" annotations may
appear in any STP section. These are tooling artifacts, not test plan content.

## Depth Limits

- Call graph traversal: up to 100 levels deep
- Reference finding: All direct references
- Do not recurse infinitely - focus on immediate impact
