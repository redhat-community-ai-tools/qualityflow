# QualityFlow on shipped code: results

*The same 10 tickets, run again once the features had shipped, the way a team runs QualityFlow when the PRs
exist: plan (Jira + GitHub PRs + LSP on the product checkout) → test cases → tests, all on GLM 5.3 through Red
Hat EnMaaS (free). QualityFlow only: the generator's numbers are on the [results page](README.md). No test was
executed: each one was loaded offline (`pytest --setup-plan` / `go test -c`) and graded by reading it against
the shipped code. Run 10 is QualityFlow main `3b7ffa3` (2026-11-09); run 7 is the same setup a week earlier.*

## Bottom line

1. **Fewer wrong tests: 27% vs 35% a week earlier.** 13 of 48 tests are wrong, down from 31 of 89. All 48
   are clean on the offline checks (none hollow, none importing the team's tests). Two tests in RHAIRFE-1487
   would hang in setup on a cluster, which only a real run can catch.
2. **More of the plan is backed by a real test or a check of the existing suite: 37% of test cases vs 34%.**
   QualityFlow leans on the team's existing tests more: 74 "already tested" claims, of which 51 hold.
3. **Every acceptance criterion is in the plan: 62 of 62** on the 8 tickets that list them.
4. **Weakest spot: 6 "already tested" claims are false.** Some name tests that do not exist. A check now fails
   any claim whose test is not in the checkout
   ([#193](https://github.com/redhat-community-ai-tools/qualityflow/pull/193)).

| 10 tickets | Run 7 | Run 10 |
|---|---|---|
| Plan test cases / expecting behaviour that never shipped | 192 / 30 (16%) | 182 / 24 (13%) |
| Tests written / loading | 89 / 89 | 48 / 46 |
| Real / weak / hollow / wrong | 25 / 32 / 1 / 31 (35%) | 16 / 19 / 0 / 13 (27%) |
| "Already tested" claims: hold / partial / false | 41 / 5 / 0 of 46 | 51 / 17 / 6 of 74 |
| Test cases with a real test or a claim that holds | 66 of 192 (34%) | 67 of 182 (37%) |
| Declined / avoidably | 57 / 11 | 60 / 11 |
| Acceptance criteria covered by the plan | not measured | 62 of 62 |

"Loading" counts tests that would get past setup; RHAIRFE-1487's two hanging tests do not.

## Per ticket (run 10)

"Real" means the test drives the product and checks what its test case expects, judged by reading it (not
"passed"). "Unshipped" counts plan cases that expect behaviour the shipped code does not have.

| Ticket | Feature | Plan cases (unshipped) | Tests: real / weak / wrong | Already-tested claims: hold / partial / false | Declined (avoidable) | Acceptance criteria covered |
|---|---|---|---|---|---|---|
| [RHAISTRAT-2493](RHAISTRAT-2493/shipped-code/) | vLLM-Omni serving | 29 (1) | 11: 4 / 5 / 2 | 8: 5 / 2 / 1 | 10 (3) | 8/8 |
| [RHAIENG-7604](RHAIENG-7604/shipped-code/) | OGX DB migration CLI for Praxis | 7 (1) | 1: 1 / 0 / 0 | 4: 3 / 1 / 0 | 2 (1) | 7/7 |
| [RHAISTRAT-1245](RHAISTRAT-1245/shipped-code/) | remote::gemini provider in OGX | 28 (2) | 0: 0 / 0 / 0 | 22: 15 / 5 / 2 | 6 (1) | 9/9 |
| [RHAISTRAT-1246](RHAISTRAT-1246/shipped-code/) | remote::anthropic provider in OGX | 13 (1) | 10: 5 / 4 / 1 | 0: 0 / 0 / 0 | 3 (1) | 9/9 |
| [RHAISTRAT-1061](RHAISTRAT-1061/shipped-code/) | Runtime config in the OGX server CRD | 15 (0) | 7: 0 / 4 / 3 | 7: 1 / 4 / 2 | 1 (1) | none listed |
| [RHAISTRAT-1456](RHAISTRAT-1456/shipped-code/) | AI Gateway support for the Codex Agent SDK | 7 (4) | 1: 0 / 0 / 1 | 0: 0 / 0 / 0 | 6 (0) | 3/3 |
| [RHAIRFE-1487](RHAIRFE-1487/shipped-code/) | MaaS multi-tenancy | 13 (1) | 8: 3 / 3 / 2 | 5: 5 / 0 / 0 | 0 (0) | 8/8 |
| [RHAISTRAT-2418](RHAISTRAT-2418/shipped-code/) | Authorino auth-decision metrics | 14 (12) | 3: 2 / 0 / 1 | 0: 0 / 0 / 0 | 11 (0) | 10/10 |
| [RHOAIENG-70680](RHOAIENG-70680/shipped-code/) | Agent catalog, backend | 41 (2) | 2: 1 / 0 / 1 | 26: 21 / 4 / 1 | 13 (2) | none listed |
| [RHAISTRAT-2277](RHAISTRAT-2277/shipped-code/) | OGX → Praxis migration | 15 (0) | 5: 0 / 3 / 2 | 2: 1 / 1 / 0 | 8 (2) | 8/8 |

## What is in each ticket's `shipped-code/` folder

| File | What |
|---|---|
| `test_plan.md` | the STP QualityFlow wrote on the shipped code |
| `test_cases.yaml` | the STD: test cases, coverage status and the existing tests each claim cites |
| `tests.diff` | the tests QualityFlow wrote, as a diff against the repos |
| `tests_summary.yaml` | what it wrote, declined (`not_implemented`, with reasons) and the product code each test drives |
| `grading.md` | every test, decline, claim and acceptance criterion checked against the shipped code, with `file:line` |

People's names are replaced with `[Name]` and their handles with `@[handle]`.
