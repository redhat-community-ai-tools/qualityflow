---
name: generate-tests
description: Generate working test implementations from STD YAML
argument-hint: <JIRA-ID> [--priority=<p0|p1|p2>]
allowed-tools: Read, Write, Edit, Task, Glob, Grep, LSP, Skill, Bash
---

# Generate Tests Command

Generates **full working test implementations** from STD YAML, in whatever
languages and frameworks the project config declares, **inside a checkout of
the team's tests repo**: the generator uses only the fixtures, helpers and
markers that repo really has, writes each test where it belongs there, and
checks it with the repo's own tooling. The phase is experimental until that
check passes, and the check collects or compiles; it never runs a test.

**Use this after design review is approved.** For test stubs (design phase), use `/std-builder` instead.

---

When the user runs `/generate-tests {JIRA_ID}`:

## Step 0: Resolve Project

Use the Skill tool to invoke the project-resolver skill:

**Tool:** Skill
**Parameters:**
- skill: "project-resolver"
- args: "$ARGUMENTS"

This returns `project_context` containing:
- `project_id`, `display_name`, `jira_id`
- `config_dir` (path to project config files)
- `feature_toggles` (what capabilities are enabled)

## Step 0.5: Parse Priority Filter (if provided)

Scan `$ARGUMENTS` for the `--priority=X` flag:

1. **Extract priority value:**
   - Pattern: `--priority=(p0|p1|p2)` (case-insensitive)
   - If found, normalize to uppercase: `priority_filter = "P0"`, `"P1"`, or `"P2"`
   - If not found, set `priority_filter = null` (generate all scenarios)

2. **Validate priority value:**
   - If flag is present but value is invalid (not p0/p1/p2), report error:

     ```text
     Error: Invalid priority value.
     Use --priority=p0, --priority=p1, or --priority=p2
     ```

   - Exit command

3. **Log filter status:**
   - If `priority_filter` is set: "Filtering test generation to priority {priority_filter}"
   - If null: "Generating tests for all priorities"

## Step 1: Check Feature Toggles

Scan `{project_context.config_dir}/` for language YAML files with
`enabled: true` (e.g., `tier1.yaml`, `tier2.yaml`).

Also check feature toggles:
- If `tier1_tests` is false and no Go config exists → skip Go
- If `tier2_tests` is false and no Python config exists → skip Python

If no language configs are found and both tier toggles are false:
- Report: "No test generation targets configured for this project."
- Exit

## Step 2: Verify STD Exists

Check for STD YAML at `outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml`.
If not found, tell the user to run `/std-builder {JIRA_ID}` first.

## Step 2.2: Require the Tests Repo Checkout

Generation needs the real suite; without it every fixture name and import is a
guess. Find the checkout:

- **Configured project:** in `{config_dir}/repositories.yaml`, the repo that
  holds this language's tests: `tier2_repo` when it is set and its `language`
  matches the STD's `code_generation_config.language`, else `primary_repo`. The
  checkout is the directory in the environment variable its `local_path_env`
  names (for example `SOURCE_REPO_PATH`).
- **Auto-discovered project** (`config_dir: null`):
  `project_context.discovery.source_repo_path`.

If there is no such variable, or it does not point at a directory, **stop**
before touching pipeline state:

```text
Error: /generate-tests needs a local checkout of {repo full_name}.
Clone it and set {local_path_env} to its path, then re-run.
```

Do not generate without it.

