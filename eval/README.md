# stp-reviewer exemplar suite

Three exemplars for the `stp-reviewer` skill, built from real QualityFlow pipeline
runs. The suite exists to answer one question: **when a new model ships, does the
reviewer still make the same call on documents we already know the answer to?**

`stp-reviewer` pins a model in its frontmatter. Changing that pin changes the quality
gate the whole pipeline depends on. This is the eval you run before you change it.

## The cases

| Case | Category | Verdict | Critical | Where it came from |
|:--|:--|:--|:--|:--|
| `cnv-68916-cdrom-hotplug` | happy-path | `APPROVED_WITH_FINDINGS` | 0 (±0) | Real run, 2026-03-19. Template-conformant STP for a GA storage feature; a long tail of style and classification findings, nothing blocking. |
| `cnv-72329-nad-live-update` | known-bad | `NEEDS_REVISION` | 3 (±1) | Real run, 2026-03-25. A technically strong STP written to the wrong structure — no Section I, no Section IV, its own 11-section layout. |
| `cnv-68916-degraded` | known-bad | `NEEDS_REVISION` | 4 (±2) | The first case's STP with five itemised degradations applied. Never run through the pipeline; every edit is listed in its `annotations.yaml`. |

Two of the three carry a verbatim reviewer output as `reference.md`
(`reference_type: captured`). The third carries a derived expected-findings checklist
(`reference_type: derived`) and says so at the top of the file — it is a controlled
mutation of a real artifact, not a fabricated run.

The two real runs land on **different verdicts**, so the suite already covers the
approve and the block path with genuine evidence. The degraded case adds something the
real pair cannot: a document whose critical findings are known by construction, so a
model that quietly stops noticing rule violations fails a case instead of merely
producing a thinner review.

## Judges

| Judge | Kind | Gate |
|:--|:--|:--|
| `verdict_matches_expected` | deterministic | `min_pass_rate: 1.0` |
| `critical_findings_within_tolerance` | deterministic | `min_pass_rate: 1.0` |
| `finding_alignment` | LLM rubric, 1–5 (`prompts/review-judge.md`) | `min_mean: 3.5` |

The verdict judge scans for a line containing "Verdict" and exactly one of the three
canonical verdicts. The critical-count judge reads the count from the Summary table
row, falling back to prose if the report has been reformatted. Both are intentionally
tolerant about layout and strict about the number.

## Runbook

### 1. Baseline, on the currently pinned model

```bash
/eval-run --config eval/eval.yaml --model claude-opus-4-6
```

Use whatever `model:` currently sits in `skills/stp-reviewer/SKILL.md`. Save the run
id. If the baseline does not pass on the pinned model, stop — the suite is telling you
something about the current state, not about the new model.

### 2. Candidate, on the new model

```bash
/eval-run --config eval/eval.yaml --model <new-model>
```

### 3. Compare

```bash
/eval-compare <baseline-run-id> <candidate-run-id>
```

### Decision rule

**Ship it when all three verdicts still agree with `expected_verdict`, and each
case's critical count is inside its tolerance.** Everything else is a judgement call
against these two rules:

- **Critical findings DROPPING is the signal to investigate**, even when the verdict
  survives. `cnv-72329-nad-live-update` blocks on three criticals; if the candidate
  finds one and still says `NEEDS_REVISION`, the case passes and the reviewer has
  still become measurably more lenient. The next STP it sees may be the one where the
  last critical disappears too. Read the diff before shipping.
- **Critical findings rising on `cnv-68916-cdrom-hotplug` is the opposite failure.**
  That STP is genuinely clean; criticals there mean the candidate has become
  trigger-happy, and a reviewer that blocks good STPs gets switched off by its users.

`finding_alignment` below 3.5 with verdicts intact means the reviewer reaches the
right call by a different route. Not disqualifying, worth reading.

Then update the `model:` frontmatter in `skills/stp-reviewer/SKILL.md` **and** the
`models.skill` value in `eval/eval.yaml` in the same commit, so the baseline command
above stays honest.

## Adding an exemplar from a real run

The point of this suite is that its answers were produced, not imagined. Keep it that
way.

1. **Pick a run you would defend.** A real `/review-stp` execution whose verdict a QE
   engineer agrees with. A run whose verdict you would argue with is not an exemplar.
2. **Create `eval/dataset/cases/<jira-key>-<slug>/`.**
3. **`reference.md`** — the review report from that run, verbatim.
4. **`input.yaml`** — the STP under review as `stp_content`, plus `jira_id`,
   `jira_data`, `project_context` and `fix_scope`. Reconstruct only what the run
   genuinely had. **If the run had no Jira access, leave `jira_data: null`** — filling
   it in produces a different review and the reference stops reproducing. Mark every
   reconstructed field `MOCKED` in a comment.
5. **`annotations.yaml`** — `expected_verdict`, `expected_critical_findings` and its
   tolerance, `category`, and a `source` block naming the artifact paths and dates.
   Set tolerance from how legitimately mergeable the findings are, not from how much
   slack you want.
6. **Sanitize, then verify.** Apply `pii_rules` from `config/_defaults.yaml`: employee
   names to bracketed role placeholders, internal Jira and Git hosts to
   `your-jira-instance.example.com` / `example.com`, customer names, hostnames, IPs and
   Slack channels out. Upstream project content and Jira keys stay. Then grep the case
   directory for `redhat.com`, `@`, `corp`, `cee`, `10.`, `192.168`, `ghp_`, `glpat`
   and account for every hit. This is a public repository.
7. **Record the sanitization** in `annotations.yaml` so the next person can tell a
   redaction from an inaccuracy.

Degraded cases follow the same rules plus one: **every edit goes in
`annotations.degradations`, itemised**, with the rule it targets and the effect it
should have. An undocumented degradation is a fabrication.

## Harness notes

Written against the [agent-eval-harness](https://github.com/opendatahub-io/agent-eval-harness)
configuration reference. Two things were kept deliberately minimal because the
reference does not pin them down:

- **How `reference.md` reaches the rubric judge.** `prompts/review-judge.md` refers to
  it by name and location rather than through a template variable, so the judge works
  whether the harness injects it or the judge reads it from the case directory.
- **How the produced report reaches the deterministic judges.** Both checks scan every
  string value in `outputs` rather than naming a key, so they do not depend on the
  exact artifact key the harness uses.

`eval/` is data, not a deployable unit. `deploy.py` discovers only `agents/`,
`commands/` and `skills/`, so nothing here is packaged as a skill.
