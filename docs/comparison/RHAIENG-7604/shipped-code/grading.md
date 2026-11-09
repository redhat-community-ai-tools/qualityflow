# RHAIENG-7604 (Praxis migration ownership fields): run 10 grading (QF main 3b7ffa3, GLM 5.3)

Product: `ogx` at e121b2c5 (cited `ogx:`; migration CLI in `src/ogx/cli/migrate/praxis/`). Suite: opendatahub-tests at 7ffaaccc (cited `odh:`).
R = <local> O = R/qf/outputs/RHAIENG-7604. QF test: `odh:tests/ogx/praxis/test_qf_praxis_ownership_migration.py` (cited `T:`).
The checkout's only change is that added file; no conftest was touched.

The OGX operator (RHAIENG-7605) is not among this ticket's checkouts. Two scenarios need it, so I read it read-only in another ticket's checkout:
`<local>` at 2f5096a (cited `op:`). That commit contains #381, the fallback PR the plan cites (4af7275).

## Shipped behaviour the grading relies on

- **Tenant:** a non-empty source `tenant_id` wins (trimmed); otherwise `--fallback-tenant` applies; otherwise `TenantDerivationError` is raised (ogx:target.py:146-154).
- **Owner:** a non-empty `owner_principal` wins; otherwise `--fallback-owner-subject`; otherwise `OwnerSubjectDerivationError` (target.py:163-172).
- **Issuer:** defaults to `urn:rhoai:ogx:production` (target.py:54, cmd.py:343-348).
- **Target columns:** `tenant_id`, `owner_subject` and `owner_issuer` on responses (key `id`) and on conversations (key `conversation_id`) (target.py:176-224).
- **Row errors fail the run:** they are re-raised (reader.py:196-199), logged, and the CLI exits 1 (cmd.py:361-366).
- **Tenancy:** the source `tenant_id` column exists only when tenancy is enabled ("never created in DISABLED mode", reader.py:43-51; authorized_sqlstore.py:190-191).
  - DISABLED is the default (ogx:src/ogx/core/datatypes.py:236; distribution `OGX_TENANCY_MODE:=disabled`, src/ogx/distributions/ci-tests/config.yaml:381-383).
  - The operator leaves tenancy unchanged (op:pkg/config/generator.go:112,352).
  - The suite sets no tenancy anywhere under tests/ogx (grep: 0 hits).
- **Operator:**
  - It omits `--fallback-*` when the CR field is empty, and shell-quotes the value otherwise (op:controllers/migration_job.go:57-62).
  - It treats a Job that completed under an older attempt key as terminal: no new attempt starts (migration_job.go:594-599,615-621).
  - It reruns after a fallback change only when the previous Job failed.

## 1. QF tests (1)

Loads: collected 1, `--setup-plan` clean (loading/RHAIENG-7604.md).

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| T::TestPraxisOwnershipMigration::test_operator_migration_applies_fallback_ownership | TS-03 operator migration: present ownership kept, absent uses fallbacks, issuer is production | REAL | **What it does:** uses the suite's own migration fixtures (`praxis_migration_runner`, both Postgres pods; odh:tests/ogx/praxis/conftest.py:248-281), whose Job sets fallbacks `test-tenant`/`test-owner` (odh:tests/ogx/praxis/migration.py:63-64; constants.py:52-53). It blanks one response's tenant and owner and gives one conversation `source-tenant`/`source-owner` (T:118-135). After the migration it asserts fallbacks on the response, preserved values on the conversation, and the production issuer on both (T:181-186). That matches target.py:146-172 and :54, with the real target columns (target.py:176-224). **Caveat:** the `UPDATE … SET tenant_id` and `SELECT tenant_id` (T:35-40, 118-135) need a tenancy-enabled source. On the default (DISABLED, above) that column does not exist, so the test would error before the migration. The deployed distribution's tenancy mode is not in either checkout, so this stays a caveat (as in run 7) |

## 2. not_implemented (2)

| scenario | class | evidence (one line) |
|---|---|---|
| TS-04 Job fails with a clear missing-fallback reason, no incomplete rows | AVOIDABLE | QF says the operator Job interface is missing and that `run_migration` always sets both fallbacks. **The interface is in the suite:** the CR fields `fallbackTenant`/`fallbackOwnerSubject`, the Job name `<server>-praxis-migration` and the Job-condition wait are all at odh:tests/ogx/praxis/migration.py:42-70,85-95. A test can patch the OGXServer without a fallback and wait for condition `Failed` (ocp `wait_for_condition` takes any type). **The failure is shipped:** target.py:150-153 and :167-171, re-raised at reader.py:196-199 before the batch write (conversations.py:86 vs :152), logged with the message, exit 1 (cmd.py:361-366). The operator omits the flag when the field is empty (op:migration_job.go:57-62). Run 7's QF wrote this test |
| TS-06 rerun after both fallbacks change on a completed migration, no duplicates | JUSTIFIED | QF's stated reason (the suite helper is not configurable) is not the real one. **The real reason:** the expected outcome is not shipped. After a Job completes, a changed fallback leaves the completed attempt in place and no new Job starts (op:migration_job.go:594-599,615-621). The operator's own test asserts exactly that, with the same `target-tenant`/`target-owner` values (op:controllers/migration_job_test.go:481-526) |

