---
name: std-builder
description: Generate STD (YAML + test stubs with PSE docstrings) from an existing STP file
argument-hint: <JIRA-ID> [--priority=<p0|p1|p2>]
allowed-tools: Read, Write, Edit, Task, Glob, Grep, Skill
---

# STD Builder

Generates the complete Software Test Description (STD):
1. **STD YAML file** (internal format for automation)
2. **Test stubs with PSE docstrings** (the deliverable for human review)

Per the SOFTWARE_TEST_DESCRIPTION.md in your automation repo, the STD = docstrings in test files.

---

When the user runs this command with a Jira ID, you MUST:

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
- `stp_header`, `versioning`

**If project resolution fails:** Display the error and exit. Do not proceed.

**Check std_generation toggle:**
If `project_context.feature_toggles.std_generation` is false:
- Output: "STD generation is disabled for project {project_context.display_name} (std_generation toggle is false)."
- Exit. Do not proceed.

### Step 0.5: Pipeline State

Use the Skill tool to invoke the pipeline-state skill:

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "start-phase {JIRA_ID} std"

This will:
1. Read or initialize pipeline state
2. Validate prerequisites (`stp.status == completed`)
3. Check approval gate: if `stp_review` is in `approval_gates` (default: yes),
   verify `outputs/state/{JIRA_ID}/approvals.yaml` has `stp_review.status == approved`
4. Check if STP has been modified since last STD generation (staleness)
5. Update `std` phase status to `in_progress`

**If prerequisites not met:** Show the suggestion (e.g., "Run `/stp-builder` first") and exit.

**If approval gate blocks:** Show message: "STP Review is awaiting human approval.
Run `/review-stp {JIRA_ID}` and `/refine-stp {JIRA_ID}` to complete the review cycle." and exit.

**If STP is stale:** Show warning but continue. The user can choose to re-run
`/stp-builder` if needed.

## Step 0.6: Parse Priority Filter (if provided)

Scan `$ARGUMENTS` for the `--priority=X` flag:

1. **Extract priority value:**
   - Pattern: `--priority=(p0|p1|p2)` (case-insensitive)
   - If found, normalize to uppercase: `priority_filter = "P0"`, `"P1"`, or `"P2"`
   - If not found, set `priority_filter = null` (generate all stubs)

2. **Validate priority value:**
   - If flag is present but value is invalid (not p0/p1/p2), report error:

     ```text
     Error: Invalid priority value.
     Use --priority=p0, --priority=p1, or --priority=p2
     ```

   - Exit command

3. **Log filter status:**
   - If `priority_filter` is set: "Filtering stub generation to priority
     {priority_filter}"
   - If null: "Generating stubs for all priorities"

**Note:** The STD YAML always contains all scenarios regardless of priority
filter. Only test stubs are filtered. This allows multiple incremental PRs
for design review (P0 stubs → P1 stubs → P2 stubs) while keeping the STD
YAML complete.

## Step 1: Parse the Jira ID

Extract the Jira ID from `project_context.jira_id` (e.g., MYPROJ-12345, PROJ-494).

## Step 2: Verify STP File Exists

**CRITICAL: STD generation requires an existing STP file.**

Check that the STP file exists:
```
outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md
```

**If STP file does NOT exist:**
- Inform the user: "STP file not found. Please run `/stp-builder {JIRA_ID}` first."
- Exit - do not proceed with STD generation

**If STP file exists:**
- Proceed to Step 3

## Step 3: Generate STD YAML (Internal Format)

Use the Skill tool to invoke the std-orchestrator skill:

**Tool:** Skill
**Parameters:**
- skill: "std-orchestrator"
- args: "{JIRA_ID}"

The std-orchestrator skill will:
1. Read the STP file at `outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md`
2. Parse Section III (Requirements-to-Tests Mapping table)
3. Extract all test scenarios
4. Generate comprehensive STD YAML file:
   - Output: `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`
5. Validate STD YAML

## Step 4: Generate Test Stubs (The Actual STD)

After STD YAML is generated, generate test stubs with PSE docstrings.

Use the Skill tool to invoke stub-generator:

**Tool:** Skill
**Parameters:**
- skill: "stub-generator"
- args: "{JIRA_ID} {priority_filter}"
  (e.g., "PROJ-123 P0" if filtering, "PROJ-123" if not)

The stub-generator discovers enabled language configs from
`{project_context.config_dir}/`, maps STD scenarios to languages (by tier
or full-coverage), and generates stubs in the appropriate framework:
- Stubs are written to `outputs/std/{JIRA_ID}/{language}-tests/` (one directory per tier language)

Feature toggle checking and tier-to-language routing happen inside the
stub-generator — no pre-filtering needed here.

## Step 5: Report to User

Once complete, show the user:

