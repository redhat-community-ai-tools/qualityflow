# CNV: Polarion migration inputs

CNV QE's inputs for the **polarion-migration** skill
(`skills/polarion-migration`). This folder lives on the `cnv` branch only;
upstream holds the engine, never these values. The engine that reads them
arrives with PR #121 (redhat-community-ai-tools/qualityflow#121): merge `main`
into `cnv` once it lands.

- `profile.yaml`: CNV's migration profile. Check it with
  `python3 skills/polarion-migration/migrate.py check-profile config/projects/cnv/polarion-migration/profile.yaml`.
- `teams.yaml`: the team map, from openshift-virtualization-tests' team
  folders (conftest `TEAM_MARKERS`) and their OWNERS files. Fill in the
  components, reviewer and tracking Jira of each team and the folder map, then
  have the teams approve it.

```bash
python3 skills/polarion-migration/migrate.py init outputs/polarion/<run> \
  --profile config/projects/cnv/polarion-migration/profile.yaml \
  --cases cases.csv --requirements reqs.csv \
  --tests-repo <a clean checkout of RedHatQE/openshift-virtualization-tests at origin/main>
```

Then follow the skill's runbook, W1 to W6.

## Where the values come from

| Value | Source |
|---|---|
| `selection`: out when Status is inactive or Automation is Automated; `manualonly` kept for review | Ruth, 2026-09-24 |
| `trace.via: requirement`: case -> Polarion requirement -> the real Jira; that Jira link replaces the STP link | Ruth, 2026-09-24 |
| `trace.jira_base`, `trace.jira_hosts` | Red Hat's Jira moved to Atlassian Cloud; links on the old host are rewritten |
| `ids.sync` | the tests repo's post-merge `mark-automated-polarion` job (tox.ini; python-utility-scripts `find_polarion_ids`): an added `pytest.mark.polarion("ID")` line sets the case Automated, Status approved, hence `end_state.automated` |
| `stubs.def_suffix` | the tests repo's flake8 PolarionIds plugin (RedHatQE flake8-plugins, PID001) wants a live polarion decorator on every test, stubs included |
| `checks` | pre-commit (pre-commit.ci runs it), and a `--strict-markers` collection in the repo's own `.venv` without the cluster conftest |
| `scenarios.label` | openshift-virtualization-tests collects an unmarked test as tier2 |
| `triage.jira_pr_field` | the "Git Pull Request" field on redhat.atlassian.net, as of 2026-10 |
| `export.columns`, `export.values`, `export.steps_headers` | Polarion UI labels and Betelgeuse field ids: a guess until the sample export pins them |

## Rules

- Never use or store the shared Polarion account (`cnvqe`). The Polarion owner
  exports, and applies changes.
- An export is Red Hat internal: keep runs under `outputs/`, and send case data
  only to the approved work model (Claude through the work Vertex account).

## Open

- The sample export: pin the columns, values, step headers and aliases from
  it, then re-freeze the profile with `migrate.py profile RUN FILE`.
- Does a migrated stub count as Automated? The profile says no
  (`stub_carrier: markers`); `decorator` only with the Polarion owner's OK.
- `manualonly` cases: kept for review (`selection.review_only`), or skipped?
- Where stubs go: a module per feature, or one file per team.
- One tracking Jira per team batch (`teams.yaml`, `tracking_jira`).
