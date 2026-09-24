---
name: std-orchestrator
description: Orchestrate STP → STD pipeline (generates comprehensive STD YAML only)
model: claude-opus-4-6
---

# STD Orchestrator Skill

## Purpose

Coordinates the Software Test Description (STD) generation workflow by:

1. Parsing STP Section III to extract test scenarios
2. Generating comprehensive STD YAML file for ALL scenarios (internal format)
3. Validating output and generating summary report

**Output:**

- STD YAML file (internal format for automation). Code generation (stubs,
  implementations) is NOT this skill's job — callers invoke stub-generator /
  test-generator themselves after this skill returns.

---

## Input Required

**One of two sources** — an STP, or a scenario list:

- `stp_file_path`: Path to the STP markdown file (e.g., `outputs/PROJ-66855/stp/PROJ-66855_test_plan.md`)
- `scenario_list_path`: Path to a scenario list YAML (e.g.,
  `outputs/PROJ-66855/input/PROJ-66855_scenarios.yaml`) — used when there is no
  STP: bug fixes, smaller features, and scenarios imported from an external test
  case management system. See **Step 1B**.

Plus:

- `jira_id`: The Jira ticket ID (e.g., "PROJ-66855")
- `output_dir`: Base directory for outputs (defaults to `outputs/{JIRA_ID}/std/`)

When both are present the STP wins and the scenario list is ignored — say so in
the summary report rather than silently picking one.

---

## Workflow

Execute the following steps in order:

---

### Step 1: Load Scenarios

Scenarios come from the STP when there is one (**Step 1A**) and from a scenario
list file when there is not (**Step 1B**). Both produce the same `scenarios`
structure, and everything downstream is identical.

### Step 1A: Parse STP Section III

**Read the STP file and extract all test scenarios from Section III (Test Scenarios & Traceability).**

**Expected bullet-based format:**

```markdown
- **[PROJ-12345]** — As a user, I want to reset a VM
  - *Test Scenario:* [Tier 1] Verify basic reset operation succeeds
  - *Priority:* P0

- **[PROJ-12345]** — As a user, I want to verify reset preserves state
  - *Test Scenario:* [Tier 1] Verify reset preserves pod UID
  - *Priority:* P0
```

**Parse and extract:**

- Requirement ID (Jira key from `**[ID]**`)
- Requirement summary (text after `—`)
- Test type classification from test scenario:
  - Tier mode: `[Tier 1]`, `[Tier 2]`
  - Auto mode: `[unit]`, `[functional]`, `[integration]`, `[e2e]`
- Priority (P0, P1, P2)
- Scenario description (from `*Test Scenario:*` line)
- Coverage status (if present): `[EXISTING_COVERAGE]`, `[PARTIAL_COVERAGE]`

**Store as:**

```yaml
scenarios:
  - scenario_id: 1
    tier: "Tier 1"                # tier mode
    test_type: "functional"       # auto mode (one or the other)
    priority: "P0"
    description: "Verify basic reset operation succeeds"
    coverage_status: "NEW"        # optional, defaults to NEW
  - scenario_id: 2
    tier: "Tier 1"
    priority: "P0"
    description: "Verify reset preserves pod UID"
    coverage_status: "EXISTING_COVERAGE"
    covered_by:
      - test_function: "TestResetPreservesPodUID"
        test_file: "pkg/compute/reset_test.go"
```

---

### Step 1B: Read a Scenario List

When there is no STP, the scenarios are handed to the pipeline directly. This is
the seam for inputs other than an STP — an importer for an external test case
management system writes this file and the rest of the pipeline is unchanged.

**Format** (`outputs/{JIRA_ID}/input/{JIRA_ID}_scenarios.yaml`):

```yaml
source: "polarion"                  # free text — where these scenarios came from
context:
  jira_id: "PROJ-12345"
  title: "Short feature or bug title"
  feature_description: "What the change does, in user terms."
  jira_url: "https://jira.example.com/browse/PROJ-12345"
  known_limitations: []             # optional
scenarios:
  - scenario_id: 1
    external_id: "TC-4471"          # optional — the id in the source system
    requirement_id: "PROJ-12345"    # the Jira requirement this covers
    requirement_summary: "As a user, I want ..."
    test_type: "functional"         # auto mode; or tier: "Tier 1" in tier mode
    priority: "P0"
    description: "Verify basic reset operation succeeds"
    coverage_status: "NEW"          # optional, defaults to NEW
    preconditions: []               # optional — carried from the source system
    steps: []                       # optional
    expected: []                    # optional
```

**Validate it before use** (never hand-check these):

```bash
python3 skills/std-reviewer/validate_std.py --scenarios \
  outputs/{JIRA_ID}/input/{JIRA_ID}_scenarios.yaml
```

Exit code 1 means the file is unusable — report the errors and exit rather than
generating an STD from a malformed list.

**Rules:**

