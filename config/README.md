# QualityFlow Configuration Guide

This directory contains the multi-project configuration system for QualityFlow.
Each project gets its own subdirectory under `projects/` with YAML files that
control every aspect of test plan generation, test code generation, and
pipeline behavior.

## How Config Loading Works

Every QualityFlow command (`/stp-builder`, `/std-builder`, `/generate-tests`)
invokes the **project-resolver** skill as Step 0:

1. Parse the Jira ID to extract the prefix (e.g., `MYPROJ` from `MYPROJ-123`)
2. Look up the prefix in `routing.yaml` to find the project (e.g., `example`)
3. Load `_defaults.yaml` (shared defaults for all projects)
4. Load `projects/<project>/project.yaml` (project-specific overrides)
5. Merge feature toggles (project values override defaults)
6. Return `project_context` with `config_dir`, `feature_toggles`, and identity

Agents then read only the config files they need from the resolved `config_dir`.

## Directory Structure

```text
config/
  _schema.yaml                          # Validation rules for project configs
  _defaults.yaml                        # Shared defaults (all projects inherit)
  routing.yaml                          # Jira prefix -> project routing
  projects/
    example/                            # Example project (copy for your own)
      project.yaml                      # Identity, toggles, scope boundaries
      repositories.yaml                 # Repos, orgs, build system
      components.yaml                   # Component -> package mappings
      jira.yaml                         # Jira instance config
      environment.yaml                  # Platform requirements
      pii_exceptions.yaml               # PII allowlist
      coverage.yaml                     # Coverage tracking config
      patterns/                         # Pattern detection rules
        tier{N}_patterns.yaml            # Per-tier code patterns
      reference/                        # Reference test files
      templates/                        # Code/document templates
        stp/                            # STP document templates
        std/                            # STD YAML templates
```

## Adding a New Project

### Step 1: Copy the example skeleton

```bash
cp -r config/projects/example config/projects/<name>
```

### Step 2: Add routes in `routing.yaml`

Add one or more prefix entries that map Jira issue prefixes to your project:

```yaml
routes:
  - prefix: "MYPROJ"
    project: "<name>"
  - prefix: "MYBUGS"
    project: "<name>"
```

### Step 3: Edit the YAML files

Update each file with your project's real values. The required files are:

| File | Purpose |
|------|---------|
| `project.yaml` | Core identity, feature toggles, scope boundaries |
| `repositories.yaml` | Repository locations and build configuration |
| `components.yaml` | Component-to-package mappings for code analysis |
| `jira.yaml` or `github.yaml` | Issue source config — at least one of the two is required. `jira.yaml`: Jira instance URL, prefixes, custom fields. `github.yaml`: GitHub label mappings (free-form) |
| `environment.yaml` | Platform, cluster requirements |
| `pii_exceptions.yaml` | Allowed names and vendor replacements |

### Step 4: Create optional files based on feature toggles

| File | Required when |
|------|---------------|
| `tier*.yaml` (one per tier) | `test_strategy: "tier"`. Copy `tier.yaml.example` for each tier your project defines |
| `code_generation_config.yaml` | `test_strategy: "tier"` with custom code gen settings |
| `coverage.yaml` | Coverage tracking is needed, or coverage-gap driven test planning is wanted on PRs |

### Step 5: Add optional directories

These directories are optional but recommended:

- `patterns/` -- Pattern YAML files for code generation
- `reference/` -- Example test files the generators learn from
- `templates/` -- STP/STD/test file templates

### Step 6: Deploy and test

```bash
uv run deploy.py --target both
# Then run a command against a Jira ID with your new prefix
```

## File Reference

### routing.yaml

Maps Jira issue prefixes to project directories.

```yaml
version: "1.0"

routes:
  - prefix: "MYPROJ"        # Jira prefix to match
    project: "example"       # Directory name under projects/

default_project: null        # null = fail on unknown prefix
                             # Set to a project ID for fallback
```

Multiple prefixes can route to the same project (e.g., if your team uses
multiple Jira boards).

