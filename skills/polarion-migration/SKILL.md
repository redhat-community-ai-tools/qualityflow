---
name: polarion-migration
description: Migrate non-automated Polarion test cases into openshift-virtualization-tests as STD design stubs — a case ledger from the CSV export, agent triage, team review, std-builder stubs placed per team, one tests-repo PR per team, and a Polarion reconciliation proposal for the owner.
model: inherit
---

# Polarion Migration

**User-Invocable:** yes. Run it per export, one stage at a time.

## Purpose

CNV QE is moving off Polarion. Its end state has two values: a case is
**automated** (an implemented test carries its ID) or **inactive**. This skill
takes the cases that are neither yet, Ruth's selection rule:

```
Status != inactive  AND  Automation != Automated
```

and gives each one a team-approved outcome: an STD stub in the tests repo, a
link to an existing implemented test, retirement, or a hold. `manualonly` cases
are in the set and stay visible for review.

The mechanical half is `migrate.py` in this directory. The judgement calls are
an agent's (W2 triage, W4 placement) and the teams' (W3, the folder map).

## Boundaries

- Nothing here logs in to Polarion, uses the shared `cnvqe` account, or writes
  to Polarion, Jira or GitHub. The Polarion owner exports, and applies changes.
- The export is Red Hat internal. Keep each run under `outputs/` (git ignores
  it), and send case data only to the approved work model. No personal accounts
  (Jev / TypeSafe) without explicit data approval.
- A tests-repo PR holds reviewed stubs and a summary, never raw export data.
- Each test links the Jira of **its own** requirement; only the module header
  links the team's tracking issue. A case with no confirmed Jira is held until a
  reviewer names it.

## Decision gate

The defaults below are built in. Changing one is a code change, made only on
the owner's say-so.

| Decision | Default |
|---|---|
| Does a design stub count as Automated? | **No.** A stub has `__test__ = False`. Its case stays active until a Phase 2 test with the real ID merges, unless the team retires it |
| Where does a stub carry its Polarion ID? | Under its docstring `Markers:` as `polarion("CNV-…")`, never as a live `@pytest.mark.polarion`. The tests repo's post-merge `mark-automated-polarion` job marks a case Automated from any merged line with `pytest.mark.polarion("ID")`. `validate_std.py` and `package` refuse one on a stub. Phase 2 turns the entry into the real decorator. **But** the tests repo's flake8 PolarionIds plugin (`PID001`) requires a real polarion decorator on every test, stubs included, which is why its own STD stubs carry live decorators. So `package` adds `# noqa: PID001` to each stub's `def` line. `package --polarion-marker decorator` follows the repo's practice instead, on the owner's say-so: the stub gets the decorator, and W6 then proposes Automated for a merged stub |
| The two end states | W6 proposes **Status** and **Automation** separately: Automated only for an implemented test with the real ID (ready to apply once the owner verifies the sync), Inactive only for a team-approved retirement. A stub-only case stays pending, listed as an end-state gap |
| `manualonly` cases | Triage always says `manual-only-review`; the team decides |
| Tracking Jira, teams, folder map | The owner supplies `teams.yaml`: a tracking Jira per team batch, a reviewer, and the approved component-to-folder map |
| Model for Red Hat data | The approved work Claude/Vertex path. The session that runs W2 and W4 checks this before it starts the triagers or `/std-builder`; an agent cannot check it for itself |

None of these stop W0–W3: parse, triage and review while they are pending.

## Run

`RUN` is a fresh directory per export, for example `outputs/polarion/2026-10-sample`.
Every command prints what it did; exit 1 means checks failed and lists them,
exit 2 means a usage or input problem.

| Stage | Command | Exit criterion |
|---|---|---|
| W0 | `migrate.py init RUN --cases cases.csv --requirements reqs.csv --tests-repo ~/ovt --query "…" --exported-at …` | `manifest.json`: SHA-256, encoding, delimiter, header, record count per file; tests-repo commit |
| W1 | `migrate.py ledger RUN --jira-base https://redhat.atlassian.net --jira-projects CNV [--col FIELD=HEADER] [--allow FIELD=VALUE[=MEANING]] [--collected collect.txt]` | `ledger.json`/`.csv`, one row per input row, `unaccounted 0`; export defects fixed |
| — | `migrate.py teams RUN teams.yaml` | the team map frozen into the run |
| W2 | `migrate.py triage RUN queue`, the triagers, then `migrate.py triage RUN merge` | every eligible case has a verdict, or a named hold |
| W3 | `migrate.py review RUN sheets`, then `review RUN import review/TEAM.csv`, then `review RUN calibrate` | every case has a decision or an explicit hold; calibration written |
| W4 | `migrate.py scenarios RUN --team T [--tier "Tier 2"]`, `/std-builder {TRACKING_KEY}`, `migrate.py place RUN --team T`, `migrate.py package RUN --team T` | one stub per approved case, each placed, the package checks pass |
| W5 | `migrate.py stage RUN --team T --checkout ~/ovt-fresh [--checks]`, open the PR by hand, then `record-pr` | one reviewed PR per team; ledger has its URL and the stubs' final paths |
| W6 | `migrate.py reconcile RUN --tests-repo ~/ovt-main [--sync-verified]`, the owner applies, then `migrate.py verify RUN fresh.csv` | the fresh export matches the proposal |

