# RHAISTRAT-2277 — QualityFlow round 6

Scored read-only against shipped operator `e94d19d` and OGX `f27e1991`; duplicate baseline is the ticket's pre-feature opendatahub-tests snapshot `e4f8a60a23af75e1fda2c67c20414fd298e5cd90`, not current main. Counted all 35 STD `scenarios[]` entries (35 NEW). Generator and round-4 scores are copied from the supplied scorecards.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| 1. Wrong / total | 2/10 | 0/35 | **2/35** |
| 2. Redundant / total | 0/10 | 0/35 | **0/35** |
| 3. Requirements covered / total | 13/19 | 17/19 | **15/19** |
| 4. Runnable as written / after TBDs / total | 2/—/10 | 0/0/10 sampled | **0/0/10 sampled** |
| 5. Verified problems found | 0 | 5 (4 if grouped) | **2** |

**1. Wrong:** STD TS-17 explicitly says “Execute migration and cutover while writes continue”; TS-18 repeats this for concurrent writes and expects consistent resource versions. Shipped `ogx-k8s-operator/docs/upgrade-praxis-migration.md:84–88` requires an operational write freeze before enabling the migration Job. These are two unsupported execution procedures, not merely missing values.
The CLI copies records using `INSERT … ON CONFLICT DO NOTHING` (`ogx/src/ogx/cli/migrate/praxis/target.py:507–537`); it supplies no continuous synchronization of concurrently changed source records. TS-17/18's audit/concurrency TBDs do not supply the missing freeze.
Not counted: TS-32's post-write recovery policy and TS-33's unsafe-rollback criteria/rejection contract remain TBD; the shipped webhook warns rather than automatically rejecting disablement (`api/v1beta1/ogxserver_webhook.go:65–74`). Greenfield TS-01 does not specify omitted `praxisMode`, so default automatic enablement is not inferred. Praxis-only error/header/citation contracts could not be verified from these checkouts.

**2. Redundant:** All 35 NEW scenarios exercise the Praxis boundary, migration, recovery, or associated documentation; none is already asserted by the snapshot tests. Snapshot `tests/ogx/conftest.py:292–298` constructs the client against `ogx_test_route`, and a search of snapshot `tests/ogx` finds no Praxis integration.
Partial overlap only: TS-04/11 reuse Responses/embedding behavior from `test_responses_create` and `test_inference_embeddings`; TS-20 overlaps OGX-direct RAG and the pre/post-upgrade RAG tests. Their public-boundary and transition requirements remain new.

**3. Covered:** R1→01/34; R2→02; R3→11; R4→14; R5→13; R6→20/21 (STP explicitly scopes these to existing documents); R7→17/18; R8→15; R9→03/28; R10→23; R11→32/33; R12→05; R13→06; R15→29/30; R16→26/27. Wrong or conditional scenarios still count as targeted coverage under part2's rules.
Missing: R14 (explicit accessibility of existing OGX embeddings data), C1 (migration Job and `status.migration` cutover gates), C2 (Praxis mode off by default), C3 (startup guard for unmigrated DB). Generic inventory, interruption, and guide scenarios do not explicitly test those contracts.

**4. Runnable:** Used `random.seed(2277); random.sample(range(1,36),10)` over alphabetically sorted test IDs because 35 > 20. Sorted sample: **003, 004, 005, 008, 017, 022, 023, 027, 031, 034**; 0 runnable now, 0 runnable merely after answering TBDs.
003/004/005/008 lack concrete requests, payloads, or event names; 017 lacks executable migration/write/audit steps and contradicts the freeze; 022/023/027 lack requests and migration/ACL procedures; 031 lacks fault-injection/export commands; 034 delegates execution to an unspecified guide. Even supplying header names, schemas, or policy answers leaves prose procedures requiring implementation. No cluster tests were run.

**5. Problems found:** (1) The parent routing-only/no-state-migration strategy conflicts with runtime-state migration and ownership. QF explicitly raises this in STP I.1/I.3 (“RHAIENG-6598 … schema conversion”) and rejects an unconditional five-minute routing rollback. Verified by shipped migration doc scope and soft-rollback sections; grouped as one ticket/design contradiction, not credited as discovery of the unseen soft-rollback implementation.
(2) Existing direct-OGX coverage does not establish Praxis transition/state continuity. QF raises this in STP II.2 and regression YAML `existing_coverage_notes`; snapshot client construction and OGX-direct upgrade RAG test (`test_upgrade_vector_store_rag.py:116`) confirm the gap. Counted once as an untested transition behavior, not once per proposed test. Unresolved targets, mechanisms, and policy questions receive no problem credit.

**LSP and solution visibility:** `stp/RHAISTRAT-2277_regression_analysis.yaml:1` reports **`lsp_status: ok`**; its notes say “Repo-rooted lsp_source and lsp_tests definitions/references succeeded” and “Praxis repo is not configured or checked out; no Praxis-side trace claimed.” Branch evidence records operator snapshot `24979da83050062fe8c03aa5c9b6466701128440` and tests snapshot `e4f8a60a23af75e1fda2c67c20414fd298e5cd90`.
No clear sign of solution-code exposure found in the scored output. The closest solution-like statement is STD `source_decisions`: “RHAIENG-6598 supersedes the parent routing-only model: migrate Responses and Conversations schema in place; Praxis owns their writes.” It is explicitly Jira-derived; no shipped migration Job fields, condition names, soft-rollback flag, or startup-guard implementation is claimed. STP instead states “Praxis implementation, migration executor and gateway repositories are outside the available checkouts.”

SUMMARY | RHAISTRAT-2277 | wrong 2/35 | redundant 0/35 | covered 15/19 | runnable 0/10 | problems 2
