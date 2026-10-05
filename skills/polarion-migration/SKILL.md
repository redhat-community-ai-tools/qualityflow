---
name: polarion-migration
description: Migrate a team's non-automated Polarion test cases into its tests repo as STD design stubs, driven by the team's profile — a case ledger from the CSV export, agent triage, team review, std-builder stubs placed per team, one tests-repo PR per team, and a Polarion reconciliation proposal for the owner.
model: inherit
---

# Polarion Migration

**User-Invocable:** yes. Run it per export, one stage at a time.

## Purpose

A team moving off Polarion keeps the test cases that are not automated yet,
and gives each one a team-approved outcome: an STD stub in its tests repo, a
link to an existing implemented test, retirement, or a hold. In the end state
every case is **automated** (an implemented test carries its ID) or
**retired**.

The mechanical half is `migrate.py` in this directory, the same engine for
every team. What is particular to a team lives in its **profile**, one YAML
file: how its export spells its fields, which cases are not migrated yet, how
a case reaches its Jira requirement, and its tests repo's conventions.
`profile.example.yaml` documents every key. The judgement calls are an
agent's (W2 triage, W4 placement) and the teams' (W3, the folder map).

## Boundaries

- Nothing here logs in to Polarion, uses a shared account, or writes to
  Polarion, Jira or GitHub. The Polarion owner exports, and applies changes.
- An export is internal data. Keep each run under `outputs/` (git ignores it),
  and send case data only to the model your organization approves for it.
- A tests-repo PR holds reviewed stubs and a summary, never raw export data.
- Each test links the Jira of **its own** requirement; only the module header
  links the team's tracking issue. A case with no confirmed Jira is held until a
  reviewer names it.

## The profile

| Section | Decides |
|---|---|
| `export` | the encoding, the header of every field, the Test Steps table's header words, the Type values, every Status and Automation value and their aliases, importance -> priority |
| `selection` | which cases stay out (`exclude` rules) and which are kept for review only (`review_only`, e.g. manual-only cases) |
| `trace` | where a case's Jira link sits (`via`: on its linked requirement, or on the case), the link roles that count, the Jira base URL and its other host names, the allowed Jira projects |
| `repo` | the tests repo, its default branch, the folder every test sits under, its pull request URL |
| `ids` | the pytest mark that carries an ID, where a stub carries it (`markers` or `decorator`), and the repo's sync (a job that marks a case automated from a merged marker line), if any |
| `stubs`, `scenarios` | the comment a stub's `def` line ends with; the scenario label (tier or test type) |
| `checks`, `pr` | the commands `stage --checks` runs; the PR branch name and lines every PR body adds |
| `end_state` | the values W6 proposes for automated and for retired cases |
| `triage` | what the triage agent needs: the Jira site, its PR field, the product repos, where test plans live |

Every key is required, since an engine default would be some team's value.
`migrate.py check-profile FILE` lists every problem. A team keeps its profile
out of the shared branch: for example in
`config/projects/<project>/polarion-migration/` on its own branch, or in a
repo of its own. `init` freezes it into the run, and every output records its
SHA-256.

## Decision gate

Each of these is a profile value. Choose it before W4; none of them stops
W0–W3.

| Decision | Profile value | Safe choice |
|---|---|---|
| Does a design stub count as automated? | `ids.stub_carrier`, with `ids.sync` | `markers`: the stub lists its ID under its docstring `Markers:`, never as a live marker, so a sync cannot mark the case automated; it stays active until a Phase 2 test with the real ID merges. Choose `decorator` only when the repo's own rules require a live marker on stubs and the Polarion owner accepts what its sync then does |
| What does the repo's lint want on a stub? | `stubs.def_suffix` | the comment that keeps a lint quiet while the ID stays in the docstring (stub-generator may write it too; `package` never doubles it) |
| Which cases are review-only? | `selection.review_only` | the export's manual-only value: triage always says `manual-only-review`, the team decides |
| The two end states | `end_state` | W6 proposes automated only for an implemented test with the real ID (ready once the owner verifies the sync), retired only for a team-approved retirement. A stub-only case stays pending, listed as an end-state gap |
| Tracking Jira, teams, folder map | `teams.yaml` | the owner supplies a tracking Jira per team batch, a reviewer, and the team-approved component-to-folder map |
| Model for internal data | — | the model your organization approves. The session that runs W2 and W4 checks this before it starts the triagers or `/std-builder`; an agent cannot check it for itself |