- `preconditions` / `steps` / `expected`, when present, are the source system's
  own wording. Pass them to std-generator as the basis for the PSE content —
  **do not invent replacements**; refine wording only, never the meaning. When
  absent, std-generator derives PSE from `description` as it does for an STP.
- `external_id` is carried into the STD scenario unchanged, so a migrated test
  can be traced back to its source record. It does not by itself produce any
  marker in the stubs — that stays governed by the project's `polarion` toggle.
- `context.jira_url` becomes the per-test reference in the stubs (`Jira:`),
  since there is no STP to link. See **stub-generator**.

---

### Step 2: Generate Comprehensive STD YAML (Single File)

**Generate ONE comprehensive STD file for ALL scenarios:**

1. **Extract STP context** (needed by std-generator).
   **From a scenario list (Step 1B):** take `context.*` as-is — `jira_id`,
   `title`, `feature_description`, `known_limitations` (default `[]`) — set
   `source_constants: []`, `api_extensions: false`, and `stp_reference: null`,
   then skip to sub-step 2. Steps 1.5 and 1.7 below read the STP and do not
   apply. **From an STP:**
   - Jira issue metadata (from Metadata & Tracking)
   - Feature description (from Feature Overview)
   - Known limitations (from Section I.2)
   - API extensions (from Section I.3 API Extensions checkbox)
   - Test environment (from Section II.3)
   - Source bugs (if Closed Loop ticket)
   - Fix versions

1.5. **Extract Source Constants (if present):**

- Check if the STP contains a `## Source Constants` or `#### Section III.2 — Source Constants` section
- If found, parse the markdown table into a structured array:

     ```yaml
     source_constants:
       - name: "SENTINEL"
         value: "# --- managed section - do not edit ---"
         source_file: "pkg/scripts/sync.sh"
         line: 14
     ```

- Values are in backtick-wrapped cells — strip the backticks but preserve the exact content
- If the section is not present, set `source_constants` to an empty array

1.7. **Resolve Merged STP URL:**

- Before generating the STD, check if the STP has been merged into a design-docs
  repository. If a merged URL is available, set `stp_reference.url` so that
  stub-generator can use it in module docstrings instead of the local file path.
- **Resolution order:**
  1. Read the STP file's Metadata section for a design-docs URL
  2. If the STP metadata contains a PR URL, check if it has been merged (via
     GitHub MCP `get_pull_request`). If merged, convert the PR URL to a blob URL
     on the default branch.
  3. If a `design_docs_repo` is configured in `repositories.yaml`, construct the
     expected URL
  4. If none found, set `stp_reference.url` to null — stub-generator will fall
     back to the local file path.

2. **Call std-generator skill** with scenarios, STP context,
   `source_constants` array (from Step 1.5, may be empty), `stp_reference` (from Step 1.7), and STP file path.
   From a scenario list: the same call with `stp_reference: null`, `source_constants: []`,
   and the scenario list path in place of the STP file path.

   **Small tickets (≤15 scenarios):** Generate all scenarios in a single
   Write call (existing behavior).

   **Large tickets (>15 scenarios) — chunked generation:**

   Large STPs exceed the output token limit when generated in one pass.
   Write the STD YAML incrementally:

   a. **First chunk**: Call std-generator with scenarios 1–15. Write the
      complete file (document_metadata + common_preconditions +
      code_generation_config + scenarios 1–15) using the Write tool.
      End the file with a YAML comment on its own line:
      `# --- STD_CONTINUATION ---`

   b. **Next chunks**: For each subsequent batch of up to 15 scenarios:
      - Read the current file (input tokens — no limit)
      - Call std-generator with ONLY the new batch of scenarios
        (provide the shared metadata as read-only context, do NOT
        regenerate it)
      - Use the Edit tool to replace `# --- STD_CONTINUATION ---` with
        the new scenarios followed by `# --- STD_CONTINUATION ---`

   c. **Final chunk**: After the last batch, Edit to remove the
      `# --- STD_CONTINUATION ---` line

   Each chunk generates ≤15 scenarios (~2,500 lines), staying well under
   the output token limit. The final file is identical to single-pass output.

3. **Output file:**
   - `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`
   - Example: `outputs/PROJ-66855/std/PROJ-66855_test_description.yaml`
   - Single comprehensive file with:
     - document_metadata (shared across all scenarios)
     - common_preconditions (shared infrastructure)
     - scenarios array (one entry per STP scenario)

4. **Validate STD output:**
   - File exists
   - Valid YAML syntax
   - No leftover `# --- STD_CONTINUATION ---` markers
   - All required sections populated:
     - document_metadata
     - common_preconditions
     - scenarios array (count matches STP scenarios)
   - Each scenario has required fields:
     - test_id, tier, priority
     - test_objective, test_steps, assertions

---

### Step 3: Generate Summary Report

**Create a summary report with:**

- Total scenarios processed
- STD file generated
- Validation results
- Execution time
- Any errors or warnings