Then pick each scenario's target directory, repo-relative:
`code_generation_config.target_test_directories` / `target_test_directory` from
the STD. When the STD names none, or names one outside the checkout, use the
folder of the existing tests closest to the feature (grep the checkout for the
STD's component and feature terms) and say so in the summary.

## Step 2.5: Pipeline State

Code generation is a **single generic phase** (`codegen`), regardless of how
many languages Step 1 enables — the phase machine is language-agnostic. Use the
Skill tool to invoke the pipeline-state skill once:

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "start-phase {JIRA_ID} codegen"

This will:
1. Read or initialize pipeline state
2. Validate prerequisites (`std.status == completed`)
3. Check approval gate: if `std_review` is in `approval_gates` (default: yes),
   verify `outputs/{JIRA_ID}/state/approvals.yaml` has `std_review.status == approved`
4. Check if the STD has been modified since it was recorded (staleness)
5. Update the phase status to `in_progress`

**If the approval gate blocks:** Show message: "STD Review is awaiting human
approval. Approve the reviewed STD from the dashboard, or record it in
`outputs/{JIRA_ID}/state/approvals.yaml`. (The review cycle runs automatically
inside `/std-builder`; if no review report exists yet, run
`/review-std {JIRA_ID}` and `/refine-std {JIRA_ID}`.)" and exit — do not
generate for ANY language. The gate is on the STD itself, not per-language,
so one block means the STD is not approved.

**If prerequisites are not met:** Show the suggestion (e.g., "Run
`/std-builder` first") and exit.

**If the STD is stale:** Show the warning but continue. The user can choose
to re-run `/std-builder` if needed.

## Step 3: LSP Pattern Analysis (if enabled)

If `lsp_analysis` toggle is true:

Use the Skill tool to invoke the lsp-tracer skill:

**Tool:** Skill
**Parameters:**
- skill: "lsp-tracer"
- args: "{JIRA_ID}"

Use the Skill tool to invoke the feature-finder skill:

**Tool:** Skill
**Parameters:**
- skill: "feature-finder"
- args: "{JIRA_ID}"

## Step 3.5: Collect the Suite's Vocabulary

For each target directory and language, run from the QualityFlow root:

```bash
python3 skills/test-generator/repo_context.py context "$CHECKOUT" {target_dir} --language {python|go}
```

It prints the fixtures every `conftest.py` on the path from the repo root to
the target directory defines (and the `pytest_plugins` modules they load), the
helper modules the sibling tests import, the markers the repo registers
(`pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg`, `pytest_configure`),
whether `--strict-markers` is on, and up to three sibling tests. That output is
the generator's **allowed vocabulary**: pass it to Step 4 as is. This replaces
the ticket-context-analyzer agent for code generation; do not invoke it here.

## Step 4: Generate Tests

Use the Skill tool to invoke the test-generator skill:

**Tool:** Skill
**Parameters:**
- skill: "test-generator"
- args: "{JIRA_ID} {priority_filter}"
  (e.g., "PROJ-12345 P0" if filtering, "PROJ-12345" if not)

Hand it the checkout path and Step 3.5's vocabulary. The skill writes each test
to `outputs/{JIRA_ID}/{language}-tests/` and to its repo-relative `target_path`
in the checkout, and records `target_path` per file in that folder's
`summary.yaml`.

## Step 4.5: Verify in the Checkout

Run the check inside the checkout, with the repo's own tooling, on the files
written there:

```bash
python3 skills/test-generator/repo_context.py verify "$CHECKOUT" {target_path} ... \
  --repos-yaml {project_context.config_dir}/repositories.yaml
```

- Python: `uv run pytest --setup-plan -q <files>` when the repo has `uv.lock`,
  else `python -m pytest --setup-plan -q <files>` (the repo's `.venv` when it
  has one): it collects every file AND resolves every fixture a test asks for,
  running nothing — `--collect-only` let an invented fixture name pass. A file
  pytest's default discovery would skip (`test_*.py` / `*_test.py`) fails
  outright. The repo entry's `verify: {env, args}` is applied: what the repo's
  own CI sets to collect offline, e.g. an env var that stops its conftest from
  contacting a cluster (config/README.md).
- Go: `go vet ./<pkg>`, then `go test -run xxx -count=0 ./<pkg>` (compiles
  the test binary, runs nothing).

It prints `verification: passed | failed | skipped`, a `reason` and the
command. On `failed`, fix the tests (never by faking a fixture or helper) and
re-run, at most 3 attempts. `skipped` means the tool could not run (uv, pytest
or go missing, a timeout); say why.

Collection and compilation are the limit of an offline check: imports,
fixture names, markers and syntax resolve, but **no test ran**. Never claim
the tests pass.

## Step 5: Report Results

Show a summary of generated files with their `target_path`, test counts, any
fixtures the generator had to add (and where), the verification result and
reason, and the line: "Verification collects/compiles the tests in your
checkout; it does not run them."

## Step 6: Update Pipeline State (on completion)

Close out the single `codegen` phase started in Step 2.5, honestly.

**If generation produced test files**, whatever the verification result:

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "complete-phase {JIRA_ID} codegen"

Pass `--output outputs/{JIRA_ID}/{language}-tests/summary.yaml` for the primary
language (complete-phase records its checksum; a missing file warns without
failing) and phase-specific data:

```yaml
test_count: {TEST_COUNT}
files: {FILE_COUNT}
verification: passed | failed | skipped
verification_reason: "{reason from Step 4.5}"
```

With several languages, record the worst result (`failed`, then `skipped`,
then `passed`) and name each language's in the reason. The status stays
`completed`; `verification` other than `passed` marks the
tests unverified, and the dashboard keeps the phase labelled experimental.

**If generation errored and produced no test files:**

**Tool:** Skill
**Parameters:**
- skill: "pipeline-state"
- args: "fail-phase {JIRA_ID} codegen"

with the error message.

After the state updates, show the **next-step suggestion** from the response.
