---
name: lsp-tracer
description: Trace call graphs using the Claude Code LSP tool to identify regression impact
model: claude-opus-4-6
---

# LSP Tracer Skill

**Phase:** Pre-Processing
**User-Invocable:** false

## Purpose

Trace call graphs using the **LSP tool** to identify regression impact.
This skill uses the native LSP tool provided by language server plugins (e.g., gopls for Go).

The LSP tool provides structured, semantic code intelligence — far superior to
grep-based text search for understanding type hierarchies, call chains, and
interface implementations.

**Language support:** LSP analysis currently supports Go projects via gopls. Python projects can use pyright for similar analysis. The skill can be extended to support additional languages by adding language-specific LSP configurations to `{project_context.config_dir}/`.

## When to Use

Invoked by the **regression-analyzer** subagent (or directly by stp-builder)
to trace code dependencies from changed files.

## Tools Required

- **LSP** (primary — for semantic code analysis via gopls)
- Grep (for fallback text-based discovery when LSP is unavailable)
- Read (for reading source files)
- Bash (for gopls CLI fallback only)

## Prerequisites

Before tracing, verify the LSP tool is available and the repo has a go.mod.

### Step 0: LSP Readiness Check

Call the LSP tool to verify it is operational:

- **operation:** `documentSymbol`
- **filePath:** `$SOURCE_REPO_DIR/go.mod`
- **line:** 1
- **character:** 1

If the LSP tool returns "server is starting", wait 3 seconds and retry.
gopls cold-start takes a moment on large repos.

Also verify the source repo:

```bash
ls $SOURCE_REPO_DIR/go.mod 2>/dev/null && echo "Go module found" || echo "No go.mod"
```

If the LSP tool is not available (tool not registered), fall back to gopls CLI:
```bash
export PATH="/usr/local/go/bin:$PATH" && which gopls && gopls version && echo "gopls CLI READY" || echo "gopls NOT AVAILABLE"
```

If neither LSP tool nor gopls CLI is available, fall back to Grep/Read analysis.

## Input

```yaml
# Repo path: $SOURCE_REPO_DIR or read from repositories.yaml
symbols_to_trace:
  - name: HandleFeatureOperation
    file: internal/controller/resource.go        # paths are project-specific; resolved from components.yaml
    line: 105
    character: 6
  - name: FeatureOperationSpec
    file: api/v1/types.go
    line: 250
    character: 6

# Optional: If symbols_to_trace is empty but feature_candidates is provided
feature_candidates:
  explicit_mentions:
    - Resource
    - feature-name
  component_hints:
    # package_path values come from components.yaml — actual paths vary by project
    - component: controller
      package_path: internal/controller/
    - component: handler
      package_path: internal/handler/
  acceptance_criteria:
    - Resource can perform operation
```

## Alternative Entry Point Discovery (when no PR data)

If `symbols_to_trace` is empty but `feature_candidates` is provided:

### 1. Discovery from explicit_mentions

For each candidate in `explicit_mentions`, use Grep to find files:

```bash
# Search path depends on project layout — use paths from components.yaml
grep -rn "func.*Resource" --include="*.go" $SOURCE_REPO_DIR/ | head -20
```

Then for each discovered file, use the LSP tool:
- **operation:** `documentSymbol`
- **filePath:** discovered file path

### 2. Discovery from component_hints

For each component_hint:

1. Map to package path using `{project_context.config_dir}/components.yaml`
2. List Go files in the package
3. Call LSP `documentSymbol` on main files to find exported functions

### 3. Discovery from acceptance_criteria

Parse each acceptance criteria item for technical terms, then grep:

```bash
# Search path depends on project layout — use paths from components.yaml
grep -rn "func Migrate" --include="*.go" $SOURCE_REPO_DIR/ | head -10
```

### 4. Output Discovered Entry Points

```yaml
discovered_entry_points:
  - name: ReconcileNode
    file: pkg/handlers/node-labeller/node_labeller.go
    line: 45
    character: 6
    source: component_hint
    component: node-labeller
  - name: IsARM
    file: pkg/handlers/node-labeller/util.go
    line: 20
    character: 6
    source: explicit_mention
    candidate: ARM
  - ...
```

## Tracing Workflow

For each symbol to trace:

### Step 1: Locate the symbol

Call LSP tool:
- **operation:** `documentSymbol`
- **filePath:** $SOURCE_REPO_DIR/path/to/file.go

Filter results for the target symbol name.

### Step 2: Find callers (who calls this)

Call LSP tool:
- **operation:** `incomingCalls`
- **filePath:** same file
- **line:** symbol's line
- **character:** symbol's column

### Step 3: Find callees (what this calls)

Call LSP tool:
- **operation:** `outgoingCalls`
- **filePath:** same file
- **line:** symbol's line
- **character:** symbol's column

### Step 4: Go to definitions of callers

For each caller found in Step 2:
- **operation:** `goToDefinition`
- **filePath:** caller's file
- **line:** caller's line
- **character:** caller's column

### Step 5: Build the call chain

Repeat Steps 2-4 up the call chain until you reach:
- Test files (note them as test impact)
- Standard library calls
- External dependencies
- Maximum depth (3 levels for performance)

## Output Format

