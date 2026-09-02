#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click>=8.1.0",
# ]
# ///
"""
Getting-started wizard for QualityFlow's core pipeline (Claude Code / Cursor AI).

Orchestrates the manual Quick Start steps from README.md into one guided pass:
prerequisite checks -> deploy.py -> MCP server config -> optional LSP hints ->
onboard.py hand-off -> config/validate.py + a verify checklist. It wraps the
existing scripts via subprocess; it does not reimplement their logic.

Usage:
    uv run getting-started.py                                   # interactive, full run
    uv run getting-started.py --check                            # prerequisites only, no side effects
    uv run getting-started.py --yes --target claude --scope user  # non-interactive
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).parent

# Exact blocks from README.md's "Set Up MCP Servers" section — env-var
# interpolation only, never a literal secret.
MCP_ATLASSIAN = {
    "command": "uvx",
    "args": ["mcp-atlassian"],
    "env": {
        "JIRA_URL": "${JIRA_URL}",
        "JIRA_USERNAME": "${JIRA_USERNAME}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}",
    },
}
MCP_GITHUB = {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}",
    },
}
REQUIRED_ENV_VARS = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"]

LSP_INSTALL = {
    "gopls": "go install golang.org/x/tools/gopls@latest",
    "pyright": "npm install -g pyright",
}


def header(text: str) -> None:
    click.echo()
    click.secho("=" * 60, fg="blue")
    click.secho(f"  {text}", fg="blue", bold=True)
    click.secho("=" * 60, fg="blue")


def report(label: str, ok: bool, detail: str, hard: bool = False) -> bool:
    if ok:
        click.secho(f"  [PASS] {label}: {detail}", fg="green")
    elif hard:
        click.secho(f"  [FAIL] {label}: {detail}", fg="red")
    else:
        click.secho(f"  [WARN] {label}: {detail}", fg="yellow")
    return ok


def run_prereq_check() -> tuple[bool, dict[str, bool]]:
    """Step 1. Returns (all hard-required checks passed, {tool: is_missing})."""
    header("1. Prerequisite check")
    hard_ok = True

    uv_path = shutil.which("uv")
    if uv_path:
        version = subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()
        hard_ok &= report("uv", True, version, hard=True)
    else:
        hard_ok &= report("uv", False, "not found on PATH — https://github.com/astral-sh/uv", hard=True)

    v = sys.version_info
    py_ok = (v.major, v.minor) >= (3, 10)
    hard_ok &= report("python", py_ok, f"{v.major}.{v.minor}.{v.micro} (>=3.10 required)", hard=True)

    git_path = shutil.which("git")
    report("git", bool(git_path), git_path or "not found on PATH", hard=False)

    npx_path = shutil.which("npx")
    report("npx/node", bool(npx_path), npx_path or "not found on PATH (needed by the github MCP server)", hard=False)

    claude_path = shutil.which("claude")
    report("claude CLI", bool(claude_path), claude_path or "not found on PATH (fine if you use the Claude Code app)", hard=False)

    cursor_path = shutil.which("cursor")
    report("cursor CLI", bool(cursor_path), cursor_path or "not found on PATH (fine if you use the Cursor app)", hard=False)

    gopls_path = shutil.which("gopls")
    report("gopls", bool(gopls_path), gopls_path or "not found (optional — used for Go regression analysis)", hard=False)

    pyright_path = shutil.which("pyright")
    report("pyright", bool(pyright_path), pyright_path or "not found (optional — used for Python regression analysis)", hard=False)

    missing_lsp = {"gopls": not gopls_path, "pyright": not pyright_path}
    return hard_ok, missing_lsp


def run_deploy(target: str, scope: str) -> None:
    """Step 2. Invoke deploy.py via subprocess — never duplicate its copy/prune logic."""
    header("2. Deploy resources")
    cmd = ["uv", "run", str(SCRIPT_DIR / "deploy.py"), "--target", target, "--scope", scope, "--validate"]
    click.echo(f"  Running: {' '.join(cmd)}")
    click.echo()
    result = subprocess.run(cmd)
    if result.returncode != 0:
        click.echo()
        click.secho("  deploy.py failed — see output above.", fg="red")
        raise SystemExit(result.returncode)


def merge_mcp_config(path: Path, yes: bool) -> None:
    """Merge the mcp-atlassian + github blocks into path's "mcpServers", the same
    check-then-append idempotency pattern onboard.py uses for routing.yaml: never
    touch servers under other names, never overwrite an existing one without asking."""
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            click.secho(f"  Error: {path} contains invalid JSON ({e}). Leaving it untouched — fix or remove it and re-run.", fg="red")
            return
        if not isinstance(existing, dict):
            click.secho(f"  Error: {path} does not contain a JSON object. Leaving it untouched.", fg="red")
            return

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        click.secho(f"  Error: {path} 'mcpServers' is not an object. Leaving it untouched.", fg="red")
        return

    for name, block in (("mcp-atlassian", MCP_ATLASSIAN), ("github", MCP_GITHUB)):
        if name in servers:
            if yes:
                click.secho(f"  '{name}' already configured in {path} — keeping existing.", fg="yellow")
                continue
            if not click.confirm(f"  '{name}' already configured in {path}. Overwrite?", default=False):
                click.secho(f"  Keeping existing '{name}' config.", fg="yellow")
                continue
        servers[name] = block
        click.secho(f"  Set '{name}' in {path}", fg="green")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n")


def run_mcp_config(target: str, yes: bool) -> None:
    """Step 3."""
    header("3. MCP server config")
    paths = []
    if target in ("claude", "both"):
        paths.append(Path.home() / ".claude" / ".mcp.json")
    if target in ("cursor", "both"):
        paths.append(Path.home() / ".cursor" / "mcp.json")

    for path in paths:
        if yes or click.confirm(f"  Configure MCP servers in {path}?", default=True):
            merge_mcp_config(path, yes)
        else:
            click.secho(f"  Skipped {path}", fg="yellow")

    click.echo()
    click.secho("  Environment variables:", fg="cyan", bold=True)
    missing = [v for v in REQUIRED_ENV_VARS if v not in os.environ]
    if missing:
        click.secho("  Missing (MCP servers will fail without these):", fg="yellow")
        for v in missing:
            click.echo(f"    export {v}=...")
    else:
        click.secho("  All required environment variables are set.", fg="green")


def run_lsp_hints(missing_lsp: dict[str, bool]) -> None:
    """Step 4. Advisory only — print, never auto-install."""
    missing = [name for name, is_missing in missing_lsp.items() if is_missing]
    if not missing:
        return
    header("4. Optional LSP setup")
    click.echo("  Only needed if the lsp_analysis toggle is on for a project using these languages:")
    for name in missing:
        click.echo(f"    {name}: {LSP_INSTALL[name]}")


def run_project_onboarding(yes: bool) -> None:
    """Step 5. Hand off to onboard.py — never re-implement its YAML generation."""
    header("5. Project onboarding")
    do_it = False if yes else click.confirm("  Configure a project now?", default=False)
    if not do_it:
        click.echo("  Skipped. When ready:")
        click.echo(f"    - Fill in {SCRIPT_DIR / 'onboarding-template.yaml'}")
        click.echo(f"    - See {SCRIPT_DIR / 'config' / 'README.md'} for the full config reference")
        return

    default_path = Path.cwd() / "my-project.yaml"
    while True:
        dest = click.prompt("  Path for your onboarding YAML", default=str(default_path))
        dest_path = Path(dest)
        if dest_path.exists():
            click.secho(f"  {dest_path} already exists — choose another path.", fg="red")
            continue
        break

    shutil.copy2(SCRIPT_DIR / "onboarding-template.yaml", dest_path)
    click.secho(f"  Copied onboarding-template.yaml to {dest_path}", fg="green")
    click.echo("  Next steps:")
    click.echo(f"    1. Fill in {dest_path}")
    click.echo(f"    2. Preview:  uv run onboard.py --input {dest_path} --dry-run")
    click.echo(f"    3. Apply:    uv run onboard.py --input {dest_path}")


def run_final_validate() -> None:
    """Step 6."""
    header("6. Final validate + verify")
    cmd = ["uv", "run", "--with", "pyyaml", str(SCRIPT_DIR / "config" / "validate.py"), str(SCRIPT_DIR / "config")]
    click.echo(f"  Running: {' '.join(cmd)}")
    click.echo()
    result = subprocess.run(cmd)
    click.echo()
    if result.returncode != 0:
        click.secho("  config/validate.py reported errors — see output above.", fg="yellow")
    else:
        click.secho("  Config validation passed.", fg="green")

    click.echo()
    click.secho("  Verify:", fg="cyan", bold=True)
    click.echo("    1. Restart Claude Code / Cursor AI to load the deployed resources.")
    click.echo("    2. Type /stp-builder with no arguments — confirm it's recognized.")
    click.echo("    3. Once a project is configured, run /stp-builder against a real ticket.")


@click.command()
@click.option("--check", is_flag=True, default=False, help="Run prerequisite checks only (step 1) and exit. Zero side effects.")
@click.option("--target", type=click.Choice(["claude", "cursor", "both"]), default=None, help='Deploy/MCP target: "claude", "cursor", or "both". Prompted if omitted.')
@click.option("--scope", type=click.Choice(["user", "project"]), default=None, help='Deploy scope: "user" or "project". Prompted if omitted.')
@click.option("--yes", is_flag=True, default=False, help="Non-interactive: accept every prompt's default; answers 'no' to project onboarding.")
def main(check: bool, target: str | None, scope: str | None, yes: bool) -> None:
    """Guided first-run setup for QualityFlow's core pipeline: prerequisite
    checks, deploy.py, MCP server config, optional LSP hints, project
    onboarding hand-off, and a final config validate + verify checklist."""
    click.secho("QualityFlow Getting Started", fg="blue", bold=True)
    click.secho("-" * 35, fg="blue")

    hard_ok, missing_lsp = run_prereq_check()
    if not hard_ok:
        click.echo()
        click.secho("Hard prerequisite(s) missing — install them and re-run.", fg="red")
        raise SystemExit(1)

    if check:
        click.echo()
        click.secho("Prerequisite check complete.", fg="green", bold=True)
        return

    resolved_target: str = target or ("both" if yes else click.prompt("\nDeploy target", type=click.Choice(["claude", "cursor", "both"]), default="both"))
    resolved_scope: str = scope or ("user" if yes else click.prompt("Deploy scope", type=click.Choice(["user", "project"]), default="user"))

    run_deploy(resolved_target, resolved_scope)
    run_mcp_config(resolved_target, yes)
    run_lsp_hints(missing_lsp)
    run_project_onboarding(yes)
    run_final_validate()

    click.echo()
    click.secho("Done!", fg="green", bold=True)


if __name__ == "__main__":
    main()