## Run

`RUN` is a fresh directory per export, for example `outputs/polarion/2026-10-sample`.
Every command prints what it did; exit 1 means checks failed and lists them,
exit 2 means a usage or input problem.

| Stage | Command | Exit criterion |
|---|---|---|
| W0 | `migrate.py init RUN --profile profile.yaml --cases cases.csv [--requirements reqs.csv] --tests-repo ~/tests --query "…" --exported-at …` | `manifest.json`: the profile's SHA-256; per file SHA-256, encoding, delimiter, header, record count; tests-repo commit |
| W1 | `migrate.py ledger RUN [--collected collect.txt]` | `ledger.json`/`.csv`, one row per input row, `unaccounted 0`; export defects fixed |
| — | `migrate.py teams RUN teams.yaml` | the team map frozen into the run |
| W2 | `migrate.py triage RUN queue`, the triagers, then `migrate.py triage RUN merge` | every eligible case has a verdict, or a named hold |
| W3 | `migrate.py review RUN sheets`, then `review RUN import review/TEAM.csv`, then `review RUN calibrate` | every case has a decision or an explicit hold; calibration written |
| W4 | `migrate.py scenarios RUN --team T`, `/std-builder {TRACKING_KEY}`, `migrate.py place RUN --team T`, `migrate.py package RUN --team T` | one stub per approved case, each placed, the package checks pass |
| W5 | `migrate.py stage RUN --team T --checkout ~/tests-fresh [--checks]`, open the PR by hand, then `record-pr` | one reviewed PR per team; ledger has its URL and the stubs' final paths |
| W6 | `migrate.py reconcile RUN --tests-repo ~/tests-main [--sync-verified]`, the owner applies, then `migrate.py verify RUN fresh.csv` | the fresh export matches the proposal |

To change a value mid-run (a header the real export spells differently), edit
the profile and re-freeze it with `migrate.py profile RUN FILE`; the manifest
keeps the one it replaces. Then re-run what it changes: `ledger --force` for
`export`, `selection` or `trace`; `package` for `ids`, `stubs` or `repo`.

### W0: freeze the inputs

Ask the owner for the test-case CSV and, when the profile's `trace.via` is
`requirement`, a requirements CSV holding **every** requirement those cases
link (or one export with both item types: omit `--requirements`; the export
then needs a Type column). When `trace.via` is `case`, each case holds its own
Jira link and there is no requirements export. Ask for the columns the profile
names. `init` checks the profile, copies it and the files read-only into the
run, and records their hashes. Use a clean checkout of the tests repo at
`origin/<default branch>`. A byte-order mark sets a file's encoding (Excel's
"Unicode Text" is UTF-16); otherwise the profile's `export.encoding` applies to
both files.

### W1: the case ledger

`ledger` reads the frozen export and gives every case row one state:

| State | Meaning |
|---|---|
| `excluded` | matches a `selection.exclude` rule: outside the selection |
| `resolved` | selected, with exactly one confirmed Jira requirement |
| `held` | selected, but data is missing or unclear. `holds` names it: `status-empty`, `automation-empty`, `unexpected-status`, `unexpected-automation`, `unexpected-type`, `no-linked-requirement`, `requirement-not-in-export`, `requirement-without-jira`, `case-without-jira`, `invalid-jira-url`, `bare-key-is-polarion-id`, `bare-key-no-base`, `wrong-jira-project`, `ambiguous-jira` |
| `duplicate` | the same ID on an earlier row (flag `conflicting-duplicate` when they differ) |
| `invalid` | no ID, an ID that is not a work item ID, or a row with more cells than the header |

It prints the column map, the headers it does not read, and a WARNING for a
missing Setup, Test Steps, Expected Result or Description column: without one,
every case reads as lacking that section. Headers match by their letters alone
(`testSteps` is `Test Steps`). Then the reconciliation: input records =
not-a-test-case rows + every state, with nothing unaccounted. It lists every
Type, Status, Automation and link role it saw, and the linked requirements
missing from the requirements export.