```
✅ STD Generation Complete!

📄 Input: outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md

📊 Summary:
- STP scenarios: {TOTAL_COUNT}
- STD YAML: {JIRA_ID}_test_description.yaml (internal format)

📁 STD Output (for review):
{for each language with stubs generated:}
- outputs/std/{JIRA_ID}/{language}-tests/ ({COUNT} test stubs)

📋 Phase 1 Checklist:
- [ ] STP link in module docstring
- [ ] Tests grouped in class with shared preconditions
- [ ] Each test has: Preconditions, Steps, Expected
- [ ] Each test verifies ONE thing with ONE Expected
- [ ] Python test bodies contain only PSE docstring (no `pass`); Go stubs use PendingIt() with Skip()

✅ Ready for design review!

📌 Next steps:
1. Review the test stubs (the STD)
2. Submit PR for design review
3. After approval, run:
   - /generate-tests {JIRA_ID}
   - 
```

---

## Output Structure

```
outputs/std/{JIRA_ID}/
├── {JIRA_ID}_test_description.yaml     (STD YAML - internal format)
├── go-tests/                           (Tier 1 STD - test stubs)
│   └── {feature}_stubs_test.go         (PendingIt + PSE comments)
└── python-tests/                       (Tier 2 STD - test stubs)
    └── test_{feature}_stubs.py         (__test__=False + PSE docstrings)
```

---

## Workflow Overview

```
User: /std-builder {JIRA_ID}
  ↓
0. Resolve project: project-resolver → project_context
  ↓
1. Verify STP exists: outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md
  ↓
2. Generate STD YAML (internal):
   → outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml
  ↓
3. Generate test stubs (respecting feature toggles):
   → outputs/std/{JIRA_ID}/go-tests/*_stubs_test.go (if tier1_tests enabled)
   → outputs/std/{JIRA_ID}/python-tests/test_*_stubs.py (if tier2_tests enabled)
  ↓
4. Report results:
   STD complete - ready for design review
```

---

## Error Handling

**If STP file not found:**
- Error message: "STP file not found at outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md"
- Suggestion: "Please run `/stp-builder {JIRA_ID}` first to create the STP"
- Exit without proceeding

**If STP Section III is empty:**
- Error message: "No test scenarios found in STP Section III"
- Suggestion: "Verify STP file is complete and contains Requirements-to-Tests Mapping table"
- Exit

**If std-orchestrator skill fails:**
- Display error message from skill
- Show partial results if any
- Suggest reviewing errors and re-running

**If stub generation fails:**
- Show which stubs were generated successfully
- Report which scenarios failed
- STD YAML is still available for manual review

---

## Prerequisites

**Before running this command:**
1. ✅ STP file must exist (run `/stp-builder {JIRA_ID}` first)
2. ✅ STP must contain Section III with test scenarios

---

## Example Usage

**Step 1: Generate STP**
```
User: /stp-builder {JIRA_ID}
Output: outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md
```

**Step 2: Generate STD (YAML + Stubs)**
```
User: /std-builder {JIRA_ID}
Output:
   - outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml (internal)
   - outputs/std/{JIRA_ID}/go-tests/*_stubs_test.go (if tier1_tests enabled)
   - outputs/std/{JIRA_ID}/python-tests/test_*_stubs.py (if tier2_tests enabled)
```

**Step 3: After Design Review - Generate Implementation**
```
User: /generate-tests {JIRA_ID}
User: /generate-tests {JIRA_ID}
Output: Full working test implementations
```

---

## Step 6: Update Pipeline State (on completion)

After all generation completes successfully:

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "complete-phase {JIRA_ID} std"

Pass phase-specific data:
```yaml
output: "outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml"
stp_checksum_at_generation: <SHA-256 of STP file>
scenario_counts:
  total: {TOTAL_COUNT}
  tier1: {TIER1_COUNT}
  tier2: {TIER2_COUNT}
stubs:
  - language: go
    path: "outputs/std/{JIRA_ID}/go-tests/"
    count: {GO_STUB_COUNT}
  - language: python
    path: "outputs/std/{JIRA_ID}/python-tests/"
    count: {PYTHON_STUB_COUNT}
```

If generation **fails**, update with:
- skill: "pipeline-state"
- args: "fail-phase {JIRA_ID} std"

After state update, show the **next-step suggestion** from the response.

---

## Notes

- **STD = Test stubs with docstrings** (per SOFTWARE_TEST_DESCRIPTION.md)
- **STD YAML = Internal format** (for automation, not for review)
- **Two-phase workflow:**
  - Phase 1 (this command): Generate stubs for design review
  - Phase 2 (/generate-*-tests): Generate full implementation
- **Test stubs are excluded from execution:**
  - Go: `PendingIt()` with `Skip()`
  - Python: `__test__ = False` with docstring-only body

---

**End of STD Builder Command**
