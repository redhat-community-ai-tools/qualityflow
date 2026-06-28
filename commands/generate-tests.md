---
name: generate-tests
description: Generate working test implementations from STD YAML
argument-hint: <JIRA-ID>
allowed-tools: Read, Write, Edit, Task, Glob, Grep, LSP, Skill
---

# Generate Tests Command

Generates **full working test implementations** from STD YAML, in whatever
languages and frameworks the project config declares.

**Use this after design review is approved.** For test stubs (design phase), use `/std-builder` instead.

---

When the user runs `/generate-tests {JIRA_ID}`:

## Step 0: Resolve Project

Use the Skill tool to invoke the project-resolver skill:

**Tool:** Skill
**Parameters:**
- skill: "project-resolver"
- args: "$ARGUMENTS"

This returns `project_context` containing:
- `project_id`, `display_name`, `jira_id`
- `config_dir` (path to project config files)
- `feature_toggles` (what capabilities are enabled)

## Step 1: Check Feature Toggles

Scan `{project_context.config_dir}/` for language YAML files with
`enabled: true` (e.g., `go.yaml`, `python.yaml`, `tier1.yaml`, `tier2.yaml`).

Also check feature toggles:
- If `tier1_tests` is false and no Go config exists → skip Go
- If `tier2_tests` is false and no Python config exists → skip Python

If no language configs are found and both tier toggles are false:
- Report: "No test generation targets configured for this project."
- Exit

## Step 2: Verify STD Exists

Check for STD YAML at `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`.
If not found, tell the user to run `/std-builder {JIRA_ID}` first.

## Step 3: LSP Pattern Analysis (if enabled)

If `lsp_analysis` toggle is true:

Use the Skill tool to invoke the lsp-tracer skill:

**Tool:** Skill
**Parameters:**
- skill: "lsp-tracer"
- args: "{JIRA_ID}"

Use the Skill tool to invoke the feature-finder skill:

**Tool:** Skill
**Parameters:**
- skill: "feature-finder"
- args: "{JIRA_ID}"

## Step 4: Generate Tests

Use the Skill tool to invoke the test-generator skill:

**Tool:** Skill
**Parameters:**
- skill: "test-generator"
- args: "{JIRA_ID}"

The skill reads the STD YAML and project config to generate tests
for each enabled language/framework.

## Step 5: Report Results

Show a summary including:
- Generated files per language and test counts
- **Target directories** where files were placed (co-located in source
  tree with `qf_` prefix, or fallback to `outputs/`)
- **Compile gate result** (passed/failed/skipped + retry count)
- Any errors or warnings

Example output:
```
Go: 3 files → internal/cli/qf_*.go (compile gate: passed)
Python: 2 files → tests/e2e/qf_test_*.py (syntax check: passed)
```
