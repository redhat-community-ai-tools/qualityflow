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
prerequisite checks -> deploy.py -> MCP server config -> LSP server install ->
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

# Binary the Claude Code LSP plugin runs -> (tool the install needs, install command).
# deploy.py enables the plugins; these are the servers they start.
LSP_INSTALL = {
    "gopls": ("go", "go install golang.org/x/tools/gopls@latest"),
    "pyright-langserver": ("npm", "npm install -g pyright"),
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

    missing_lsp = {}
    for name, lang in (("gopls", "Go"), ("pyright-langserver", "Python")):
        path = shutil.which(name)
        report(name, bool(path), path or f"not found — {lang} LSP analysis falls back to text search", hard=False)
        missing_lsp[name] = not path
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


def run_lsp_setup(missing_lsp: dict[str, bool], yes: bool) -> None:
    """Step 4. lsp_analysis is on by default, so offer to install a missing
    language server when its installer (go / npm) is present; otherwise print
    the exact command. Never escalates (no sudo)."""
    missing = [name for name, is_missing in missing_lsp.items() if is_missing]
    if not missing:
        return
    header("4. LSP servers")
    click.echo("  lsp_analysis is on by default; without these, regression analysis uses text search.")
    click.echo("  (Not using Go or Python? Set `lsp_analysis: false` in your project.yaml.)")
    for name in missing:
        tool, cmd = LSP_INSTALL[name]
        if not shutil.which(tool):
            click.secho(f"  {name}: needs `{tool}` first, then run: {cmd}", fg="yellow")
            continue
        if not (yes or click.confirm(f"  Install {name} now ({cmd})?", default=True)):
            click.echo(f"  Skipped. Later: {cmd}")
            continue
        if subprocess.run(cmd.split()).returncode != 0:
            click.secho(f"  {name} install failed — run it yourself: {cmd}", fg="red")
        elif not shutil.which(name):
            click.secho(f"  Installed, but {name} is not on PATH — add `{tool}`'s bin dir "
                        "(go env GOPATH)/bin or (npm prefix -g)/bin to PATH.", fg="yellow")
        else:
            click.secho(f"  {name} installed.", fg="green")


# Red Hat's AI gateway (source.redhat.com, "EnMaaS"): one key for every model
# it serves; the hosted GLM 5.3 and DeepSeek V4.1 Flash have no usage cost.
# QualityFlow uses it through Codex only.
ENMAAS_URL = "https://api.enmaas.devshift.net"
ENMAAS_DIR = Path.home() / ".config" / "enmaas"
ENMAAS_KEY_FILE = ENMAAS_DIR / "key"
# file -> its backup (None: the file did not exist), so --enmaas-rollback can undo.
ENMAAS_MANIFEST = ENMAAS_DIR / "qf-migration.json"


def _enmaas_backup(path: Path) -> None:
    """Record path's pre-EnMaaS state once; a re-run keeps the first backup."""
    manifest = json.loads(ENMAAS_MANIFEST.read_text()) if ENMAAS_MANIFEST.exists() else {}
    if str(path) in manifest:
        return
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".pre-enmaas")
        shutil.copy2(path, backup)
    manifest[str(path)] = str(backup) if backup else None
    ENMAAS_DIR.mkdir(parents=True, exist_ok=True)
    ENMAAS_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


def save_enmaas_key(yes: bool) -> None:
    """The key lives only in ~/.config/enmaas/key (0600), never in a config file."""
    if ENMAAS_KEY_FILE.exists():
        click.secho(f"  Key: using {ENMAAS_KEY_FILE}", fg="green")
        return
    key = "" if yes else click.prompt("  EnMaaS key (get one via Atlas onboarding; input hidden, Enter to skip)",
                                      hide_input=True, default="", show_default=False).strip()
    if not key:
        click.secho(f"  No key saved. Later: put it in {ENMAAS_KEY_FILE} (chmod 600).", fg="yellow")
        return
    ENMAAS_DIR.mkdir(parents=True, exist_ok=True)
    ENMAAS_KEY_FILE.touch(mode=0o600)
    ENMAAS_KEY_FILE.write_text(key)
    click.secho(f"  Key saved to {ENMAAS_KEY_FILE} (0600).", fg="green")


