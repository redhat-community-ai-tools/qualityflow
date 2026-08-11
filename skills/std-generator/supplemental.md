# STD Generator - Supplemental Reference

This file contains examples, detailed algorithms, v2.1 enhancement specifications,
and changelog information for the std-generator skill. The core workflow and rules
are in `SKILL.md`.

---

## Usage Example

**Input:**

```yaml
jira_id: "PROJ-66855"
scenarios:
  - scenario_id: 1
    tier: "Tier 1"
    priority: "P0"
    description: "Default network pod can reach localnet VM on same node (different-subnet)"
    requirement_id: "PROJ-59657"

  - scenario_id: 2
    tier: "Tier 1"
    priority: "P0"
    description: "Default network pod can reach localnet VM on different nodes (baseline)"
    requirement_id: "PROJ-59657"

  # ... (13 more scenarios)

stp_context:
  feature_description: "OVN-Kubernetes localnet same-node connectivity fix"
  related_prs: ["ovn-org/ovn-kubernetes#5480", ...]
  test_environment: "Multi-node cluster with OVN-K, NMState, external router"
```

**Output:**

```
outputs/PROJ-66855/std/PROJ-66855_test_description.yaml

Contents:
---
document_metadata:
  std_version: "2.1-enhanced"
  jira_issue: "PROJ-66855"
  total_scenarios: 15
  tier_1_count: 10
  tier_2_count: 5
  ...

common_preconditions:
  infrastructure:
    - name: "Platform cluster"
      requirement: "Platform version with required CNI"
    - name: "External router container"
      requirement: "VLAN support (eth0 + eth0.100)"
  ...

scenarios:
  - scenario_id: "1"
    test_id: "TS-PROJ66855-001"
    tier: "Tier 1"
    priority: "P0"
    test_objective:
      title: "Default network pod can reach localnet VM on same node (different-subnet)"
      what: |
        This test validates that a pod on the default network can successfully
        communicate with a VM attached to a localnet network when both are
        scheduled on the same node, even when they are in different subnets.
      ...
    test_steps:
      setup:
        - step_id: "SETUP-01"
          action: "Create external router container with VLAN interface"
        ...
      test_execution:
        - step_id: "TEST-01"
          action: "Ping localnet VM from default network pod"
        ...
    assertions:
      - assertion_id: "ASSERT-01"
        description: "Ping succeeds with 0% packet loss"
        ...

  - scenario_id: "2"
    test_id: "TS-PROJ66855-002"
    ...

  # ... (13 more scenario entries)
---
```

---

## v2.1 ENHANCEMENTS (AUTO-GENERATION)

**CRITICAL:** ALL scenarios MUST be auto-enhanced with v2.1 metadata for code generation

The std-generator MUST automatically add these sections to EVERY scenario:

1. **code_generation_config** (document-level, added once after document_metadata)
2. **variables** (scenario-level, inferred from code_templates)
3. **test_structure** (scenario-level, inferred from decorators)
4. **Code template transformations** (fix shadowing, add ExpectWithOffset, generate cleanups)

---

### 1. code_generation_config Section (Document-Level)

**Location:** Insert immediately after `document_metadata` section, before `common_preconditions`

**Content:** Read from `{project_context.config_dir}/code_generation_config.yaml` (tier mode)
or populate from test-strategy-resolver output (auto mode).

```yaml
code_generation_config:
  std_version: "2.1-enhanced"
  framework: "{from project config}"           # e.g., "ginkgo-v2", "testing"
  assertion_library: "{from project config}"   # e.g., "gomega", "testify"
  language: "{from project config}"            # e.g., "go"
  package_name: "{INFER_FROM_SIG}"             # resolved via config package_name_rules

  context_init: [...]                          # from project config
  imports: {...}                               # from project config (groups vary per project)
  timeout_constants: {...}                     # from project config (tier mode only)
  helper_library_imports: {...}                # from project config (tier mode only)
```

**Package Name Inference:** Read `package_name_rules` from the project's
`code_generation_config.yaml` to map SIG names to package names.

---

### 2. variables Section (Scenario-Level)

**Location:** Add to each scenario after `patterns` section, before `code_structure`

**Algorithm:** Infer variables from code_template usage in test_steps

#### Variable Inference Rules