### W0: freeze the inputs

Ask the owner for the test-case CSV and a requirements CSV holding **every**
requirement those cases link (or one export with both item types: omit
`--requirements`; the export then needs a Type column). Ask for these columns:
ID, Type, Title, Status, Case Automation, Linked Work Items (with link roles),
Test Steps, Expected Result, Setup, Description, Case Component, Subcomponent,
Updated, Hyperlinks, and on requirements the Jira link. `init` copies the files
read-only into `RUN/input/` and records their hashes. Use a clean checkout of
the tests repo at `origin/main`. A byte-order mark sets a file's encoding
(Excel's "Unicode Text" is UTF-16); otherwise `--encoding` (UTF-8 by default)
applies to both files, so re-export a file in another encoding as UTF-8.

### W1: the case ledger

`ledger` reads the frozen export and gives every case row one state:

| State | Meaning |
|---|---|
| `excluded` | Status inactive, or Automation Automated: outside the selection |
| `resolved` | Selected, with exactly one confirmed Jira requirement |
| `held` | Selected, but data is missing or unclear. `holds` names it: `status-empty`, `automation-empty`, `unexpected-status`, `unexpected-automation`, `unexpected-type`, `no-linked-requirement`, `requirement-not-in-export`, `requirement-without-jira`, `invalid-jira-url`, `bare-key-is-polarion-id`, `bare-key-no-base`, `wrong-jira-project`, `ambiguous-jira` |
| `duplicate` | The same ID on an earlier row (flag `conflicting-duplicate` when they differ) |
| `invalid` | No ID, an ID that is not a work item ID, or a row with more cells than the header |

It prints the column map, the headers it does not read, and a WARNING for a
missing Setup, Test Steps, Expected Result or Description column: without one,
every case reads as lacking that section. Headers match by their letters
alone (`testSteps` is `Test Steps`); `--col FIELD=HEADER` maps any other, in
whichever file has the field. Then the reconciliation: input records =
not-a-test-case rows + every state, with nothing unaccounted. It lists every
Type, Status, Automation and link role it saw, and the linked requirements
missing from the requirements export.

- **Requirement links:** a link reads as `role: ID - title`, `role ID`,
  `[role] ID`, `ID - title (role)` or a bare ID, after any list mark; an ID
  inside a title is title text, and a link in another shape (a Polarion URL)
  gives its first ID with no role. Only a link with role `verifies`, or no
  role, names a case's requirement. Links with other roles (`relates to`,
  `parent`) are kept as context, and a case with no other link holds as
  `no-linked-requirement`. A verified requirement missing from the export
  holds the case, even when another one resolves.
- **Jira:** every Jira, Jira Link and Hyperlinks column of a requirement is
  read. A requirement on two rows with different links holds its cases as
  `ambiguous-jira`. Always pass `--jira-base`: links on either Red Hat Jira
  host (`issues.redhat.com`, `redhat.atlassian.net`) become
  `{base}/browse/KEY`, and a link on another host is `invalid-jira-url`.
  Without it, links keep their exported host, and the ledger warns.
- **Unknown values:** `--allow FIELD=VALUE` accepts a Status, Automation, Type
  or link role once the owner confirms it. A value that means something built
  in says so: `--allow "automation=Automated (CI)=automated"`,
  `--allow "type=Test Case (Manual)=testcase"`. A bare value that looks
  inactive, Automated or like a test case type is refused, since it could
  drop a case or make an excluded one eligible. Any other bare Type is a work
  item that is not a test case (Heading is one already).
- **Ragged rows:** empty cells past the header are dropped. A row with fewer
  cells reads the missing ones as empty and gets the flag `short-row`, listed
  under "Check in the export".

The tests repo is scanned too. Every `polarion("ID")` is recorded with
`file:line` and its kind: `decorator`, `param` (a `pytest.param` mark),
`pytestmark`, `markers-entry` (a stub's docstring), `comment` or `text`. Each
live marker also records whether its test is implemented (code, or fixtures
doing the work) and whether it is switched off (`__test__ = False` in the
module, the class or after it as `Cls.__test__ = False`, `skip`,
`xfail(run=False)`, or either as a module or class `pytestmark`). Pass
`--collected` (the output of `pytest --collect-only -q`) to check collection
too. A case whose ID is already in the repo stays in the ledger with the flag
`existing-marker`. It is not dropped: a marker on a disabled stub proves
nothing. A live marker on a test that never runs adds `live-marker-on-stub`.

`triage queue` refuses to run while invalid rows or conflicting duplicates
exist: fix the export, or pass `--allow-defects` knowingly.

### W2: triage

`triage queue` groups the resolved cases by Jira requirement and creates the
folders the triagers write into. For each group, spawn the **polarion-triager**
agent with `RUN`, the group's `JIRA_KEY`, and `PRODUCT_REPO` when a product
checkout is at hand. Groups are independent, so run them in parallel. Each
agent writes `triage/context/{KEY}@{stamp}.json` and
`triage/verdicts/{KEY}.json`, then checks them with
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
- `manual-only-review` for every manualonly case
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
| `pse_note` | optional: a correction to the source's steps (for example a VM restart the case omits); the stub applies it and says so |
| `existing_test` (`tests/…py::[Class::]name`), `attach_id` (yes/no) | `link-existing` |
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
   from that team's approved `migrate` cases. Each carries its Polarion ID, its
   own Jira, the source's own steps, `source_pse` and `source_missing` (which of
   preconditions, steps and expected Polarion lacked), `step_results` (each
   step with its own expected result) and the team's `review_note`. No approved
   case is a valid result, and nothing is written.
