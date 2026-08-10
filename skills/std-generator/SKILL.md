---
name: std-generator
description: Generate comprehensive v2.1-ENHANCED STD YAML with pattern metadata, variables, test structure from ALL STP scenarios (single file)
model: claude-opus-4-6
---

# STD Generator Skill (v2.1-enhanced)

## Purpose

Transforms **all scenarios** from a Software Test Plan (STP) into **ONE comprehensive v2.1-ENHANCED** Software Test Description (STD) YAML file with:

- Shared metadata and common preconditions
- **code_generation_config** (NEW in v2.1): imports, context init, timeout mappings
- **variables section per scenario** (NEW in v2.1): closure-scoped variable declarations
- **test_structure section per scenario** (NEW in v2.1): decorator placement, SIG() wrapper
- Detailed specifications for each scenario
- **Pattern metadata** (patterns, helpers, decorators, code templates)
- **Fixed code templates** (v2.1): no variable shadowing, ExpectWithOffset, auto-generated cleanups
- **Production-ready** for code generation (compiles without errors)

**Key Features:**

- Generates ONE file for ALL scenarios (not one file per scenario)
- Automatically adds pattern metadata to all scenarios
- Infers helper libraries from matched patterns
- Generates code templates from pattern library
- Ready for downstream code generation

## Repo Rules Integration

When `project_context.repo_rules` is available, apply these rules:

**From repo_rules.std_format (SOFTWARE_TEST_DESCRIPTION.md):**

- PSE docstring format: `Preconditions:`, `Steps:`, `Expected:` (exact section names)
- `[NEGATIVE]` indicator for failure scenarios
- `Parametrize:` section with inline `[Markers: ...]` syntax
- Shared vs test-specific preconditions rules
- Assertion wording patterns (maps to assertions)
- `__test__ = False` placement: class-level for grouped tests, after function for standalone

**From repo_rules.agents_rules (AGENTS.md):**

- Test Design Workflow: STP → STD → Implementation (mandatory)
- `tier2` is implicit — do NOT emit `@pytest.mark.tier2` in STD metadata
- Team markers are implicit — do NOT emit `@pytest.mark.network`, etc.
- `pytest.skip/skipif` are forbidden
- STD stubs must have STP link in module docstring
- Name resources by function ("client VM"), not generic labels ("VM-A")
- `@pytest.mark.incremental` for dependent tests, not `pytest-dependency`

**From repo_rules.testing_tiers (testing-tiers.md):**

- Tier definitions for classification validation:
  - Tier 1: operator/infrastructure tests, single feature verification
  - Tier 2: customer use case tests, complete user workflows
  - Tier 3: complex/hardware/platform-specific/time-consuming tests
- Use these definitions when classifying scenarios in the STD

These rules affect the `classification`, `test_structure`, and PSE docstring generation
within each scenario in the STD YAML.

## Input Required

- `scenarios`: Array of ALL scenario rows from STP Section III
  - Each scenario has:
    - `scenario_id`: Scenario number (e.g., 1, 2, 3)
    - `tier`: Tier classification (e.g., "Tier 1", "Tier 2")
    - `priority`: Priority (e.g., "P0", "P1", "P2")
    - `description`: Scenario description text
    - `requirement_id`: Requirement ID (e.g., "PROJ-59657")
- `stp_context`: Context from the STP document
  - `jira_issue`: Jira ticket ID and metadata
  - `feature_description`: Feature overview (from Feature Overview section)
  - `related_prs`: List of GitHub PRs (from Metadata)
  - `api_endpoints`: API endpoints (from Section I.3 API Extensions, if applicable)
  - `known_limitations`: Known limitations (from Section I.2)
  - `test_environment`: Test environment requirements (from Section II.3)
- `source_constants` (optional): Array of literal constants extracted from source code by the STP Builder
  - Each constant has:
    - `name`: Constant identifier (e.g., "SENTINEL", "SCRIPT_PATH")
    - `value`: Exact value from source code (verbatim, never paraphrased)
    - `source_file`: File where the constant was found
    - `line`: Line number (or `—` for PR-derived paths)
  - Example:

    ```yaml
    source_constants:
      - name: "SENTINEL"
        value: "# --- managed section - do not edit ---"
        source_file: "pkg/scripts/sync.sh"
        line: 14
    ```