**Default variables (always include):**

```yaml
variables:
  closure_scope:
    - name: "ctx"
      type: "context.Context"
      initialized_in: "BeforeAll"
      used_in: ["BeforeAll", "AfterEach"]
      comment: "Context for K8s API calls"

    - name: "namespace"
      type: "string"
      initialized_in: "BeforeAll"
      used_in: ["BeforeAll", "AfterEach"]
      comment: "Test namespace"

    - name: "err"
      type: "error"
      initialized_in: "BeforeAll"
      used_in: ["BeforeAll", "It", "AfterEach"]
      comment: "Error variable for API calls"
```

**Scan code_templates for additional variables:**

For each `code_template` in `test_steps.setup` and `test_steps.test_execution`:

1. **Look for assignment patterns:**
   - Pattern: `{var_name} = {function_call}(...)`
   - Example: `netDef = libnetwork.NewPasstNetDef(...)`
   - Example: `resource = factory.NewDefault(...)`

2. **Infer Go type from function name:**

Read the function-to-type mapping from `{project_context.config_dir}/code_generation_config.yaml`
`helper_functions` section. Each helper function entry defines the return type, enabling
variable type inference from function calls.

3. **Add to variables list:**

```yaml
- name: "{var_name}"
  type: "{inferred_type}"
  initialized_in: "{BeforeAll|It}"  # BeforeAll if in setup, It if in test_execution
  used_in: ["{locations_where_used}"]
  comment: "{Brief description from step action}"
```

**Example inference:**

```yaml
# From code_template:
# netDef = libnetwork.NewPasstNetDef("localnet-def")
# netDef, err = libnetwork.CreateNetworkDefinition(ctx, namespace, netDef)

# Inferred variable:
- name: "netDef"
  type: "*networkv1.NetworkDefinition"
  initialized_in: "BeforeAll"
  used_in: ["BeforeAll", "AfterEach"]
  comment: "Localnet network definition"
```

---

### 3. test_structure Section (Scenario-Level)

**Location:** Add to each scenario after `variables` section, before `code_structure`

**Algorithm:** Infer from scenario metadata and patterns

```yaml
test_structure:
  type: "single"  # Always "single" for now (table-driven later)

  describe:
    wrapper: "SIG"  # Always use SIG() wrapper
    description: "{INFER_FROM_FEATURE}"  # From STP feature description or scenario title
    decorators:
      - "{SIG_DECORATOR}"  # From patterns.decorators (e.g., decorators.SigNetwork)
      - "Serial"           # Always add Serial for network/storage/migration tests

  context:
    description: "{scenario.test_objective.title}"  # Use scenario title verbatim
    decorators:
      - "Ordered"                           # Always add Ordered
      - "decorators.OncePerOrderedCleanup"  # Always add for proper cleanup

  it:
    description: "should {INFER_FROM_ACCEPTANCE_CRITERIA}"
    test_id_format: "[test_id:{test_id}]"
```

**Inference Rules:**

1. **describe.description:**
   - Extract from STP Section I.1 (Feature Description)
   - Or use first 3-5 words of scenario title
   - Examples: "Localnet connectivity validation", "Live migration tests", "CPU hotplug operations"

2. **describe.decorators:**
   - Find SIG decorator from `patterns.decorators` array
     - Contains `SigNetwork` -> Use `decorators.SigNetwork`
     - Contains `SigCompute` -> Use `decorators.SigCompute`
     - Contains `SigStorage` -> Use `decorators.SigStorage`
   - Always add `Serial` for network/storage/migration tests
   - Keep any other decorators from patterns

3. **context.description:**
   - Use `test_objective.title` field verbatim
   - This provides clear test scope

4. **context.decorators:**
   - ALWAYS include: `Ordered`
   - ALWAYS include: `decorators.OncePerOrderedCleanup`
   - These are mandatory for proper test execution and cleanup order

5. **it.description:**
   - Extract from first acceptance criterion in `test_objective.acceptance_criteria`
   - Or use `test_objective.title` without "Test that..." prefix
   - Start with "should" (Ginkgo convention)
   - Example: "should allow ICMP connectivity from default network pod to localnet VM"

---

### 4. Code Template Transformations (Auto-Apply)

**Apply these transformations to ALL code_template fields:**

