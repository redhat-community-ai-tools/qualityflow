---
name: project-resolver
description: Resolve issue input (Jira ID or GitHub issue) to project configuration and load project context
---

# Project Resolver Skill

**Phase:** Pre-Processing (Step 0)
**User-Invocable:** false

## Purpose

Central config loader for QualityFlow's multi-project architecture. Every command
invokes this skill as Step 0 to resolve the issue input to a project and load its
configuration. Supports both Jira issues and GitHub issues as input.

The deterministic work (parse input, route, validate config, merge toggles) is
implemented in `skills/project-resolver/resolve.py`. This skill runs that script
and only falls back to LLM work for two things the script cannot do:
auto-discovery of unconfigured repos, and MCP-based repo file fetching.

## When to Use

Invoked as the **first step** of every command (`stp-builder`, `std-builder`,
`generate-tests`, `review-stp`, `review-std`) before any other processing.

## Tools Required

- Bash
- Read (auto-discovery fallback only)
- mcp__github__get_file_contents (repo_files fetch only)

## Input

```yaml
issue_input: "PROJ-66855"
# or: "https://your-jira.example.com/browse/PROJ-66855"
# or: "https://github.com/owner/repo/issues/1234"
# or: "owner/repo#1234"
```

## Workflow

### Step 1: Run the resolver script

```bash
python3 skills/project-resolver/resolve.py "<issue_input>" [--target <repo>:<path> ...]
```

Pass the issue input and any `--target` the caller names; other flags in the
caller's arguments (`--stp`, `--generate`, `--priority`, ...) are the caller's,
not the script's. The target is what the run works on, a path or
`<repo>:<path in its checkout>` (repo key, type or name, e.g. `tier2_repo:tests/e2e`):

| Caller | Target |
|:-------|:-------|
| `/stp-builder` | `design_docs_repo:stps` (where the STP will live) |
| `/generate-tests` | each scenario's `target_test_directory` in the tests repo (it re-resolves once it has read the STD) |
| `/fix-pr` | each changed STP/STD file of the PR |
| others | none: repo roots only |

The script parses the input (GitHub URL, GitHub short form `owner/repo#N`, Jira
`/browse/` URL, or bare Jira key — tried in that order), routes it via
`config/routing.yaml`, validates the project config against `config/_schema.yaml`
(reusing `config/validate.py`), merges the repo config layers over it (below),
shallow-merges `_defaults.yaml` feature toggles under the project's overrides,
and prints the complete `project_context` YAML to stdout.

**Exit code 0:** stdout is the `project_context`. Use it as-is. Proceed to
Step 2 only if `feature_toggles.repo_files_fetch` is true; otherwise the skill
is done.

**Exit code 3** (stderr starts with `AUTO_DISCOVERY_REQUIRED`): no route matched
but `SOURCE_REPO_PATH` is set. Run the Auto-Discovery Fallback below.

**Any other non-zero exit:** unparseable input, routing miss without
`SOURCE_REPO_PATH`, or invalid project config. Relay the script's stderr to the
user verbatim (it is actionable) and exit the command.

### Ticket repository overlay

The script applies `outputs/{JIRA_ID}/repositories.overlay.yaml` when present:
`only` filters configured repos by type (primary, tier2, design_docs, additional)
or name, `add` appends repository entries to additional_repos, then `paths`
overrides local checkouts by name. It returns `project_context.repositories`
and writes `project_context.repositories_file` (ticket-local
`repositories.resolved.yaml`) for tools needing a filename. Pass these fields
to every downstream agent/skill. They are authoritative: never reload the
shared repository list or use an excluded slot. Prefer `local_path` over the
environment variable. Without an overlay the context and behavior are unchanged.

### Repo config layers (.qualityflow/)