- `stp_file_path`: Path to source STP file (e.g., `outputs/stp/PROJ-66855/PROJ-66855_test_plan.md`)

## Output

**Single comprehensive STD YAML file:**

- Filename: `{JIRA_ID}_test_description.yaml`
- Example: `PROJ-66855_test_description.yaml`
- Location: `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`
- Size: Variable (~100-200 lines per scenario + 100 lines shared metadata)
- Format: Valid YAML with document metadata + scenarios array

**Structure:**

```yaml
---
# Document Metadata (shared)
document_metadata: {...}
common_preconditions: {...}

# Scenarios Array (one entry per STP scenario)
scenarios:
  - scenario_001: {...}
  - scenario_002: {...}
  - scenario_003: {...}
  ...
---
```

---

## Template Resolution

When generating an STD, read templates from `{project_context.config_dir}/templates/std/`
if available (provides project-specific values for infrastructure, operators, tools, etc.).
Fall back to the generic skeleton templates in this skill's `templates/` directory when
`config_dir` is null (auto-discovery mode).

---

## STD Structure (2 Main Sections + Scenarios Array)

### Section 1: document_metadata

**Purpose:** Shared metadata for the entire test suite

**Required fields:**

```yaml
document_metadata:
  std_version: "2.1-enhanced"
  generated_date: "YYYY-MM-DD"
  jira_issue: "{JIRA_ID}"
  jira_summary: "{Jira issue summary}"
  source_bugs: ["{PROJ-XXXXX}", ...]  # If applicable
  stp_reference:
    file: "outputs/stp/{JIRA_ID}/{JIRA_ID}_test_plan.md"
    version: "v1"
    sections_covered: "Section III - Requirements-to-Tests Mapping"

  # related_prs is internal metadata for code generation context.
  # It MUST NOT be propagated to Phase 1 stub module docstrings.
  # Stub docstrings contain only STP Reference and Jira ID.
  related_prs:
    - repo: "{org/repo}"
      pr_number: {number}
      url: "{PR_URL}"
      title: "{PR title}"
      merged: true

  owning_sig: "{sig-name}"
  participating_sigs: ["{sig-1}", "{sig-2}"]

  total_scenarios: {count}
  tier_counts:                    # tier mode only (empty in auto mode)
    "Tier 1": {count}
    "Tier 2": {count}
    # additional tiers as defined by project's tier*.yaml configs
  unit_count: {count}             # auto mode only (0 in tier mode)
  functional_count: {count}       # auto mode only (0 in tier mode)
  e2e_count: {count}              # auto mode only (0 in tier mode)
  p0_count: {count}
  p1_count: {count}
  existing_coverage_count: {count}  # scenarios with EXISTING_COVERAGE status
  new_count: {count}                # scenarios with NEW status
  test_strategy_mode: "tier|auto"
```

**Derivation:**

- Extract from STP metadata table (Section I)
- Count scenarios by tier/type and priority
- Count scenarios by coverage_status
- List all related PRs from STP Section II.4

---

### Section 1.5: code_generation_config (NEW IN v2.1)

**Purpose:** Code generation configuration for downstream test file generation

**Mode-dependent population:**

#### Tier mode (`test_strategy: "tier"`)

Read from `{project_context.config_dir}/code_generation_config.yaml`. This file
contains all project-specific values: framework, imports, context init, timeout
constants, helper library mappings, and inference rules.

#### Auto mode (`test_strategy: "auto"` or `config_dir: null`)

Populate from `test_strategy` output (from test-strategy-resolver skill):