- **Requirement links** (`trace.via: requirement`): a link reads as
  `role: ID - title`, `role ID`, `[role] ID`, `ID - title (role)` or a bare ID,
  after any list mark; an ID inside a title is title text, and a link in
  another shape (a Polarion URL) gives its first ID with no role. Only a link
  with a `trace.roles` role, or no role, names a case's requirement. Links with
  other roles are kept as context, and a case with no other link holds as
  `no-linked-requirement`. A linked requirement missing from the export holds
  the case, even when another one resolves.
- **Jira:** every column the profile's `export.columns.jira` names is read. A
  requirement on two rows with different links holds its cases as
  `ambiguous-jira`. A link on `trace.jira_base`'s host, or on one of
  `trace.jira_hosts`, becomes `{base}/browse/KEY`; a link on another host is
  `invalid-jira-url`. A bare key becomes a link on the base, unless it is a
  Polarion ID of the export (`bare-key-is-polarion-id`).
- **Values:** a Status or Automation value the profile does not list holds the
  case, and so does a Type it does not name. To accept one, add it to the
  profile: a label that means a listed value goes in `export.aliases`, so a case
  that reads as excluded stays excluded.
- **Ragged rows:** empty cells past the header are dropped. A row with fewer
  cells reads the missing ones as empty and gets the flag `short-row`, listed
  under "Check in the export".

