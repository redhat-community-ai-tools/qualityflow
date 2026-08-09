---
name: std-orchestrator
description: Orchestrate STP → STD pipeline (generates comprehensive STD YAML only)
model: claude-opus-4-6
phase_support: true
default_phase: phase1
---

# STD Orchestrator Skill

## Purpose

Coordinates the Software Test Description (STD) generation workflow by:

1. Parsing STP Section III to extract test scenarios
2. Generating comprehensive STD YAML file for ALL scenarios (internal format)
3. **Routing to code generators with appropriate phase**
4. Validating output and generating summary report

**Output:**

- STD YAML file (internal format for automation)
- **Test stubs with PSE docstrings** (the actual deliverable per SOFTWARE_TEST_DESCRIPTION.md)

---

## Input Required

- `stp_file_path`: Path to the STP markdown file (e.g., `outputs/stp/PROJ-66855/PROJ-66855_test_plan.md`)
- `jira_id`: The Jira ticket ID (e.g., "PROJ-66855")
- `output_dir`: Base directory for outputs (defaults to `outputs/std/{JIRA_ID}/`)
- `phase`: `phase1` (default) or `phase2`

---

## Phase Parameter

**Phase 1 (default):**

- Generate STD YAML (internal format)
- Call code generators with `phase=phase1`
- Output: Test stubs with PSE docstrings + `pass` body
- Tests excluded from collection (`__test__ = False` for Python, `PendingIt()` for Go)

**Phase 2:**

- Generate STD YAML (internal format)
- Call code generators with `phase=phase2`
- Output: Full working test implementations

---

## Workflow

Execute the following steps in order:

---

### Step 1: Parse STP Section III

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

### Step 2: Generate Comprehensive STD YAML (Single File)

**Generate ONE comprehensive STD file for ALL scenarios:**

1. **Extract STP context** (needed by std-generator):
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

2. **Call std-generator skill** with scenarios, STP context,
   `source_constants` array (from Step 1.5, may be empty), and STP file path.

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
   - `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`
   - Example: `outputs/std/PROJ-66855/PROJ-66855_test_description.yaml`
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

### Step 2.5: Route to Code Generators (Based on Phase + Strategy)

**After STD YAML is validated, call appropriate code generators.**

**Routing depends on `test_strategy_mode` in the STD YAML `document_metadata`:**

#### Tier mode routing

1. Detect tier split in STD (Tier 1 count, Tier 2 count)
2. Call the unified **stub-generator** (phase1) or **test-generator** (phase2)
   - The generator reads project config to determine all enabled languages
   - Output: Test stubs or implementations for all configured languages

#### Auto mode routing

1. Read `code_generation_config.language` from STD YAML
2. Route to the unified generator based on detected language:

| Language | Generator | Output |
|:---------|:----------|:-------|
| `go` | stub-generator / test-generator | Go test stubs/implementations |
| `python` | stub-generator / test-generator | Python test stubs/implementations |

3. Generate for ALL scenarios with `coverage_status: NEW` or `PARTIAL_COVERAGE`
4. Skip `EXISTING_COVERAGE` scenarios
5. Pass `code_generation_config` so the generator uses detected framework conventions

**Output files:**

```
outputs/std/{JIRA_ID}/
├── go-tests/           (if language is Go, or Tier 1 in tier mode)
│   └── *_stubs_test.go (Phase 1: stubs, Phase 2: implementation)
└── python-tests/       (if language is Python, or Tier 2 in tier mode)
    └── test_*_stubs.py (Phase 1: stubs, Phase 2: implementation)
```

---

### Step 3: Generate Summary Report

**Create a summary report with:**

- Total scenarios processed
- STD file generated
- **Phase indicator** (Phase 1 stubs or Phase 2 implementation)
- **Code files generated** (Go and/or Python)
- Validation results
- Execution time
- Any errors or warnings

**Output format:**

```yaml
---
status: success
component: std-orchestrator
jira_id: PROJ-66855
phase: phase1  # or phase2
stp_file: outputs/stp/PROJ-66855/PROJ-66855_test_plan.md
output_dir: outputs/std/PROJ-66855/

execution_summary:
  total_stp_scenarios: 12
  tier_1_scenarios: 9
  tier_2_scenarios: 3
  std_file_generated: "PROJ-66855_test_description.yaml"
  scenarios_in_std: 12
  total_duration: "2 minutes"

code_generation:
  phase: phase1
  go_tests:
    file_count: 2
    test_count: 9
    status: "stubs_generated"  # or "implementation_generated" for phase2
  python_tests:
    file_count: 1
    test_count: 3
    status: "stubs_generated"

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
outputs/std/PROJ-66855/
├── PROJ-66855_test_description.yaml     (NEW - comprehensive STD for ALL scenarios)
└── std_generation_summary.yaml         (summary report)
```

**Key design:**

- **ONE comprehensive STD file** for all scenarios (not one file per scenario)
- **STD mirrors STP structure:** document_metadata + common_preconditions + scenarios array
- **No separate std/ folder** - single file at outputs/std/{JIRA_ID}/ level
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

- ✅ All scenarios from STP Section III extracted
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

**User command (Phase 1 - default):**

```
Generate STD/PSE/Code for PROJ-66855
```

**Orchestrator execution (Phase 1):**

```
1. Read outputs/stp/PROJ-66855/PROJ-66855_test_plan.md
2. Parse Section III → 12 scenarios found (9 Tier 1, 3 Tier 2)
3. Call std-generator ONCE → PROJ-66855_test_description.yaml
4. Validate STD YAML
5. Call stub-generator → 9 Go stubs + 3 Python stubs
7. Generate summary → std_generation_summary.yaml
8. Report to user: "✅ Generated Phase 1 test stubs for 12 scenarios"
```

**Example output (Phase 1):**

```
✅ Phase 1 Test Stubs Generated!

📄 Input: outputs/stp/PROJ-66855/PROJ-66855_test_plan.md

📊 Summary:
- STP scenarios: 12 (9 Tier 1, 3 Tier 2)
- STD file: PROJ-66855_test_description.yaml (internal format)
- Phase: 1 (Design stubs with PSE docstrings)

📁 Output:
- outputs/std/PROJ-66855/PROJ-66855_test_description.yaml
- outputs/std/PROJ-66855/go-tests/ (9 test stubs with PSE comments)
- outputs/std/PROJ-66855/python-tests/ (3 test stubs with PSE docstrings)

📋 Phase 1 Checklist:
- [ ] STP link in module docstring
- [ ] Tests grouped in class with shared preconditions
- [ ] Each test has: Preconditions, Steps, Expected
- [ ] Each test verifies ONE thing with ONE Expected
- [ ] Test bodies contain only 'pass'

✅ Ready for design review!

📌 Next steps:
1. Review the test stubs
2. Submit PR for design review
3. After approval, run:
   - /generate-tests PROJ-66855         (test implementations)
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
