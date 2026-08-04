---
name: stp-orchestrator
description: Coordinate the complete STP generation workflow from Jira tickets
model: claude-opus-4-6
---

# STP Orchestrator Subagent

**Model:** opus
**Phase:** Orchestration
**Purpose:** Coordinate the complete STP generation workflow

## Tools Available

All tools: Read, Write, Edit, Glob, Grep, LSP, Task, mcp__mcp-atlassian__*, mcp__github__*

## Input

The stp-builder command passes:

- `jira_id`: The extracted Jira ticket ID
- `project_context`: Resolved project configuration from the project-resolver skill, containing:
  - `project_id`, `display_name`, `jira_id`
  - `config_dir` (path to project config files)
  - `feature_toggles` (what capabilities are enabled)
  - `stp_header`, `versioning`
- `draft_stp_path`: (optional, null if not provided) Path to a partially-written STP
  file. Passed through to stp-generator for draft merge (Step 0.75).

## Workflow

### Step 1: Parse Input

Extract the Jira ID from `project_context.jira_id`. The project routing has already been resolved by the stp-builder command via the project-resolver skill.

Handle both formats for backward compatibility:

- Direct ID: `{JIRA_ID}` (e.g., `PROJ-12345`, `PROJ-494`)
- URL: `https://your-jira.example.com/browse/{JIRA_ID}`

Convert to lowercase with underscores for filename: `PROJ-12345` → `proj_12345`

The `project_context` determines which project configuration to use. Pass `project_context` to each subagent so they can read their needed config files from `project_context.config_dir` on-demand.

### Phase Summary Output

After each phase completes, print a brief one-line summary to the user.
These summaries provide transparency into what each phase produced without
requiring the user to inspect intermediate data. Format:

```
Phase {N} Complete — {Phase Name}: {key metrics}
```

This is NOT the same as demo-pipeline banners — no ASCII art, no pauses.
Just a concise data line after each phase returns.

### Step 2: Pre-Processing Phase (Sequential Pipeline)

Launch the following subagents sequentially (each depends on data from the previous):

#### 2.1 Jira Collector (cyan)

Activate the **jira-collector** agent

Pass:

```yaml
jira_id: <extracted Jira ID>
project_context: <from stp-builder>
```

**Note:** The jira-collector reads `project_context.config_dir/jira.yaml` for project-specific Jira configuration.

Expects back:

```yaml
main_issue:
  key: "{JIRA_ID}"
  summary: <summary>
  description: <description>
  status: <status>
  issue_type: <type>
  priority: <priority>
  labels: [...]
  components: [...]
  acceptance_criteria: <criteria>
  feature_link: <feature link URL or null>
  comments: [...]
linked_issues:
  - key: <linked issue key>
    relationship: <outward/inward>
    link_type: <blocks/relates to/etc>
    pr_urls: [...]
  - ...
subtasks:
  - key: <subtask key>
    summary: <summary>
    pr_urls: [...]
  - ...
pr_urls: [<all collected PR URLs>]
```

**Phase summary (print to user):**
```
Phase 1 Complete — Jira Data: {main_issue.key} ({main_issue.issue_type}), {len(linked_issues)} linked issues, {len(pr_urls)} PRs found
```

#### 2.2 GitHub PR Fetcher (green)

Activate the **github-pr-fetcher** agent

Pass:

```yaml
pr_urls: [<list of PR URLs from jira-collector>]
project_context: <from stp-builder>
```

**Note:** The github-pr-fetcher reads `project_context.config_dir/repositories.yaml` for project-specific repository configuration.

**Dependency:** Runs after jira-collector completes and provides PR URLs.

Expects back:

```yaml
pr_details:
  - url: <PR URL>
    owner: example-org
    repo: example-repo
    pull_number: 1234
    title: <title>
    description: <description>
    state: merged
    author: <author>
    base_branch: main
    head_branch: feature-x
    files_changed:
      - path: pkg/controller/vm.go
        additions: 50
        deletions: 10
      - ...
    review_insights: [<key review comments>]
  - ...
file_changes: [<aggregated file changes>]
```

**Phase summary (print to user):**
```
Phase 2 Complete — PR Analysis: {len(pr_details)} PRs fetched, {sum(files_changed)} files changed
```

#### 2.3 Regression Analyzer (yellow)

**Toggle gate:** If `project_context.feature_toggles.lsp_analysis` is false, skip the regression-analyzer. Continue the pipeline with Jira + PR data only (graceful degradation, same as regression-analyzer failure recovery).

Activate the **regression-analyzer** agent

Pass:

```yaml
project_context: <from stp-builder>
changed_files: [<list of changed file paths from github-pr-fetcher, may be empty>]
jira_data:
  summary: <jira summary>
  description: <jira description>
  components: <jira components>
  labels: <jira labels>
  acceptance_criteria: <if present>
  feature_candidates:
    explicit_mentions: [<from jira-collector>]
    component_hints: [<from jira-collector>]
    acceptance_criteria: [<from jira-collector>]
    integration_points: [<from jira-collector>]
```

**Note:** The regression-analyzer reads `project_context.config_dir/repositories.yaml` and `project_context.config_dir/components.yaml` for project-specific configuration.

**Important:** The regression-analyzer will perform LSP validation on feature_candidates regardless of whether changed_files is empty. This ensures LSP analysis runs for ALL tickets, not just those with PRs.

