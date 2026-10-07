---
name: add-repo
description: Add a repository to a project's config (tests repo, design-docs repo, or an extra repo QualityFlow reads for context) with every field the pipeline needs
argument-hint: <org/repo or GitHub URL> [--project <id>] [--type primary|tier2|design_docs|additional] [--language <lang>]
allowed-tools: Read, Edit, Write, Bash, Glob
---

# Add a repository to a QualityFlow project

`$ARGUMENTS`: the repo (`org/repo` or `https://github.com/org/repo`), then
optional flags. The dashboard's project settings import does the same, with
the same entry shape.

## Step 1: Which project and which slot

- `--project`: the directory under `config/projects/`. Without it: the only
  project there besides `example`, else list them and stop, asking which.
- `--type` (default `additional`):
  - `primary`: the tests repo (generated tests and existing-coverage search)
  - `tier2`: a second tests repo, when a tier's tests live elsewhere
  - `design_docs`: where the team keeps its STPs (Push to PR, existing-STP lookup)
  - `additional`: read for context (product code, shared libraries)

## Step 2: The entry

Look the repo up read-only (`gh api repos/{org}/{repo} --jq '{default_branch,language}'`);
when that fails, use `main` and the `--language` given. Write, in
`config/projects/{project}/repositories.yaml`:

```yaml
name: "<repo>"
org: "<org>"
full_name: "<org>/<repo>"
url: "https://github.com/<org>/<repo>"
local_path_env: "<REPO_NAME_UPPER>_REPO_PATH"   # non-alphanumerics become _
default_branch: "<branch>"
language: "<lang>"                               # lower case
```

- `primary`/`tier2`/`design_docs` replace that slot (`primary_repo`, ...);
  when the slot already holds the same repo, keep its other keys
  (`build_command`, ...). `primary_repo` also needs `build_system` (ask, or
  leave `""`).
- `additional` appends to `additional_repos`, or completes an existing entry
  for the same repo without dropping its keys.
- Edit only that block; keep comments and the rest of the file as they are.

## Step 3: Check and tell the user what is left

Run `python3 config/validate.py config/projects/{project}/` and fix what it
reports. Then tell the user:

- to clone the repo and export the variable, e.g.
  `git clone https://github.com/<org>/<repo> ~/src/<repo>` and
  `export <REPO_NAME_UPPER>_REPO_PATH=~/src/<repo>`. Without a checkout the
  analysis steps (LSP, existing tests) skip the repo;
- on a shared dashboard, the entry is saved but the pod has no checkout of
  the repo (it clones only the QualityFlow repo, `GIT_REPO_URL`), so the
  analysis steps skip it there until the deployment clones it and sets the
  same variable;
- for `design_docs`, that Push to PR and the existing-STP lookup now use it.
