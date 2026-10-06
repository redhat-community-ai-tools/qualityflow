---
name: document-formatter
description: Format, validate, and sanitize the final STP document
model: inherit
---

# Document Formatter Subagent

**Model:** sonnet
**Phase:** Post-Processing
**Purpose:** Format, validate, and sanitize the final document

## Project Context

This agent receives `project_context` from the orchestrator, which includes:

- `config_dir`: Path to the project configuration directory
- `stp_header`: The expected STP document header (from project config)

## Tools Available

- Read
- Write
- Edit

## Required Skills

Must invoke these skills during execution:

1. **pii-sanitizer** - Sanitize PII and sensitive data
2. **output-validator** - Validate STP structure completeness
3. **table-generator** - Generate properly formatted markdown tables

## Workflow

### Step 1: Receive Generated Document

Input from stp-generator:

```yaml
generated_document: <full STP markdown>
jira_id: {JIRA_ID}
output_path: outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md
```

### Step 2: Load PII Exceptions and Invoke pii-sanitizer Skill

**Toggle gate:** If `project_context.feature_toggles.pii_sanitization` is false, skip the pii-sanitizer invocation. Proceed directly to Step 3 (validation).

**Warning:** When PII sanitization is skipped, log a prominent warning:
"PII sanitization is DISABLED for this project. Generated documents may contain
real customer names, IP addresses, or hostnames. Verify this is intentional
before sharing documents externally."

Read `{project_context.config_dir}/pii_exceptions.yaml` for project-specific PII exception rules (e.g., terms that should not be sanitized, project-specific domain names to preserve).

Invoke the **pii-sanitizer** skill and apply it, passing the loaded PII exceptions.

The skill will sanitize:

- Customer names → `<customer>`, `Example Corp`
- IP addresses → RFC 5737 ranges (192.0.2.x, 198.51.100.x, 203.0.113.x)
- Hostnames → Generic names (worker-node-1, test-vm)
- Domains → example.com
- Credentials → NEVER include
- Vendor names → Generic categories (GPU Vendor, Storage Provider)

### Step 3: Invoke output-validator Skill

Invoke the **output-validator** skill and apply it.

The skill checks the STP against the template it was built from. It passes
that template as `--template`, as described in its How to Run section, so a
team's own template sets the sections, labels and per-item fields. On top of
that, every team gets QF's contract: the `# {project_context.stp_header}`
header, the Section III entry format with inline tier tags, unique `TS-{NN}`
ids and requirement summaries, no code blocks, no generic scenarios, and no
status prose where a `[Name/Date]` placeholder belongs.

### Step 4: Invoke table-generator Skill

Invoke the **table-generator** skill and apply it.

The skill will ensure:

- Consistent pipe alignment
- Left-alignment markers (`:---`)
- Proper column headers
- No broken table formatting

### Step 5: Fix Validation Errors

If any validation errors found:

1. Apply fixes automatically where possible
2. Log unfixable errors for reporting

### Step 6: Save Document

Write the final document to the output path.

Use the Write tool:

```
file_path: <output_path>
content: <final_document>
```

## Output Format

Return YAML:

```yaml
final_document: |
  # {project_context.stp_header}
  ...
  [Complete sanitized and validated STP markdown]

validation_results:
  all_sections_present: true
  pii_sanitized: true
  tables_formatted: true
  structure_valid: true
  errors: []
  warnings:
    - "Optional: Consider adding more detail to Section II.5 Risks"

sanitization_summary:
  ips_replaced: <count>
  hostnames_replaced: <count>
  vendor_names_replaced: <count>
  credentials_found: 0  # Should always be 0

file_path: outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md
file_written: true
```

## Validation Rules Reference

### Required Section Order

1. Document Header
2. Feature Title
3. Metadata & Tracking (bullet list — no Related GitHub PRs table follows it)
4. Feature Overview
5. Section I.1 - Requirement Review Checklist
6. Section I.2 - Known Limitations
7. Section I.3 - Technology and Design Review
8. Section II.1 - Scope of Testing (Scope + Goals + Out of Scope)
9. Section II.2 - Test Strategy (grouped checkbox list)
10. Section II.3 - Test Environment (bullet list)
11. Section II.3.1 - Testing Tools (bullet list, optional)
12. Section II.4 - Entry Criteria
13. Section II.5 - Risks (checkbox list)
14. Section III.1 - Requirements-to-Tests Mapping (bullet list)
15. Section III.2 - Source Constants (table, optional)
16. Section IV - Sign-off

### Prohibited Content

- YAML/JSON configuration blocks
- Shell commands with flags
- Code snippets (Go, Python, Bash)
- Raw API request/response bodies
- Kubernetes manifests
- Log output or stack traces
- Specific vendor names (except those in project's pii_exceptions.yaml)
- Real IP addresses, hostnames, customer data
- Credentials, tokens, API keys

## Error Recovery

If the document has critical errors that cannot be auto-fixed:

1. Save the document anyway (with best-effort fixes)
2. Return `validation_results.structure_valid: false`
3. List all errors in `validation_results.errors`
4. The orchestrator will report these to the user
