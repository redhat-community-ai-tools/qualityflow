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

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import click

# Type aliases
Scope = Literal["user", "project"]
Target = Literal["claude", "cursor", "both"]

# Written into each target base (~/.claude, ~/.cursor) after a real deploy so
# the next run knows which files it is allowed to prune.
MANIFEST_NAME = ".qf-deployed.json"


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


def drop_symlinks(entries: list[Path]) -> list[Path]:
    """Refuse symlinked source entries: is_dir()/copytree would follow them and
    copy an arbitrary filesystem location into the user's ~/.claude tree."""
    kept = []
    for entry in entries:
        if entry.is_symlink():
            click.secho(f"  Warning: skipping symlink (not followed): {entry}", fg="yellow")
        else:
            kept.append(entry)
    return kept


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
        result["agents"] = drop_symlinks(list(agents_dir.glob("*.md")))

    # Discover commands (flat .md files)
    commands_dir = source_dir / "commands"
    if commands_dir.exists():
        result["commands"] = drop_symlinks(list(commands_dir.glob("*.md")))

    # Discover skills (directories containing SKILL.md or any content)
    skills_dir = source_dir / "skills"
    if skills_dir.exists():
        result["skills"] = [d for d in drop_symlinks(list(skills_dir.iterdir())) if d.is_dir()]

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
        # Copy entire directory tree; symlinks=True keeps links as links rather
        # than dereferencing them into copies of whatever they point at.
        shutil.copytree(skill_dir, dest_skill_dir, symlinks=True)

    # Collect all files for reporting
    for src_file in skill_dir.rglob("*"):
        if src_file.is_file():
            rel_path = src_file.relative_to(skill_dir)
            dest_file = dest_skill_dir / rel_path
            copied.append((src_file, dest_file))

    return copied


def read_manifest(base: Path) -> set[str]:
    """Relative paths the previous deploy to this base recorded writing.
    Missing or unreadable manifest means 'we wrote nothing here' — prune nothing."""
    try:
        return set(json.loads((base / MANIFEST_NAME).read_text())["files"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def write_manifest(
    base: Path, results: dict[str, list[tuple[Path, Path]]], source: Path
) -> None:
    """Record the agent/command files this run wrote, so the next run knows
    exactly which destination files are ours to prune."""
    payload = {
        "source": str(source),
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": sorted(
            f"{category}/{dest.name}"
            for category in ("agents", "commands")
            for _, dest in results[category]
        ),
    }
    tmp = base / (MANIFEST_NAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, base / MANIFEST_NAME)


def prune_stale_files(
    source: dict[str, list[Path]], paths: dict[str, Path], dry_run: bool
) -> tuple[list[Path], list[Path]]:
    """Delete destination *.md files that a *previous run of this script* wrote
    and that no longer have a matching source file (renamed/deleted source .md
    would otherwise leave a stale live agent behind forever). Only touches *.md
    directly inside the exact target dirs deploy.py copies into — never skills
    (those are rmtree'd per-skill on copy) and never subdirectories.

    A destination file is only deleted when it is listed in the target's
    .qf-deployed.json manifest; anything else in those directories was put there
    by the user or another tool and is reported, never removed. Returns
    (pruned, not_pruned)."""
    manifest = read_manifest(paths["agents"].parent)
    pruned: list[Path] = []
    not_pruned: list[Path] = []
    for category in ("agents", "commands"):
        if not source[category]:
            # Empty source category — refuse to prune rather than wipe the dir
            # (an empty discovery is more likely a bad --source than intent).
            continue
        src_names = {f.name for f in source[category]}
        dest_dir = paths[category]
        if not dest_dir.is_dir():
            continue
        for dest_file in sorted(dest_dir.glob("*.md")):
            if dest_file.name in src_names:
                continue
            if f"{category}/{dest_file.name}" in manifest:
                if not dry_run:
                    dest_file.unlink()
                pruned.append(dest_file)
            else:
                not_pruned.append(dest_file)
    return pruned, not_pruned


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
    help="Custom source directory (default: the directory containing this script)",
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
    all_pruned: dict[str, list[Path]] = {}
    all_not_pruned: dict[str, list[Path]] = {}

    for flag, target_name, get_paths in (
        ("claude", "Claude Code", get_claude_paths),
        ("cursor", "Cursor", get_cursor_paths),
    ):
        if target not in (flag, "both"):
            continue
        paths = get_paths(scope, project_path)
        base = paths["agents"].parent
        if not dry_run:
            base.mkdir(parents=True, exist_ok=True)
            if not os.access(base, os.W_OK):
                click.secho(f"Error: No write permission to {base}", fg="red")
                raise SystemExit(1)
        all_results[target_name] = deploy_resources(
            source_files, paths, target_name, dry_run
        )
        (
            all_pruned[target_name],
            all_not_pruned[target_name],
        ) = prune_stale_files(source_files, paths, dry_run)
        if not dry_run:
            write_manifest(base, all_results[target_name], source)

    # Print summary
    print_summary(all_results, dry_run)

    # Prune report — stale agent/command .md files with no matching source
    click.echo()
    click.secho("  Pruned stale files:", fg="cyan", bold=True)
    prune_action = "Would prune" if dry_run else "Pruned"
    any_pruned = False
    for target_name, files in all_pruned.items():
        for f in files:
            any_pruned = True
            click.secho(f"    {prune_action} ({target_name}): {f}", fg="red")
    if not any_pruned:
        click.echo("    (none)")

    # Files we would have removed but did not, because no manifest claims them —
    # either there is no manifest yet, or there is one and the file simply is not
    # in it. Either way something other than deploy.py put them there.
    leftovers = [(t, f) for t, files in all_not_pruned.items() for f in files]
    if leftovers:
        click.echo()
        click.secho(
            "  Not pruned (not written by a previous run of deploy.py; "
            "delete by hand if stale):",
            fg="cyan",
            bold=True,
        )
        for target_name, f in leftovers:
            click.secho(f"    Kept ({target_name}): {f}", fg="yellow")


if __name__ == "__main__":
    main()