```yaml
code_generation_config:
  std_version: "2.1-enhanced"
  framework: "{test_strategy.framework}"           # e.g., "testing"
  assertion_library: "{test_strategy.assertion_library}"  # e.g., "testify"
  language: "{test_strategy.language}"              # e.g., "go"
  package_name: "{test_strategy.package_name}"      # e.g., "cli"

  # Co-located test placement
  target_test_directory: "{resolved_directory}"     # e.g., "internal/cli"
  filename_prefix: "qf_"                            # prefix for generated test files

  imports:
    standard: "{test_strategy.imports.standard}"
    framework: "{test_strategy.imports.framework}"
    project: "{test_strategy.imports.project}"

  # Omit project-specific fields in auto mode:
  # context_init, dot_imports, project-specific import groups,
  # timeout_constants, helper_library_imports
```

**Resolving `target_test_directory` (auto mode):**

1. From the PR diff `changed_files`, identify ALL package directories
   where production code was modified (e.g., `internal/cli/run.go` → `internal/cli`)
2. Verify each directory contains existing `_test.go` files (confirming
   tests belong there)
3. If a single directory dominates the changes, use it as the primary value
4. If multiple directories changed, set `target_test_directory` to the
   primary directory AND add a `target_test_directories` list field:

   ```yaml
   target_test_directory: "internal/cli"          # primary (most changes)
   target_test_directories:                        # all candidate packages
     - "internal/cli"
     - "internal/forge/github"
     - "internal/harness"
   ```

5. If no `.go` files changed (e.g., only shell scripts or docs), derive
   from `imports.project` entries — translate each import path to a
   filesystem path relative to the module root (e.g.,
   `github.com/org/repo/internal/cli` → `internal/cli`)
6. **Never set to `null`.** If nothing resolves from changed files or
   imports, scan test scenarios for referenced functions/types and resolve
   their packages. As a last resort, use the module root directory.

The test generator uses `target_test_directories` (plural) when available
to distribute tests per-scenario to the correct package. When only
`target_test_directory` (singular) is set, it still resolves per-scenario
placement from each scenario's referenced imports.

Skip project-specific fields (context_init, dot_imports, project-specific import
groups, timeout constants, helper_library_imports) when in auto mode. These are
project-specific and have no meaning for auto-detected projects.

#### Tier mode — code_generation_config schema

In tier mode, the `code_generation_config` section is populated from
`{project_context.config_dir}/code_generation_config.yaml`. The file provides:

```yaml
code_generation_config:
  std_version: "2.1-enhanced"
  framework: "{from config}"              # e.g., "ginkgo-v2"
  assertion_library: "{from config}"      # e.g., "gomega"
  language: "{from config}"               # e.g., "go"
  package_name: "{INFER_FROM_SIG}"        # resolved via config package_name_rules

  target_test_directory: "{INFER_FROM_SIG_AND_COMPONENT}"
  filename_prefix: "qf_"

  context_init: [...]                     # from config
  imports:                                # from config (groups vary per project)
    dot_imports: [...]
    standard: [...]
    # Additional project-specific import groups from config

  timeout_constants: {...}                # from config
  helper_library_imports: {...}           # from config
```

**Derivation:**

- **package_name**: Infer from `owning_sig` using `package_name_rules` in config
- **target_test_directory** (tier mode): Resolve from `components.yaml`
  `component_package_map` if available, or derive from `owning_sig` using
  `target_test_directory_rules` in config
  - If `config_dir` has `repositories.yaml` with a `test_directory` field, use that
  - Never set to `null` — use `owning_sig` default as last resort
- **filename_prefix**: Always `"qf_"` (from `_defaults.yaml` `test_file_prefix`)
- All other fields are read directly from the project's `code_generation_config.yaml`

---

### Section 2: common_preconditions

**Purpose:** Infrastructure and environment requirements shared by ALL scenarios

**Required fields:**

```yaml
common_preconditions:
  infrastructure:
    - name: "{Platform name}"
      requirement: "{Platform version from project config}"
      validation: "{Platform validation command}"

    - name: "{Product name}"
      requirement: "{Product version from project config}"
      validation: "{Product validation command}"

    - name: "{Additional infrastructure}"
      requirement: "{From STP Section II.5}"
      validation: "{Validation command}"

  operators:
    - name: "{Operator name}"
      namespace: "{namespace}"
      validation: "{cli_tool get resource command}"

  cluster_configuration:
    topology: "{Single-node|Multi-node}"
    cpu_virtualization: "{Standard|Nested}"
    storage: "{StorageClass requirement}"
    network: "{CNI requirement}"

  rbac_requirements:
    - permission: "{verb} on {resource}"
      scope: "{Cluster|Namespace: {namespace}}"
      validation: "{cli_tool} auth can-i {verb} {resource}"
```

