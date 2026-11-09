# QualityFlow vs Test Plan Generator: results

*10 tickets. Both tools planned each one, then wrote tests from their own plan with the same model
(GLM 5.3 through Red Hat EnMaaS, free). Every test case and every test was checked one by one against the code
that shipped. No test was executed: each one was loaded offline (`pytest --setup-plan` / `go test -c`, which
resolve fixtures and compile without running anything) and graded by reading it against the shipped code.
Method and details: [test-plan-generator-comparison.md](../test-plan-generator-comparison.md).*

## Bottom line

1. **QualityFlow's plans are wrong far less often: 17% of its test cases vs 44%.** It reads the product code;
   the generator plans from the strategy text. Coverage is the same (103 vs 101 of 129 requirements).
2. **QualityFlow finds 5x more real problems: 15 vs 3.** These are places where the ticket and the code disagree,
   and existing tests that cannot fail. Four existing tests in opendatahub-tests are broken
   ([list](../test-plan-generator-comparison.md#broken-tests-in-opendatahub-tests-each-verified)).
3. **Both write about 40 useful tests. The generator adds about 250 that need fixing or deleting.** Counting
   good tests that load and are not copies of the team's existing ones: 40 vs 39. Of the generator's 291 tests,
   120 are wrong, 77 fail to load and 46 test nothing. QualityFlow's 123 all load and all touch the product; 34 are
   wrong. It skips more cases instead: 147, a third of them avoidably.
4. **Neither tool's tests can be merged unreviewed. The model is the limit.** A stronger model helps both.

**Use QualityFlow to plan. Review any generated test before it merges.**

QualityFlow alone on the same tickets once the code shipped, with this week's fixes: [shipped-code.md](shipped-code.md)
(27% of its tests wrong, down from 35%; every acceptance criterion in the plan).

## Per ticket

"Good" means the test drives the product and checks what its test case expects, judged by reading it against
the shipped code (no test was run, so "good" does not mean "passed"). "Fails to load" means the test would crash
before it starts, e.g. a missing fixture or an import error.

| Ticket | Feature | Plan: wrong cases, generator | Plan: wrong cases, QualityFlow | Good tests (gen / QF) | Wrong tests (gen / QF) | Fails to load (gen / QF) |
|---|---|---|---|---|---|---|
| [RHAISTRAT-2493](RHAISTRAT-2493/) | vLLM-Omni serving | 13/51 | 0/29 | 3 / 4 | 6 / 1 | 58 / 0 |
| [RHAIENG-7604](RHAIENG-7604/) | OGX DB migration CLI for Praxis | 0/4 | 0/16 | 4 / 0 | 0 / 14 | 0 / 0 |
| [RHAISTRAT-1245](RHAISTRAT-1245/) | remote::gemini provider in OGX | 5/24 | 1/24 | 14 / 7 | 2 / 1 | 0 / 0 |
| [RHAISTRAT-1246](RHAISTRAT-1246/) | remote::anthropic provider in OGX | 2/16 | 1/24 | 6 / 6 | 4 / 0 | 19 / 0 |
| [RHAISTRAT-1061](RHAISTRAT-1061/) | Runtime config in the OGX server CRD | 35/44 | 0/27 | 2 / 7 | 41 / 1 | 0 / 0 |
| [RHAISTRAT-1456](RHAISTRAT-1456/) | AI Gateway support for the Codex Agent SDK | 19/27 | 1/22 | 5 / 5 | 17 / 2 | 0 / 0 |
| [RHAIRFE-1487](RHAIRFE-1487/) | MaaS multi-tenancy | 22/27 | 33/33 | 10 / 6 | 14 / 1 | 0 / 0 |
| [RHAISTRAT-2418](RHAISTRAT-2418/) | Authorino auth-decision metrics | 0/27 | 3/24 | 0 / 0 | 20 / 0 | 0 / 0 |
| [RHOAIENG-70680](RHOAIENG-70680/) | Agent catalog, backend | 23/47 | 4/36 | 19 / 5 | 13 / 14 | 0 / 0 |
| [RHAISTRAT-2277](RHAISTRAT-2277/) | OGX → Praxis migration | 2/10 | 2/35 | 0 / 2 | 3 / 0 | 0 / 0 |
| **Total** | | **121/277 (44%)** | **45/270 (17%)** | **63 / 42** | **120 / 34** | **77 / 0** |

QualityFlow's MaaS plan (RHAIRFE-1487) is all wrong for one reason. It was made from the code as it was in May,
when the resource was `Tenant`; the feature shipped as `AITenant`. Without that ticket, 12 of 237 (5%) are wrong.

## What is in each ticket's folder

| File | What it is |
|---|---|
| `qualityflow/test_plan.md` | QualityFlow's test plan (STP) |
| `qualityflow/test_cases.yaml` | QualityFlow's test cases (STD) |
| `qualityflow/tests.diff` | the tests QualityFlow wrote, as a diff against the repos |
| `qualityflow/tests_summary.yaml` | which cases got a test, and why the others did not |
| `generator/plan/` | the generator's published plan and test cases |
| `generator/tests.diff` | the tests the generator wrote |
| `grading_plans.md` | every plan test case checked against the shipped code, with file:line |
| `grading_tests.md` | every test checked, with file:line |
| `shipped-code/` | QualityFlow's plan, test cases, tests and grading on the shipped code ([results](shipped-code.md)) |

People's names are replaced with `[Name]`.