```yaml
# Note: file paths below are illustrative — actual paths are project-specific
call_graph:
  - symbol: HandleFeatureOperation
    file: internal/controller/resource.go
    line: 105

    incoming_calls:  # Who calls this function
      - caller: ReconcileResource
        file: internal/controller/resource.go
        line: 45
        relationship: direct
      - caller: ProcessResourceUpdate
        file: internal/controller/update.go
        line: 89
        relationship: direct

    outgoing_calls:  # What this function calls
      - callee: ValidateChange
        file: internal/controller/validation.go
        line: 120
        relationship: direct

    references:  # All code that references this symbol
      - file: internal/controller/resource_test.go
        line: 456
        context: test
      - file: tests/feature_test.go
        line: 78
        context: test

dependency_chains:
  - chain_name: Feature Operation > State Change
    path:
      - symbol: HandleFeatureOperation
        file: internal/controller/resource.go
      - symbol: UpdateInstanceSpec
        file: internal/handler/instance.go
      - symbol: PrepareStateChange
        file: internal/handler/state.go
    impact: State management may be affected by feature operation changes

summary:
  symbols_traced: 5
  total_callers: 12
  total_callees: 8
  total_references: 45
  max_chain_depth: 3
  tool_used: lsp-native
```

## LSP Operation Guide

### Finding Incoming Calls (Who Calls This)

```yaml
operation: incomingCalls
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns list of functions that call the target function.

### Finding Outgoing Calls (What This Calls)

```yaml
operation: outgoingCalls
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns list of functions that the target function calls.

### Finding All References

```yaml
operation: findReferences
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns all locations where the symbol is referenced.

### Going to Definition

```yaml
operation: goToDefinition
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns the location where the symbol is defined.

### Get Type Information (Hover)

```yaml
operation: hover
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns type signature and documentation.

### Call Hierarchy Preparation

```yaml
operation: prepareCallHierarchy
filePath: <absolute path to file>
line: <1-based line number>
character: <1-based column>
```

Returns call hierarchy item for the symbol.

## Tracing Strategy

### Level 1: Direct Dependencies

- All incoming calls to changed functions
- All outgoing calls from changed functions
- All usages of changed types

### Level 2: Indirect Dependencies

- Callers of the direct callers
- Callees of the direct callees
- Types that embed changed types

### Level 3: Transitive (Optional)

- Only trace if Level 2 shows high-risk patterns
- Stop at 3 levels to stay within context limits

## Path Normalization

**Repository Base:** `$SOURCE_REPO_DIR`

When reporting paths, use relative paths from repo root:

- Absolute: `$SOURCE_REPO_DIR/internal/controller/resource.go`
- Relative: `internal/controller/resource.go`

## Feature Mapping

Map code locations to features by reading `{project_context.config_dir}/components.yaml` `path_to_feature` mapping. The mapping is project-specific — each project defines its own directory-to-feature associations. Do not assume a fixed directory layout.

## Depth Limits

- **Maximum Call Chain Depth:** 3 levels (to stay within context limits)
- **Maximum References:** 30 per symbol
- **Stop Conditions:**
  - Reaching test files (note as test impact)
  - Reaching standard library
  - Reaching external dependencies

## Example Trace

Input:

```yaml
symbols_to_trace:
  - name: HandleFeatureOperation
    file: internal/controller/resource.go       # path from components.yaml
    line: 105
    character: 6
```

LSP Tool Calls:

```
1. LSP documentSymbol on internal/controller/resource.go -> find HandleFeatureOperation at line 105
2. LSP incomingCalls on resource.go:105:6 -> ReconcileResource (resource.go:45), ProcessResourceUpdate (update.go:89)
3. LSP outgoingCalls on resource.go:105:6 -> ValidateChange (validation.go:120)
4. LSP goToDefinition on instance.go:230:6 -> UpdateInstanceSpec definition
```

Output:

```yaml
dependency_chains:
  - chain_name: Feature Operation > Instance Update > State Change
    path:
      - HandleFeatureOperation (resource.go:105)
      - UpdateInstanceSpec (instance.go:230)
      - PrepareStateChange (state.go:45)
    impact: State management depends on instance spec updates
    recommended_test: Verify state change works after feature operation

summary:
  tool_used: lsp-native
```

## Fallback: gopls CLI

If the LSP tool is not registered (tool not available), fall back to gopls CLI
commands via Bash. Always prepend `/usr/local/go/bin` to PATH.

```bash
export PATH="/usr/local/go/bin:$PATH" && cd $SOURCE_REPO_DIR && gopls symbols ./path/to/file.go 2>/dev/null
export PATH="/usr/local/go/bin:$PATH" && cd $SOURCE_REPO_DIR && gopls references ./path/to/file.go:<line>:<col> 2>/dev/null
export PATH="/usr/local/go/bin:$PATH" && cd $SOURCE_REPO_DIR && gopls definition ./path/to/file.go:<line>:<col> 2>/dev/null
export PATH="/usr/local/go/bin:$PATH" && cd $SOURCE_REPO_DIR && gopls call_hierarchy ./path/to/file.go:<line>:<col> 2>/dev/null
```

If neither LSP nor CLI is available, use Grep/Read as final fallback.
