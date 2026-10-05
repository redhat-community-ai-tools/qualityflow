---
name: output-validator
description: Validate STP document structure and content completeness
model: claude-opus-4-6
---

# Output Validator Skill

**Phase:** Post-Processing
**User-Invocable:** false

## Purpose

Validate STP document structure and content completeness.

## When to Use

Invoked by the **document-formatter** subagent to verify the STP before saving.

## How to Run

**Step 1 — mechanical checks (always run the script; never re-do these by
hand).** From the repo root:

```bash
python3 skills/output-validator/validate_doc.py <stp_file> \
  [--template <stp template>] \
  [--stp-header "{project_context.stp_header without leading '# '}"] [--yaml]
```

- `--template`: the template the STP was built from, in template-engine's
  order. If `project_context.repo_rules.stp_template` is set, write it to
  `outputs/{JIRA_ID}/stp/{JIRA_ID}_stp_template.md` and pass that path.
  Otherwise pass `{project_context.config_dir}/templates/stp/stp-template.md`
  when it exists. Leave the flag out only when the STP was built from
  template-engine's bundled template, which is the default.

- Exit code 0: no errors (warnings may still be listed — relay them).
- Exit code 1: at least one FAIL — the listed errors must be fixed before save.
- `--yaml` prints the machine-readable report; default is a plain PASS/FAIL
  table plus ERROR/WARNING lines.

The script deterministically covers two layers.

- **From the template.** The document header and feature title follow the
  template's own lines, with placeholders as wildcards. The template's
  sections must appear in order, with its `---` rules between them. Its bold
  block labels must appear too (e.g. `**Test Limitations**`, the risk
  categories), as must its fixed labelled items (checklist and field labels)
  and the keys nested under them (e.g. Feature Maturity's DP/TP/GA). An
  example item (a bullet whose sub-items carry `*Field:*` lines, such as
  `- **[Known Limitation]**` with `*Sign-off:*`) means every real item in its
  block carries those fields; a block with no items states "None". A heading
  or item marked "if applicable", "optional" or "remove this field" may be
  left out. One value rule applies when the template has the field: Feature
  Maturity values are versions, not prose.
- **QF's contract, for every team.** Section III entry format
  (`- **[Jira-ID]**` + `*Test Scenario:*` + `*Priority:*`, or the table
  layout), inline tier/test-type tags (`[Tier 1]`, never
  `Tier 1 (Functional)`), `TS-{NN}` ids unique (sequential order is a
  warning), unique requirement summaries, the fixed generic-scenario strings,
  code fences, NFR-scenario keyword cross-reference (warning), `[Name/Date]`
  placeholders never replaced by status prose, `Decision:`/`Justification:`
  blocks, non-RFC-5737 IPs and non-example emails. Appendix, Summary,
  Glossary and References sections, old-style numbering (II.4.A-D, II.6-8)
  and the removed "Current Status" field are also flagged, unless the
  template itself has them.

**Step 2 — semantic checks (the ONLY LLM part of this skill).** After the
script passes, review the document for the checks a regex cannot decide:

1. **AC-Scenario Temporal Alignment.** Scan Section III.1 for temporal
   mismatches: if a requirement summary or its parent context contains
   temporal keywords ("continuous", "continuously", "throughout", "during
   the entire", "while running", "sustained", "uninterrupted", "without
   disruption") AND its test scenario only describes a final-state check
   ("Verify [noun] after", "Verify [noun] is [state]", "without interrupting"
   as end-state), emit:
   - **Warning:** "Scenario may not match AC temporal scope — AC requires
     continuous/ongoing verification but scenario appears to check end-state
     only. Consider a scenario that verifies the condition holds *during* the
     operation."
2. **Third-party vendor names.** The script cannot know which product names
   are vendors; flag any vendor names not allowed by the project's
   `pii_exceptions.yaml` (see the pii-sanitizer skill).
3. **Scenario quality beyond fixed strings.** Generic/meta scenarios that
   paraphrase "tests should pass" without matching the script's literal list.

## Output Format

Merge the script report and the semantic findings:

```yaml
validation_results:
  valid: true
  checks:
    structure.document_header: pass
    content.template_items: pass
    content.valid_test_tiers: pass
    # ... one line per script check ...
  errors: []
  warnings:
    - "Scenario ids are not in document order (renumber while no STD exists): TS-01, TS-35, TS-02"
total_checks: 25
passed: 25
failed: 0
warnings: 1
```

## Error Severity

| Severity | Handling |
|:---------|:---------|
| **Error** (script FAIL) | Must be fixed before save |
| **Warning** (script or semantic) | Document can be saved, but should be addressed |
| **Info** | Optional improvement suggestion |

## Auto-Fix Capabilities

Some issues can be auto-fixed after the script identifies them:

| Issue | Auto-Fix |
|:------|:---------|
| Wrong tier format | Convert "Tier 1 (Functional)" to "[Tier 1]" |
| Missing horizontal rule | Insert `---` at expected positions |
| Trailing whitespace | Remove |
| Old metadata field name | Rename "Feature in Jira" to "Feature Tracking", "Jira Tracking" to "Epic Tracking" |

Issues that CANNOT be auto-fixed:

- Missing sections (need content)
- Invalid test scenarios (need rewriting)
- Code blocks (need conceptual replacement)
- Platform-level tests (need rejection)

After any auto-fix, re-run the script to confirm a clean report.
