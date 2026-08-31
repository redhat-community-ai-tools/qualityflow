---
name: generate-tests
description: Generate working test implementations from STD YAML
argument-hint: <JIRA-ID> [--priority=<p0|p1|p2>]
allowed-tools: Read, Write, Edit, Task, Glob, Grep, LSP, Skill, Bash
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

## Step 0.5: Parse Priority Filter (if provided)

Scan `$ARGUMENTS` for the `--priority=X` flag:

1. **Extract priority value:**
   - Pattern: `--priority=(p0|p1|p2)` (case-insensitive)
   - If found, normalize to uppercase: `priority_filter = "P0"`, `"P1"`, or `"P2"`
   - If not found, set `priority_filter = null` (generate all scenarios)

2. **Validate priority value:**
   - If flag is present but value is invalid (not p0/p1/p2), report error:

     ```text
     Error: Invalid priority value.
     Use --priority=p0, --priority=p1, or --priority=p2
     ```

   - Exit command

3. **Log filter status:**
   - If `priority_filter` is set: "Filtering test generation to priority {priority_filter}"
   - If null: "Generating tests for all priorities"

## Step 1: Check Feature Toggles

Scan `{project_context.config_dir}/` for language YAML files with
`enabled: true` (e.g., `tier1.yaml`, `tier2.yaml`).

Also check feature toggles:
- If `tier1_tests` is false and no Go config exists → skip Go
- If `tier2_tests` is false and no Python config exists → skip Python

If no language configs are found and both tier toggles are false:
- Report: "No test generation targets configured for this project."
- Exit

## Step 2: Verify STD Exists

Check for STD YAML at `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`.
If not found, tell the user to run `/std-builder {JIRA_ID}` first.

## Step 2.5: Pipeline State

Code generation is a **single generic phase** (`codegen`), regardless of how
many languages Step 1 enables — the phase machine is language-agnostic. Use the
Skill tool to invoke the pipeline-state skill once:

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "start-phase {JIRA_ID} codegen"

This will:
1. Read or initialize pipeline state
2. Validate prerequisites (`std.status == completed`)
3. Check approval gate: if `std_review` is in `approval_gates` (default: yes),
   verify `outputs/{JIRA_ID}/state/approvals.yaml` has `std_review.status == approved`
4. Check if the STD has been modified since it was recorded (staleness)
5. Update the phase status to `in_progress`

**If the approval gate blocks:** Show message: "STD Review is awaiting human
approval. Approve the reviewed STD from the dashboard, or record it in
`outputs/{JIRA_ID}/state/approvals.yaml`. (The review cycle runs automatically
inside `/std-builder`; if no review report exists yet, run
`/review-std {JIRA_ID}` and `/refine-std {JIRA_ID}`.)" and exit — do not
generate for ANY language. The gate is on the STD itself, not per-language,
so one block means the STD is not approved.

**If prerequisites are not met:** Show the suggestion (e.g., "Run
`/std-builder` first") and exit.

**If the STD is stale:** Show the warning but continue. The user can choose
to re-run `/std-builder` if needed.

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
- args: "{JIRA_ID} {priority_filter}"
  (e.g., "PROJ-12345 P0" if filtering, "PROJ-12345" if not)

The skill reads the STD YAML and project config to generate tests
for each enabled language/framework.

## Step 4.5: Verify Compilation / Collection

For each language that produced test files, run the verification command
with the Bash tool:

**Go:**

```bash
go vet ./...
```

(run in the package directory containing the generated tests)

**Python:**

```bash
python -m pytest --collect-only <generated test files>
```

Fix any compilation or collection errors and re-run (max 3 attempts).

**Record the result honestly — the verification outcome MUST appear in the
Step 5 summary as one of:**

- `passed` — the command ran and exited 0
- `failed` — the command ran and errors remain after 3 fix attempts
  (report the remaining errors)
- `skipped (<reason>)` — the command could not run at all; state why
  (e.g., "go toolchain not installed", "pytest not installed")

Never silently omit verification. A skip must be visible in the output
summary, not implied.

## Step 5: Report Results

Show a summary of generated files per language, test counts,
the verification result per language from Step 4.5
(passed / failed / skipped with reason), and any errors or warnings.

## Step 6: Update Pipeline State (on completion)

Close out the single `codegen` phase started in Step 2.5, honestly:

**If generation succeeded and verification is `passed` or `skipped` for every
language generated:**

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "complete-phase {JIRA_ID} codegen"

Pass `--output outputs/{JIRA_ID}/{language}-tests/summary.yaml` for the primary
language (complete-phase records its checksum; a missing file warns without
failing) and phase-specific data:

```yaml
files: {FILE_COUNT}
tests: {TEST_COUNT}
verification: "{passed | skipped (<reason>)}"
```

**If generation errored, or verification is `failed` (for any language) after 3
fix attempts:**

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "fail-phase {JIRA_ID} codegen"

with the error message. Tests that don't compile or collect are not a
completed phase — recording them as one would hide the failure from the
dashboard.

After the state updates, show the **next-step suggestion** from the response.