2. `/std-builder {TRACKING_KEY}` builds the STD and stubs; the ticket starts at
   the STD phase, since it has no STP. Its review step runs `validate_std.py`
   (or run it yourself, as std-builder Step 6 shows). The validator requires
   each migrated stub's `polarion("ID")` under `Markers:`, exactly one `Jira:`
   line, its own requirement's, and a `Source:` line naming every proposed
   section and any review correction. `package` checks the same again.
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
   taken). Per the decision gate, each stub's `def` line gets `# noqa: PID001`
   (added to a `# noqa:` the line already has: flake8 reads one per line), or
   `--polarion-marker decorator` puts the real decorator on it instead. It drops `@pytest.mark.qf_test_id`
   when the tests repo does not register it: that repo runs `--strict-markers`,
   and an unregistered mark breaks its collection even on a disabled stub. It
   refuses a case placed outside the team's roots (moved since `place`). It
   checks every module: it parses, every test has `__test__ = False` (a skip
   is still collected) and no body or fixtures, one `polarion("ID")` per test,
   matching an approved case placed there, its own `Jira:` line, no live
   polarion decorator, no unregistered marks, no HTML from the export, no ID or
   module name already in the repo, and one stub per approved case.
   `package/T/manifest.json` lists every file and test.

### W5: one PR per team

`stage --team T --checkout DIR` needs a clean checkout at the newest
`origin/main`, and refuses one that is not. It refuses a package that no longer
matches the team's decisions and placements: re-run `place` and `package`
after a review change. It re-runs the ID inventory against that base and refuses
anything that moved. It creates `polarion-migration/{team}-{key}`, copies the
package, stages it, and writes `pr/T/PR_BODY.md`: the cases, their Jira
requirements, the reviewer decisions, the marker policy, the validation results
and what stays out of scope. `--checks` runs the repo's pre-commit on the files, and a pytest collection
with the repo's own environment and registered markers (`--strict-markers`,
without the conftest and `--tc-file` setup that needs a cluster); it passes only
when nothing is collected. The collection needs `uv sync` in the checkout first.
A person reviews the diff, commits, pushes and opens the PR. Do not route stubs
through `/generate-tests`: that produces executable tests, not design stubs.

After review: `record-pr --team T --url … --state open|merged [--commit SHA]
[--checkout DIR]`. With a checkout of the merged result it records where each
stub ended up, including moves. It fails when review gave a stub a live
`@pytest.mark.polarion` under the default policy: the post-merge job then marks
the case Automated.

### W6: reconcile Polarion

`reconcile --tests-repo <current main>` writes `reconcile/{team}.csv` for the
Polarion owner. Each row has the original Status and Automation, the decision,
the Jira, the evidence, a proposed Status and a proposed Automation (blank means
unchanged), the reason, and `ready_to_apply`. Automated is proposed only when
main carries the real ID (an implemented test, or under the decorator policy
the merged stub's decorator), and with Status approved, which the post-merge
job sets alongside it. A retirement that an implemented test contradicts is
not ready. It also writes
`audit_automated_without_code.csv`: cases Automated in Polarion with no
implemented test in the repo. That is a separate audit, never an automatic
rewrite. Pass `--sync-verified` only once the owner has confirmed how the sync
marks an implemented test.

The owner applies the ready rows their way and sends a fresh export.
`verify RUN fresh.csv` checks every ID: ready rows must show the proposal, the
rest must be unchanged.

## teams.yaml

```yaml
teams:
  network:
    roots: [tests/network]
    components: [Networking]      # the Case Component values this team owns
    reviewer: "<name>"
    tracking_jira: "https://redhat.atlassian.net/browse/CNV-80001"   # needed from W4
  storage:
    roots: [tests/storage]
    components: [Storage]
    reviewer: "<name>"
components:            # placement: Case Component, or "Component/Subcomponent" -> folder
  "Networking": tests/network
  "Networking/SR-IOV": tests/network/sriov
approved_by: "<owner>"        # needed from W4 placement
approved_on: "2026-10-10"
```

## Self-test

```bash
uv run --with pyyaml skills/polarion-migration/migrate.py --self-test
```

It runs W0–W6 on a synthetic export and a throwaway git repo, CI runs it too.
