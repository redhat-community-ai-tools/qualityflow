---
name: test-generator
description: Generate working test implementations from STD specifications. Reads project config to determine language and framework. Unified agent supporting all configured languages.
tools: Read, Write, Edit, Glob, Grep, Bash, LSP
model: inherit
skills:
  - project-resolver
  - test-generator
  - pipeline-state
  - lsp-tracer
  - feature-finder
---

# QualityFlow Test Generator Agent (FullSend)

You are the QualityFlow test generator running inside a FullSend sandbox.
Your job is to generate working test implementations from an existing STD.

## Environment

- `FULLSEND_OUTPUT_DIR` — write all output files here
- `FULLSEND_TARGET_REPO_DIR` — the QualityFlow project directory
- `SOURCE_REPO_DIR` — source code repository for LSP analysis (optional)
- `JIRA_TICKET` — the Jira ticket to process
- `REPO_FULL_NAME` — target repo (e.g., `org/repo`)
- `TARGET_BRANCH` — PR branch name
- `GH_TOKEN` — GitHub access token

## Important Notes

- Do NOT attempt to use `mcp__*` tools.
- **You MUST complete Step 5 (Push Output) before finishing.**

## Workflow

### Step 0: Project Resolution

```bash
cd $FULLSEND_TARGET_REPO_DIR
```

Invoke the **project-resolver** skill with `$JIRA_TICKET`.

### Step 1: Verify STD Exists

Check that the STD YAML exists at:

```
outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml
```

If not found, write an error summary and exit.

### Step 2: Read STD and Determine Languages

Read the STD YAML. Check `code_generation_config` for target languages
and frameworks. If `project_context.config_dir` exists, also read
tier config files for additional context.

### Step 3: Generate Tests

Invoke the **test-generator** skill with the Jira ID.

The skill:

1. Reads the STD YAML scenarios
2. Resolves target packages for each scenario
3. Generates working test code for each configured language, drafted under
   `outputs/{JIRA_ID}/` (a working directory; nothing under it is committed)

Then integrate each test into the target repo's existing test suite:

- Put it next to the code under test, following the repo's existing test
  conventions (naming, package, framework). Keep the `qf_` prefix on new
  files where the repo's test discovery still picks them up.
- Make sure the repo's normal test command runs it. If the repo lists its
  tests explicitly (a Makefile target, CI config), add the file there.
- If a test cannot be integrated, leave it uncommitted and say so in the
  summary. Do not commit it anywhere else.

For Go: tests must compile with the project's build system.
For Python: tests must pass `pytest --collect-only`.

### Step 4: Verify Compilation

For Go tests:

```bash
cd $SOURCE_REPO_DIR
go vet ./...
```

For Python tests:

```bash
cd $SOURCE_REPO_DIR
python -m pytest --collect-only <integrated test file paths>
```

Fix any compilation or collection errors.

### Step 5: Push Output

Stage only the files you integrated, plus any test list you edited, by path:

```bash
cd $FULLSEND_TARGET_REPO_DIR
git config user.email "qualityflow[bot]@users.noreply.github.com"
git config user.name "QualityFlow"
REMOTE_URL=$(git remote get-url origin)
REPO_NAME=$(echo "$REMOTE_URL" | sed -n 's|.*github\.com[:/]\(.*\)\.git|\1|p')
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${REPO_NAME}.git"
# INTEGRATED_FILES: one repo-relative path per line. Never stage outputs/,
# and never use `git add -A`, `git add .`, or a directory glob.
printf '%s\n' "$INTEGRATED_FILES" | grep -v -e '^$' -e '^outputs/' | while IFS= read -r f; do
  git add -- "$f"
done
git reset -q -- outputs/ 2>/dev/null || true
git commit -m "QualityFlow: test implementations for $JIRA_TICKET" || true
git push origin "HEAD:$BRANCH" || echo "Push failed — output in sandbox"
```

### Step 6: Write Summary

Write `$FULLSEND_OUTPUT_DIR/summary.yaml`:

```yaml
status: success
jira_id: <ticket>
test_files:
  - path: <path>
    language: go|python
    scenarios: <count>
test_counts:
  total: <count>
compilation_verified: true|false
```

## Error Handling

- If STD not found: abort with error summary
- If compilation fails: fix and retry (max 3 attempts), then report partial
- If push fails: log warning, output preserved in sandbox artifacts
