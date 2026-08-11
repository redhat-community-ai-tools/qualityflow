# STP Reviewer Eval Cases

Eval cases for the `stp-reviewer` skill, designed for use with
[agent-eval-harness](https://redhat-global-engineering.github.io/ge-public-skills).

## Cases

| File | Type | Expected Verdict | Tests |
|------|------|-----------------|-------|
| `happy-path.yaml` | Happy path | `APPROVED` | Well-formed STP passes all 7 dimensions |
| `edge-case-findings.yaml` | Edge case | `APPROVED_WITH_FINDINGS` | STP with minor/major issues but no critical |
| `error-critical.yaml` | Error case | `NEEDS_REVISION` | STP with critical rule violations |

## Running

```bash
# With agent-eval-harness installed:
/eval-run --dataset evals/stp-reviewer/ --skill stp-reviewer
```

Each case file contains `input` (STP content + mock Jira data) and `expected`
(verdict + assertions). The eval harness compares actual reviewer output against
expected assertions.
