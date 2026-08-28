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
  [--stp-header "{project_context.stp_header without leading '# '}"] [--yaml]
```

- Exit code 0: no errors (warnings may still be listed — relay them).
- Exit code 1: at least one FAIL — the listed errors must be fixed before save.
- `--yaml` prints the machine-readable report; default is a plain PASS/FAIL
  table plus ERROR/WARNING lines.

The script deterministically covers: document header, feature title format,
required-section presence and order, horizontal rules, every list-item count
(Metadata 6, I.1 5, I.3 5, II.1 Out-of-Scope >=1, II.2 13 across 4 categories,
II.3 10, II.5 7 categories), Section III.1 entry format
(`- **[Jira-ID]**` + `*Test Scenario:*` + `*Priority:*`), inline tier format
(`[Tier 1]`/`[Tier 2]` only), unique requirement summaries, the fixed
generic-scenario strings, code-fence detection, NFR-scenario keyword
cross-reference (warning), risk sub-item completeness (warning), prohibited
sections (Appendix/Summary/Glossary/References), old-style numbering
(II.4.A-D, II.6-8), `Decision:`/`Justification:` blocks, non-RFC-5737 IPs,
non-example emails, and the removed "Current Status" metadata field.

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
    list_items.section_ii_2: pass
    content.valid_test_tiers: pass
    # ... one line per script check ...
  errors: []
  warnings:
    - "Risk category '- [x] **Other**' has 0 sub-items, expected 3 (Risk, Mitigation, Impact/Status)"
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