**Output format:**

```yaml
---
status: success
component: std-orchestrator
jira_id: PROJ-66855
stp_file: outputs/PROJ-66855/stp/PROJ-66855_test_plan.md
output_dir: outputs/PROJ-66855/std/

execution_summary:
  total_stp_scenarios: 12
  tier_1_scenarios: 9
  tier_2_scenarios: 3
  std_file_generated: "PROJ-66855_test_description.yaml"
  scenarios_in_std: 12
  total_duration: "2 minutes"

validation_results:
  std_file:
    file: PROJ-66855_test_description.yaml
    status: valid
    yaml_syntax: passed
    required_sections: passed
    scenarios_count: 12

errors: []
warnings: []

notes:
  - "STD YAML generated as internal format"
  - "Use /generate-tests for implementations"
---
```

---

## Output Structure

**Simple structure (STD YAML only):**

```
outputs/PROJ-66855/std/
├── PROJ-66855_test_description.yaml     (NEW - comprehensive STD for ALL scenarios)
└── std_generation_summary.yaml         (summary report)
```

**Key design:**

- **ONE comprehensive STD file** for all scenarios (not one file per scenario)
- **STD mirrors STP structure:** document_metadata + common_preconditions + scenarios array
- **No separate std/ folder** - single file at outputs/{JIRA_ID}/std/ level
- **No test stubs** - STD YAML is input for code generators
- **Downstream usage:** /generate-tests reads this STD file

---

## Skills Called

This orchestrator calls 1 specialized skill:

1. **std-generator** - Transforms STP scenarios → comprehensive STD YAML file

**Architecture:**

- STD YAML is the only output
- Code generation happens in a separate command (/generate-tests)
- Clean separation: specification (STD) vs implementation (code)

---

## Error Handling

- **If STP parsing fails:**
  - Log error: "Cannot parse Section III from STP file"
  - Suggest: Check STP format, ensure Section III exists
  - Exit with status: error

- **If the scenario list is invalid** (validate_std.py --scenarios exits 1):
  - Log error: "Scenario list is invalid" and relay every reported error
  - Exit with status: error — do not generate an STD from a malformed list

- **If std-generator fails for a scenario:**
  - Log warning: "STD generation failed for scenario {num}"
  - Continue with other scenarios
  - Mark scenario as failed in summary

- **Set overall status to:**
  - `success`: All scenarios processed successfully
  - `partial`: Some scenarios failed, but >50% succeeded
  - `error`: >50% scenarios failed or critical error

---

## Success Criteria

The orchestration is complete when:

- ✅ All scenarios extracted (STP Section III, or the scenario list)
- ✅ Comprehensive STD YAML file created
- ✅ Valid YAML syntax
- ✅ All required sections populated
- ✅ Summary report generated

**Minimum acceptable outcome:**

- At least 80% of scenarios successfully included in STD
- All P0 scenarios successfully included
- Summary report explains any failures
- STD file passes validation

---

## Validation Checklist

Before marking orchestration as complete, validate:

- [ ] STD YAML file exists
- [ ] Valid YAML syntax (can be parsed)
- [ ] document_metadata section populated
- [ ] common_preconditions section populated
- [ ] scenarios array contains all STP scenarios
- [ ] Each scenario has required fields (test_id, tier, priority, test_objective, test_steps, assertions)
- [ ] No missing or null values in critical fields
- [ ] Test IDs are unique

---

## Usage Example

**User command:**

```
Generate STD for PROJ-66855
```

**Orchestrator execution:**

```
1. Read outputs/PROJ-66855/stp/PROJ-66855_test_plan.md
2. Parse Section III → 12 scenarios found (9 Tier 1, 3 Tier 2)
3. Call std-generator ONCE → PROJ-66855_test_description.yaml
4. Validate STD YAML
5. Generate summary → std_generation_summary.yaml
6. Report to user: "✅ Generated STD YAML for 12 scenarios"
```

**Example output:**

```
✅ STD YAML Generated!

📄 Input: outputs/PROJ-66855/stp/PROJ-66855_test_plan.md

📊 Summary:
- STP scenarios: 12 (9 Tier 1, 3 Tier 2)
- STD file: PROJ-66855_test_description.yaml (internal format)

📁 Output:
- outputs/PROJ-66855/std/PROJ-66855_test_description.yaml

📌 Next steps (performed by the caller, not this skill):
- Stub generation for design review (stub-generator)
- After design approval: /generate-tests PROJ-66855
```

---

## Notes

- **Output**: Single comprehensive STD YAML file only
- **No code generation**: Use /generate-tests for code
- **Single comprehensive STD**: ONE file for ALL scenarios (mirrors STP structure)
- **STD replaces old multi-file approach**: More maintainable, less duplication
- **Clean separation**: Specification (STD) vs implementation (code generation)

---

**End of STD Orchestrator Skill**