#### Transformation #1: Fix Variable Shadowing

**Problem:** Templates use `:=` (short declaration) which creates new variables scoped to BeforeAll/It blocks

**Solution:** Replace `:=` with `=` for all closure-scoped variables

**Algorithm:**

```python
def fix_variable_shadowing(code_template, closure_variables):
    """
    Replace := with = for variables declared at closure scope
    """
    for var in closure_variables:
        # Pattern: "var := ..." -> "var = ..."
        code_template = re.sub(
            rf'^(\s*){var}\s*:=\s*',
            rf'\1{var} = ',
            code_template,
            flags=re.MULTILINE
        )

        # Pattern: "_, err := ..." -> "_, err = ..." if err is closure variable
        if var == 'err':
            code_template = re.sub(
                r'^(\s*)_,\s*err\s*:=\s*',
                r'\1_, err = ',
                code_template,
                flags=re.MULTILINE
            )

            # Pattern: "resource, err := ..." -> "resource, err = ..."
            code_template = re.sub(
                r'^(\s*)(\w+),\s*err\s*:=\s*',
                r'\1\2, err = ',
                code_template,
                flags=re.MULTILINE
            )

    return code_template
```

**Example transformation:**

```yaml
# BEFORE:
code_template: |
  netDef := libnetwork.NewPasstNetDef("localnet-def")
  _, err := libnetwork.CreateNetworkDefinition(ctx, namespace, netDef)

# AFTER:
code_template: |
  netDef = libnetwork.NewPasstNetDef("localnet-def")
  netDef, err = libnetwork.CreateNetworkDefinition(ctx, namespace, netDef)
```

#### Transformation #2: Add ExpectWithOffset

**Problem:** `Expect(err)` doesn't provide good stack traces in helper functions

**Solution:** Use `ExpectWithOffset(1, err)` instead

**Algorithm:**

```python
def add_expect_with_offset(code_template):
    """
    Replace Expect(err) with ExpectWithOffset(1, err) for better error traces
    """
    code_template = re.sub(
        r'Expect\(err\)\.ToNot\(HaveOccurred\(\)\)',
        r'ExpectWithOffset(1, err).ToNot(HaveOccurred())',
        code_template
    )

    # Also handle Should, ShouldNot patterns
    code_template = re.sub(
        r'Expect\(([^)]+)\)\.To\(',
        r'ExpectWithOffset(1, \1).To(',
        code_template
    )

    return code_template
```

**Example transformation:**

```yaml
# BEFORE:
Expect(err).ToNot(HaveOccurred())

# AFTER:
ExpectWithOffset(1, err).ToNot(HaveOccurred())
```

#### Transformation #3: Auto-Generate Cleanup Templates

**Problem:** Cleanup steps often lack code_template

**Solution:** Auto-generate cleanup code from setup steps

**Algorithm:**

```python
def generate_cleanup_templates(setup_steps, closure_variables):
    """
    Auto-generate cleanup code_templates based on setup steps
    """
    cleanup_steps = []

    for step in setup_steps:
        resource_var = detect_resource_variable(step.code_template)
        resource_type = get_variable_type(resource_var, closure_variables)

        cleanup_code = generate_cleanup_code(resource_var, resource_type)

        cleanup_steps.append({
            "step_id": f"CLEANUP-{len(cleanup_steps)+1:02d}",
            "action": f"Delete {resource_type_name(resource_type)}",
            "code_template": cleanup_code
        })

    return cleanup_steps


def generate_cleanup_code(var_name, var_type):
    """
    Generate cleanup code based on resource type.
    Read cleanup templates from {project_context.config_dir}/code_generation_config.yaml
    under the cleanup_templates section. Each entry maps a Go type to a cleanup
    code template with {var_name} placeholders.
    """
    templates = read_from_config("cleanup_templates")
    return templates.get(var_type, '# Cleanup for {var_name}').format(var_name=var_name)
```

**Example auto-generation:**