**Derivation:**

- Extract from STP Section II.5 (Test Environment)
- Extract from STP Section I.2 (Technology and Design Review)
- Infer RBAC from feature type (API operations, resource management)

---

### Section 3: scenarios

**Purpose:** Array of detailed scenario specifications

**Structure:** One entry per STP scenario

**Required fields for each scenario:**

```yaml
scenarios:
  - scenario_id: "{NUM}"
    test_id: "TS-{JIRA_ID}-{NUM:03d}"
    tier: "{from tier-classifier}"       # tier mode — matches project's tier*.yaml configs
    test_type: "{unit|functional|e2e}"  # auto mode (use instead of tier)
    priority: "{P0|P1|P2}"
    mvp: {true|false}
    requirement_id: "{REQUIREMENT_ID}"

    # ===== COVERAGE STATUS (from STP deduplication) =====
    coverage_status: "{NEW|PARTIAL_COVERAGE|EXISTING_COVERAGE}"  # optional, defaults to NEW
    covered_by:                           # present only for EXISTING_COVERAGE or PARTIAL_COVERAGE
      - test_function: "{existing test function name}"
        test_file: "{path to existing test file}"
        behavior_tested: "{brief description}"

    # For EXISTING_COVERAGE scenarios: only include scenario_id, test_id,
    # requirement_id, coverage_status, and covered_by. Skip all sections
    # below (patterns, variables, test_structure, test_steps, assertions).

    # ===== PATTERN METADATA (AUTO-GENERATED, tier mode only) =====
    patterns:
      primary: "{matched_primary_pattern}"
      secondary:
        - "{matched_setup_pattern_1}"
        - "{matched_setup_pattern_2}"
        - "{matched_execution_pattern_1}"
      helpers_required:
        - name: "{helper_library_name}"
          functions: ["{function1}", "{function2}"]
          purpose: "{what_it_does}"
      decorators:
        - "{decorator_1}"
        - "{decorator_2}"

    # ===== VARIABLE DECLARATIONS (AUTO-GENERATED in v2.1) =====
    variables:
      closure_scope:
        - name: "{variable_name}"
          type: "{Go_type}"
          initialized_in: "{BeforeAll|It}"
          used_in: ["{BeforeAll}", "{It}", "{AfterEach}"]
          comment: "{Brief description}"
    # =========================================================

    # ===== TEST STRUCTURE (AUTO-GENERATED in v2.1) =====
    test_structure:
      type: "{single|table-driven}"

      describe:
        wrapper: "SIG"
        description: "{Feature description}"
        decorators:
          - "{SIG_decorator}"
          - "Serial"

      context:
        description: "{Scenario description}"
        decorators:
          - "Ordered"
          - "decorators.OncePerOrderedCleanup"

      it:
        description: "should {test_objective}"
        test_id_format: "[test_id:{test_id}]"
    # ===================================================

    code_structure: |
      Context("{scenario_description}", Ordered) {
        BeforeAll(func() {
          // Setup
        })
        It("[test_id:{test_id}]should {test_objective}", func() {
          // Test
        })
      }
    # =============================================

    test_objective:
      title: "{scenario.description}"
      what: |
        {Expand scenario description into 2-3 sentences explaining:
         - What functionality is being tested
         - What specific aspect/behavior is validated
         - What operations are performed}

      why: |
        {Explain business/technical rationale:
         - Why this test is important
         - What user need it addresses
         - What could break if this fails}

      acceptance_criteria:
        - "{Criterion 1: clear, measurable condition}"
        - "{Criterion 2: ...}"

    classification:
      test_type: "{Functional|Integration|E2E}"
      scope: "{Single-component|Multi-component}"
      automation_approach: "{from project config or auto-detected}"

    specific_preconditions:
      # Scenario-specific requirements (beyond common_preconditions)
      - name: "{Specific requirement}"
        requirement: "{Details}"
        validation: "{Command}"

    test_data:
      # YAML definitions for this specific scenario
      resource_definitions:
        - name: "{resource_name}"
          type: "{ResourceType — from project's API types}"
          yaml: |
            {Complete YAML definition}

      api_endpoints:
        # If applicable
        - operation: "{operation_name}"
          method: "{GET|POST|PUT|DELETE}"
          path: "{API path}"
          expected_status: {200|201|etc}

    test_steps:
      setup:
        - step_id: "SETUP-01"
          action: "{Setup action}"
          command: "{Command or API call}"
          validation: "{Expected result}"
          pattern_id: "{matched_pattern}"        # AUTO-ADDED
          code_template: |                       # AUTO-ADDED
            {code from pattern library}

      test_execution:
        - step_id: "TEST-01"
          action: "{Test action}"
          command: "{Command or API call}"
          validation: "{Expected result}"
          pattern_id: "{matched_pattern}"        # AUTO-ADDED
          code_template: |                       # AUTO-ADDED
            {code from pattern library}

      cleanup:
        - step_id: "CLEANUP-01"
          action: "{Cleanup action}"
          command: "{Command}"

    assertions:
      - assertion_id: "ASSERT-01"
        priority: "P0"
        description: "{What is being validated}"
        condition: "{Expected condition}"
        failure_impact: "{What failure means}"

    dependencies:
      kubernetes_resources:
        - "{Resource type}: {name}"

      external_tools:
        - "{Tool name} {version}+"

      scenario_specific_rbac:
        - "{permission description}"

```

