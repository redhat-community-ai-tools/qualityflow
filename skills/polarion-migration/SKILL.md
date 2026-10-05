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
- Each stub links the Jira of **its own** requirement, never the batch's
  tracking issue. A case with no confirmed Jira is held until a reviewer names it.

## Decision gate

The defaults below are built in. Changing one is a code change, made only on
the owner's say-so.

| Decision | Default |
|---|---|
| Does a design stub count as Automated? | **No.** A stub has `__test__ = False`. Its case stays active until a Phase 2 test with the real ID merges, unless the team retires it |
| Where does a stub carry its Polarion ID? | Under its docstring `Markers:` as `polarion("CNV-…")`, never as a live `@pytest.mark.polarion`. The tests repo's post-merge `mark-automated-polarion` job marks a case Automated from any merged line with `pytest.mark.polarion("ID")`. `validate_std.py` and `package` refuse one on a stub. Phase 2 turns the entry into the real decorator |
| The two end states | W6 proposes **Status** and **Automation** separately: Automated only for an implemented test with the real ID (ready to apply once the owner verifies the sync), Inactive only for a team-approved retirement. A stub-only case stays pending, listed as an end-state gap |
| `manualonly` cases | Triage always says `manual-only-review`; the team decides |
| Tracking Jira, teams, folder map | The owner supplies `teams.yaml`: a tracking Jira per team batch, a reviewer, and the approved component-to-folder map |
| Model for Red Hat data | The approved work Claude/Vertex path |

None of these stop W0–W3: parse, triage and review while they are pending.

## Run

`RUN` is a fresh directory per export, for example `outputs/polarion/2026-10-sample`.
Every command prints what it did; exit 1 means checks failed and lists them,
exit 2 means a usage or input problem.

| Stage | Command | Exit criterion |
|---|---|---|
| W0 | `migrate.py init RUN --cases cases.csv --requirements reqs.csv --tests-repo ~/ovt --query "…" --exported-at …` | `manifest.json`: SHA-256, encoding, delimiter, header, record count per file; tests-repo commit |
| W1 | `migrate.py ledger RUN [--col FIELD=HEADER] [--allow automation=…] [--jira-base https://redhat.atlassian.net] [--jira-projects CNV] [--collected collect.txt]` | `ledger.json`/`.csv`, one row per input row, `unaccounted 0`; export defects fixed |
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
the tests repo at `origin/main`.

### W1: the case ledger

`ledger` reads the frozen export and gives every case row one state:

| State | Meaning |
|---|---|
| `excluded` | Status inactive, or Automation Automated: outside the selection |
| `resolved` | Selected, with exactly one confirmed Jira requirement |
| `held` | Selected, but data is missing or unclear. `holds` names it: `status-empty`, `automation-empty`, `unexpected-status`, `unexpected-automation`, `no-linked-requirement`, `requirement-not-in-export`, `requirement-without-jira`, `invalid-jira-url`, `bare-key-is-polarion-id`, `bare-key-no-base`, `wrong-jira-project`, `ambiguous-jira` |
| `duplicate` | The same ID on an earlier row (flag `conflicting-duplicate` when they differ) |
| `invalid` | No ID, or a malformed row |

It prints the reconciliation: input records = not-a-test-case rows + every
state, with nothing unaccounted. It also lists every Status and Automation
value it saw, so the owner can confirm unknown ones (`--allow`).

