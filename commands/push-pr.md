---
name: push-pr
description: Open or update the pull requests that put a ticket's STP in the team's design-docs repo and its generated tests in the team's tests repo — never in the QualityFlow repo
argument-hint: <JIRA-ID> [--folder <stps subfolder>]
allowed-tools: Read, Bash, Glob, Grep, Skill
---

# Push {JIRA_ID}'s outputs to the team's repos

The dashboard's **Push to PR** does the same; this is the CLI path. Outputs
belong in the team's repos, where its reviewers already work. Nothing is ever
committed to the QualityFlow repo: `outputs/` stays a local working copy.

## Input

`$ARGUMENTS`: a Jira ID, optionally `--folder <name>` (the `stps/` subfolder
in the design-docs repo, e.g. the owning SIG's).

## Step 0: Resolve the project

Invoke the **project-resolver** skill with the Jira ID. From
`{project_context.config_dir}/repositories.yaml` read `design_docs_repo` and
`primary_repo` (the tests repo): `full_name`, `default_branch`.

Use `gh` (authenticated as the person running this; never print or store a
token). If you cannot push to a repo, push to your fork of it and open the PR
from there (`gh repo fork --remote=false`, then push to the fork).

## Step 1: What goes where

| Output | Repo | Path |
|---|---|---|
| `outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md` | `design_docs_repo` | `stps/<folder>/{JIRA_ID}.md` |
| generated tests (`outputs/{JIRA_ID}/{lang}-tests/`) | `primary_repo` | each file's `target_path` from `summary.yaml`, else `tests/qualityflow/{JIRA_ID}/<file>` |

- No `design_docs_repo`: the STP goes nowhere (it stays local); say so.
- `<folder>`: `--folder`, else the folder of the existing PR (Step 2), else
  the `stps/` subfolder whose name matches the STP's Owning SIG; with no
  match, list `gh api repos/{design_docs}/contents/stps --jq '.[]|select(.type=="dir").name'`
  and stop, asking for `--folder`.
- When the STP came from the team itself (`{JIRA_ID}_stp_source.yaml`
  exists), it is already in its repo: skip it.
- STD, reviews and intermediate YAML are not pushed.
- Tests are pushed only when the codegen phase recorded
  `verification: passed` (pipeline state). Otherwise skip them and say why.
- A Python test file pytest would never collect (not `test_*.py` /
  `*_test.py`) is refused, as on the dashboard.

## Step 2: Open or update — one PR per repo, branch `qualityflow/{jira_id lowercase}`

`outputs/{JIRA_ID}/state/pr_info.yaml` records the PR (same file the
dashboard writes: `url`, `number`, `target_repo`, `branch`, `stp_folder`,
`pushed_blobs`, and `tier2_pr` for the tests PR).

1. **Open PR exists:** check out its branch, and before writing each file
   compare the branch's current blob sha (`git rev-parse HEAD:<path>`) with
   `pushed_blobs[<path>]`. If they differ, someone edited it on the PR: stop
   and say so — never overwrite a reviewer's change. Otherwise write the
   files, commit `QualityFlow: update for {JIRA_ID}`, push (no force).
2. **No PR, or it was closed:** branch from `default_branch`, write the
   files, commit `QualityFlow: {STP|tests} for {JIRA_ID}`, push, and
   `gh pr create` with a body listing the ticket link and the files.
3. **Merged:** stop — the document now lives in its repo; change it there.

Record the result in `pr_info.yaml`, with `pushed_blobs` set to each file's
`git hash-object` value, so the next update can detect edits on the PR.

## Output

The PR URL(s), opened or updated, and anything skipped with the reason.
Next steps: ask reviewers on the PR (`gh pr edit {n} --add-reviewer ...`, or
the dashboard's Ask for review), then fold their comments in with
`/fix-pr {PR_URL}` — it edits the document on the PR and syncs the local copy.
