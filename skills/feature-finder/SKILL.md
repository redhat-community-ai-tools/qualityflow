---
name: feature-finder
description: Discover code entry points from Jira data when no PR data exists
model: claude-opus-4-6
---

# Feature Finder Skill

**Phase:** Pre-Processing
**User-Invocable:** false

## Purpose

Discover entry points from Jira data when no PR data exists. Extracts potential symbols and code locations from Jira ticket content for LSP validation.

## When to Use

Invoked by the **regression-analyzer** subagent when:

- No PRs are available for the ticket
- Additional entry points are needed beyond PR-discovered symbols
- Feature candidates from Jira need to be mapped to code locations

## Tools Required

- Grep
- Glob
- Read
- LSP (workspaceSymbol, documentSymbol)

## Input

```yaml
jira_data:
  summary: "Add ARM/multiarch support for node scheduling"
  description: "Enable VMs to be scheduled on ARM nodes..."
  components: [app-handler, node-labeller]
  labels: [ARM, multiarch]
  acceptance_criteria:
    - VMs can be scheduled on ARM nodes
    - Node labels correctly identify architecture
  feature_candidates:
    explicit_mentions: [ResourceInstance, NodeLabeller, ARM]
    component_hints:
      - component: app-handler
        package_path: pkg/handlers/
      - component: node-labeller
        package_path: pkg/handlers/node-labeller/
    integration_points: [node-scheduling, architecture-detection]
```

## What to Look For

From the Jira data, extract:

1. **Feature name and related terminology**
   - Technical terms from summary and description
   - Capitalized terms (likely type/function names)

2. **API types and fields mentioned**
   - ResourceInstance, Instance, DataResource, VolumeSpec
   - NodeLabeller, SchedulingPolicy, etc.

3. **Component names that map to packages**
   - app-controller, app-handler, app-api
   - storage, network, migration, etc.

4. **Function/action names from acceptance criteria**
   - "schedule" → Schedule*, Scheduling*
   - "migrate" → Migrate*, Migration*
   - "attach" → Attach*, Hotplug*

## Component-to-Package Mapping

**Reference:** Read `{project_context.config_dir}/components.yaml` for the complete mapping.

## Discovery Method

### Phase 1: Keyword Extraction

Extract keywords from Jira data:

1. **From Summary:** Technical terms, API types, feature names
2. **From Components:** Map to package paths per table above
3. **From Labels:** Often contain feature names (ARM, multiarch, etc.)
4. **From Acceptance Criteria:** Action verbs, type names
5. **From Description:** Capitalized terms, quoted identifiers

### Phase 2: Symbol Search

For each extracted keyword:

1. **Use Grep for text-based discovery:**

   ```
   # Use repo path from `repositories.yaml` in `project_context.config_dir`
   Grep pattern="func.*NodeLabeller" path="<repo_path>/pkg/handlers/"
   Grep pattern="type.*ARM" path="<repo_path>/pkg/"
   ```

2. **Use LSP workspaceSymbol for semantic search:**

   ```
   LSP operation="workspaceSymbol" query="NodeLabeller" filePath="<repo_path>/pkg/" line=1 character=1
   ```

### Phase 3: Package Exploration

For each component_hint:

1. **Glob the package for main files:**

   ```
   # Use repo path from `repositories.yaml` in `project_context.config_dir`
   Glob pattern="<repo_path>/pkg/handlers/node-labeller/*.go"
   ```

2. **Use LSP documentSymbol to list exported functions:**

   ```
   LSP operation="documentSymbol" filePath="<repo_path>/pkg/handlers/node-labeller/node_labeller.go" line=1 character=1
   ```

3. **Filter for exported symbols (uppercase first letter in Go)**

## Output Format

**IMPORTANT:** Only report symbols/entry points actually named in the Jira source evidence or confirmed to exist by grep/LSP against the repo. Never infer, paraphrase, or fabricate a symbol, function, or feature name that isn't present in the input or the searched code.

```yaml
discovered_entry_points:
  - name: ReconcileNode
    file: pkg/handlers/node-labeller/node_labeller.go
    line: 45
    character: 6
    source: component_hint
    discovery_method: documentSymbol
    original_keyword: node-labeller
  - name: IsARM64
    file: pkg/handlers/node-labeller/util.go
    line: 28
    character: 6
    source: explicit_mention
    discovery_method: grep
    original_keyword: ARM
  - name: GetArchitecture
    file: pkg/handlers/node-labeller/node_labeller.go
    line: 120
    character: 6
    source: acceptance_criteria
    discovery_method: workspaceSymbol
    original_keyword: architecture
  - ...

keywords_searched:
  - keyword: NodeLabeller
    found: true
    matches: 3
  - keyword: ARM
    found: true
    matches: 5
  - keyword: multiarch
    found: false
    matches: 0
  - ...

packages_explored:
  - package: pkg/handlers/node-labeller/
    files_found: 4
    exported_symbols: 12
  - ...

summary:
  total_keywords: 8
  keywords_found: 6
  total_entry_points: 15
  packages_explored: 2
```

## Integration with lsp-tracer

The output from this skill feeds directly into **lsp-tracer** (K4):

```yaml
# feature-finder output becomes lsp-tracer input
# Repo path from `repositories.yaml` in `project_context.config_dir`
symbols_to_trace:
  - name: ReconcileNode
    file: <repo_path>/pkg/handlers/node-labeller/node_labeller.go
    line: 45
    character: 6
  - name: IsARM64
    file: <repo_path>/pkg/handlers/node-labeller/util.go
    line: 28
    character: 6
  - ...
```

## Example Usage

**Input Jira for PROJ-494 (no PRs):**

- Summary: "ARM multiarch support"
- Components: [app-handler]
- Labels: [ARM, multiarch]

**Discovery Process:**

1. Extract keywords: ARM, multiarch, app-handler
2. Map app-handler → pkg/handlers/node-labeller/
3. Grep for "ARM" in pkg/handlers/ → find IsARM64, GetArchitecture
4. Glob pkg/handlers/node-labeller/*.go → find main files
5. documentSymbol on each file → list exported functions
6. Return discovered_entry_points for lsp-tracer

**Result:** Even without PRs, we discover entry points like ReconcileNode, IsARM64, GetArchitecture for call graph analysis.
