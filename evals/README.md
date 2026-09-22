# Plugin evals

`claude plugin eval` suite for the `/review-stp` flow (the `stp-reviewer` skill).
Each case runs with the plugin and without it; `Δ` is what QualityFlow adds.

| Case | Expected | What it catches |
|:--|:--|:--|
| `01-cdrom-hotplug` | `NEEDS_REVISION`, 1–2 critical | Rule A leaks ("reconcile" in a Testing Goal, "VM controller" in a scenario) that a March run missed |
| `02-nad-72329` | `NEEDS_REVISION`, 2–4 critical | A well-written STP in the wrong structure (no Section I / IV) |
| `03-degraded` | `NEEDS_REVISION`, 2–6 critical | Five planted defects: Rule A ×2, Rule C, Dimension 2 coverage gap, Rule J |
| `04-neg-std-review` | reviewer does not fire | An STD review request must not trigger the STP reviewer |

Cases 01–03 are real, sanitized pipeline STPs from the `eval/stp-reviewer-exemplars` branch.

## Run

```bash
GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json" \
  claude plugin eval . -j 8 --scaffold --no-publish --judge-model sonnet
```

- `--scaffold` is required: each case's `fixture.sh` copies `fixtures/input.yaml` into the
  run's working directory. `context.add_dirs` does not reach the agent in the current build.
- On Vertex, pin `GOOGLE_APPLICATION_CREDENTIALS`: runs get a throwaway `$HOME`, so the
  default ADC path is not found.
- `--judge-model sonnet`: the default judge may resolve to a model your Vertex project lacks.

A full run is 24 agent runs, about 13 minutes and $15 at list price.