**Derivation:**

- `test_objective.title`: Use scenario.description verbatim
- `test_objective.what`: Expand description with specifics
- `test_objective.why`: Infer from STP Section I.1 (Requirement Review)
- `acceptance_criteria`: Extract from scenario description and STP acceptance criteria
- `classification`: Infer from tier and scenario complexity
- `specific_preconditions`: Add scenario-specific requirements (e.g., external router for networking tests)
- `test_data`: Generate realistic YAML for VMs, pods, networks based on scenario
  - **CRITICAL — Source Constants Rule:** When `source_constants` are provided in the input,
    use them **verbatim** for any matching test_data fields. Specifically:
    - Sentinel/marker strings: use the exact `value` from source_constants, never infer or paraphrase
    - File paths: use the exact path from source_constants, never construct paths from description text
    - Template content: if a source constant provides template text, embed it as-is
    - If a test scenario references a concept that matches a source constant by name (e.g., "sentinel",
      "marker", "script path"), the STD MUST use the source_constants value — not an LLM-inferred value
    - If no source_constants are provided, derive test_data from scenario descriptions as before (best-effort)
- `test_steps`: Expand scenario into 5-10 detailed steps (setup → execute → cleanup)
- `assertions`: Extract validation points from scenario description (2-5 per scenario)
- `dependencies`: List K8s resources, tools, and RBAC specific to this scenario

---

## PATTERN ENHANCEMENT (AUTO-GENERATION)

**Mode gate:** Pattern enhancement applies in **tier mode only** (`test_strategy: "tier"`).
In **auto mode**, skip this entire section — auto-detected projects do not have pattern
libraries, decorators, or project-specific helpers. Auto-mode scenarios use a simpler
structure: `test_objective`, `test_steps`, `assertions`, and reference `code_generation_config`.

**CRITICAL (tier mode only):** All scenarios MUST include pattern metadata for production-ready STD.

**Auto-discovery guard:** If `project_context.config_dir` is null, skip this entire
Pattern Enhancement section. Auto-mode scenarios use `code_generation_config` from the
STD YAML metadata instead of pattern libraries.

For each scenario, analyze the description and automatically add pattern metadata using the rules below.

### Pattern Matching Rules

**Requires:** `project_context.config_dir` is not null.

Apply these rules to match scenarios to patterns from `{project_context.config_dir}/patterns/` directory:

#### 1. Keywords → Primary Pattern

Analyze the scenario description for these keywords:

- Contains **"connectivity"**, **"ping"**, **"reach"** → `network-connectivity-001`
- Contains **"migration"**, **"migrate"** → `migration-001`
- Contains **"hotplug"**, **"attach"** → `network-hotplug-001`
- Contains **"lifecycle"**, **"create"**, **"delete"** → `vm-lifecycle-001`
- Contains **"console"**, **"login"**, **"SSH"** → `console-001`
- Contains **"snapshot"**, **"restore"** → `snapshot-001`
- Contains **"clone"**, **"copy"** → `clone-001`

#### 2. Resources → Setup Patterns

Identify required resources and add setup patterns:

- Resource type mentions → Add corresponding `factory-*` pattern from pattern library
- **Any resource creation** → Also add appropriate `wait-*` pattern (wait for resource ready)

#### 3. Actions → Execution Patterns

Identify test actions and add execution patterns:

- Action: **"ping"**, **"connectivity test"** → Add `network-ping-001`
- Action: **"migrate"** → Add `migration-execute-001`
- Action: **"console"**, **"login"** → Add `console-001`
- Action: **"hotplug"**, **"attach"** → Add `network-hotplug-execute-001`

#### 4. Infer Helpers from Patterns

Based on matched patterns, automatically infer required helper libraries:

**Pattern → Helper Mapping:**
Read from `{project_context.config_dir}/code_generation_config.yaml` `helper_library_imports` section.
Each pattern maps to one or more helper libraries defined in the project config.

**Helper Library Functions:**
Read from `{project_context.config_dir}/code_generation_config.yaml` `helper_functions` section.
The project config defines available helper functions, their signatures, and return types.

#### 5. Add Decorators

Add test decorators based on tier and domain:

**Tier-based:**

- Tier 1 → `decorators.Tier1`
- Tier 2 → `decorators.Tier2`

**Domain-based (from scenario description):**

- Network-related → `decorators.SigNetwork`
- Migration-related → `decorators.SigCompute`
- Storage-related → `decorators.SigStorage`
- Compute-related → `decorators.SigCompute`

**Always add:**

- `Ordered` (for proper test execution order)
- `decorators.OncePerOrderedCleanup` (for cleanup after ordered tests)

#### 6. Generate Code Templates

For each matched pattern:

1. **Read pattern definition** from `{project_context.config_dir}/patterns/tier1_patterns.yaml`
2. **Extract the `template` field** for that pattern
3. **Add as `code_template`** to the corresponding test step
4. **Add `pattern_id`** to link step to pattern

**Example:**

```yaml
test_steps:
  setup:
    - step_id: "SETUP-01"
      action: "Create resource instance"
      pattern_id: "factory-001"           # Added
      code_template: |                    # Added from pattern library
        resource := factory.NewDefault(
            builder.WithInterface(iface),
            builder.WithNetwork(network),
        )
```

#### 7. Generate Code Structure

For each scenario, generate a Ginkgo test structure hint:

```go
Context("{scenario_description}", Ordered) {
  BeforeAll(func() {
    // Setup from test_steps.setup
  })
  It("[test_id:{test_id}]should {test_objective}", func() {
    // Test execution from test_steps.test_execution
  })
}
```

Replace placeholders:

- `{scenario_description}`: Brief description of scenario
- `{test_id}`: The test_id field (e.g., TS-PROJ12345-001)
- `{test_objective}`: The test_objective.title field

---

### Pattern Library Reference

**Location**: `{project_context.config_dir}/patterns/tier1_patterns.yaml`

**Available Patterns:**

- `network-connectivity-001` - Network connectivity tests
- `factory-001` - Resource creation with factory
- `wait-002` - Wait for resource ready
- `console-001` - Console login
- `migration-001` - Live migration
- `network-def-001` - Network definition creation
- `factory-pod-001` - Pod creation
- `table-001` - Table-driven tests
- `network-hotplug-001` - Network interface hotplug
- `snapshot-001` - Snapshot operations
- `clone-001` - Cloning operations

Each pattern provides:

- **keywords**: Trigger words for matching
- **resources**: Applicable K8s resources
- **actions**: Test actions
- **helpers**: Required helper libraries
- **template**: Ready-to-use code template

---

### Pattern Enhancement Validation

Before generating the STD file, validate pattern metadata:

- [ ] All scenarios have `patterns.primary` field
- [ ] All scenarios have `patterns.helpers_required` array
- [ ] All scenarios have `patterns.decorators` array
- [ ] All scenarios have `code_structure` field
- [ ] All test steps have `pattern_id` where applicable
- [ ] All test steps have `code_template` where applicable
- [ ] Pattern IDs reference actual patterns in `{project_context.config_dir}/patterns/`

---

## LLM Prompt for Comprehensive STD Generation

**System Prompt:**

```
You are an expert QE engineer generating a comprehensive Software Test Description (STD) from a Software Test Plan (STP).

Your task:
1. Read ALL scenarios from the STP Section III (Requirements-to-Tests Mapping table)
2. Extract shared metadata from STP Sections I and II
3. Generate ONE comprehensive STD YAML file with:
   - document_metadata (shared across all scenarios)
   - common_preconditions (shared infrastructure/environment)
   - scenarios array (detailed spec for each scenario)

Guidelines:
- Generate ONE file for ALL scenarios (not one file per scenario)
- Extract common preconditions to avoid duplication
- Be specific and detailed in scenario specifications
- Use realistic patterns from the project's pattern library
- Include complete YAML definitions for test resources
- Link scenarios to requirements (Jira, GitHub PRs)
- Prioritize assertions (P0 = critical, P1 = nice to have)

CRITICAL - Pattern Enhancement (AUTO-GENERATED):
- For EACH scenario, analyze the description and automatically add pattern metadata
- Apply pattern matching rules (keywords → patterns, resources → setup patterns, etc.)
- Infer helper libraries from matched patterns
- Add decorators based on tier and domain
- Generate code templates from pattern library (`{project_context.config_dir}/patterns/tier1_patterns.yaml`)
- Add code_structure hint for each scenario
- Add pattern_id and code_template to each test step
- This is NOT optional - ALL scenarios MUST have pattern metadata

Output only valid YAML. Do not include explanations outside the YAML structure.

CHUNKED GENERATION (when called with a batch, not all scenarios):
- The orchestrator may call you multiple times with batches of ~15 scenarios
- First call: generate document_metadata + common_preconditions + code_generation_config + the batch of scenarios
- Subsequent calls: generate ONLY the new batch of scenarios (YAML array items indented under `scenarios:`)
- Do NOT regenerate metadata or common_preconditions on subsequent calls
- Each batch output must be valid YAML fragments that can be appended to the scenarios array
```

**User Prompt Template:**

```
Generate a comprehensive Software Test Description (STD) YAML file for ALL scenarios in the following STP:

STP FILE: {stp_file_path}

DOCUMENT METADATA:
  Jira Issue: {jira_id} - {jira_summary}
  Source Bugs: {source_bugs}
  Related PRs: {related_prs}
  Owning SIG: {owning_sig}
  Total Scenarios: {total_scenarios}

STP CONTEXT:
  Feature Description: {feature_description}
  Non-Goals: {non_goals}
  Test Environment: {test_environment}
  Fix Versions: {fix_versions}

SOURCE CONSTANTS (from STP Section III.2, if present):
{source_constants_array}
NOTE: These values were extracted from actual source code by the STP Builder.
Use them VERBATIM in test_data fields. Do not infer, paraphrase, or modify.

ALL SCENARIOS (from STP Section III.1):
{scenarios_array}

Generate ONE comprehensive STD YAML file with:
1. document_metadata (shared metadata for entire test suite)
2. common_preconditions (shared infrastructure/environment requirements)
3. scenarios (array with detailed spec for each scenario)

Output filename: {JIRA_ID}_test_description.yaml
Output only valid YAML.
```

---

## Final Validation Checklist

Before outputting the STD YAML, validate ALL of the following:

**Base STD Structure:**

