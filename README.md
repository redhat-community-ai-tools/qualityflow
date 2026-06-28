# QualityFlow — AI-powered QE test planning and code generation

QualityFlow is a platform-agnostic QE (Quality Engineering) pipeline that generates test plans, test descriptions, and working test implementations from Jira tickets.

## Where QualityFlow fits in the SDLC

```
┌─────────────────────────────────────────────────────────┐
│                      SDLC                               │
│                                                         │
│  Triage → Prioritize → Code → Review → Test → Retro    │
│                                         ^^^^            │
│                                     QualityFlow         │
└─────────────────────────────────────────────────────────┘
```

## Lifecycle

QualityFlow runs a 7-stage pipeline using 8 specialized agents:

```
Jira ticket
  │
  ├─ stp-builder          → Software Test Plan (STP) from Jira + PR data
  ├─ stp-reviewer         → Automated QE review of the STP
  ├─ stp-refiner          → Iterative fix loop until STP is APPROVED
  │
  ├─ std-builder          → STD YAML + Go/Python test stubs from STP
  ├─ std-reviewer         → Automated QE review of the STD
  ├─ std-refiner          → Iterative fix loop until STD is APPROVED
  │
  ├─ go-test-generator    → Working Go/Ginkgo tests from STD
  └─ python-test-generator → Working Python/pytest tests from STD
```

## Test backpressure — not every issue needs a test

QualityFlow does not blindly generate tests for every issue. Multiple stages apply backpressure to prevent test proliferation:

**Tier classifier** — Analyzes the issue scope and decides which test tier is appropriate (unit, functional, e2e) or whether testing is warranted at all. A one-line typo fix does not get an e2e test suite.

**Scope boundaries** — Each project config defines what is in-scope vs out-of-scope for testing. Tests are only generated for functionality owned by the team, not for upstream platform behavior or third-party dependencies.

**STP review gate** — Before any test code is generated, the STP reviewer evaluates the test plan for quality: are the scenarios meaningful? Is the coverage proportional to the change? Redundant or frivolous scenarios are flagged as findings. Only approved plans proceed to code generation.

**Requirement coverage analysis** — The pipeline traces requirements back to Jira acceptance criteria. If an issue has no testable acceptance criteria (e.g., a documentation update, a CI config change), the pipeline reports that no test scenarios are applicable rather than inventing tests.

The result: test generation is triggered by **validated requirements**, not by issue count.

## Architecture

QualityFlow separates **tool** from **project config**:

- **Tool** (this repo) — agents, skills, and commands. Platform-agnostic, project-agnostic.
- **Project config** (`config/`) — routing, components, patterns, templates, reference tests. Team-specific.

The `config/` directory ships with `config/projects/example/` — a skeleton showing the required YAML structure. Teams copy it to create their own project config.

## Adding your project

1. Copy the example skeleton:

   ```bash
   cp -r config/projects/example config/projects/my-project
   ```

2. Edit each YAML file with your project's real values (see comments in each file).

3. Add route(s) in `config/routing.yaml`:

   ```yaml
   routes:
     - prefix: "MYPROJ"
       project: "my-project"
   ```

See `config/README.md` for the full configuration reference.

## Deployment (Claude Code / Cursor)

Requires [uv](https://github.com/astral-sh/uv):

```bash
uv run deploy.py --target claude              # Deploy to ~/.claude/
uv run deploy.py --target cursor              # Deploy to ~/.cursor/
uv run deploy.py --target both                # Deploy to both
uv run deploy.py --dry-run --target both      # Preview changes
```

After deployment, restart Claude Code or Cursor to load the agents, skills, and commands.

## Platform integration

QualityFlow provides the core agents, skills, and configuration. Platform-specific integration (harness definitions, sandbox policies, CI workflows) lives in separate repositories:

- **FullSend**: see [qualityflow-fullsend](https://github.com/redhat-community-ai-tools/qualityflow-fullsend)

## Directory layout

```
qualityflow/
├── agents/      16 agent prompts (incl. qualityflow unified orchestrator)
├── commands/     7 slash command definitions (Claude Code / Cursor)
├── skills/      24 reusable skills
├── config/      Project config framework + example skeleton
│   ├── routing.yaml
│   ├── _defaults.yaml
│   ├── _schema.yaml
│   └── projects/
│       └── example/    <- Copy this for your project
├── deploy.py    Deploy to Claude Code / Cursor environments
└── README.md
```

## Prerequisites

- Jira API token with read access to your project
- GitHub token with repo read access (for PR diffs and repo file fetch)