The tests repo is scanned too. Every `polarion("ID")` is recorded with
`file:line` and its kind: `decorator`, `param` (a `pytest.param` mark),
`pytestmark`, `markers-entry` (a stub's docstring), `comment` or `text`. Each
live marker also records whether its test is implemented (code, or fixtures
doing the work) and whether it is switched off (`__test__ = False`, `skip`,
`xfail(run=False)`). Pass `--collected` (the output of `pytest --collect-only
-q`) to check collection too. A case whose ID is already in the repo stays in
the ledger with the flag `existing-marker`. It is not dropped: a marker on a
disabled stub proves nothing.

`triage queue` refuses to run while invalid rows or conflicting duplicates
exist: fix the export, or pass `--allow-defects` knowingly.

### W2: triage

`triage queue` groups the resolved cases by Jira requirement. For each group,
spawn the **polarion-triager** agent with `RUN` and the group's `JIRA_KEY`.
Groups are independent, so run them in parallel. Each agent writes
`triage/context/{KEY}@{stamp}.json` and `triage/verdicts/{KEY}.json`, then
checks its own file with `triage RUN merge --group KEY --dry-run`. When all are
done, run `triage RUN merge` once.

`merge` enforces:
- one verdict per case, from `migrate`, `covered-by-implemented-test`,
  `retire-candidate`, `manual-only-review`, `needs-investigation`
- a rationale, an uncertainty, a proposed team
- evidence with a source (a URL, or `repo@commit:path:line`) for every verdict
  but `needs-investigation`
- `manual-only-review` for every manualonly case
- `needs-investigation` everywhere when the context fetch failed
- `covered_by` naming a test for `covered-by-implemented-test`

A changed verdict keeps the old one in `triage_history`, with its context
snapshot, so reruns can be compared.

### W3: team review

`review sheets` writes `review/{team}.csv` per team. A case's team comes from
the component map, then the triage's proposal, else `unassigned`. Held cases and
cases with an existing marker are included. The reviewer fills:

| Column | Required for |
|---|---|
| `decision` | `migrate`, `link-existing`, `retire` or `hold` (blank = not decided yet) |
| `reviewer`, `date` (YYYY-MM-DD), `rationale` | every decision |
| `chosen_jira` | `migrate` of a case whose Jira link is on hold |
| `existing_test` (`tests/…py::name`), `attach_id` (yes/no) | `link-existing` |
| `retire_reason`, `polarion_owner` | `retire` |

`review import` checks the whole sheet and imports nothing if any row is wrong.
`review calibrate` compares the triage with the decisions: agreement per
verdict, disagreements, false retirement proposals, cases without evidence. It
describes this sample only. Fix the triager's rules before the full export.

### W4: stubs and their place

1. `scenarios --team T` writes `outputs/{TRACKING_KEY}/input/{TRACKING_KEY}_scenarios.yaml`
   from that team's approved `migrate` cases, each with its Polarion ID, its own
   Jira, the source's own steps, and `source_pse`. No approved case is a valid
   result, and nothing is written.
2. `/std-builder {TRACKING_KEY}` builds the STD and stubs. `validate_std.py`
   requires each migrated stub's `polarion("ID")` under `Markers:`, its own
   `Jira:` line, and a `Source:` line where Polarion had no steps or expected
   result.
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
      convention. Below `--min-confidence` (0.7) it falls through.
   4. **owner**: `placement/T.owner.csv` with `polarion_id,folder,owner,date,note`.
      It settles the rest, and overrides any layer.

   Re-run `place` after each file. The output counts the cases each layer placed.
4. `package --team T` splits the std-builder module into one new module per
   folder (`{folder}/test_{feature}.py`). It drops `@pytest.mark.qf_test_id`
   when the tests repo does not register it: that repo runs `--strict-markers`,
   and an unregistered mark breaks its collection even on a disabled stub. It
   checks every module: it parses, every test is switched off and has no body or
   fixtures, one `polarion("ID")` per test, matching an approved case placed
   there, its own `Jira:` line, no live polarion decorator, no unregistered
   marks, no HTML from the export, no ID or module name already in the repo, and
   one stub per approved case. `package/T/manifest.json` lists every file and
   test.

### W5: one PR per team

`stage --team T --checkout DIR` needs a clean checkout at the newest
`origin/main`. It re-runs the ID inventory against that base and refuses
anything that moved. It creates `polarion-migration/{team}-{key}`, copies the
package, stages it, and writes `pr/T/PR_BODY.md`: the cases, their Jira
requirements, the reviewer decisions, the marker policy, the validation results
and what stays out of scope. `--checks` runs the repo's pre-commit on the files.
A person reviews the diff, commits, pushes and opens the PR. Do not route stubs
through `/generate-tests`: that produces executable tests, not design stubs.

After review: `record-pr --team T --url … --state open|merged [--commit SHA]
[--checkout DIR]`. With a checkout of the merged result it records where each
stub ended up, including moves.

### W6: reconcile Polarion

`reconcile --tests-repo <current main>` writes `reconcile/{team}.csv` for the
Polarion owner. Each row has the original Status and Automation, the decision,
the Jira, the evidence, a proposed Status and a proposed Automation (blank means
unchanged), the reason, and `ready_to_apply`. It also writes
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
    reviewer: "<name>"
    tracking_jira: "https://redhat.atlassian.net/browse/CNV-80001"   # needed from W4
  storage:
    roots: [tests/storage]
    reviewer: "<name>"
components:            # Case Component, or "Component/Subcomponent" -> folder
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
