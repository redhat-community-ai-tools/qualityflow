# RHAIENG-7604 (Praxis migration ownership fields): run 5 grading, both tools on GLM 5.3

Product: `ogx` at e121b2c5 (cited as `ogx:<path>:<line>`; migration CLI in `src/ogx/cli/migrate/praxis/`). Suite:
`opendatahub-tests` 7ffaacc (`odh:`). QF graded from its 60-minute re-run (the first attempt timed out at 30 min).

Shipped behaviour both tools depend on:
- Tenant: a non-empty source `tenant_id` wins; otherwise the fallback; otherwise "Failed to derive tenant_id: source row has no tenant_id and --fallback-tenant was not provided" (`ogx:src/ogx/cli/migrate/praxis/target.py:146-154`). Owner: same logic with the `--fallback-owner-subject` message (`target.py:163-172`). Tenant is derived before owner (`target.py:382-383, 408-421`).
- Every row gets `owner_issuer = urn:rhoai:ogx:production` (`target.py:54,390,425,446,470`).
- A row error aborts the run (`reader.py:196-199`), and the CLI logs `str(exc)` before exiting 1 (`cmd.py:361-366`). So the Job log carries the derivation message.
- Unauthenticated API writes store `owner_principal = ""` and the default tenant or `""` (`ogx:src/ogx/core/storage/sqlstore/authorized_sqlstore.py:98-102`). Both tools stamp identities with SQL instead, which is the right fixture approach. Tenancy mode (whether `tenant_id` exists, `reader.py:43-51`) is not in either checkout and is not held against either tool.

## Run 4's finding: does any QF test seed history now?

No longer true. Every run-5 test seeds through `seed_conversations`/`seed_responses` (`:119-136`) and stamps
`tenant_id`/`owner_principal` on responses, conversations and conversation_messages, plus inline and standalone items,
with SQL (`:139-187`). The new defect is in that same helper. To create an "orphan", `_seed_paths` calls
`seed_responses(..., conversation_id=f"{prefix}-orphan")` (`:130-136`), i.e. `responses.create(conversation="qf-<hex>-orphan")`.
The product rejects that id: it must match `^conv_[0-9a-f]{48}$`
(`ogx:src/ogx/core/conversations/validation.py:9`, enforced at
`ogx:src/ogx/providers/inline/responses/builtin/responses/openai_responses.py:975-980`). Even a well-formed id that
does not exist fails, because the conversation is looked up (`openai_responses.py:373-375` →
`ogx:src/ogx/core/conversations/conversations.py:447-449`). The API cannot create a response in a missing
conversation. The migrator's orphan path is a `conversation_messages` row without an `openai_conversations` row
(`target.py:429-447`), which only a SQL insert can build. All 14 tests call `_seed_paths` first, so every test fails
at `:131` on correct code, before it migrates anything. Each is graded WRONG: its precondition expects the product
to accept a response for a nonexistent, malformed conversation.

Reference only (not scored): with the orphan inserted by SQL, most tests would still fail on correct code.
- Responses sent in a conversation also write `conversation_items` through the API (`openai_responses.py:1464-1468,1815-1833`) with `owner_principal = ""` (`authorized_sqlstore.py:99`). `_seed_paths` never stamps those rows (it updates only responses, conversations and messages, and inserts its own two items), and the items phase migrates them (`target.py:450-471`). Every success-expecting run without an owner fallback (TS-001, 003, 004, 007, 009) would then abort on them.
- One class-scoped OGXServer is shared by all 14 tests, and only the target tables are truncated (`:99-108`). So tenant-less rows seeded by TS-003…006 stay in the source and break later no-tenant-fallback runs.
- The per-record `_assert_seed` (`:314-341`), which checks tenant, owner and issuer on responses, both conversations and both items, is the best assertion design either tool produced for this ticket.

## QualityFlow tests (14, `odh:tests/ogx/praxis/test_qf_praxis_state_ownership.py`, class TestQfPraxisStateOwnership)

