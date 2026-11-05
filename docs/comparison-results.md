# Comparison results: every round

*2026-11-05. QualityFlow against the AI Engineering Test Plan Generator on the same 10 tickets, graded case by case
against the code that shipped. Method and tickets: [test-plan-generator-comparison.md](test-plan-generator-comparison.md).
Nothing in any round ran on a cluster.*

## Bottom lines

1. **Plans: QualityFlow is wrong far less often.** It plans before the code exists, as the generator does: 17% of its
   test cases are wrong, against 44% of the generator's. Coverage is the same (103 vs 101 of 129 requirements), and it
   finds 5x the real problems (15 vs 3). Once the code has shipped, under 1% of its test cases are wrong.
2. **Tests: the model is the ceiling, for both tools.** On gpt-5.6-luna about 5% of test cases get a real test. On
   GLM 5.3 (free, Red Hat EnMaaS) both write about 40 real new tests.
3. **The difference is what comes with them.** The generator adds about 250 tests that need work: 120 wrong, 46
   hollow, 77 that do not load. QualityFlow's all load and none is hollow, but it declines more cases.
4. **Once the code ships, QualityFlow tells you what is already tested.** 41 of 46 "already covered" claims hold
   and none is false. That is the part a team can rely on to skip work.
5. **Every round found a QualityFlow gap, and each one is now fixed and checked** (12 PRs, listed below).

## Rounds

**Plans** (Section III test cases, per case):

| Round | Date | Setup | Wrong cases (GEN / QF) | Reqs covered of 129 | Problems found |
|---|---|---|---|---|---|
| 4 | 10-26 | QF on the shipped code, gpt-6.1-sol | 44% / <1% | 101 / 114 | 3 / 38 |
| 6 | 10-26 | **fair**: QF on the code as of the generator's plan date | 44% / 17% | 101 / 103 | 3 / 15 |

Rounds 1-3 were a 2-ticket pilot and two runs without LSP, so they don't count.

**Tests** (each tool writes tests from its own plan; same model, sandboxed, no network):

| Run | Date | Model | Real tests (GEN / QF) | Bottom line |
|---|---|---|---|---|
| QF only | 10-31 | luna | — / 10 of 270 | 24% hollow; the offline check missed it (fixed: #175, #176) |
| 3 | 11-02 | luna | 7 / 14 | GEN: 156 of 240 do not load, 65 hollow. QF: declines 196 cases |
| 4 | 11-03 | luna | — / 14 | a scripted product search cut avoidable declines from 89 to 71, but no extra real tests |
| 5 | 11-04 | GLM 5.3 | 63 / 42 | real, new and loading: 40 / 39. GEN: 120 wrong, 46 hollow, 77 do not load. QF: 34 wrong, 0 hollow, all load |
| 6 | 11-04 | GLM 5.3 | — / 38 | QF on the shipped code: 37% of cases get a real test or a verified existing one; 6 false "covered" claims |
| 7 | 11-04 | GLM 5.3 | — / 25 | after #180, #183 and #184: no false claims; tests from an unmerged PR fell from 13 to 0; 34% of cases |

Runs 6 and 7 differ by about as much as the fixes changed. Expect that spread from a single run on this model.

## What QualityFlow changed because of it

| PR | Change | Found in |
|---|---|---|
| #173 | test cases use the literals the plan collected, never invented ones | plans round 6 |
| #175 | the offline check uses the checkout's own venv and never runs TestMain | QF-only test run |
| #176 | the check fails tests that never touch the product | QF-only test run |
| #177 | the check fails tests that would error at setup, and edits to the team's files | QF-only test run |
| #178 | the product is searched per scenario before writing; skip-only tests fail the check | run 3 |
| #179 | the free EnMaaS models are a runtime (via Codex) | run 4 (luna was the ceiling) |
| #180 | the check fails a listed test file that is not in the checkout | run 5 |
| #182 | LSP works on repos with several Go modules | run 6 |
| #183 | the check fails tests citing code the checkout does not have (an open PR) | run 6 |
| #184 | the plan reads Jira's own text, not the model's summary of it | run 6 |
| #185 | the duplicate check runs on a detached checkout of main | run 6 |
| #186 | the check fails a test file that imports the team's tests, so they do not run twice | run 7 (open) |
| #187 | a requirement that only a held PR delivers goes to Out of Scope, not into scenarios | run 7 (open) |

All but #186 and #187 are merged and live on cnv2 (build 203).

## Still open

- **Test bodies.** Most remaining wrong tests come from one setup mistake each, such as a fixture never requested
  or a wait for a field the resource does not have. The offline check cannot see those. A stronger model, or a live
  run in CI, can.
- **Declines when planning before the code exists.** 51 of 147 were avoidable in run 5. Planning on the shipped
  code removes most of them (4 to 11).

Per-test gradings (file:line for every verdict) are kept by the QualityFlow maintainers; ask for them.
