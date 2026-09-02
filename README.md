# QualityFlow

AI-powered test planning and code generation framework for [Claude Code](https://claude.ai/code) and [Cursor AI](https://cursor.com).

QualityFlow provides agents, commands, and skills that automate the full test engineering lifecycle — from Jira ticket (or GitHub issue) to working test code.

## What It Does

| Command | Output |
|---------|--------|
| `/stp-builder PROJ-12345` | Software Test Plan (STP) markdown |
| `/review-stp PROJ-12345` | Automated QE review of the STP |
| `/refine-stp PROJ-12345` | Iterative STP improvement until approved |
| `/std-builder PROJ-12345` | Test Description YAML + test stubs |
| `/review-std PROJ-12345` | Automated review of the STD |
| `/refine-std PROJ-12345` | Iterative STD improvement until approved |
| `/generate-tests PROJ-12345` | Working test implementations (language from config) |
| `/fix-pr <PR-URL>` | Fix STP/STD documents based on PR review comments |

All commands accept a Jira ID (`PROJ-12345`), a Jira URL, a GitHub issue URL (`https://github.com/my-org/my-repo/issues/1234`), or a GitHub short form (`my-org/my-repo#1234`).

## Pipeline

```
Jira Ticket / GitHub Issue
    |
    v
/stp-builder ──> STP markdown
    |               |
    v               v
/review-stp    /refine-stp (iterative)
    |
    v
/std-builder ──> STD YAML + test stubs (all configured languages)
    |               |
    v               v
/review-std    /refine-std (iterative)
    |
    v
/generate-tests ──> Working test implementations
    |                (language and framework driven by project config)
    v
/fix-pr ──> Auto-fix PR review comments on STP/STD documents
```

## Architecture

QualityFlow is built entirely from markdown and YAML — no compiled code. It uses three resource types that deploy into Claude Code or Cursor AI:

- **Agents** — orchestrate multi-step workflows (e.g., STP generation pipeline with Jira collection, PR analysis, regression tracing, document generation)
- **Commands** — user-invocable slash commands that coordinate agents and skills
- **Skills** — reusable, specialized units for specific tasks (requirement mapping, scenario building, tier classification, template rendering)

### Agent Orchestration (STP Pipeline)

```
stp-orchestrator
    |
    +-- jira-collector             (fetch Jira issue + linked issues)
    +-- github-issue-collector     (fetch GitHub issue + cross-references)
    +-- github-pr-fetcher          (fetch PR diffs and review comments)
    +-- regression-analyzer        (LSP-based call graph tracing)
    +-- stp-generator              (generate STP using skills)
    |       +-- requirement-mapper
    |       +-- scenario-builder
    |       +-- tier-classifier
    |       +-- template-engine
    +-- document-formatter         (PII sanitization + validation)
```

### Multi-Project Support

QualityFlow supports multiple projects through a directory-per-project configuration system:

```
config/
    _defaults.yaml          # Shared defaults
    _schema.yaml            # Validation rules
    routing.yaml            # Jira prefix / GitHub repo -> project routing
    projects/
        example/            # Example project configuration
            project.yaml    # Identity, toggles, scope boundaries
            repositories.yaml
            components.yaml
            jira.yaml
            ...
```

Every command reads the Jira ticket prefix (e.g., `MYPROJ` from `MYPROJ-12345`) or GitHub repo (e.g., `my-org/my-repo`) and routes to the correct project configuration automatically.

## Team Dashboard

Want a shared, always-on view of pipeline runs, approvals, and coverage for your team
instead of (or alongside) the Claude Code CLI flow below? There's a FastAPI dashboard with
a Helm chart for OpenShift/Kubernetes. Start with
**[deploy/ONBOARDING.md](deploy/ONBOARDING.md)** — a 15-minute install-and-wire-your-data
checklist. Full reference (every option, env vars, SSO) is in [deploy/README.md](deploy/README.md).

## Quick Start

Fastest path: the 15-minute checklist in **[ONBOARDING.md](ONBOARDING.md)**, or run the
guided wizard `uv run getting-started.py` to prompt through the same steps. The sections
below are the full manual reference for anyone who wants to see (or script) each step
individually.

### Prerequisites

- [Claude Code](https://claude.ai/code) or [Cursor AI](https://cursor.com)
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Jira API access (API token)
- GitHub access (personal access token)

### Installation

```bash
git clone https://github.com/redhat-community-ai-tools/qualityflow.git
cd qualityflow

# Deploy to Claude Code
uv run deploy.py --target claude

# Or deploy to Cursor AI
uv run deploy.py --target cursor

# Or both
uv run deploy.py --target both

# Preview changes without deploying
uv run deploy.py --dry-run --target claude
```

After deployment, restart Claude Code or Cursor AI to load the resources.

### Verify Installation

After deploying and restarting Claude Code:

1. Open Claude Code in any project directory
2. Type `/stp-builder` — you should see the command recognized with a description
3. If commands are not recognized, ensure you restarted Claude Code after running `deploy.py`

### Set Up MCP Servers

QualityFlow uses [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers to connect to Jira and GitHub. Create or update `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "${JIRA_URL}",
        "JIRA_USERNAME": "${JIRA_USERNAME}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

**What each server does:**

| Server | Purpose | Package |
|--------|---------|---------|
| `mcp-atlassian` | Jira issue retrieval, linked issues, comments | [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian) |
| `github` | PR diffs, code search, file contents, GitHub issues | [@modelcontextprotocol/server-github](https://github.com/modelcontextprotocol/servers/tree/main/src/github) |

Set the environment variables in your shell profile or export them before launching Claude Code.

For Cursor AI, configure MCP servers in Cursor Settings > MCP.

### Set Up LSP Servers (Optional)

For regression analysis and code tracing (`lsp_analysis` toggle), install language servers:

- **Go:** [gopls](https://pkg.go.dev/golang.org/x/tools/gopls) — `go install golang.org/x/tools/gopls@latest`
- **Python:** [pyright](https://github.com/microsoft/pyright) — `npm install -g pyright`

These are used by the regression-analyzer agent to trace call graphs in your project's source code. If you don't need LSP analysis, set `lsp_analysis: false` in your project's `feature_toggles`.

### Configure Your Project

1. Copy the template and fill in your project's values:

```bash
cp onboarding-template.yaml my-project.yaml
# edit my-project.yaml — project_id, display_name, repo_*, jira_url,
# jira_prefixes, platform_name, components are required
```

2. Preview what `onboard.py` will generate:

```bash
uv run onboard.py --input my-project.yaml --dry-run
```

3. Apply it by re-running without `--dry-run`:

```bash
uv run onboard.py --input my-project.yaml
```

This generates the full `config/projects/<project_id>/` YAML set, validates it against
`config/_schema.yaml` before writing anything (nothing is written on a validation
failure), and appends a route to `config/routing.yaml` automatically — skipping the
append if a route for that project already exists. Use `--force` to overwrite an
existing project directory.

#### Or configure by hand

```bash
cp -r config/projects/example config/projects/myproject
```

Edit the YAML files to match your project (Jira instance, repositories, components, test
patterns), then add a route in `config/routing.yaml`:

```yaml
routes:
  - prefix: "MYPROJ"
    project: "myproject"
```

### Re-deploy

Either path needs a re-deploy to pick up the new project config:

```bash
uv run deploy.py --target claude
```

### Generate Your First STP

In Claude Code, run:

```
/stp-builder PROJ-12345
```

Or with a GitHub issue:

```
/stp-builder my-org/my-repo#1234
```

## Configuration

See [`config/README.md`](config/README.md) for the full configuration reference, including:

- Project YAML file reference
- Feature toggles
- Scope boundaries
- Adding new projects

### Feature Toggles

Control which pipeline stages are enabled per project:

| Toggle | Default | Effect |
|--------|---------|--------|
| `test_strategy` | `"auto"` | `"auto"`: detect from repo. `"tier"`: use `tier*.yaml` configs |
| `stp_generation` | true | Enable `/stp-builder` |
| `std_generation` | true | Enable `/std-builder` |
| `lsp_analysis` | true | Run LSP-based regression analysis |
| `pii_sanitization` | true | Run PII sanitization |

## Test Tiers

Tiers are defined per-project via `tier*.yaml` config files. Each tier specifies its own
language, framework, and scope. Teams can define any number of tiers using the
`tier.yaml.example` template. Unit Tests are always available as a built-in tier.

Each tier config includes a `reference_guide` field for the team's testing guide URL
and `reference_tests` for example test file links.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding projects, skills, and agents.

## Glossary

| Term | Definition |
|------|-----------|
| **STP** | Software Test Plan — markdown document mapping Jira requirements to test scenarios with tier classification |
| **STD** | Software Test Description — YAML specification derived from an STP, listing each test scenario with preconditions, steps, and expected results |
| **PSE** | Preconditions / Steps / Expected — structured docstring format used in all generated test stubs |
| **Tier** | Project-defined test classification level. Each tier has its own language, framework, and scope — defined via `tier*.yaml` configs |
| **MCP** | Model Context Protocol — open standard for connecting AI assistants to external tools and data sources |
| **SIG** | Special Interest Group — community team label used in some projects for test organization |
| **Approval gate** | Human-in-the-loop review point where an STP or STD review verdict must be approved before proceeding |
| **PII sanitization** | Automatic replacement of customer names, IPs, and hostnames with generic values in generated documents |

## License

Apache License 2.0. See [LICENSE](LICENSE).