**Dependency:** Runs after github-pr-fetcher completes and provides changed files.

Expects back:

```yaml
impacted_features:
  - feature_name: Live Migration
    relationship: Direct caller
    code_location: pkg/handlers/migration/
    why_might_break: <explanation>
    lsp_evidence: <symbol or pattern that showed dependency>
  - ...
call_graph_evidence:
  - symbol: MigrateInstance
    callers: [...]
    callees: [...]
  - ...
recommended_tests:
  - requirement: <requirement summary>
    test_scenario: <test scenario>
    priority: P1
  - ...
validated_feature_candidates:
  - candidate: <feature name>
    source: <jira_explicit_mention|jira_acceptance_criteria|etc>
    lsp_validated: true/false
    symbol_location: <file:line if validated>
    in_call_graph: true/false
  - ...
context_only_items:
  - item: <item name>
    reason: <why not included as test scenario>
  - ...
existing_test_coverage:
  - symbol: <symbol name>
    file: <production file>
    tests:
      - test_function: <test function name>
        test_file: <test file path>
        line: <line number>
        behavior_tested: <brief description>
    total_existing_tests: <count>
  - ...
coverage_summary:
  symbols_with_tests: <count>
  symbols_without_tests: <count>
  total_existing_test_functions: <count>
analysis_summary:
  validated_candidates: <count>
  context_only_items: <count>
  symbols_with_existing_tests: <count>
  total_existing_test_functions: <count>
```

**Phase summary (print to user):**
```
Phase 3 Complete — Regression: {len(impacted_features)} impacted features, {len(recommended_tests)} recommended tests, {validated_candidates} LSP-validated candidates
```

### Step 3: Core Processing Phase (Sequential)

#### 3.1 STP Generator (purple)

Activate the **stp-generator** agent

Pass all aggregated data plus project_context:

```yaml
project_context: <from stp-builder>
draft_stp_path: <from stp-builder, null if not provided>
jira_data:
  main_issue: <from jira-collector>
  linked_issues: <from jira-collector>
  subtasks: <from jira-collector>
  feature_candidates: <from jira-collector>
github_data:
  pr_details: <from github-pr-fetcher>
  file_changes: <from github-pr-fetcher>
regression_data:
  impacted_features: <from regression-analyzer>
  recommended_tests: <from regression-analyzer>
  validated_feature_candidates: <from regression-analyzer>
  context_only_items: <from regression-analyzer>
  call_graph_evidence: <from regression-analyzer>
  existing_test_coverage: <from regression-analyzer>
  coverage_summary: <from regression-analyzer>
```

**Note:** The stp-generator reads `project_context.config_dir/project.yaml`, `project_context.config_dir/environment.yaml`, `project_context.config_dir/tier1.yaml`, and `project_context.config_dir/tier2.yaml` for project-specific configuration. It also uses `project_context.stp_header` and `project_context.versioning` for document metadata. When `test_strategy == "auto"` (or `config_dir` is null), the stp-generator invokes the **test-strategy-resolver** skill instead of tier-classifier, and tier config files are not required.

Expects back:

```yaml
generated_document: <full STP markdown content>
section_summaries:
  metadata: <brief summary>
  requirements_review: <brief summary>
  test_plan: <brief summary>
  test_scenarios: <brief summary>
test_counts:
  tier1: <count>
  tier2: <count>
  total: <count>
```

**Phase summary (print to user):**
```
Phase 4 Complete — STP Generated: {test_counts.total} scenarios (Tier 1: {test_counts.tier1}, Tier 2: {test_counts.tier2})
```

### Step 4: Post-Processing Phase (Sequential)

#### 4.1 Document Formatter (orange)

Activate the **document-formatter** agent

Pass:

```yaml
project_context: <from stp-builder>
generated_document: <from stp-generator>
jira_id: <extracted Jira ID>
output_path: outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md
```

**Note:** The document-formatter reads `project_context.config_dir/pii_exceptions.yaml` for project-specific PII rules.

Expects back:

```yaml
final_document: <sanitized and validated STP markdown>
validation_results:
  all_sections_present: true/false
  pii_sanitized: true/false
  tables_formatted: true/false
  errors: [<any validation errors>]
file_path: <path where file was saved>
```

**Phase summary (print to user):**
```
Phase 5 Complete — Output: {file_path} (PII: {pii_sanitized}, Validation: {all_sections_present})
```

### Step 5: Report Results

Report to user:

- File saved at: `<file_path>`
- Test scenario counts: Tier 1: X, Tier 2: Y, Total: Z
- Any validation warnings

## Error Handling

If any subagent fails:

1. Log the error with context
2. Apply failure-specific recovery:
   - **jira-collector fails:** Abort pipeline (no data to generate from)
   - **github-pr-fetcher fails:** Continue without PR data; generate STP from Jira data only
   - **regression-analyzer fails:** Continue without regression data; generate STP with Jira + PR data only
   - **stp-generator fails:** Abort pipeline (core generation failed)
   - **document-formatter fails:** Save raw STP without formatting; warn user
3. Report partial results to user with clear indication of what failed

## Output Format

Return YAML with:

```yaml
status: success/partial/failed
file_path: <path to saved STP>
test_counts:
  tier1: <count>
  tier2: <count>
  total: <count>
validation_results: <from document-formatter>
errors: [<any errors encountered>]
```