def migrate_codex_to_enmaas(codex_home: Path) -> None:
    """Add the gateway as a Codex provider plus an `enmaas` profile
    (`codex --profile enmaas`) with the hosted models in its catalog; the
    default profile is untouched. Same provider settings and catalog as the
    runner's enmaas runtime (pipeline_runner.enmaas_model_catalog)."""
    sys.path.insert(0, str(SCRIPT_DIR))
    from pipeline_runner import ENMAAS_HOSTED, enmaas_model_catalog

    config = codex_home / "config.toml"
    profile = codex_home / "enmaas.config.toml"
    catalog_path = codex_home / "enmaas-models.json"
    for path in (config, profile, catalog_path):
        _enmaas_backup(path)
    text = config.read_text() if config.exists() else ""
    if "[model_providers.enmaas]" not in text:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(text.rstrip() + ("\n\n" if text.strip() else "") +
                          "[model_providers.enmaas]\n"
                          'name = "EnMaaS"\n'
                          f'base_url = "{ENMAAS_URL}/v1"\n'
                          'env_key = "ENMAAS_KEY"\n'
                          'wire_api = "responses"\n'
                          "requires_openai_auth = false\n"
                          "supports_websockets = false\n")
    lines = [f'model = "{next(iter(ENMAAS_HOSTED))}"', 'model_provider = "enmaas"', 'web_search = "disabled"']
    catalog = enmaas_model_catalog()
    if catalog:
        catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
        lines.append(f'model_catalog_json = "{catalog_path}"')
    else:
        click.secho("  Codex: could not build the hosted-model catalog (`codex debug models --bundled`); "
                    "hosted models may reject apply_patch.", fg="yellow")
    profile.write_text("\n".join(lines) + "\n")
    click.secho(f"  Codex: provider in {config}, profile {profile}.", fg="green")
    click.echo(f'  Codex reads the key from $ENMAAS_KEY: add  export ENMAAS_KEY="$(cat {ENMAAS_KEY_FILE})"'
               "  to your shell rc, then  codex --profile enmaas.")


def rollback_enmaas() -> None:
    """Undo the migration: restore every backed-up file, remove ones it created."""
    if not ENMAAS_MANIFEST.exists():
        click.secho("  Nothing to roll back (no EnMaaS migration recorded).", fg="yellow")
        return
    for path, backup in json.loads(ENMAAS_MANIFEST.read_text()).items():
        if backup:
            shutil.move(backup, path)
        else:
            Path(path).unlink(missing_ok=True)
        click.echo(f"  Restored {path}")
    ENMAAS_MANIFEST.unlink()
    click.secho(f"  Rolled back. The key in {ENMAAS_KEY_FILE} is kept; delete it yourself if unwanted.", fg="green")


def run_enmaas_setup(enmaas: bool | None, yes: bool) -> None:
    """Optional step: save the EnMaaS key and add an `enmaas` Codex profile.
    Every file it changes is backed up first; `--enmaas-rollback` restores them."""
    if enmaas is None:
        enmaas = False if yes else click.confirm(
            "\n  Add Red Hat EnMaaS to Codex (free hosted GLM / DeepSeek)?", default=False)
    if not enmaas:
        return
    header("EnMaaS gateway (Codex)")
    save_enmaas_key(yes)
    if shutil.which("codex"):
        migrate_codex_to_enmaas(Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    else:
        click.secho("  codex not found on PATH — install the Codex CLI, then re-run with --enmaas.", fg="yellow")
    click.echo("  Dashboard: Settings -> Runtime -> EnMaaS, and paste the key in EnMaaS Key.")
    click.echo("  CLI: pipeline_runner.py run <ticket> <phase> --runtime enmaas (with $ENMAAS_KEY set).")
    click.echo("  Undo: uv run getting-started.py --enmaas-rollback")


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
@click.option("--enmaas/--no-enmaas", default=None, help="Save an EnMaaS key and add an `enmaas` Codex profile (backs up every file it changes). Prompted if omitted; --yes means no.")
@click.option("--enmaas-rollback", is_flag=True, default=False, help="Undo the EnMaaS migration (restore the backed-up files) and exit.")
def main(check: bool, target: str | None, scope: str | None, yes: bool,
         enmaas: bool | None, enmaas_rollback: bool) -> None:
    """Guided first-run setup for QualityFlow's core pipeline: prerequisite
    checks, deploy.py, MCP server config, LSP server install, project
    onboarding hand-off, and a final config validate + verify checklist."""
    click.secho("QualityFlow Getting Started", fg="blue", bold=True)
    click.secho("-" * 35, fg="blue")

    if enmaas_rollback:
        header("EnMaaS rollback")
        rollback_enmaas()
        return

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
    run_enmaas_setup(enmaas, yes)
    run_lsp_setup(missing_lsp, yes)
    run_project_onboarding(yes)
    run_final_validate()

    click.echo()
    click.secho("Done!", fg="green", bold=True)


if __name__ == "__main__":
    main()