```yaml
# From SETUP step:
- step_id: "SETUP-01"
  action: "Create resource instance"
  code_template: |
    resource = factory.NewResource(...)
    resource, err = client.Resource(namespace).Create(ctx, resource, metav1.CreateOptions{})
    ExpectWithOffset(1, err).ToNot(HaveOccurred())

# Auto-generated CLEANUP (from cleanup_templates in code_generation_config.yaml):
- step_id: "CLEANUP-01"
  action: "Delete resource"
  code_template: |
    By("Deleting resource")
    err = client.Resource(namespace).Delete(ctx, resource.Name, metav1.DeleteOptions{})
    ExpectWithOffset(1, err).ToNot(HaveOccurred())
```

---

### 5. v2.1 Enhancement Validation

**See the consolidated "Final Validation Checklist" section in SKILL.md for all validation checks including v2.1 enhancements.**

---

### 6. Updated LLM Prompt (v2.1)

**Add to System Prompt:**

```
CRITICAL - v2.1 ENHANCEMENTS (AUTO-GENERATE):

After generating base STD structure, you MUST automatically enhance it with v2.1 metadata:

1. code_generation_config Section (MANDATORY):
   - Add after document_metadata, before common_preconditions
   - Use static template (same for all tickets)
   - Infer package_name from owning_sig (sig-network -> "network", etc.)

2. variables Section per Scenario (MANDATORY):
   - Add after patterns section, before code_structure
   - Include default variables: ctx, namespace, err
   - Scan all code_template fields to infer additional variables
   - Map function calls to Go types using helper_functions from project config

3. test_structure Section per Scenario (MANDATORY):
   - Add after variables section, before code_structure
   - Infer decorators from patterns.decorators
   - Always include: Ordered, decorators.OncePerOrderedCleanup in context
   - Use SIG() wrapper for Describe

4. Fix Code Templates (MANDATORY):
   - Replace := with = for all closure-scoped variables
   - Replace Expect(err) with ExpectWithOffset(1, err)
   - Auto-generate cleanup templates from setup steps

5. Validation (BEFORE OUTPUT):
   - All scenarios have variables section
   - All scenarios have test_structure section
   - All code_templates use = (not :=) for closure variables
   - All Expect(err) use ExpectWithOffset
   - All scenarios have cleanup templates

If you cannot complete v2.1 enhancements for any scenario, DO NOT output partial STD.
Return error report instead.
```

---

### 7. v2.1 Success Criteria

STD v2.1 generation is successful when:

- All base STD requirements met (from v2.0)
- `code_generation_config` section present and complete
- ALL scenarios have `variables` section with inferred closure variables
- ALL scenarios have `test_structure` section with correct decorators
- ALL code_templates use `=` instead of `:=` for closure variables
- ALL error checks use `ExpectWithOffset(1, err)`
- ALL cleanup templates auto-generated from setup
- Generated Go code compiles with valid syntax (no shadowing errors)

**Quality bar:** Generated STD must be code-generation-ready without manual edits.

---

## v2.1 Update Changelog

**Date**: 2026-01-22

### Summary of Changes (v2.0 to v2.1)

| Feature | v2.0 | v2.1 | Change Type |
|:--------|:-----|:-----|:------------|
| **std_version** | "2.0-enhanced" | "2.1-enhanced" | Update value |
| **code_generation_config** | Missing | Add section | NEW SECTION |
| **variables per scenario** | Missing | Infer from code_templates | NEW SECTION |
| **test_structure** | Missing | Infer from decorators | NEW SECTION |
| **Variable shadowing** | `:=` in templates | `=` in templates | FIX TEMPLATES |
| **ExpectWithOffset** | `Expect(err)` | `ExpectWithOffset(1, err)` | FIX TEMPLATES |
| **Cleanup templates** | Missing | Auto-generate from setup | ADD TEMPLATES |
| **OncePerOrderedCleanup** | Not in decorators | Always add for Ordered | ADD DECORATOR |

### Files Modified

1. **`SKILL.md`**
   - std_version: "2.0-enhanced" -> "2.1-enhanced"
   - Added code_generation_config section template
   - Added variables and test_structure to scenario schema
   - Updated validation checklist for v2.1

### Design Decisions

1. **Document-level code_generation_config**: Reduces duplication across scenarios
2. **Inference over specification**: Infer variables and test_structure from existing data
3. **Transform don't replace**: Fix code_templates in-place rather than regenerating
4. **Fail-fast validation**: Don't output incomplete STD

---

**End of STD Generator Supplemental Reference**