## 3. existing_coverage (4 scenarios marked EXISTING_COVERAGE)

All named tests exist and call the real product code, with no mocks.

| scenario | named test(s) | verdict | evidence |
|---|---|---|---|
| TS-01 source tenant and owner preserved | test_tenant.py::test_tenant_id_column_takes_precedence_when_present; test_owner.py::test_source_owner_principal_takes_precedence | VERIFIED | `TenantDeriver(...).derive(_, "tenant-a") == "tenant-a"` (ogx:tests/unit/cli/migrate/test_tenant.py:15-18) and `OwnerSubjectDeriver(...).derive("source-owner") == "source-owner"` (test_owner.py:14-17). Every transform uses these derivers (target.py:382-383,408,422) |
| TS-02 every row has owner_issuer `urn:rhoai:ogx:production` | test_issuer.py::test_default_owner_issuer_is_a_valid_urn; test_transforms.py::test_custom_owner_issuer_is_copied_to_every_target_row | PARTIAL | **What the named tests check:** one checks only that the default constant is a valid URN (test_issuer.py:14-15). The other passes a *custom* issuer to all five row kinds (test_transforms.py:430-469). Neither asserts the production default on rows. **Unnamed tests do:** test_transforms.py:163-169 and test_cmd.py:24-30 close it |
| TS-05 invalid fallback tenant and blank owner rejected | test_tenant.py::test_invalid_fallback_tenant_rejected; test_owner.py::test_missing_or_blank_fallback_is_rejected | VERIFIED | `"Not Valid!"` raises ValueError naming `fallback-tenant` (test_tenant.py:56-58). `""` and `"   "` raise naming `fallback-owner-subject … non-empty` (test_owner.py:33-36). Both derivers are built before any I/O (cmd.py:128-129) |
| TS-07 fallback values shell-quoted in dry-run and live commands | op:controllers/migration_job_test.go::TestReconcileMigration_FallbackArguments | VERIFIED | It covers four cases: omitted, tenant only, owner only, and both with `'`, `$(…)`, `;`. It asserts each quoted flag appears exactly twice, once in the dry-run and once in the live command, and is absent when omitted (op:migration_job_test.go:189-234; quoting at migration_job.go:57-62). Verified in the operator checkout named above, which is not one of this ticket's own checkouts |

**PARTIAL_COVERAGE claims (not counted in covered=):**
- TS-03 cites test_db_migration.py as "parity but no ownership columns". Accurate: it compares only created_at/model/metadata (odh:tests/ogx/praxis/test_db_migration.py:36-43,118-135).
- TS-06 cites `TestReconcileMigration_FallbackChangeStartsNewAttempt` as "fallback changes create a new attempt key". Misleading: that test first marks the Job failed (op:migration_job_test.go:706), and after a completed Job no new attempt starts (:481-526).

## 4. The plan

- **1 of 7 scenarios expects behaviour the shipped code does not have: TS-06.**
  - It expects a completed migration to rerun after the fallbacks change.
  - The shipped operator keeps the completed attempt (op:migration_job.go:615-621).
  - The plan's "updated" example values come from the operator test that asserts no rerun (std yaml source_constants; op:migration_job_test.go:505-506).
- **Loose but not counted:**
  - Calling the issuer "fixed": `--owner-issuer` overrides it (cmd.py:343-348).
  - TS-03 presupposes a source with a `tenant_id` column without saying tenancy must be enabled (reader.py:43-51).
- **Shipped behaviour the plan misses:**
  - `--owner-issuer` URN validation (target.py:106-111).
  - `--fallback-tenant` lower-casing (target.py:87).
  - The `openai_conversations`/`conversation_messages` tenant-mismatch error (target.py:410-416).
  - `--continue-on-error` being dry-run only (cmd.py:124-125).
  - Conversation items: the `openai_conversation_items` target table, which shares the derivers, is never asserted.

## 5. Acceptance criteria

7 bullets in `main_issue.acceptance_criteria`, numbered in order.

| AC | text (short) | verdict | plan scenario |
|---|---|---|---|
| AC-1 | target tenant_id = source tenant_id when present and non-empty | COVERED | TS-01 (and TS-03) |
| AC-2 | target tenant_id = `--fallback-tenant` when source has none | COVERED | TS-03 |
| AC-3 | clear error when tenant missing and no fallback | COVERED | TS-04 (CLI level also unit-tested, test_tenant.py:37-43) |
| AC-4 | all target rows have owner_issuer `urn:rhoai:ogx:production` | COVERED | TS-02 (and TS-03) |
| AC-5 | owner_subject = source owner_principal when present | COVERED | TS-01 (and TS-03) |
| AC-6 | owner_subject = `--fallback-owner-subject` when absent | COVERED | TS-03 |
| AC-7 | clear error when owner missing and no fallback | COVERED | TS-04 (CLI level also unit-tested, test_owner.py:43-45) |

SCORE RHAIENG-7604 | QF tests=1 real=1 weak=0 hollow=0 wrong=0 loads=1 declined=2 justified=1 avoidable=1 cases=7 real_cases=1 covered=4 verified=3 partial=1 false=0 plan_wrong=1 acs=7 ac_covered=7 ac_out_of_scope=0 ac_missed=0
