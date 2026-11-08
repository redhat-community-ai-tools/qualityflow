# RHAIENG-7604 — round 6

Scored all 16 STD scenarios (14 integration, 2 e2e; all NEW); no sampling required. Applied the counting rules and seven ACs in `h2h-round2/neutral/part1.md`. Generator and round 4 figures are carried from that scorecard and `h2h-round4/score-part1.md` respectively. Runnable columns give **now / after answering explicit TBDs / total**.

| Metric | Generator | QF round 4 | QF round 6 |
|---|---|---|---|
| Wrong test cases / total | 0/4 | 0/19 | **0/16** |
| Redundant new cases / total | 0/4 | 0/19 | **0/16** |
| Requirements covered / total | 7/7 | 7/7 | **7/7** |
| Runnable now / after TBDs / total | 0 / 0 / 4 | 11 / 11 / 19 | **0 / 0 / 16** |
| Verified real problems found | 0 | 2 | **0** |

Evidence paths below use `S = <local>`; QF files are under `h2h-round6/qf/RHAIENG-7604/`.

**Wrong — 0/16.**
- STD TS-01–06 and TS-09–14 correctly assert source identity precedence, explicit fallback use and failure without the corresponding fallback. Shipped `S/repos/ogx/src/ogx/cli/migrate/praxis/target.py:146–172` implements these rules; transformations at lines 361–503 apply them across the five listed paths.
- TS-07/08 assert `urn:rhoai:ogx:production`, matching `target.py:54`. The flags exist in `cmd.py:329–348`; operator Job fallback wiring and failure propagation match `S/repos/ogx-k8s-operator/controllers/migration_job.go:54–67`.
- No whitespace-only or atomic rollback assertion is imposed. Whitespace and skip-errors are explicit open questions; unspecified fallback values and TBD commands are not wrong cases. Exact-equality assertions are weak for padded source values because the shipped derivers trim them, but no padded input is prescribed.

**Redundant — 0/16.**
- Searched the snapshot `S/snap/RHAIENG-7604/opendatahub-tests/tests` for fallback flags, ownership fields and Praxis migration. No test asserts this database ownership mapping; this older snapshot does not even contain `tests/ogx/praxis/`.
- Its Praxis AITenant tests exercise MaasTenantConfig payload-processing migration, a different mechanism. The source-repo unit test `test_tenant_id_column_takes_precedence_when_present` is outside the metric's opendatahub-tests scope.

**Covered — 7/7.**
- AC1 → TS-01/02; AC2 → TS-03/04; AC3 → TS-05/06; AC4 → TS-07/08; AC5 → TS-09/10; AC6 → TS-11/12; AC7 → TS-13/14. TS-15/16 add operator upgrade coverage.
- This is the same seven-AC denominator as the earlier rounds. Invalid fallback tenant, invalid issuer, continue-on-error misuse and nonzero dry-run exit on skipped rows are not covered; they are additional implementation validations, not denominator requirements.

**Runnable — 0 now, 0 after explicit TBDs, of 16.**
- Every scenario leaves the CLI prefix/connection options and schema SQL queries unresolved. TS-15/16 additionally leave operator configuration keys and Job identification unresolved. These block execution now.
- Even after those explicit TBDs are answered, all cases retain generic setup such as “Create isolated source history” without seed SQL, an executable fixture or a cited seeding procedure. TS-15/16 also omit the upgrade procedure. This applies the same strict seeding rule that excluded round 4's near-runnable CLI cases; answering TBDs is not permission to invent the remaining procedure.
- The Python stubs add prose only, with `__test__ = False`; they supply no executable seeding or migration implementation. This is a document execution assessment, not a live migration run.

**Problems — 0 verified findings.**
- STP I.1/II.5 raises whitespace and skip-errors questions, and a possible operator/CLI divergence. The shipped code resolves the questions and passes the matching fallback flags; these are ambiguities or prospective risks, not verified defects.
- The regression text says “old tenant tests do not prove the new ownership contract,” accurately describing the pre-feature snapshot. It does not identify a shipped-code coverage defect. Round 4's issuer-override and partial-batch-commit findings are not raised by round 6 and receive no credit here.

**LSP and possible solution exposure.** `stp/RHAIENG-7604_regression_analysis.yaml` reports `lsp_status: partial`: primary source LSP unavailable, text search used; tests-repo LSP verified only the separate AITenant migration. No sign of solution-code exposure found. Its evidence says “Checkout predates the contract; no claim of LSP validation.” The STD labels the correct issuer and fallback flags “Jira acceptance criterion; candidate implementation not available.” `stp/*_github_data.yaml` records merged PR metadata from Jira but `diff_available: false`, empty `file_changes`, and “contents unavailable, not imported.” These show metadata exposure, not solution contents.

SUMMARY | RHAIENG-7604 | wrong 0/16 | redundant 0/16 | covered 7/7 | runnable 0/16 | problems 0