All 14 load (collected 14, setup-plan clean).

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| ::test_source_tenants_are_preserved_without_fallback | TS-001 | WRONG | `_seed_paths` (:371) fails at the orphan seed (:131-136), rejected at `openai_responses.py:975-980`. It never reaches the migration |
| ::test_source_tenants_override_fallback | TS-002 | WRONG | Same orphan-seed failure (:412) |
| ::test_missing_and_empty_tenants_use_fallback | TS-003 | WRONG | Same (:451) |
| ::test_mixed_tenants_preserve_source_and_fallback | TS-004 | WRONG | Same (:496) |
| ::test_missing_tenants_fail_without_fallback | TS-005 | WRONG | Same (:541). Its assertions ("--fallback-tenant", "tenant_id" in the Job log, :562-563) match `target.py:151-153`, but it never gets there |
| ::test_unauthorized_tenant_substitution_fails_without_fallback | TS-006 | WRONG | Same (:584) |
| ::test_all_migrated_rows_have_required_owner_issuer | TS-007 | WRONG | Same (:625) |
| ::test_fallback_rows_retain_required_owner_issuer | TS-008 | WRONG | Same (:664) |
| ::test_source_owners_are_preserved_without_fallback | TS-009 | WRONG | Same (:705) |
| ::test_source_owners_override_fallback | TS-010 | WRONG | Same (:746) |
| ::test_missing_and_empty_owners_use_fallback | TS-011 | WRONG | Same (:785) |
| ::test_mixed_owners_preserve_source_and_fallback | TS-012 | WRONG | Same (:830) |
| ::test_missing_owners_fail_without_fallback | TS-013 | WRONG | Same (:875). Its log assertions (:896-897) match `target.py:168-171` |
| ::test_unauthorized_owner_substitution_fails_without_fallback | TS-014 | WRONG | Same (:918) |

## QualityFlow declines (not_implemented: 2)

| plan case | class | evidence |
|---|---|---|
| TS-015 upgraded (3.5 → 3.6) history retains ownership | AVOIDABLE | The reason, "no upgrade harness", ignores the suite's upgrade-lane pattern: seed in a `pre_upgrade` test, assert in a `post_upgrade` one (`odh:tests/ai_safety/evalhub/upgrade/test_evalhub_upgrade.py:34,48`, `odh:tests/model_serving/model_server/upgrade/test_upgrade.py:29-58`). The version pair comes from the lane, not the test. Same verdict as RHAISTRAT-2493 TS-028 |
| TS-016 migration Job fails with a fallback omitted | AVOIDABLE | QF's own `_run_migration(expect_success=False)` and `_migration_job_logs` (:200-276), used by TS-005/013, are this case. Only the 3.5-seeded precondition needs the same upgrade markers |

## Generator tests (4, `odh:tests/update_db_migration_cli_for_praxis_state_ownership_schema_changes/`)

All 4 load (collected 4, setup-plan clean). Each test gets its own namespace and OGXServer: class-scoped fixtures on
module-level functions are per-function. Each seeds only conversations through the API (no responses, so no items
and no messages) and stamps identities with SQL.

| test (file::name) | plan case | class | evidence (one line) |
|---|---|---|---|
| test_e2e_...::test_tc_e2e_001 | TC-E2E-001 | REAL | Two conversations stamped with tenant/owner (:184-193), migration with no fallbacks must Complete (:146-150), then per-row `tenant_id`/`owner_subject` equality and issuer on every target row (:213-231). This is `target.py:146-149,163-166,425` |
| test_e2e_...::test_tc_e2e_002 | TC-E2E-002 | REAL | Row A tenant NULL + owner, Row B tenant + owner NULL (:261-278), both fallbacks. Asserts A → fallback tenant/own owner and B → own tenant/fallback owner (:301-307), plus the issuer on all rows (:316). Matches `target.py:150-154,167-172` |
| test_neg_...::test_tc_neg_001 | TC-NEG-001 | REAL | Tenant NULL + owner, no fallbacks. Job reaches Failed (:131), the log contains "tenant_id" and "fallback" (:183-186; message `target.py:151-153` logged by `cmd.py:363-365`), and the row is not in the target (:188-196). Run 3's unreachable error match is gone |
| test_neg_...::test_tc_neg_002 | TC-NEG-002 | REAL | Tenant set + owner NULL, no fallbacks. Failed Job, the log has "owner_principal" and "fallback" (:240-243; `target.py:168-171`; the tenant is derived first and passes), and the row is absent (:245-253) |

Not held against the generator: each case runs on the conversations path only (no responses or items). The plan's
"same fixture pre- and post-upgrade" precondition is an open gap in its own plan.

## Generator skips

None: all 4 plan cases have a test.

SCORE RHAIENG-7604 | QF tests=14 real=0 weak=0 hollow=0 wrong=14 loads=14 declined=2 justified=0 avoidable=2 cases=16 real_cases=0 | GEN tests=4 real=4 weak=0 hollow=0 wrong=0 loads=4 declined=0 justified=0 avoidable=0 cases=4 real_cases=4
