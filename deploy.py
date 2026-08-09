#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click>=8.1.0",
# ]
# ///
"""
Deployment script for copying Quality Flow resources to Claude Code and/or Cursor AI environments.

Usage:
    uv run deploy.py --target claude              # Deploy to Claude Code (user scope)
    uv run deploy.py --target cursor              # Deploy to Cursor (user scope)
    uv run deploy.py --target both                # Deploy to both
    uv run deploy.py --target claude --scope project  # Deploy to project (current dir)
    uv run deploy.py --target both --dry-run      # Preview without copying
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Literal

import click

# Type aliases
Scope = Literal["user", "project"]
Target = Literal["claude", "cursor", "both"]


def get_claude_paths(scope: Scope, project_path: Path | None) -> dict[str, Path]:
    """Return dict of Claude Code target paths."""
    if scope == "user":
        base = Path.home() / ".claude"
    else:
        base = (project_path or Path.cwd()) / ".claude"

    return {
        "agents": base / "agents",
        "commands": base / "commands",
        "skills": base / "skills",
    }


def get_cursor_paths(scope: Scope, project_path: Path | None) -> dict[str, Path]:
    """Return dict of Cursor target paths."""
    if scope == "user":
        base = Path.home() / ".cursor"
    else:
        base = (project_path or Path.cwd()) / ".cursor"

    return {
        "agents": base / "agents",
        "commands": base / "commands",
        "skills": base / "skills",
    }


def discover_source_files(source_dir: Path) -> dict[str, list[Path]]:
    """Find agents, commands, and skills in source directory."""
    result = {
        "agents": [],
        "commands": [],
        "skills": [],
    }

    # Discover agents (flat .md files)
    agents_dir = source_dir / "agents"
    if agents_dir.exists():
        result["agents"] = list(agents_dir.glob("*.md"))

    # Discover commands (flat .md files)
    commands_dir = source_dir / "commands"
    if commands_dir.exists():
        result["commands"] = list(commands_dir.glob("*.md"))

    # Discover skills (directories containing SKILL.md or any content)
    skills_dir = source_dir / "skills"
    if skills_dir.exists():
        result["skills"] = [d for d in skills_dir.iterdir() if d.is_dir()]

    return result


def copy_flat_files(
    files: list[Path], dest_dir: Path, dry_run: bool
) -> list[tuple[Path, Path]]:
    """Copy .md files to destination. Returns list of (src, dest) tuples."""
    copied = []

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for src_file in files:
        dest_file = dest_dir / src_file.name
        if not dry_run:
            shutil.copy2(src_file, dest_file)
        copied.append((src_file, dest_file))

    return copied


def copy_skill_directory(
    skill_dir: Path, dest_dir: Path, dry_run: bool
) -> list[tuple[Path, Path]]:
    """Recursively copy skill folder. Returns list of (src, dest) tuples."""
    copied = []
    skill_name = skill_dir.name
    dest_skill_dir = dest_dir / skill_name

    if not dry_run:
        # Remove existing skill directory if it exists
        if dest_skill_dir.exists():
            shutil.rmtree(dest_skill_dir)
        # Copy entire directory tree
        shutil.copytree(skill_dir, dest_skill_dir)

    # Collect all files for reporting
    for src_file in skill_dir.rglob("*"):
        if src_file.is_file():
            rel_path = src_file.relative_to(skill_dir)
            dest_file = dest_skill_dir / rel_path
            copied.append((src_file, dest_file))

    return copied


def deploy_resources(
    source: dict[str, list[Path]],
    paths: dict[str, Path],
    target_name: str,
    dry_run: bool,
) -> dict[str, list[tuple[Path, Path]]]:
    """Deploy all resources to a target. Returns dict of copied files by category."""
    results = {
        "agents": [],
        "commands": [],
        "skills": [],
    }

    # Copy agents
    if source["agents"]:
        results["agents"] = copy_flat_files(source["agents"], paths["agents"], dry_run)

    # Copy commands
    if source["commands"]:
        results["commands"] = copy_flat_files(
            source["commands"], paths["commands"], dry_run
        )

    # Copy skills
    for skill_dir in source["skills"]:
        copied = copy_skill_directory(skill_dir, paths["skills"], dry_run)
        results["skills"].extend(copied)

    return results


def print_summary(
    results: dict[str, dict[str, list[tuple[Path, Path]]]],
    dry_run: bool,
) -> None:
    """Display what was deployed."""
    action = "Would deploy" if dry_run else "Deployed"

    for target_name, categories in results.items():
        click.echo()
        click.secho(f"{'=' * 50}", fg="blue")
        click.secho(f"  {target_name.upper()}", fg="blue", bold=True)
        click.secho(f"{'=' * 50}", fg="blue")

        for category, files in categories.items():
            if files:
                click.echo()
                click.secho(f"  {category.capitalize()}:", fg="cyan", bold=True)
                # Group by destination directory for cleaner output
                dest_dirs = {}
                for src, dest in files:
                    dest_dir = dest.parent
                    if dest_dir not in dest_dirs:
                        dest_dirs[dest_dir] = []
                    dest_dirs[dest_dir].append(dest.name)

                for dest_dir, filenames in dest_dirs.items():
                    click.echo(f"    {action} to: {dest_dir}")
                    for name in sorted(filenames):
                        click.secho(f"      - {name}", fg="green")

    # Summary totals
    click.echo()
    click.secho("=" * 50, fg="yellow")
    click.secho("  SUMMARY", fg="yellow", bold=True)
    click.secho("=" * 50, fg="yellow")

    total_files = 0
    for target_name, categories in results.items():
        target_total = sum(len(files) for files in categories.values())
        total_files += target_total
        click.echo(f"  {target_name}: {target_total} files")

    click.echo()
    if dry_run:
        click.secho(f"  Total: {total_files} files would be deployed", fg="yellow")
        click.echo()
        click.secho("  Run without --dry-run to deploy.", fg="yellow")
    else:
        click.secho(f"  Total: {total_files} files deployed", fg="green", bold=True)


@click.command()
@click.option(
    "--target",
    type=click.Choice(["claude", "cursor", "both"]),
    required=True,
    help='Target environment: "claude", "cursor", or "both"',
)
@click.option(
    "--scope",
    type=click.Choice(["user", "project"]),
    default="user",
    help='Deployment scope: "user" (home dir) or "project" (project dir)',
)
@click.option(
    "--project-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Path to project root (default: current dir if scope=project)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview without copying",
)
@click.option(
    "--source",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Custom source directory (default: ./resources)",
)
@click.option(
    "--validate",
    is_flag=True,
    default=False,
    help="Validate project configs before deploying",
)
def main(
    target: Target,
    scope: Scope,
    project_path: Path | None,
    dry_run: bool,
    source: Path | None,
    validate: bool,
) -> None:
    """Deploy Quality Flow resources to Claude Code and/or Cursor AI environments."""
    # Determine source directory
    if source is None:
        source = Path(__file__).parent

    if not source.exists():
        click.secho(f"Error: Source directory not found: {source}", fg="red")
        raise SystemExit(1)

    # Discover source files
    source_files = discover_source_files(source)

    total_items = (
        len(source_files["agents"])
        + len(source_files["commands"])
        + len(source_files["skills"])
    )

    if total_items == 0:
        click.secho("Error: No resources found to deploy.", fg="red")
        raise SystemExit(1)

    # Validate configs if requested
    if validate:
        config_dir = source / "config"
        if config_dir.exists():
            import subprocess
            validate_script = config_dir / "validate.py"
            if validate_script.exists():
                click.echo()
                click.secho("Validating project configs...", fg="cyan")
                result = subprocess.run(
                    ["uv", "run", "--with", "pyyaml", str(validate_script), str(config_dir)],
                    capture_output=True, text=True,
                )
                click.echo(result.stdout)
                if result.returncode != 0:
                    if result.stderr:
                        click.echo(result.stderr)
                    click.secho("Config validation failed. Fix errors before deploying.", fg="red")
                    raise SystemExit(1)
            else:
                click.secho("Warning: --validate requested but config/validate.py not found", fg="yellow")
        else:
            click.secho("Warning: --validate requested but config/ directory not found", fg="yellow")

    # Display header
    click.echo()
    click.secho("Quality Flow Resource Deployment", fg="blue", bold=True)
    click.secho("-" * 35, fg="blue")
    click.echo(f"  Source: {source}")
    click.echo(f"  Target: {target}")
    click.echo(f"  Scope:  {scope}")
    if scope == "project":
        effective_path = project_path or Path.cwd()
        click.echo(f"  Path:   {effective_path}")
    if dry_run:
        click.secho("  Mode:   DRY RUN", fg="yellow", bold=True)

    click.echo()
    click.echo(f"  Found: {len(source_files['agents'])} agents, "
               f"{len(source_files['commands'])} commands, "
               f"{len(source_files['skills'])} skills")

    # Deploy to targets
    all_results = {}

    if target in ("claude", "both"):
        paths = get_claude_paths(scope, project_path)
        if not dry_run:
            base = paths["agents"].parent
            base.mkdir(parents=True, exist_ok=True)
            if not os.access(base, os.W_OK):
                click.secho(f"Error: No write permission to {base}", fg="red")
                raise SystemExit(1)
        all_results["Claude Code"] = deploy_resources(
            source_files, paths, "Claude Code", dry_run
        )

    if target in ("cursor", "both"):
        paths = get_cursor_paths(scope, project_path)
        if not dry_run:
            base = paths["agents"].parent
            base.mkdir(parents=True, exist_ok=True)
            if not os.access(base, os.W_OK):
                click.secho(f"Error: No write permission to {base}", fg="red")
                raise SystemExit(1)
        all_results["Cursor"] = deploy_resources(
            source_files, paths, "Cursor", dry_run
        )

    # Print summary
    print_summary(all_results, dry_run)


if __name__ == "__main__":
    main()
