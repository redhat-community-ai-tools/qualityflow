# Test Plan Generator vs QualityFlow

*2026-10-26; test writing and shipped-code runs added 2026-11-04. 10 tickets, every test case and every generated test checked against
the code that later shipped.*

## Bottom line

- **QualityFlow is wrong far less often** (17% vs 44% of test cases), because it plans against the code that exists.
- **Coverage is the same** (103 vs 101 of 129 requirements).
- **QualityFlow finds 5x more real problems** (15 vs 3): places where the ticket disagrees with the code, and weak existing tests.
- **Writing the tests, both get about 40 useful ones; the generator adds 250 that need work.** QualityFlow's tests all
  load and none is hollow; it declines more cases instead ([Writing the tests](#writing-the-tests)).
- **Once the code has shipped, QualityFlow tells you what is already tested.** After this week's fixes, 41 of its 46
  "already covered" claims hold and none is false ([Once the code ships](#once-the-code-ships)).

| | Test Plan Generator | QualityFlow |
|---|---|---|
| Wrong test cases | 44% | 17% |
| Requirements covered | 101 of 129 | 103 of 129 |
| Real problems found | 3 | 15 |

The table compares the plans. Each tool then wrote tests from its own plan: see [Writing the tests](#writing-the-tests).

## Actions

| # | Action | Owner |
|---|---|---|
| 1 | Plan against the existing code, not only the strategy text, to cut the 44% wrong test cases | Test Plan Generator team |
| 2 | Fix the 4 broken tests listed below | opendatahub-tests owners |
| 3 | Use QualityFlow to plan before the code exists: fewer wrong test cases, more problems found | Teams choosing a tool |
| 4 | Place generated tests where the suite's fixtures load, check they collect, and do not copy existing tests | Test Plan Generator team |
| 5 | Write the 51 tests QualityFlow declined that the suite could support | QualityFlow maintainers |
| 6 | Fail a test that imports the team's own tests; leave out scenarios that wait on a held, unmerged PR | QualityFlow maintainers |

## Broken tests in opendatahub-tests (each verified)

1. vLLM-Omni latency test fails only above 3.5 s; the ticket says 350 ms at the Route (`vllm_omni/constant.py`; raised on #2246, still open).
2. Gemini `test_config_conditional_activation_pattern` checks `${env.GEMINI_API_KEY:+gemini-inference}`; the shipped config has `${env.ENABLE_GEMINI:+gemini}`, so it fails.
3. MaaS token rate-limit test passes when nothing is throttled (`require_429=False`, `test_maas_token_rate_limits.py:60`).
4. Praxis tenant-isolation tests call the OGX route and set `x-tenant-id` themselves, so they never go through Praxis.

## Writing the tests

*2026-11-04. Each tool wrote tests from its own plan for the same 10 tickets, with the same model and setup: GLM 5.3
through Red Hat's EnMaaS gateway (free), via Codex, sandboxed, no network, against opendatahub-tests and each product
repo as shipped. QualityFlow used `/generate-tests`; the generator its own `test-plan-case-implement` skill (written
for Claude, run under Codex here so both had the same model). Every test was read against its plan case and the shipped code; none was run on a cluster.*

| | Test Plan Generator | QualityFlow |
|---|---|---|
| Tests written | 291 | 123 |
| Real: drives the product, checks the expected outcome | 63 | 42 |
| Real, loads, and not a copy of an existing test | 40 | 39 |
| Wrong: expects behaviour or names the code does not have | 120 (41%) | 34 (28%) |
| Hollow: never touches the product | 46 | 0 |
| Does not load (missing fixtures) | 77 | 0 |
| Plan cases with no test | 1 | 147 (51 could have had one) |

- **Same number of useful tests, very different clean-up.** Besides its 40, the generator's tests are often wrong,
  placed where the suite's fixtures do not load, re-bind the team's tests (33 on RHAISTRAT-2493), or copy them
  (20 of 24 on RHAISTRAT-1245). QualityFlow checks that each test loads and touches the product before it finishes.
- **QualityFlow's gap is declines.** 96 of its 147 are right (the feature did not ship, or nothing can drive it);
  51 had what they needed in the product or the suite.
- **The model is the ceiling for both.** On gpt-5.6-luna the same setup gave QualityFlow 14 real tests and the
  generator 4 that load.

## Once the code ships

*2026-11-04, QualityFlow only. Its normal flow once the feature has merged: a new plan from Jira, the feature's
GitHub PRs and LSP on the shipped code, then `/generate-tests`. Same 10 tickets, same model (GLM 5.3, free). Run
twice: before and after the fixes #180, #183 and #184 (now merged, with #185). The generator was not re-run.*

| | Before the fixes | After |
|---|---|---|
| Test cases | 177 | 192 |
| "Already covered by a shipped test" (verified / partial / false) | 47 (28 / 13 / 6) | 46 (41 / 5 / 0) |
| New tests: real / wrong | 38 / 33 of 98 | 25 / 31 of 89 |
| New tests that load / hollow | 98 / 0 | 89 / 1 |
| Declines: justified / avoidable | 29 / 4 | 46 / 11 |
| Cases with a real new test or a verified existing one | 37% | 34% |

- **The coverage claims are what a team can rely on to skip work, and none is false now.** The fixes also stopped
  tests written for code that was only in an unmerged PR (RHAISTRAT-2418: 13 wrong tests, now 0).
- **Test bodies are the model's ceiling.** Run to run, two tickets swung on one setup mistake each (a fixture never
  requested; a wait on a Job `phase`, which Jobs do not have). The offline check cannot see those; a stronger model
  or a live run can.

## Details

**Full numbers.** Wrong test cases: generator 121 of 277, QualityFlow 45 of 270. Without MaaS multi-tenancy,
QualityFlow is wrong on 12 of 237 (5%): all 33 of its MaaS test cases use the `Tenant` resource the code had in May,
and the feature later shipped as `AITenant`. Without the solution, QualityFlow made the generator's kind of mistake, once.

**Once the code exists.** With today's code and the merged feature PRs, QualityFlow got 2 of 282 wrong (<1%),
114 of 129 covered, 38 problems found. That is re-checking a plan after implementation, a
different job from planning before it.

## Method

- **Fair comparison:** QualityFlow got each product repo and opendatahub-tests as they were the day the generator
  wrote its plan, before the feature merged (two snapshots moved back to the commit before the implementation), and
  no GitHub access, so it could not read the feature's PRs. It read Jira (as of today) and traced the code with LSP.
  Cheap model: gpt-6.1-sol via Codex, $21 for all 10.
- Same count-based scorecard for both tools, per test case, against the shipped code. The per-ticket scoring
  evidence is kept by the QualityFlow maintainers; ask for it.
- The generator's outputs are its published plans; it was not re-run.
- Caveats: Jira was read as it is today, so later comments may mention the implementation; LSP was ok or partial on
  9 tickets (the Go language server timed out on parts of large repos); this run was scored by Codex, earlier rounds by Claude.
- **Writing the tests:** graded by Claude with one rubric (real / weak / hollow / wrong per test; a test that only
  calls a team test counts as hollow), loading by the same mechanical check for both (`pytest --setup-plan` in the
  checkout's own environment, `go test -c` for Go), copies by comparing each new test with the suite's existing ones
  (80% similar or more). Three runs were repeated: QualityFlow's RHAIENG-7604 timed out at 30 minutes and re-ran with
  60; the generator's RHAISTRAT-1245 was cut off by the gateway; QualityFlow's RHOAIENG-70680 found an earlier run's
  test in the shared folder and copied it, so it re-ran in an isolated folder. Per-test evidence is kept by the
  QualityFlow maintainers.

### The tickets

All 10 plans in the generator's current format in
[opendatahub-io/opendatahub-test-plans](https://github.com/opendatahub-io/opendatahub-test-plans): 7 published, 3 in
open PRs. Left out: 4 older-format plans (MCP catalog, Python client signing, Models-as-a-Service, PR #13 GPU runtimes).

| Ticket | Feature | Generator plan date | Product repo QF read |
|---|---|---|---|
| RHAISTRAT-2493 | vLLM-Omni serving | 2026-08-11 | odh-model-controller |
| RHAIENG-7604 | OGX DB migration CLI for Praxis | 2026-09-25 | ogx |
| RHAISTRAT-1245 | remote::gemini provider in OGX | 2026-06-05 | ogx |
| RHAISTRAT-1246 | remote::anthropic provider in OGX | 2026-08-17 (PR #19) | ogx |
| RHAISTRAT-1061 | Runtime config in the OGX server CRD | 2026-06-16 | ogx-k8s-operator |
| RHAISTRAT-1456 | AI Gateway support for the Codex Agent SDK | 2026-06-12 | ogx |
| RHAIRFE-1487 | MaaS multi-tenancy | 2026-05-13 | models-as-a-service |
| RHAISTRAT-2418 | Authorino auth-decision metrics | 2026-08-14 (PR #18) | models-as-a-service |
| RHOAIENG-70680 | Agent catalog, backend | 2026-07-07 | model-registry |
| RHAISTRAT-2277 | OGX → Praxis migration | 2026-08-11 (PR #16) | ogx-k8s-operator |
