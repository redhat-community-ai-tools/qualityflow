#!/usr/bin/env python3
"""Deterministic project resolver for QualityFlow.

Parses an issue input (Jira ID/URL, GitHub issue URL/short form), routes it
via config/routing.yaml, validates the project config, merges the repo config
layers (.qualityflow/ in the repo checkouts, config/layers.py) over it, merges
feature toggles, and prints the resolved project_context YAML to stdout.

Usage: resolve.py "<issue input>" [--target PATH ...] [--folder NAME]

Exit codes:
  0 - success, project_context on stdout
  1 - error (unparseable input, routing miss, invalid config or repo config layer)
  3 - routing miss but SOURCE_REPO_PATH is set: caller must run the
      auto-discovery flow documented in SKILL.md (marker: AUTO_DISCOVERY_REQUIRED)
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

# Reuse the shared validators from config/validate.py
sys.path.insert(0, str(CONFIG_DIR))
import validate as config_validate  # noqa: E402
from model_policy import merge_policy  # noqa: E402
import layers as config_layers  # noqa: E402


def fail(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def parse_input(issue_input: str) -> dict:
    """Detection order per SKILL.md: GitHub URL, GitHub short form, Jira URL, Jira ID."""
    s = issue_input.strip()

    m = re.match(r"^https?://github\.com/([^/\s]+)/([^/\s]+)/issues/(\d+)/?$", s)
    if m:
        return {"type": "github", "owner": m.group(1), "repo": m.group(2), "number": int(m.group(3))}

    m = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)$", s)
    if m:
        return {"type": "github", "owner": m.group(1), "repo": m.group(2), "number": int(m.group(3))}

    m = re.search(r"/browse/([A-Z][A-Z0-9]*-\d+)", s)
    if m:
        key = m.group(1)
        return {"type": "jira", "key": key, "prefix": key.split("-")[0]}

    m = re.match(r"^([A-Z][A-Z0-9]*)-(\d+)$", s)
    if m:
        return {"type": "jira", "key": s, "prefix": m.group(1)}

    fail(
        f'Cannot parse input "{issue_input}". Expected one of:\n'
        "  - Jira ID: PROJ-12345\n"
        "  - Jira URL: https://your-jira.example.com/browse/PROJ-12345\n"
        "  - GitHub issue URL: https://github.com/owner/repo/issues/123\n"
        "  - GitHub short form: owner/repo#123"
    )


def route(parsed: dict, routing: dict) -> str | None:
    """First-match-wins over routes; falls back to default_project (may be None)."""
    for r in routing.get("routes", []):
        if parsed["type"] == "jira" and parsed["prefix"] in (r.get("jira_prefixes") or []):
            return r.get("project")
        if parsed["type"] == "github":
            if f"{parsed['owner']}/{parsed['repo']}" in (r.get("github_repos") or []):
                return r.get("project")
    return routing.get("default_project")


def routing_miss(parsed: dict, routing: dict, targets=()):
    known_prefixes = sorted({p for r in routing.get("routes", []) for p in (r.get("jira_prefixes") or [])})
    known_repos = sorted({p for r in routing.get("routes", []) for p in (r.get("github_repos") or [])})
    detail = (
        f"Known Jira prefixes: {', '.join(known_prefixes) or '(none)'}\n"
        f"Known GitHub repos: {', '.join(known_repos) or '(none)'}"
    )
    if os.environ.get("SOURCE_REPO_PATH"):
        # The checkout's own .qualityflow/ (if any) goes on stdout as repo_layer,
        # for the auto-discovery flow to apply over its synthesized context.
        schema = config_validate.load_yaml(CONFIG_DIR / "_schema.yaml")
        defaults = config_validate.load_yaml(CONFIG_DIR / "_defaults.yaml") or {}
        try:
            layer = config_layers.resolve_auto(schema, defaults, targets, os.environ)
        except ValueError as exc:
            fail(f"Repo config layers in SOURCE_REPO_PATH are invalid:\n{exc}")
        if layer:
            print(yaml.safe_dump({"repo_layer": layer}, sort_keys=False), end="")
            for entry in layer["config_layers"]:
                for warning in entry.get("warnings", []):
                    print(f"config warning: {entry['id']}: {warning}", file=sys.stderr)
        fail(
            "AUTO_DISCOVERY_REQUIRED\n"
            "No route matched but SOURCE_REPO_PATH is set. Run the auto-discovery\n"
            "flow in skills/project-resolver/SKILL.md (scan the repo, synthesize a\n"
            "project_context with config_dir: null).\n" + detail,
            code=3,
        )
    fail(
        "Unknown issue source. No project configured and no source repo available for auto-detection.\n"
        "To add a new project, create config/projects/{name}/ and add a route in config/routing.yaml.\n"
        "Alternatively, set SOURCE_REPO_PATH to a local checkout for auto-discovery.\n" + detail
    )


FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")  # a stps/ subfolder, as Push to PR takes it


def _read(path: Path) -> dict:
    data = config_validate.load_yaml(path) if path.is_file() else None
    return data if isinstance(data, dict) else {}


def _sig(name: str) -> str:
    """'sig-network', 'SIG Network' and 'Network' compare equal."""
    s = re.sub(r"[^a-z0-9]", "", name.lower())
    return s[3:] if s.startswith("sig") and len(s) > 3 else s


def ticket_folder(ticket_dir: Path, jira_id: str, docs_root, explicit=None):
    """The ticket's stps/<folder> in the design-docs repo, whose .qualityflow/
    applies to every STP and STD step (#231), and where it came from. First
    found: --folder, the one recorded in pipeline state, the imported STP's
    path, the ticket's PR, the stps/ subfolder named after the STP's Owning SIG
    (as Push to PR picks it). (None, None) when none is known."""
    state = _read(ticket_dir / "state" / "pipeline_state.yaml")
    imported = re.match(r"stps/([^/]+)/", str(_read(ticket_dir / "stp" / f"{jira_id}_stp_source.yaml").get("path") or ""))
    for folder, source in ((explicit, "--folder"), (state.get("stp_folder"), "pipeline state"),
                           (imported and imported[1], "the imported STP"),
                           (_read(ticket_dir / "state" / "pr_info.yaml").get("stp_folder"), "the ticket's PR")):
        if folder and FOLDER.fullmatch(str(folder)):
            return str(folder), source
    stp = ticket_dir / "stp" / f"{jira_id}_test_plan.md"
    sig = re.search(r"^\s*- \*\*Owning SIG:\*\*\s*(.+?)\s*$", stp.read_text(errors="replace"), re.M) if stp.is_file() else None
    if sig and docs_root and (docs_root / "stps").is_dir():
        match = [d.name for d in (docs_root / "stps").iterdir() if d.is_dir() and _sig(d.name) == _sig(sig[1])]
        if len(match) == 1:
            return match[0], "the STP's Owning SIG"
    return None, None


def record_folder(ticket_dir: Path, jira_id: str, folder: str, project_id: str, display_name: str):
    """stp_folder in pipeline state, so later steps and the dashboard use the
    same folder. Locked like the dashboard's own writes to the file."""
    sys.path.insert(0, str(REPO_ROOT / "skills" / "pipeline-state"))
    import state as pipeline_state  # noqa: E402

    path = ticket_dir / "state" / "pipeline_state.yaml"
    with pipeline_state.yaml_lock(str(path)):
        data = _read(path) or pipeline_state.new_state(jira_id, project_id, display_name)
        if data.get("stp_folder") != folder:
            data["stp_folder"] = folder
            pipeline_state.atomic_write(str(path), data)


def main():
    ap = argparse.ArgumentParser(description="Resolve an issue input to its project_context.")
    ap.add_argument("issue_input")
    ap.add_argument("--target", action="append", default=[], metavar="PATH",
                    help="what the run works on: a path, or <repo>:<path in its checkout> "
                         "(e.g. tier2_repo:tests/e2e). Repeatable: their deepest common directory. "
                         ".qualityflow/ dirs above it outrank the repo root's")
    ap.add_argument("--folder", metavar="NAME",
                    help="the ticket's stps/ subfolder in the design-docs repo: its .qualityflow/ "
                         "applies to every STP and STD step. Recorded in pipeline state")
    args = ap.parse_args()
    if args.folder is not None and not FOLDER.fullmatch(args.folder):
        fail(f"--folder {args.folder!r}: one stps/ subfolder name (letters, digits, . _ -)")

    parsed = parse_input(args.issue_input)

    routing = config_validate.load_yaml(CONFIG_DIR / "routing.yaml")
    if routing is None or isinstance(routing, Exception):
        fail(f"Cannot read config/routing.yaml: {routing}")

    project_id = route(parsed, routing)
    if project_id is None:
        routing_miss(parsed, routing, args.target)

    project_dir = CONFIG_DIR / "projects" / project_id
    if not project_dir.is_dir():
        fail(f'Project config directory not found: {project_dir}\nCreate it or fix the route in config/routing.yaml.')

    schema = config_validate.load_yaml(CONFIG_DIR / "_schema.yaml")
    defaults = config_validate.load_yaml(CONFIG_DIR / "_defaults.yaml") or {}
    if schema is None or isinstance(schema, Exception):
        fail(f"Cannot read config/_schema.yaml: {schema}")

    errors = config_validate.validate_project(project_dir, schema, defaults)
    if errors:
        fail(f'Project "{project_id}" config is invalid:\n' + "\n".join(errors))

    jira_id = (parsed["key"] if parsed["type"] == "jira"
               else f"{parsed['owner']}-{parsed['repo']}-{parsed['number']}")
    ticket_dir = REPO_ROOT / "outputs" / jira_id
    repositories = None
    overlay = ticket_dir / "repositories.overlay.yaml"
    if overlay.exists():
        from repository_overlay import apply_overlay
        try:
            repositories = apply_overlay(
                config_validate.load_yaml(project_dir / "repositories.yaml"), overlay)
        except (ValueError, yaml.YAMLError) as exc:
            fail(str(exc))
        repositories_file = overlay.with_name("repositories.resolved.yaml")
        repositories_file.write_text(yaml.safe_dump(repositories, sort_keys=False))

    # The ticket's stps/<folder> (#231): every step targets it, so the folder's
    # .qualityflow/ applies to the STP and STD runs, not only to Push to PR.
    repos = repositories if repositories is not None else config_validate.load_yaml(project_dir / "repositories.yaml") or {}
    docs = repos.get("design_docs_repo") if isinstance(repos, dict) else None
    targets, folder = list(args.target), None
    if isinstance(docs, dict) and docs:
        docs_root = config_layers.checkout(docs, os.environ)
        folder, source = ticket_folder(ticket_dir, jira_id, docs_root, args.folder)
        if folder and source != "pipeline state" and (args.folder or (ticket_dir / "state" / "pipeline_state.yaml").is_file()):
            central_project = config_validate.load_yaml(project_dir / "project.yaml") or {}
            record_folder(ticket_dir, jira_id, folder, project_id, central_project.get("display_name", project_id))
        if folder and targets in ([], ["design_docs_repo:stps"]):
            targets = [f"design_docs_repo:stps/{folder}"]
            print(f"config: stps/{folder} (from {source})", file=sys.stderr)
            if docs_root and not (docs_root / "stps" / folder).is_dir():
                print(f"config warning: stps/{folder} is not in the design-docs checkout: only the layers above it apply",
                      file=sys.stderr)
        elif not folder and targets in ([], ["design_docs_repo:stps"]) and docs_root and \
                any((docs_root / "stps").glob(f"*/{config_layers.LAYER_DIR}")):
            print(f"config: no stps/ folder known for {jira_id}, so no folder's {config_layers.LAYER_DIR}/ applies "
                  "(the STP run takes --folder; Push to PR records one)", file=sys.stderr)

    # Repo config layers: .qualityflow/ in the checkouts, merged over the central dir.
    try:
        layered = config_layers.resolve(
            project_id, project_dir, repos,
            schema, defaults, targets, os.environ, ticket_dir / "config" / project_id)
    except ValueError as exc:
        fail(f'Repo config layers for project "{project_id}" are invalid:\n{exc}')
    config_dir = f"config/projects/{project_id}"
    resolved_file = ticket_dir / "config.resolved.yaml"
    if layered and "config_dir" in layered:
        project_dir = layered["config_dir"]
        config_dir = project_dir.relative_to(REPO_ROOT).as_posix()
        resolved_file.write_text(yaml.safe_dump({
            "config_hash": layered["config_hash"], "config_dir": config_dir,
            "config_layers": layered["config_layers"], "config_provenance": layered["config_provenance"],
            "files": layered["files"]}, sort_keys=False))
        for key, layer in layered["config_provenance"].items():
            print(f"config: {key} from {layer}", file=sys.stderr)
        # A layer added context repos: the ticket overlay (highest) applies over them too.
        if repositories is not None and any(k.startswith("repositories.yaml:") for k in layered["config_provenance"]):
            repositories = apply_overlay(config_validate.load_yaml(project_dir / "repositories.yaml"), overlay)
            repositories_file.write_text(yaml.safe_dump(repositories, sort_keys=False))
    elif resolved_file.exists():  # a run without layers must not inherit an earlier run's
        resolved_file.unlink()
        shutil.rmtree(ticket_dir / "config", ignore_errors=True)
    for layer in (layered or {}).get("config_layers", []):
        for warning in layer.get("warnings", []):
            print(f"config warning: {layer['id']}: {warning}", file=sys.stderr)

    project = config_validate.load_yaml(project_dir / "project.yaml")

    # Shallow merge: project toggles over defaults (flat keys only)
    toggles = {**defaults.get("feature_toggles", {}), **(project.get("feature_toggles") or {})}

    versioning = project.get("versioning") or {}
    context = {
        "project_id": project_id,
        "display_name": project.get("display_name", project_id),
        "jira_id": jira_id,
        "issue_source": parsed["type"],
        "config_dir": config_dir,
        "feature_toggles": toggles,
        "model_policy": merge_policy(defaults, project),
        "stp_header": (project.get("stp_document") or {}).get("header", "Test Plan"),
        "versioning": {
            "product_name": versioning.get("product_name", project.get("display_name", project_id)),
            "platform_name": versioning.get("platform_name", "N/A"),
            "current_version": versioning.get("current_version", "N/A"),
        },
        # Auto mode: the tiers scenarios are labelled with instead of test
        # types (empty = test-type labels). See stp-generator Step 4.
        "scenario_tiers": project.get("scenario_tiers") or [],
        # pytest marks every Python STD stub carries as a decorator, e.g. [manual].
        "stub_marks": project.get("stub_marks") or [],
        # Populated by the caller when feature_toggles.repo_files_fetch is true
        # (MCP fetch step in SKILL.md — not reachable from this script).
        "repo_rules": {},
    }
    if folder:  # the ticket's stps/ subfolder in the design-docs repo (#231)
        context["stp_folder"] = folder
    if repositories is not None:
        context["repositories"] = repositories
        context["repositories_file"] = str(repositories_file)
    if layered:
        context["config_layers"] = layered["config_layers"]
        if "config_dir" in layered:
            context["config_provenance"] = layered["config_provenance"]
            context["config_hash"] = layered["config_hash"]
    if parsed["type"] == "github":
        context["github_issue"] = {
            "owner": parsed["owner"],
            "repo": parsed["repo"],
            "number": parsed["number"],
            "url": f"https://github.com/{parsed['owner']}/{parsed['repo']}/issues/{parsed['number']}",
        }

    print(yaml.safe_dump({"project_context": context}, sort_keys=False, default_flow_style=False), end="")


if __name__ == "__main__":
    main()
