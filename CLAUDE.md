# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QualityFlow is an AI-powered, multi-project test planning and code generation framework. It provides Claude Code and Cursor AI with agents, commands, and skills that automate:

- **STP (Software Test Plan)** generation from Jira tickets or GitHub issues
- **STD (Software Test Description)** YAML specifications from STPs
- **Working test implementations** in any language/framework (driven by project config)

## Deployment

Requires [uv](https://github.com/astral-sh/uv). No traditional build system — the project is entirely markdown, YAML, and a Python deployment script.

```bash
uv run deploy.py --target claude              # Deploy to ~/.claude/
uv run deploy.py --target cursor              # Deploy to ~/.cursor/
uv run deploy.py --target both                # Deploy to both
uv run deploy.py --target both --scope project --project-path /path/to/project
uv run deploy.py --dry-run --target both      # Preview changes
uv run deploy.py --target both --validate     # Validate configs before deploying
```

After deployment, restart Claude Code or Cursor AI to load resources.

## CI/CD

GitHub Actions workflows in `.github/workflows/validate.yml`:
- **config-validate**: Validates all project configs against `_schema.yaml`
- **deploy-dry-run**: Runs `deploy.py --dry-run` to catch broken resource copies
- **lint-specs**: Checks frontmatter in agents/commands, SKILL.md presence in skills, output path consistency

Config validation can also be run locally:
```bash
python config/validate.py config/                    # Validate all projects
python config/validate.py config/projects/example/   # Validate one project
```

## Architecture

### Resource Types

Resources are deployed to `.claude/` and/or `.cursor/` directories. The `config/` directory stays at the project root and is read at runtime.

| Source | Deployed To |
|--------|-------------|
| `agents/*.md` | `{base}/agents/` |
| `commands/*.md` | `{base}/commands/` |
| `skills/{name}/` | `{base}/skills/{name}/` |
| `config/` | *(not deployed — read from project root at runtime)* |

### Pipeline Flow

```
/stp-builder {JIRA_ID}
  → STP markdown (outputs/{JIRA_ID}/stp/{JIRA_ID}_test_plan.md)

/review-stp {JIRA_ID}
  → STP review report (outputs/{JIRA_ID}/reviews/{JIRA_ID}_stp_review.md)

/std-builder {JIRA_ID}
  → STD YAML (outputs/{JIRA_ID}/std/{JIRA_ID}_test_description.yaml)
  → Test stubs (outputs/{JIRA_ID}/std/{language}-tests/, one dir per tier language)

/review-std {JIRA_ID}
  → STD review report (outputs/{JIRA_ID}/reviews/{JIRA_ID}_std_review.md)

/generate-tests {JIRA_ID}
  → Working test implementations (language determined by project config)
  → outputs/{JIRA_ID}/{language}-tests/ (language determined by tier config)

/fix-pr {PR_URL} [--dry-run] [--review-id=ID]
  → Fixes STP/STD documents in a PR based on review comments
  → Posts fix summary comment on PR
  → Commits and pushes updated documents
```

### Agent Orchestration

The STP pipeline uses sequential agent orchestration:

1. **jira-collector** or **github-issue-collector** — fetches issue data and linked issues via MCP (selected based on `issue_source` in project context)
2. **github-pr-fetcher** — fetches PR diffs and review comments via MCP
3. **regression-analyzer** — LSP-based call graph tracing for impact analysis
4. **stp-generator** — generates STP markdown using skills (requirement-mapper, scenario-builder, tier-classifier or test-strategy-resolver, template-engine)
5. **document-formatter** — PII sanitization and structural validation

The **stp-orchestrator** agent coordinates this pipeline. In code generation, `/generate-tests` extracts LSP patterns via the **lsp-tracer** and **feature-finder** skills.

The **PR fix loop** uses the **pr-fix-agent** to process review comments on PRs containing STP/STD documents. It classifies comments (via **comment-classifier**), auto-fixes what it can using existing skills, and flags the rest for human input. Triggered by `/fix-pr` or by CI on `pull_request_review.submitted` events.

### Skills

Skills are reusable, specialized units invoked by agents. Each skill lives in `skills/{name}/` and contains a `SKILL.md` defining its behavior. Key categories:

- **Config:** project-resolver (Step 0 for all commands)
- **Analysis:** lsp-tracer, feature-finder, pr-analyzer
- **Mapping:** requirement-mapper, scenario-builder, tier-classifier, test-strategy-resolver
- **Generation:** template-engine, std-generator, test-generator (unified, config-driven)
- **Stubs:** stub-generator (unified, config-driven)
- **Review:** stp-reviewer, std-reviewer, review-rules-extractor
- **PR Fix Loop:** comment-classifier (classifies review comments for auto-fix routing)
- **Utility:** jira-parser, link-resolver, pii-sanitizer, output-validator, table-generator

### MCP Server Integration

Configured in `~/.claude/.mcp.json` — four servers provide external data access:

- **mcp-atlassian** — Jira issue retrieval via API v3 (tools `mcp__mcp-atlassian__*`, uses API token auth)
- **github** — PR diffs and code search (runs via npx)
- **gitlab** — Repository browsing and MR data (runs via npx)
- **deepwiki** — AI-powered repository documentation and architecture analysis

Jira uses API token auth (email + token in env vars). GitHub uses `GITHUB_PERSONAL_ACCESS_TOKEN`. GitLab uses `GITLAB_PERSONAL_ACCESS_TOKEN`.

## Multi-Project Configuration

QualityFlow supports multiple projects through a directory-per-project config system.

### Config Structure

```
config/
  _schema.yaml                    # Validation rules
  _defaults.yaml                  # Shared defaults (all projects inherit)
  routing.yaml                    # Issue source → project routing (Jira prefixes + GitHub repos)
  projects/
    example/                      # Example project skeleton (copy for your project)
      project.yaml               # Identity, toggles, scope boundaries
      repositories.yaml          # Repos, orgs, build system
      components.yaml            # Component → package mappings
      jira.yaml                  # Jira instance config
      environment.yaml           # Platform requirements
      pii_exceptions.yaml        # PII allowlist
      coverage.yaml              # Coverage tracking config
      patterns/                  # Pattern detection rules
      reference/                 # Reference test files
      templates/                 # Code/document templates
```

### Config Loading Flow

Every command invokes the **project-resolver** skill as Step 0:

1. Parse input → detect source type (Jira or GitHub)
2. For Jira: extract prefix (e.g., `PROJ` from `PROJ-12345`) → match against `routes[].jira_prefixes`
3. For GitHub: extract `owner/repo` (e.g., `my-org/my-repo` from URL or short form) → match against `routes[].github_repos`
4. Read `config/routing.yaml` → resolve to project (e.g., `example`)
5. Load `config/_defaults.yaml` + `config/projects/example/project.yaml`
6. Merge feature toggles (project overrides defaults)
7. Return `project_context` with `config_dir`, `feature_toggles`, `issue_source`, identity

**Auto-discovery fallback:** When routing lookup fails and
`SOURCE_REPO_PATH` is set, the project-resolver scans the target repo
for language markers (`go.mod`, `pyproject.toml`, etc.) and test
conventions. It returns a synthesized `project_context` with
`config_dir: null` and `test_strategy: "auto"`. All downstream skills
check `config_dir` before reading tier config files.

Agents then read only the config files they need from `config_dir`.

### Feature Toggles

| Toggle | Default | Effect when false |
|--------|---------|-------------------|
| `test_case_markers` | false | Omit external test case management markers in stub-generator and test-generator |
| `polarion` | false | Omit Polarion test case markers in stub-generator and test-generator (project-specific alias for `test_case_markers`) |
| `unit_tests` | false | Informational only (no command or skill gates on this toggle) |
| `exclude_unit_from_stp` | false | When true, exclude unit-level test scenarios from STP generation |
| `test_strategy` | `"auto"` | `"auto"`: detect language/framework from source repo. `"tier"`: use `tier*.yaml` configs for classification and code generation |
| `tier1_tests` | true | Block tier 1 test generation in `/generate-tests`, skip tier 1 stubs in `/std-builder`. Only applies when `test_strategy: "tier"`. Legacy — prefer `enabled` field in tier config |
| `tier2_tests` | true | Block tier 2 test generation in `/generate-tests`, skip tier 2 stubs in `/std-builder`. Only applies when `test_strategy: "tier"`. Legacy — prefer `enabled` field in tier config |
| `stp_generation` | true | Block `/stp-builder` with early exit |
| `std_generation` | true | Block `/std-builder` with early exit |
| `stp_review` | true | Block `/review-stp` with early exit |
| `std_review` | true | Block `/review-std` with early exit |
| `lsp_analysis` | true | Skip regression-analyzer in STP pipeline, skip lsp-tracer/feature-finder in code generation |
| `pii_sanitization` | true | Skip pii-sanitizer invocation in document-formatter |

### Review Rules Resolution

The review commands (`/review-stp`, `/review-std`) use the **review-rules-extractor** skill
to produce project-specific review rules automatically. The skill reads existing config files
(`project.yaml`, `components.yaml`, `tier1.yaml`, `tier2.yaml`, `patterns/tier1_patterns.yaml`)
and optionally scans locally available repositories to extract a complete `review_rules`
structure. A static `review_rules.yaml` is optional -- if present, its values override the
dynamically extracted rules.

### Adding a New Project

1. Create `config/projects/{name}/` with required YAML files
2. Add route(s) in `config/routing.yaml`
3. Set `feature_toggles` to enable/disable capabilities
4. Deploy: `uv run deploy.py --target both`

Review rules are extracted automatically from the config files at review time. Optionally
create a `review_rules.yaml` to override specific values (e.g., `internal_to_user_mappings`,
`layered_product` scope).

## Source of Truth for Resources

The `agents/`, `commands/`, and `skills/` directories are the **source of truth** for all agents, commands, skills, and slash commands. The `config/` directory is the **source of truth** for project configuration. The `.claude/` and `.cursor/` directories are deployment targets — they contain copies produced by `deploy.py`.

When asked to edit agents, commands, or skills, always make changes in `agents/`, `commands/`, or `skills/`.
When asked to edit project config, always make changes in `config/`.
Never edit files under `.claude/` or `.cursor/` unless the user explicitly provides the exact path.

## Key Conventions

### Test Tier Classification (Tier Mode)

When `test_strategy: "tier"`, tiers are defined by the project's `tier*.yaml` config files.
Each tier config specifies its own language, framework, and scope. Teams can define any
number of tiers (tier1.yaml, tier2.yaml, tier3.yaml, etc.) using the `tier.yaml.example` template.

Unit Tests are always available as a built-in tier (developer-responsibility, not auto-generated).

### Auto Mode (Detection-Driven)

When `test_strategy: "auto"` (or when project-resolver auto-detects an
unconfigured project), QualityFlow uses detection-driven routing instead
of tier classification:

- The **test-strategy-resolver** skill scans the source repository to
  detect language, framework, and conventions
- Scenarios use descriptive labels ("unit", "functional", "integration",
  "e2e") instead of tier numbers
- Code generators read framework and imports from `code_generation_config`
  in the STD YAML, not from `tier*.yaml` configs
- `config_dir: null` is the universal signal to all downstream skills
  that they're in auto-discovery mode

### Coverage Deduplication

The regression-analyzer produces an `existing_test_coverage` section that
maps symbols to their existing test functions. The stp-generator uses
this to tag requirements with `coverage_status`:

| Status | Meaning | STP/STD behavior |
|--------|---------|------------------|
| `NEW` | No existing tests cover this behavior | Generate scenario normally |
| `PARTIAL_COVERAGE` | Some aspects covered, gaps remain | Generate scenario for uncovered gap only |
| `EXISTING_COVERAGE` | Fully covered by existing tests | Show in STP Section III as informational; skip stub/test generation |

When `coverage_status` is absent, treat it as `NEW` (backward compatible).

**Measured coverage overrides this.** The table above is driven by static
analysis: a symbol counts as covered because a test function *references* it.
When the pipeline runs on a pull request, the **pr-analyzer** skill measures
which added lines are actually executed (from the PR's coverage check run, a
local coverage profile, or CoverPort) and emits a `coverage_gaps` block. A
symbol whose changed lines measure as unhit is downgraded from
`EXISTING_COVERAGE` to `PARTIAL_COVERAGE`, and its scenarios carry
`coverage_targets` naming the `file:lines` they must make execute. See
**scenario-builder** for the override rule. Set `COVERAGE_MODE=off` to disable.

### Output File Naming

**Pipeline artifacts** (intermediate, cleaned up post-pipeline):

```
outputs/
└── {JIRA_ID}/
    ├── stp/
    │   └── {JIRA_ID}_test_plan.md
    ├── reviews/
    │   ├── {JIRA_ID}_stp_review.md
    │   └── {JIRA_ID}_std_review.md
    ├── std/
    │   ├── {JIRA_ID}_test_description.yaml
    │   └── {language}-tests/           (one dir per tier language)
    │       └── {feature}_stubs{ext}
    └── {language}-tests/
        └── summary.yaml                (metadata only)
```

**Co-located test files** (final, placed in source package directories):

```
{target_test_directory}/
└── qf_{feature}{ext}                   (co-located with production code, naming per language convention)
```

The `qf_` filename prefix distinguishes QF-generated tests from
hand-written and FS-generated tests. All `qf_*` files are discoverable
via `find . -name 'qf_*'`.

When `target_test_directory` is unresolvable (no source repo, no
package mapping), tests fall back to `outputs/{JIRA_ID}/{language}-tests/`.

### PSE Format for Test Docstrings

All generated test stubs use Preconditions/Steps/Expected documentation:

```
Preconditions: Running VM, network namespace configured
Steps:
  1. Create network interface spec
  2. Call hotplug API
Expected: Interface attached successfully, traffic flows
```

### PII Sanitization Rules

- Customer names → `<customer>`, `Example Corp`
- IP addresses → RFC 5737 examples (192.0.2.0/24)
- Hostnames → Generic names (worker-node-1, test-vm)
- Domains → example.com

### Pattern Libraries

Generated tests use project-specific pattern libraries for idiomatic code:

- Per-tier pattern files: `config/projects/{project}/patterns/tier{N}_patterns.yaml`

Intended guidance: fresh LSP patterns (from regression-analyzer) should take priority over historical patterns. This precedence is advisory — it is not currently enforced by a mechanism.

### STP Document Structure

STPs follow a project-specific template at `config/projects/{project}/templates/stp/stp-template.md` with four sections:

- Section I: Motivation & Requirements Review (requirement review checklist, known limitations, technology review)
- Section II: Software Test Plan (scope, goals, strategy, environment, risks)
- Section III: Test Scenarios & Traceability (requirements-to-tests mapping, bullet-based format)
- Section IV: Sign-off & Approval

The STP uses checkbox-based and bullet-list formats (not tables) for most sections.
Section III uses a bullet-based format: `- **[Jira-ID]** — requirement summary` with indented test scenario and priority.

### Two-Phase Test Generation with Review

Phase 1 (Design): `/stp-builder` produces the STP, then
`/review-stp` performs automated QE review (7 dimensions
including rule compliance, requirement coverage, and scenario
quality). `/std-builder` produces STD YAML + stub files with
`PendingIt()` (Go) or `__test__ = False` (Python), then
`/review-std` performs automated review (6 dimensions including
STP-STD traceability, pattern correctness, and code generation
readiness). Stub files use the `_stubs` suffix
(`_stubs_test.go` for Go, `test_*_stubs.py` for Python) and
are written to `outputs/{JIRA_ID}/std/`.

Phase 2 (Implementation): `/generate-tests` fills in working
test bodies that compile (Bazel for Go) or pass collection (pytest).
The language and framework are determined by project config.
Implementations are written to separate directories
(`outputs/{JIRA_ID}/{language}-tests/`),
so Phase 1 stubs are preserved for reference.

### Automated Review System

Review commands (`/review-stp`, `/review-std`) perform semantic
QE review — evaluating content quality, accuracy, and
completeness rather than structural validation (which
output-validator already handles). Reviews produce structured
reports with verdicts:

| Verdict | Meaning |
|---------|---------|
| `APPROVED` | 0 critical, 0 major findings |
| `APPROVED_WITH_FINDINGS` | 0 critical, 1+ major/minor findings |
| `NEEDS_REVISION` | 1+ critical findings |

Review reports are saved to `outputs/{JIRA_ID}/reviews/`.

## Interactive Demo

An interactive HTML demo showcasing the QualityFlow pipeline lives at
`outputs/demos/qualityflow-pipeline-demo.html` and can be deployed via
GitLab Pages or GitHub Pages when demo files change on `main`.

If changes are made to the pipeline flow (new agents, new commands,
new pipeline steps, or changes to the STP/STD/code generation structure),
update the demo HTML to reflect the current pipeline.

## Configuration Documentation

The file `config/README.md` documents the multi-project configuration system
(directory structure, YAML file reference, feature toggles, adding new
projects). Keep it in sync with the actual configuration:

- When adding, removing, or renaming YAML files under `config/` or
  `config/projects/`, update `config/README.md` to reflect the change.
- When adding or changing feature toggles in `_defaults.yaml` or any
  `project.yaml`, update the Feature Toggles Reference table in
  `config/README.md`.
- When changing the config loading flow (project-resolver skill, routing
  logic, defaults merging), update the relevant sections in
  `config/README.md`.
- When adding a new project under `config/projects/`, verify the
  step-by-step guide in `config/README.md` is still accurate.