The tests repo is scanned too. Every `mark("ID")` (the profile's `ids.mark`)
is recorded with `file:line` and its kind: `decorator`, `param` (a
`pytest.param` mark), `pytestmark`, `markers-entry` (a stub's docstring),
`comment` or `text`. Each live marker also records whether its test is
implemented (code, or fixtures doing the work) and whether it is switched off
(`__test__ = False` in the module, the class or after it as
`Cls.__test__ = False`, `skip`, `xfail(run=False)`, or either as a module or
class `pytestmark`). Pass `--collected` (the output of
`pytest --collect-only -q`) to check collection too. A case whose ID is already
in the repo stays in the ledger with the flag `existing-marker`. It is not
dropped: a marker on a disabled stub proves nothing. A live marker on a test
that never runs adds `live-marker-on-stub`.

`triage queue` refuses to run while invalid rows or conflicting duplicates
exist: fix the export, or pass `--allow-defects` knowingly.

### W2: triage

`triage queue` groups the resolved cases by Jira requirement and creates the
folders the triagers write into. For each group, spawn the **polarion-triager**
agent with `RUN`, the group's `JIRA_KEY`, and `PRODUCT_REPO` when a checkout of
one of the profile's `triage.product_repos` is at hand. Groups are independent,
so run them in parallel. Each agent writes `triage/context/{KEY}@{stamp}.json`
and `triage/verdicts/{KEY}.json`, then checks them with
`triage RUN merge --group KEY --dry-run`. When all are done, run
`triage RUN merge` once.

`merge` enforces:
- one verdict per case, from `migrate`, `covered-by-implemented-test`,
  `designed-as-stub`, `retire-candidate`, `manual-only-review`,
  `needs-investigation`
- a rationale, an uncertainty, a proposed team
- evidence with a source (a URL, or `owner/repo@commit:path[:line]`) for every
  verdict but `needs-investigation`, and the same for every claim in the context
  file
- `manual-only-review` for every case `selection.review_only` matches
- `needs-investigation` for every other case when the Jira fetch failed
- `covered_by` naming the test(s) for `covered-by-implemented-test` and
  `designed-as-stub`, each one a def in the frozen tests repo
- the queue still matching the ledger: after `ledger --force`, re-run `triage queue`
- optional `gaps` (what a covering test misses, stale or thin steps) and
  `suggested_jira` (a successor requirement), both shown to the team

A changed verdict keeps the old one in `triage_history`, with its context
snapshot, so reruns can be compared.

### W3: team review

`review sheets` writes `review/{team}.csv` per team. A case's team comes from
the folder map, then the team whose `components` list has the case's component,
then the triage's proposal, else `unassigned`. Held cases and cases with an
existing marker are included. A reviewer can move a case to another team by
editing its `team` cell; the move sticks. The reviewer fills:

| Column | Required for |
|---|---|
| `decision` | `migrate`, `link-existing`, `retire` or `hold` (blank = not decided yet) |
| `reviewer`, `date` (YYYY-MM-DD), `rationale` | every decision |
| `chosen_jira` | `migrate` of a case whose Jira link is on hold (the triage's `triage_suggested_jira` is a hint). The case's own requirement: never a team's tracking Jira |
| `team` | `migrate` of an `unassigned` case: a team from teams.yaml |
| `pse_note` | optional: a correction to the source's steps (for example a restart the case omits); the stub applies it and says so |
| `existing_test` (`<root>/…py::[Class::]name`), `attach_id` (yes/no) | `link-existing` |
| `retire_reason`, `polarion_owner` | `retire` |

`sheet_version` and `row` tie each row to its case; reviewers leave them, and
sort whole rows only. `review import` checks the whole sheet and imports
nothing if any row is wrong. It refuses a row from an older sheet (the cases
were regenerated since), an emptied `decision` cell over an imported decision
(write `hold` to withdraw one), and a case listed twice. A spreadsheet's
date-time (`2026-10-08 00:00:00`) and `TRUE`/`y` read as a date and `yes`.
Regenerating the sheets refuses while a sheet holds edits that were not
imported (`--force` drops them), and removes the sheet of a team that no
longer has a case. Other files in `review/` (a reviewer's own copy) are left
alone.
`review calibrate` compares the triage with the decisions: agreement per
verdict (`designed-as-stub` and `covered-by-implemented-test` expect
`link-existing`), disagreements, false retirement proposals, cases without
evidence. It describes this sample only. Fix the triager's rules before the full
export.

### W4: stubs and their place

1. `scenarios --team T` writes `outputs/{TRACKING_KEY}/input/{TRACKING_KEY}_scenarios.yaml`
   from that team's approved `migrate` cases, labelled by the profile's
   `scenarios.label` and prioritised by `export.priority`. Each carries its
   Polarion ID, its own Jira, the source's own steps, `source_pse` and
   `source_missing` (which of preconditions, steps and expected Polarion
   lacked), `step_results` (each step with its own expected result) and the
   team's `review_note`. No approved case is a valid result, and nothing is
   written.
2. `/std-builder {TRACKING_KEY}` builds the STD and stubs; the ticket starts at
   the STD phase, since it has no STP. Its review step runs `validate_std.py`
   (or run it yourself, as std-builder Step 6 shows). QualityFlow's own stubs
   always list the ID as `polarion("ID")` under `Markers:`; the validator
   requires that entry, exactly one `Jira:` line, its own requirement's, and a
   `Source:` line naming every proposed section and any review correction.
   `package` checks the same again.
3. `place --team T` decides each stub's folder. It stops at the first layer that
   decides:
   1. **siblings**: implemented tests of other cases under the same Jira
      requirement, inside the team's roots (0.95 if they all share a folder,
      0.75 for a majority)
   2. **folder map**: the team-approved `components` entry (0.9)
   3. **model**: for each case still unplaced, read `placement/T.json`
      (`candidates` are the existing folders with tests, and their names). Write
      `placement/T.model.json`:
      `{"cases": [{"polarion_id", "folder", "confidence", "rationale", "cited_tests"}]}`.
      `folder` must be one of the candidates: the model cannot start a new
      convention. A confidence outside `--min-confidence` (0.7) to 1 falls
      through, and an entry for a case that is not the team's approved
      migrate case fails `place`.
   4. **owner**: `placement/T.owner.csv` with `polarion_id,folder,owner,date,note`.
      It settles the rest, and overrides any layer. The owner may name a new
      folder under the team's roots; `stage` creates it.

   Re-run `place` after each file. The output counts the cases each layer placed.
4. `package --team T` splits the std-builder module into one new module per
   folder (`{folder}/test_{feature}.py`; `--module` names it when that name is
   taken), in the team's form. With the `markers` carrier the ID stays under
   `Markers:` as `mark("ID")`, and each `def` line ends with
   `stubs.def_suffix` once (stub-generator may have written it; a noqa suffix
   joins a noqa the line has, since flake8 reads one per line). With
   `decorator` the stub gets `@pytest.mark.<mark>("ID")` and loses the
   `Markers:` entry and the suffix. It drops `@pytest.mark.qf_test_id` when the
   tests repo does not register it: under `--strict-markers` an unregistered
   mark breaks collection even on a disabled stub. It reads the repo's pytest
   config the way pytest does (`pytest.ini`, `.pytest.ini`, `pyproject.toml`
   with Python 3.11 or later, `tox.ini`, `setup.cfg`). It refuses a case placed
   outside the team's roots (moved since `place`). It checks every module: it
   parses, every test has `__test__ = False` (a skip is still collected) and no
   body or fixtures, one ID per test, matching an approved case placed there,
   its own `Jira:` line, no live marker the repo's sync matches (markers
   carrier), no unregistered marks, no HTML from the export, no ID or module
   name already in the repo, and one stub per approved case.
   `package/T/manifest.json` lists every file and test.

### W5: one PR per team

`stage --team T --checkout DIR` needs a clean checkout at the newest
`origin/<default branch>`, and refuses one that is not. It refuses a package
that no longer matches the team's decisions and placements: re-run `place` and
`package` after a review change. It re-runs the ID inventory against that base
and refuses anything that moved. It creates the profile's `pr.branch`, copies
the package, stages it, and writes `pr/T/PR_BODY.md`: the cases, their Jira
requirements, the reviewer decisions, where the IDs sit, the profile's
`pr.notes`, the validation results and what stays out of scope. `--checks` runs
the profile's `checks` in the checkout, as argument lists with `{files}` as the
staged files, never through a shell; a check passes on one of its `ok` exit
codes, and one whose command is missing is reported as not run. A person
reviews the diff, commits as the repo asks, pushes and opens the PR. Do not
route stubs through `/generate-tests`: that produces executable tests, not
design stubs.

After review: `record-pr --team T --url … --state open|merged [--commit SHA]
[--checkout DIR]`. The URL must be a pull request of the profile's repo. With
a checkout of the merged result it records where each stub ended up, including
moves. Under the `markers` carrier, in a repo with a sync, it fails when review
gave a stub a live marker: the sync then marks the case automated.

### W6: reconcile Polarion

`reconcile --tests-repo <current default branch>` writes `reconcile/{team}.csv`
for the Polarion owner. Each row has the original Status and Automation, the
decision, the Jira, the evidence, a proposed Status and a proposed Automation
(blank means unchanged), the reason, and `ready_to_apply`. The proposed values
are the profile's `end_state`: automated only when the default branch carries
the real ID (an implemented test, or a merged stub's live decorator that the
repo's sync marks), retired only for a team-approved retirement. A retirement
that an implemented test contradicts is not ready. A stub the sync flipped
under the `markers` carrier is proposed back to the export's own values. It
also writes `audit_automated_without_code.csv`: cases whose Automation is
`end_state.automated`'s, with no implemented test in the repo. That is a
separate audit, never an automatic rewrite. Pass `--sync-verified` only once
the owner has confirmed how the sync marks an implemented test.

The owner applies the ready rows their way and sends a fresh export.
`verify RUN fresh.csv` checks every ID: ready rows must show the proposal, the
rest must be unchanged (labels compare by their meaning, aliases included).

## teams.yaml

```yaml
teams:
  web:
    roots: [tests/web]            # under the profile's repo.root
    components: [Web]             # the component values this team owns
    reviewer: "<name>"
    tracking_jira: "https://jira.example.com/browse/PROJ-80001"   # needed from W4
  api:
    roots: [tests/api]
    components: [API]
    reviewer: "<name>"
components:            # placement: component, or "Component/Subcomponent" -> folder
  "Web": tests/web
  "Web/Forms": tests/web/forms
approved_by: "<owner>"        # needed from W4 placement
approved_on: "2026-10-10"
```

## Self-test

```bash
uv run --with pyyaml skills/polarion-migration/migrate.py --self-test
```

It runs W0–W6 for two synthetic teams, alpha and beta, that disagree on every
profile key (it asserts so), so a value hard-coded in the engine fails one of
them. It also checks that no file of the engine, this runbook, the example
profile or the triage agent holds a team's host, repo, work item ID or lint
code. CI runs it too.
