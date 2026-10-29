# Test Plan Generator vs QualityFlow

*2026-10-26. 10 tickets, every test case checked against the code that later shipped.*

## Bottom line

- **QualityFlow is wrong far less often** (17% vs 44% of test cases), because it plans against the code that exists.
- **Coverage is the same** (103 vs 101 of 129 requirements).
- **QualityFlow finds 5x more real problems** (15 vs 3): places where the ticket disagrees with the code, and weak existing tests.

| | Test Plan Generator | QualityFlow |
|---|---|---|
| Wrong test cases | 44% | 17% |
| Requirements covered | 101 of 129 | 103 of 129 |
| Real problems found | 3 | 15 |

This compares the plans. Test implementation is not compared: QualityFlow writes plan-level steps and implements
them in its own test-generation step, once the plan is right.

## Actions

| # | Action | Owner |
|---|---|---|
| 1 | Plan against the existing code, not only the strategy text, to cut the 44% wrong test cases | Test Plan Generator team |
| 2 | Fix the 4 broken tests listed below | opendatahub-tests owners |
| 3 | Use QualityFlow to plan before the code exists: fewer wrong test cases, more problems found | Teams choosing a tool |

## Broken tests in opendatahub-tests (each verified)

1. vLLM-Omni latency test fails only above 3.5 s; the ticket says 350 ms at the Route (`vllm_omni/constant.py`; raised on #2246, still open).
2. Gemini `test_config_conditional_activation_pattern` checks `${env.GEMINI_API_KEY:+gemini-inference}`; the shipped config has `${env.ENABLE_GEMINI:+gemini}`, so it fails.
3. MaaS token rate-limit test passes when nothing is throttled (`require_429=False`, `test_maas_token_rate_limits.py:60`).
4. Praxis tenant-isolation tests call the OGX route and set `x-tenant-id` themselves, so they never go through Praxis.

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