### project.yaml

Core identity and behavior configuration.

```yaml
project_id: "example"                           # Must match directory name
display_name: "My Project"                      # Human-readable name
description: "Example project for QualityFlow"
```

**feature_toggles** -- Override defaults from `_defaults.yaml`:

```yaml
feature_toggles:
  test_strategy: "auto"     # "auto" or "tier"
  # Per-tier enable/disable is controlled by the `enabled` field in each tier*.yaml
```

See [Feature Toggles Reference](#feature-toggles-reference) for all toggles.

**versioning** -- Product and platform version strings used in STP documents:

```yaml
versioning:
  product_name: "My Product"
  platform_name: "Kubernetes"
  current_version: "1.0"
```

**time_saved** -- Per-team calibration for the dashboard's "Time Saved"
estimate. Any subset overrides the shared defaults in `_defaults.yaml`; unset
keys inherit. These are assumptions about by-hand authoring effort, not measured
numbers -- set them to what an STP / scenario / test actually costs your team.

```yaml
time_saved:
  hours_per_stp: 2.0        # per generated STP
  hours_per_scenario: 0.5   # per STD scenario (when the STD carries scenario metadata)
  hours_per_std: 1.5        # flat per-STD fallback when a doc has no scenario metadata
  minutes_per_test: 20      # per generated test
```

Resolution precedence per coefficient: `project.yaml time_saved` >
`_defaults.yaml time_saved` > `QF_HOURS_PER_*` / `QF_MINUTES_PER_TEST` env var >
built-in default. The env vars remain a deployment-level fallback for keys set
in neither config file.

**scope_boundaries** -- Define what is in/out of scope for this project:

```yaml
scope_boundaries:
  validation_gate: "Does this test exercise our project's code?"
  testing_levels:
    reject:
      - level: "Platform"
        description: "Core platform features not owned by this team"
    accept:
      - level: "Project"
        description: "Features owned and maintained by this team"
```

### repositories.yaml

Repository locations for code analysis and test generation.

**primary_repo** (required) -- The main source code repository:

```yaml
primary_repo:
  name: "my-project"                   # Repository name
  org: "my-org"                        # GitHub organization
  full_name: "my-org/my-project"       # org/name
  url: "https://github.com/my-org/my-project"
  local_path_env: "SOURCE_REPO_PATH"   # Env var pointing to local clone
  default_branch: "main"
  language: "go"                       # Primary language
  build_system: "make"                 # Build system (make, bazel, etc.)
  build_command: "make test"           # Command to run tests
```

**tier2_repo** (optional) -- Separate repository for end-to-end tests:

```yaml
tier2_repo:
  name: "my-project-e2e"
  org: "my-org"
  full_name: "my-org/my-project-e2e"
  default_branch: "main"
  language: "python"
```

### components.yaml

Maps source code components to package paths and features. Used by the
regression-analyzer and code generation agents to understand project structure.

```yaml
component_package_map:
  api:
    package_path: "pkg/api/"
    features:
      - { name: "REST API", path: "pkg/api/handlers/" }
      - { name: "Authentication", path: "pkg/api/auth/" }

path_to_feature:
  "pkg/api/handlers/": "REST API"
  "pkg/api/auth/": "Authentication"
```

### jira.yaml

Jira instance configuration for the jira-collector agent.

```yaml
instance:
  url: "https://your-org.atlassian.net"
  browse_pattern: "https://your-org.atlassian.net/browse/{key}"

prefixes:
  - "MYPROJ"

custom_fields:
  feature_link: "Feature Link"
  git_pull_request: "Git Pull Request"

pr_url_scan_pattern: "https://github.com/.*/pull/\\d+"
```

### tier*.yaml (tier configs)

Per-tier test generation configuration. Each project defines its own tiers
using `tier.yaml.example` as a template. Each tier specifies its own language
and framework — there is no hardcoded mapping between tier numbers and languages.

Copy `tier.yaml.example` once per tier: `tier1.yaml`, `tier2.yaml`, `tier3.yaml`, etc.

```yaml
enabled: true
tier: "Tier 1"                     # Tier label (must be unique per project)
display_name: "Functional"         # Human-readable tier name
language: "go"                     # Any language: go, python, java, rust, etc.
framework: "ginkgo-v2"            # Framework for this tier
```

Key sections (vary by language):

- **imports** -- Organized by category (language-specific)
- **helper_libraries** -- Test helper package import paths
- **timeout_constants** -- Named timeout constants available in the framework
- **test_patterns** -- Framework-specific naming conventions
- **reference_guide** -- URL to team's testing guide for this tier
- **reference_tests** -- URLs to example test files

### code_generation_config.yaml

Project-specific code generation settings used by the `std-generator` skill
when producing STD YAML in tier mode. In auto mode (`test_strategy: "auto"`
or `config_dir: null`), the `test-strategy-resolver` skill detects these
values from the source repository instead.

Key sections:

- **framework/language** -- Target test framework and language
- **imports** -- Organized import groups for generated test files
- **helper_library_imports** -- Import paths for test helper packages
- **helper_functions** -- Available functions per helper library
- **variable_type_inference** -- Function name to Go type mapping
- **cleanup_templates** -- Resource cleanup code by type
- **package_name_rules** -- Rules for inferring test package names

### environment.yaml

Platform and infrastructure requirements for test execution.

```yaml
platform:
  name: "Kubernetes"
  short_name: "K8s"
  cli_tools:
    - "kubectl"

cluster_requirements:
  topology: "Single-node"
  min_worker_nodes: 1
```

### pii_exceptions.yaml

Controls PII sanitization behavior. Names listed here are allowed in generated
documents without replacement.

```yaml
allowed_product_names:
  - "Kubernetes"

allowed_project_names:
  - "Go"
  - "Python"

vendor_replacements:
  cloud: "Cloud Provider"
  hardware: "Hardware Vendor"
```

## Feature Toggles Reference

Feature toggles are defined in `_defaults.yaml` and can be overridden per
project in `project.yaml`. Project values take precedence.

| Toggle | Default | Effect |
|--------|---------|--------|
| `polarion` | `false` | `true`: Include Polarion test case markers in generated test stubs and tests. `false`: Omit markers |
| `unit_tests` | `false` | Informational only |
| `test_strategy` | `"auto"` | `"auto"`: Detect language/framework from source repo (see [Auto vs Tier Mode](#auto-vs-tier-mode)). `"tier"`: Use `tier*.yaml` configs for classification and code generation |
| `tier1_tests` | `true` | Legacy toggle for backward compat. Prefer `enabled` field in tier config. Only applies when `test_strategy: "tier"` |
| `tier2_tests` | `true` | Legacy toggle for backward compat. Prefer `enabled` field in tier config. Only applies when `test_strategy: "tier"` |
| `stp_generation` | `true` | `true`: Enable `/stp-builder`. `false`: Block `/stp-builder` with early exit |
| `std_generation` | `true` | `true`: Enable `/std-builder`. `false`: Block `/std-builder` with early exit |
| `stp_review` | `true` | `true`: Enable `/review-stp`, and `/stp-builder` auto-chains review + refinement after generating the STP. `false`: Block `/review-stp` and skip the auto-chain |
| `std_review` | `true` | `true`: Enable `/review-std`, and `/std-builder` auto-chains review + refinement after generating the STD. `false`: Block `/review-std` and skip the auto-chain |
| `lsp_analysis` | `true` | `true`: Run regression-analyzer in STP pipeline, run lsp-tracer/feature-finder in code generation. `false`: Skip LSP-based analysis |
| `pii_sanitization` | `true` | `true`: Run pii-sanitizer in document-formatter. `false`: Skip PII sanitization |

## Auto vs Tier Mode

The `test_strategy` toggle controls how QualityFlow classifies test scenarios
and selects code generation frameworks.

### Tier mode (`test_strategy: "tier"`)

Used by projects that have one or more `tier*.yaml` files in their
config directory:

- **Classification:** The `tier-classifier` skill reads the project's
  tier configs and assigns scenarios to the appropriate tier
- **Code generation:** Reads framework, imports, and patterns from
  each tier's config file
- **Routing:** Each tier config's `enabled` field controls whether
  that tier's generator runs
- **STP labels:** From tier config's `tier` + `display_name` fields
  (e.g., "Tier 1 (Functional)", "Tier 3 (Specialized)")

### Auto mode (`test_strategy: "auto"`)

Used by unconfigured projects or projects without a config directory
(`config_dir: null`):

- **Detection:** The `test-strategy-resolver` skill scans the source
  repository to detect language, framework, and conventions
- **Code generation:** Reads framework, imports, and package name from
  `code_generation_config` in the STD YAML (populated by detection)
- **Routing:** Routes to generators by detected language, not by tier
  counts
- **STP labels:** Descriptive types ("unit", "functional", "integration",
  "e2e") instead of tier numbers
- **Coverage dedup:** Scenarios with `coverage_status: EXISTING_COVERAGE`
  are skipped (no stubs or tests generated for already-tested behaviors)

### Coverage-gap driven planning (PR runs)

When the pipeline is triggered by a **pull request** and `COVERAGE_MODE` is not
`off`, the `pr-analyzer` skill measures which of the PR's added lines are not
executed by tests, and STP scenarios are aimed at those lines.

Sources are tried in order, first answer wins:

| Source | Needs | Gives |
|--------|-------|-------|
| PR coverage check run (`codecov/patch`) | `gh` only | Patch %, per-file %, gate |
| Local coverage profile | `SOURCE_REPO_DIR` + `coverage_gap.command` | Exact uncovered line numbers |
| CoverPort `product_coverage` | Codecov flag, or registry access | Whether code ever ran in a live env |

The `coverage_gap` section of `coverage.yaml` configures sources 2 and 3;
source 1 works with no config. Measured results override the static
`coverage_status` verdict — see the Coverage Deduplication section of the root
`CLAUDE.md`. When no source answers, the pipeline runs exactly as before.

### Feeding live coverage to the dashboard (from CI)

The QualityFlow dashboard ingests raw coverage reports at
`POST /api/coverage/upload` (auto-detects Go `coverage.out`, LCOV, and Cobertura
XML). A composite action ships the report from a product repo's CI — add one
step after your tests produce a coverage file:

```yaml
- uses: redhat-community-ai-tools/qualityflow/.github/actions/coverage-upload@main
  with:
    coverage-file: coverage.out          # or lcov.info / coverage.xml
    dashboard-url: https://qf.example.com # your dashboard base URL, no trailing slash
    api-key: ${{ secrets.QUALITYFLOW_API_KEY }}
    # branch: defaults to github.ref_name
```

`org`, `repo`, and `commit` are derived from the `github` context. Set the
`QUALITYFLOW_API_KEY` repo (or org) secret to match the dashboard's
`QUALITYFLOW_API_KEY`; when the dashboard runs without a key (local mode) any
value is accepted. Uploaded coverage is stored per repo/commit and surfaces in
the dashboard's per-repo coverage view and trend.

Teams **already onboarded to CoverPort** need no CI step: CoverPort's
coverage-processor pipeline publishes coverage to SonarCloud, and the dashboard
reads it back automatically. The per-repo coverage endpoint falls back
direct-upload → SonarCloud → Codecov, so an onboarded repo shows coverage
labelled "via CoverPort (SonarCloud)" out of the box.

Set at deploy time (only for private Sonar projects / self-hosted SonarQube):

- `SONAR_TOKEN` (or `SONARCLOUD_TOKEN`) — auth for private projects.
- `SONAR_HOST_URL` — defaults to `https://sonarcloud.io`; point at a self-hosted
  SonarQube if needed.

The Sonar project key defaults to `{org}_{repo}` (the convention in each repo's
`sonar-project.properties`). Override per repo in `coverage.yaml` with a
`sonar_project_key` field on the repo entry.

### How auto mode activates

Auto mode activates when the project-resolver cannot find a configured
project for the Jira prefix AND the `SOURCE_REPO_PATH` environment
variable points to a local repository checkout. The resolver scans the
repo for language markers (`go.mod`, `pyproject.toml`, etc.) and test
conventions, then returns a synthesized `project_context` with
`config_dir: null` and `test_strategy: "auto"`.

### Toggle interaction

| `test_strategy` | Tier configs | Required? |
|:----------------|:-------------|:----------|
| `"tier"` | `enabled` field in each `tier*.yaml` controls which generators run | At least one `tier*.yaml` (enforced by schema) |
| `"auto"` | Ignored (routing by detected language) | No |

### Auto-discovery `project_context` shape

When auto mode activates, the returned `project_context` looks different from
a configured project:

```yaml
# Auto-discovered (config_dir: null)
project_id: "auto-my-org-my-repo"
display_name: "my-org/my-repo (auto-detected)"
config_dir: null                        # <-- downstream skills check this
feature_toggles:
  test_strategy: "auto"
  lsp_analysis: true
  pii_sanitization: true
detected:
  language: "go"
  framework: "ginkgo-v2"
  test_directory: "tests/"
```

All downstream skills (std-generator, stub-generator, test-generator,
review-rules-extractor) check `config_dir` before reading config files and
fall back to STD YAML metadata or defaults when it is null.

## Config Validation

Validate project configs from the command line:

```bash
# Validate all projects
python config/validate.py config/

# Validate a single project
python config/validate.py config/projects/example/
```

The validation script checks: required files exist, required YAML fields
present, toggle-to-file consistency, and YAML syntax. It also runs as part
of CI (`.github/workflows/validate.yml`).

Add `--validate` to `deploy.py` to validate before deploying:

```bash
uv run deploy.py --target both --validate
```

## Schema Validation

`_schema.yaml` defines validation rules that the project-resolver checks:

- **Required files** -- Every project must have `project.yaml`,
  `repositories.yaml`, `components.yaml`, `environment.yaml`,
  and `pii_exceptions.yaml`
- **Issue source files** -- At least one of `jira.yaml` or `github.yaml`
  must exist and parse (a project needs Jira, GitHub, or both)
- **Optional files** -- `tier*.yaml` configs are required when
  `test_strategy` is `"tier"` (at least one must exist)
- **Required fields** -- Each YAML file has required fields (e.g.,
  `project.yaml` must have `project_id` and `display_name`; tier configs
  must have `enabled`, `tier`, `language`, `framework`)
- **Tier consistency** -- When `test_strategy` is `"tier"`, at least one
  `tier*.yaml` file must exist. These checks are skipped in auto mode

## Defaults Inheritance

`_defaults.yaml` provides shared defaults inherited by all projects:

- **feature_toggles** -- Default toggle values (projects override individual
  toggles, unset toggles inherit the default)
- **output_structure** -- File path patterns for all output types (STP, STD,
  stubs, tests) using `{JIRA_ID}` and `{feature}` placeholders
- **test_id_format** -- Pattern for test scenario IDs
  (`TS-{JIRA_ID}-{NUM:03d}`)
- **pii_rules** -- Default PII replacement values (customer names, IPs,
  hostnames, domains)
- **stp_defaults** -- Default STP document settings

Projects do not need to redefine these values unless they want different
behavior.

## Optional Directories

### patterns/

Contains YAML files with code patterns for the test generators:

- `tier{N}_patterns.yaml` -- Per-tier code patterns (one file per tier)

Fresh LSP patterns extracted at runtime take priority over these historical
patterns.

### reference/

Contains example test files that generators use as style references:

- `tier{N}/` -- Per-tier example test files

Each subdirectory should include a `README.md` explaining what the reference
files demonstrate.

### templates/

Contains templates for document and code generation:

- `stp/` -- STP markdown templates (`stp-template.md`)
- `std/` -- STD YAML templates (`std_template.yaml`)
- `tier{N}/` -- Per-tier test file templates
