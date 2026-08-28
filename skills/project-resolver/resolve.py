#!/usr/bin/env python3
"""Deterministic project resolver for QualityFlow.

Parses an issue input (Jira ID/URL, GitHub issue URL/short form), routes it
via config/routing.yaml, validates the project config, merges feature toggles,
and prints the resolved project_context YAML to stdout.

Exit codes:
  0 - success, project_context on stdout
  1 - error (unparseable input, routing miss, invalid config)
  3 - routing miss but SOURCE_REPO_PATH is set: caller must run the
      auto-discovery flow documented in SKILL.md (marker: AUTO_DISCOVERY_REQUIRED)
"""

import os
import re
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


def routing_miss(parsed: dict, routing: dict):
    known_prefixes = sorted({p for r in routing.get("routes", []) for p in (r.get("jira_prefixes") or [])})
    known_repos = sorted({p for r in routing.get("routes", []) for p in (r.get("github_repos") or [])})
    detail = (
        f"Known Jira prefixes: {', '.join(known_prefixes) or '(none)'}\n"
        f"Known GitHub repos: {', '.join(known_repos) or '(none)'}"
    )
    if os.environ.get("SOURCE_REPO_PATH"):
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


def main():
    if len(sys.argv) != 2:
        fail('Usage: python3 skills/project-resolver/resolve.py "<issue input>"')

    parsed = parse_input(sys.argv[1])

    routing = config_validate.load_yaml(CONFIG_DIR / "routing.yaml")
    if routing is None or isinstance(routing, Exception):
        fail(f"Cannot read config/routing.yaml: {routing}")

    project_id = route(parsed, routing)
    if project_id is None:
        routing_miss(parsed, routing)

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

    project = config_validate.load_yaml(project_dir / "project.yaml")

    # Shallow merge: project toggles over defaults (flat keys only)
    toggles = {**defaults.get("feature_toggles", {}), **(project.get("feature_toggles") or {})}

    versioning = project.get("versioning") or {}
    context = {
        "project_id": project_id,
        "display_name": project.get("display_name", project_id),
        "jira_id": parsed["key"] if parsed["type"] == "jira"
        else f"{parsed['owner']}-{parsed['repo']}-{parsed['number']}",
        "issue_source": parsed["type"],
        "config_dir": f"config/projects/{project_id}",
        "feature_toggles": toggles,
        "stp_header": (project.get("stp_document") or {}).get("header", "Test Plan"),
        "versioning": {
            "product_name": versioning.get("product_name", project.get("display_name", project_id)),
            "platform_name": versioning.get("platform_name", "N/A"),
            "current_version": versioning.get("current_version", "N/A"),
        },
        # Populated by the caller when feature_toggles.repo_files_fetch is true
        # (MCP fetch step in SKILL.md — not reachable from this script).
        "repo_rules": {},
    }
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
