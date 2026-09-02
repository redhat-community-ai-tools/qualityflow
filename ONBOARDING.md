# Onboarding to QualityFlow (core pipeline)

The goal: go from nothing to running `/stp-builder` against your own ticket.
Budget ~15 minutes. This is the Claude Code/Cursor agent pipeline — commands,
agents, skills, and per-project config. No servers, no cluster.

Want the shared team dashboard instead (or in addition)? Use
[deploy/ONBOARDING.md](deploy/ONBOARDING.md).

Reference: full manual walkthrough and every option is in [README.md](README.md).

## 0. Prerequisites

- [Claude Code](https://claude.ai/code) or [Cursor AI](https://cursor.com)
- [uv](https://github.com/astral-sh/uv) and `git`
- `node`/`npx` — the `github` MCP server runs via `npx`
- A **Jira API token** and a **GitHub personal access token**

```bash
git clone https://github.com/redhat-community-ai-tools/qualityflow.git
cd qualityflow
uv run getting-started.py --check
```

`--check` only reports pass/fail per prerequisite — it makes no changes.

## 1. Install

The wizard runs prereqs, deploy, MCP config, and validation in one guided pass:

```bash
uv run getting-started.py
```

It prompts for target (`claude`/`cursor`/`both`) and scope, then:
deploys `agents/`, `commands/`, `skills/` via `deploy.py`, offers to
write/merge the MCP server blocks into your MCP config, checks that the
referenced env vars are actually set, and points you at project setup (step 2
below). Non-interactive runs (e.g. CI) can pass `--yes` to accept every
prompt's default.

### Or do it by hand

```bash
uv run deploy.py --target claude   # or cursor, or both
```

Restart Claude Code or Cursor. Then add the MCP server blocks to
`~/.claude/.mcp.json` (Cursor: `~/.cursor/mcp.json`) — see
[README.md's "Set Up MCP Servers"](README.md#set-up-mcp-servers) for the
exact JSON. Finally export the env vars it references
(`JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`, `GITHUB_PERSONAL_ACCESS_TOKEN`)
in the shell that launches your editor.

## 2. Configure your project

Primary path — the wizard automates what used to be a hand-edit of 6+ YAML files:

```bash
cp onboarding-template.yaml my-project.yaml
# fill in project_id, repo, jira, components, ...
uv run onboard.py --input my-project.yaml --dry-run   # preview
uv run onboard.py --input my-project.yaml              # apply
```

`onboard.py` stages the generated config in a temp dir, validates it, and
only on success writes `config/projects/<id>/` and appends a route to
`config/routing.yaml`.

Full field reference, and the manual "copy `config/projects/example` and
hand-edit" alternative, are in [config/README.md](config/README.md#adding-a-new-project).

## 3. Optional: LSP servers

Regression analysis (`lsp_analysis` toggle) uses `gopls`/`pyright` to trace
call graphs. See [README.md's "Set Up LSP Servers"](README.md#set-up-lsp-servers-optional)
for install commands. Don't need it? Set `lsp_analysis: false` in your
project's `feature_toggles` and skip this.

## Verify

- Restart Claude Code / Cursor after any deploy.
- Type `/stp-builder` — it should be recognized with a description.
- `python3 config/validate.py config/` passes.
- Run `/stp-builder <YOUR-PREFIX-123>` against a real ticket.

## Gotchas

- **Restart after every deploy.** Claude Code/Cursor only picks up
  `agents/`/`commands/`/`skills/` changes on restart, including re-deploys.
- **MCP env vars are shell-scoped.** The MCP config file holds `${VAR}`
  placeholders, never real values — the vars must be exported in the same
  shell that launches Claude Code/Cursor, not just present somewhere on disk.
- **Auto mode vs tier mode.** `test_strategy: "auto"` (the default) detects
  language/framework from the source repo; `test_strategy: "tier"` uses your
  `tier*.yaml` configs. An unrouted Jira prefix or GitHub repo falls back to
  auto-discovery only if `SOURCE_REPO_PATH` is set — otherwise routing just
  fails.
- **`onboard.py` won't touch an existing route.** If a route for your
  `project_id` already exists in `routing.yaml`, the append step is skipped
  silently (by design — it's idempotent, not an error).
- **`config/` is not deployed.** It's read straight from the repo root at
  runtime — it never gets copied into `~/.claude` or `~/.cursor`, so there's
  no separate "deploy the config" step.
