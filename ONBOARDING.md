# Onboarding to QualityFlow (core pipeline)

The goal: go from nothing to running the whole pipeline (plan, test cases,
tests) against your own ticket.
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

### Point QualityFlow at your code

Each repo in your project's `repositories.yaml` names the env var that holds its
local clone (`local_path_env`): `SOURCE_REPO_PATH` for the primary repo, and
e.g. `TESTS_REPO_PATH` for a separate tests repo. Clone them and export the vars
in the same shell that launches Claude Code/Cursor:

```bash
export SOURCE_REPO_PATH=~/src/my-project        # the primary repo's clone
export TESTS_REPO_PATH=~/src/my-project-e2e     # only if tests live in another repo
```

Regression analysis reads these clones through LSP and searches them for tests
that already exist; without them it falls back to text search, and
`/generate-tests` stops, because it writes into the tests repo's clone.

## 3. LSP servers (on by default)

Regression analysis (`lsp_analysis`, default on) traces Go and Python call
graphs through Claude Code's LSP tool. `deploy.py` already enabled the LSP
plugins; `getting-started.py` offers to install the `gopls` /
`pyright-langserver` binaries they start. Details in
[README.md's "LSP Servers"](README.md#lsp-servers-on-by-default). Without a
server, runs say `LSP unavailable (<reason>) — used text search` and carry
on. Don't want it? Set `lsp_analysis: false` in your project's
`feature_toggles`.

## 4. Optional: capture cost per run (team dashboard)

A Claude Code session cannot see its own token cost, so `/stp-builder` run
interactively records no cost and the dashboard's Cost tile stays at
"0% captured". To have cost, tokens and the model recorded on the ticket,
launch phases through the runner instead — same headless run as the
dashboard's Run button, with the usage the CLI reports written to
`pipeline_state.yaml` (`--runtime claude|cursor|codex|enmaas`; default codex):

```bash
uv run pipeline_runner.py run <YOUR-PREFIX-123> stp --runtime claude   # stp | std | codegen | stp_review | std_review | stp_refine | std_refine
```

Cost is attributed to the ticket and phase, not to a person. Spend still lands
on whichever Vertex project / API key the run used.

## 5. Run the whole pipeline

Open Claude Code (or Cursor) in your QualityFlow clone, then, for one ticket:

| Step | Command | What happens |
|---|---|---|
| 1. Plan | `/stp-builder PROJ-123` | Writes the STP, then reviews it and fixes critical or major findings (at most 2 rounds) |
| 2. Approve | `/approve PROJ-123 stp` | Records your approval; the next step waits for it. Not happy? Write notes in `outputs/PROJ-123/reviews/PROJ-123_stp_feedback.md` and run `/refine-stp PROJ-123 --address-findings` instead |
| 3. Test cases | `/std-builder PROJ-123` | Writes the STD and one pending stub per test case, then reviews and fixes them |
| 4. Approve | `/approve PROJ-123 std` | Unlocks test generation |
| 5. Tests | `/generate-tests PROJ-123` | Writes tests into your tests repo's clone and checks they load and every fixture resolves (it never runs them) |
| 6. Ship | `/push-pr PROJ-123` | Opens PRs: the STP into your design-docs repo, the tests into your tests repo |

The builders already run the review and the fix pass. Use `/review-stp` or
`/review-std` only to re-review a document you edited by hand. Every output
lands in `outputs/PROJ-123/` (`stp/`, `std/`, `reviews/`, `<language>-tests/`,
`state/`).

The same flow without a chat window, with cost recorded (step 4 above):

```bash
uv run pipeline_runner.py run PROJ-123 stp --runtime enmaas
python3 skills/pipeline-state/state.py approve PROJ-123 stp --by "Your Name"
uv run pipeline_runner.py run PROJ-123 std --runtime enmaas
python3 skills/pipeline-state/state.py approve PROJ-123 std --by "Your Name"
uv run pipeline_runner.py run PROJ-123 codegen --runtime enmaas
```

## Verify

- Restart Claude Code / Cursor after any deploy, and open it in your QualityFlow clone:
  commands run its scripts and read its `config/` from there.
- Type `/stp-builder` — it should be recognized with a description.
- `uv run config/validate.py config/` passes.
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