- [ ] Valid YAML syntax (parse with YAML parser)
- [ ] document_metadata section complete
- [ ] document_metadata.std_version is "2.1-enhanced"
- [ ] common_preconditions section complete
- [ ] scenarios array has entries for ALL STP scenarios
- [ ] Each scenario has required fields:
  - [ ] scenario_id, test_id, tier, priority
  - [ ] test_objective (title, what, why, acceptance_criteria)
  - [ ] test_steps (setup, test_execution, cleanup)
  - [ ] assertions (at least 1 per scenario)
- [ ] No "TODO" or placeholder values
- [ ] All scenario test_ids follow format: TS-{JIRA_ID}-{NUM:03d}

**Pattern Enhancement:**

- [ ] ALL scenarios have `patterns` section with `primary` field
- [ ] ALL scenarios have `patterns.helpers_required` array
- [ ] ALL scenarios have `patterns.decorators` array
- [ ] ALL scenarios have `code_structure` field
- [ ] ALL test steps have `pattern_id` where applicable
- [ ] ALL test steps have `code_template` where applicable
- [ ] Pattern IDs match patterns in `{project_context.config_dir}/patterns/tier1_patterns.yaml`

**v2.1 Enhancement:**

- [ ] `code_generation_config` section exists at document level
- [ ] `code_generation_config.std_version` is "2.1-enhanced"
- [ ] `code_generation_config.package_name` is inferred from owning_sig
- [ ] ALL scenarios have `variables` section
- [ ] ALL scenarios have `test_structure` section
- [ ] ALL `variables.closure_scope` includes at minimum: ctx, namespace, err
- [ ] ALL `test_structure.context.decorators` includes: Ordered, decorators.OncePerOrderedCleanup
- [ ] ALL code_templates use `=` (not `:=`) for closure variables
- [ ] ALL `Expect(err)` calls use `ExpectWithOffset(1, err)`
- [ ] ALL scenarios with setup steps have corresponding cleanup templates

**Source Constants Compliance (when source_constants provided):**

- [ ] ALL sentinel/marker strings in test_data match source_constants values exactly
- [ ] ALL file paths in test_data match source_constants paths exactly
- [ ] No test_data field contains an LLM-inferred value when a matching source_constant exists
- [ ] Source constants are referenced with their original name in a `source_constant_ref` field

**If ANY validation fails:**

- Log error with scenario_id and specific failure
- Do NOT output incomplete STD
- Return error report to user

---

## Success Criteria

STD generation is successful when:

- ✅ Valid YAML file created
- ✅ All 3 main sections populated (document_metadata, common_preconditions, scenarios)
- ✅ Scenarios array has {total_scenarios} entries
- ✅ No duplicate scenario IDs
- ✅ File size appropriate (~150 lines per scenario + 100 lines metadata)
- ✅ Traceability complete (Jira, PRs, STP reference)

---

## Error Handling

- **If scenario description is vague:**
  - Log warning: "Scenario {num} lacks detail - generating best-effort spec"
  - Generate spec with inferred details
  - Mark for human review in validation report

- **If STP context is incomplete:**
  - Use defaults (e.g., if no PRs → empty related_prs array)
  - Generate STD with available information
  - Log warning about missing context

- **If YAML generation fails:**
  - Return error message with LLM output
  - Suggest manual review and correction
  - Provide partial output if possible

---

## Output Location

**Primary output:**

- `outputs/std/{JIRA_ID}/{JIRA_ID}_test_description.yaml`

**Example:**

- `outputs/std/PROJ-66855/PROJ-66855_test_description.yaml`

**Note:** This comprehensive STD YAML is the single source of truth for all test scenarios. It is used by downstream generators (stub-generator, test-generator) to produce test stubs and working test code.

---

## Usage Example

See `supplemental.md` (in this skill directory) for detailed input/output examples.

---

## v2.1 Enhancements

v2.1 adds auto-generated `code_generation_config`, `variables`, and `test_structure` sections,
plus code template transformations (variable shadowing fixes, ExpectWithOffset, auto-cleanup).

For detailed algorithms, inference rules, transformation pseudocode, and the v2.1 changelog,
see `supplemental.md` (in this skill directory).

---

**End of STD Generator Skill**