A configured repo's local checkout may carry a `.qualityflow/` directory, at
its root or in any child directory, with config for the code there
(`config/layers.py`; format and rules in config/README.md "Repo config
layers"). The script finds them automatically and merges them over the
central project dir, highest first: the `.qualityflow/` dirs above the target
(deepest first), the target repo's root, the other repo roots in
`config_sources.order`, then `config/projects/{project_id}/`. A checkout is
untrusted: a layer must declare `version: 1` and this `project_id` (another
project's layer is skipped with a warning), may hold only the allowed files and
`project.yaml` keys, and may turn `pii_sanitization`, `repo_files_fetch`,
`stp_review`, `std_review` on but never off. Any other problem exits 1 naming
the file and layer: relay it like any config error.

When a layer applies, `config_dir` points at the merged copy,
`outputs/{JIRA_ID}/config/{project_id}/`, so every agent reading
`{config_dir}/...` sees the merged files unchanged, and the context gains
`config_layers`, `config_provenance` and `config_hash` (Output Format). The
script also writes `outputs/{JIRA_ID}/config.resolved.yaml` (the hash, layers,
provenance and every effective file); pipeline-state's `complete-phase`
records its `config_hash` on the phase. stderr names the layer each
overridden key came from and every warning. Without a `.qualityflow/` the
context is exactly as before.

### Apply model defaults

Use `project_context.model_policy` (shared defaults merged with project runtime
keys). Preserve any explicit user model choice, including runner model-env
settings. Otherwise dispatch collection agents (`jira-collector`,
`github-issue-collector`, `github-pr-fetcher`) and `document-formatter` with
`cheap[runtime]`, reviewers with `review[runtime]`, and other agents with
`standard[runtime]`. Pass this policy and any explicit choice to child agents.
Only review agents/phases may automatically select the review model, including
when a builder auto-chains a review. Use the host's model argument when it
supports one; when unavailable, report that selection is unsupported and inherit.
Inline skills keep their caller's model. Frontmatter remains `inherit` to
preserve explicit choices across Claude, Codex, and Cursor.

### Step 2 (optional): Fetch Repo Files (repo_rules)

**Guard:** Skip this step if `feature_toggles.repo_files_fetch` is false or absent.

Use `project_context.repositories` when present, otherwise read
`{config_dir}/repositories.yaml`, and check for a `repo_files` section.
If present, fetch each declared file from its source repository:

```
For each entry in repo_files:
  repo_config = repositories_yaml[entry.repo]   # org + name from the repo section
  Try:
    content = mcp__github__get_file_contents(
      owner=repo_config.org, repo=repo_config.name,
      path=entry.path, branch=repo_config.default_branch)  # defaults to main
    repo_rules[entry_name] = content
  On failure:
    If entry.fallback: repo_rules[entry_name] = Read("{config_dir}/{entry.fallback}")
    Else: repo_rules[entry_name] = null; log a warning
```

**Parallel fetching:** All repo_files entries are independent — fetch them in
parallel (multiple `mcp__github__get_file_contents` calls in one message).

Attach the result as `project_context.repo_rules` (the script emits `repo_rules: {}`
as the placeholder).

**CODEOWNERS of the design-docs repo.** In the same step, when `repositories.yaml`
has a `design_docs_repo`, fetch `.github/CODEOWNERS`, then `CODEOWNERS`, from it
(`mcp__github__get_file_contents`, or `gh api repos/{org}/{name}/contents/{path}`).
The people who own the STP directory review every STP PR, so stp-generator lists
them as stakeholders. Parse each non-comment line (`<pattern> @owner ...`) into
`project_context.codeowners`; neither file → `codeowners: []`, no warning needed:

```yaml
codeowners:
  - pattern: "/stps/"            # as written in the file
    owners: ["@jsmith", "@my-org/qe-team"]
```

**Past signers.** `past_signers.py --repo {design_docs_repo.full_name}` lists
who signed the repo's merged STPs (`*Sign-off:*`, `*PM/Lead Agreement:*`), with
counts, folders and the date of the newest STP each signed. stp-generator runs
it for the stakeholders sidecar, so an STP's author knows whom to ask for its
sign-offs; it is not part of `project_context`.

### Auto-Discovery Fallback (script exit code 3)

**Trigger:** Routing lookup failed AND `SOURCE_REPO_PATH` points to a local
checkout of the target repository. Synthesize a project context by scanning
the repo.

#### 1. Detect Language

Scan `SOURCE_REPO_PATH` for language markers (check in order, use first match):

| File Present | Language Detected |
|:-------------|:------------------|
| `go.mod` | go |
| `Cargo.toml` | rust |
| `pyproject.toml` or `requirements.txt` or `setup.py` | python |
| `package.json` | typescript/javascript |

If no marker found: default to the most common file extension in the repo.

#### 2. Detect Test Framework

Scan for existing test files near production code:

**Go:**

- Glob `*_test.go` files in `SOURCE_REPO_PATH`
- Read the first 3-5 test files found
- Grep imports for framework detection:
  - `"github.com/onsi/ginkgo"` → framework: `ginkgo-v2`
  - `"github.com/stretchr/testify"` → assertion_library: `testify`
  - `"testing"` (stdlib only) → framework: `testing`
- Read `package` declaration → package_convention: `same-package` or `external`

**Python:**

- Glob `test_*.py` or `*_test.py` files
- Grep imports: `pytest`, `unittest`
- framework: `pytest` or `unittest`

**Fallback:** If no test files found, use safe defaults:

- Go → `framework: "testing"`, `assertion_library: "testify"`, `package_convention: "same-package"`
- Python → `framework: "pytest"`

#### 3. Return Synthesized Project Context

```yaml
project_context:
  project_id: "auto-detected"
  display_name: "{repo directory name}"
  jira_id: "{original input ID, or {owner}-{repo}-{number} for GitHub}"
  issue_source: "jira" | "github"
  config_dir: null
  discovery:
    language: "{detected}"
    framework: "{detected}"
    assertion_library: "{detected or null}"
    package_convention: "{same-package or external}"
    test_file_pattern: "{glob pattern for test files}"
    source_repo_path: "{SOURCE_REPO_PATH}"
  feature_toggles:
    test_strategy: "auto"
    tier1_tests: false
    tier2_tests: false
    unit_tests: false
    stp_generation: true
    std_generation: true
    stp_review: true
    std_review: true
    lsp_analysis: true
    pii_sanitization: false
    repo_files_fetch: false
  stp_header: "Test Plan"
  versioning:
    product_name: "{repo directory name}"
    platform_name: "N/A"
    current_version: "N/A"
  repo_rules: {}
```

**Key:** `config_dir: null` signals to ALL downstream skills that they are in
auto-discovery mode. Skills MUST check for `config_dir: null` before attempting
to read tier1.yaml, tier2.yaml, or any other project config files.

Auto-discovery does not read a repo's `.qualityflow/` yet: with no routed
project there is no `project_id` to check its identity marker against.

## Output Format

The script emits (and the skill returns) this shape:

```yaml
project_context:
  project_id: "{project_id}"
  display_name: "{display_name}"
  jira_id: "PROJ-12345"          # canonical ID; "{owner}-{repo}-{number}" for GitHub
  issue_source: "jira" | "github"
  config_dir: "config/projects/{project_id}"
  feature_toggles:                # _defaults.yaml shallow-merged under project.yaml overrides
    test_strategy: "auto" | "tier"
    unit_tests: true/false
    tier1_tests: true/false
    tier2_tests: true/false
    stp_generation: true/false
    std_generation: true/false
    stp_review: true/false
    std_review: true/false
    lsp_analysis: true/false
    pii_sanitization: true/false
    repo_files_fetch: true/false
  stp_header: "{project.yaml stp_document.header, default 'Test Plan'}"
  versioning:
    product_name: "{from project.yaml, default display_name}"
    platform_name: "{from project.yaml, default 'N/A'}"
    current_version: "{from project.yaml, default 'N/A'}"
  repo_rules: {}                  # populated by Step 2 when repo_files_fetch is true
  codeowners: []                  # design_docs_repo CODEOWNERS, populated by Step 2
```

When a checkout has a `.qualityflow/` (Repo config layers above), also:

```yaml
  config_dir: "outputs/PROJ-12345/config/{project_id}"   # the merged copy
  config_layers:                  # highest precedence first
    - id: "my-tests:tests/e2e"    # {repo name}:{dir in the checkout}
      source: "repo_dir"          # repo_dir | repo_root | central
      repo: "my-tests"
      dir: "tests/e2e"
      files: ["components.yaml", "project.yaml"]
      digest: "sha256:..."
      status: "applied"           # or skipped_mismatch (another project's layer)
      warnings: ["feature_toggles.pii_sanitization: False ignored, ..."]  # when any
    - {id: "central", source: "central", repo: null, dir: "config/projects/{project_id}", status: "applied"}
  config_provenance:              # {file}:{key path} (or a whole file) -> layer id, for overridden keys
    "project.yaml:feature_toggles.lsp_analysis": "my-tests:."
    "templates/stp/stp-template.md": "my-tests:tests/e2e"
  config_hash: "sha256:..."       # of the effective config; stable across identical runs
```

`config_provenance` and `config_hash` are absent when every layer found was
skipped (`config_dir` then stays central).

When `issue_source == "github"`, the script also includes:

```yaml
  github_issue:
    owner: "{owner}"
    repo: "{repo}"
    number: {number}
    url: "https://github.com/{owner}/{repo}/issues/{number}"
```

The `jira_id` field contains the canonical issue identifier regardless of source
and is used in output paths, test IDs, and all downstream processing.

### repo_rules Usage by Skills

| Skill | Uses from repo_rules |
|:------|:--------------------|
| template-engine | `stp_template` — official STP template structure |
| stp-generator | `stp_template`, `stp_guide` — template + guide for generation |
| stp-reviewer | `stp_template`, `stp_guide`, `testing_tiers`, `stp_review_rules` — review against official docs and the team's own review checklist |
| std-generator | `std_format`, `agents_rules` — STD format rules + coding standards |
| stub-generator | `std_format`, `agents_rules` — PSE format + stub conventions |
| test-generator | `agents_rules` — fixture, marker, and code pattern rules |
| std-reviewer | `std_format`, `agents_rules` — validate stubs against repo rules |

## Error Handling

All parse/routing/config errors are produced by the script with actionable
messages — relay stderr verbatim and exit the command. The only non-error
non-zero exit is code 3 (`AUTO_DISCOVERY_REQUIRED`), which routes to the
Auto-Discovery Fallback above.

## Usage by Commands

| Command | Uses from project_context |
|:--------|:--------------------------|
| stp-builder | Passes to stp-orchestrator for all subagents |
| std-builder | Checks tier1_tests/tier2_tests to decide which stubs to generate |
| generate-tests | Checks tier1_tests/tier2_tests; generates for enabled languages |
| review-stp | Uses issue_source to decide Jira vs GitHub data fetch |
| review-std | Checks std_review toggle |

## Usage by Agents

Each agent reads additional config files on-demand from `config_dir`. Repository
reads use `project_context.repositories` / `repositories_file` when present,
including repo_files, CODEOWNERS and past signers; excluded repos are not fetched:

| Agent | Reads from config_dir |
|:------|:----------------------|
| jira-collector | `jira.yaml`, `components.yaml` |
| github-issue-collector | `github.yaml` (optional), `components.yaml` |
| github-pr-fetcher | `repositories.yaml` (optional) |
| regression-analyzer | `repositories.yaml`, `components.yaml` |
| stp-generator | `project.yaml` (incl. `stakeholders`), `environment.yaml`, `tier1.yaml`, `tier2.yaml` |
| document-formatter | `pii_exceptions.yaml` |
| ticket-context-analyzer | `repositories.yaml` |

## Feature Toggle Notes

The `unit_tests` toggle is informational only. It signals whether unit tests are
in scope for a project configuration, but no QualityFlow command or skill gates
on it. The toggles that ARE actively gated by commands, agents, or skills:
`tier1_tests`, `tier2_tests`, `stp_generation`, `std_generation`, `stp_review`,
`std_review`, `lsp_analysis`, `pii_sanitization`, `repo_files_fetch`, `polarion`,
`polarion_lint`.

The `test_strategy` toggle controls how test classification and code generation work:

- `"auto"` (default): detect framework, package, imports from the target repo's
  existing tests. Uses `test-strategy-resolver` skill instead of `tier-classifier`.
  Does not require tier1.yaml/tier2.yaml.
- `"tier"`: use tier classification with project-defined `tier*.yaml` configs.
  Each tier defines its own language and framework. Uses `tier-classifier` skill.

When `config_dir` is `null` (auto-detected project), `test_strategy` is always
`"auto"` and `tier1_tests`/`tier2_tests` are both `false`.
