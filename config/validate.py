#!/usr/bin/env python3
"""Validate QualityFlow project configurations against _schema.yaml."""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


def load_yaml(path: Path) -> dict | Exception | None:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        return e
    except FileNotFoundError:
        return None


def check_required_fields(data: dict, fields: list[str], file_label: str) -> list[str]:
    errors = []
    for field in fields:
        parts = field.split(".")
        obj = data
        for part in parts:
            if not isinstance(obj, dict) or part not in obj:
                errors.append(f"  {file_label}: missing required field '{field}'")
                break
            obj = obj[part]
    return errors


def validate_project(project_dir: Path, schema: dict, defaults: dict) -> list[str]:
    errors = []
    project_name = project_dir.name

    # 1. Check required files exist and parse
    for fname in schema.get("required_files", []):
        fpath = project_dir / fname
        if not fpath.exists():
            errors.append(f"  Missing required file: {fname}")
            continue
        result = load_yaml(fpath)
        if isinstance(result, Exception):
            errors.append(f"  YAML syntax error in {fname}: {result}")

    # 1b. Issue sources: at least one of issue_source_files must exist and parse
    source_files = schema.get("issue_source_files", ["jira.yaml", "github.yaml"])
    has_source = False
    for fname in source_files:
        result = load_yaml(project_dir / fname)
        if result is None:
            continue
        if isinstance(result, Exception):
            errors.append(f"  YAML syntax error in {fname}: {result}")
        else:
            has_source = True
    if not has_source:
        errors.append(f"  No issue source configured: at least one of {', '.join(source_files)} must exist and parse")

    # 2. Load project.yaml for toggle checks
    project_data = load_yaml(project_dir / "project.yaml")
    if project_data is None or isinstance(project_data, Exception):
        errors.append("  Cannot validate toggles: project.yaml unreadable")
        return errors

    # 3. Validate required fields per file
    file_validators = {
        "project.yaml": "project_yaml",
        "repositories.yaml": "repositories_yaml",
        "components.yaml": "components_yaml",
        "jira.yaml": "jira_yaml",
        "github.yaml": "github_yaml",
    }
    for fname, schema_key in file_validators.items():
        fpath = project_dir / fname
        if not fpath.exists():
            continue
        data = load_yaml(fpath)
        if data is None or isinstance(data, Exception):
            continue
        field_spec = schema.get("validation", {}).get(schema_key, {})
        required = field_spec.get("required_fields", [])
        errors.extend(check_required_fields(data, required, fname))

    # 4. Validate project_id matches directory name
    pid = project_data.get("project_id", "")
    if pid != project_name:
        errors.append(f"  project_id '{pid}' does not match directory name '{project_name}'")

    # 5. Tier-config consistency: when test_strategy == "tier", at least one
    #    tier*.yaml must exist. Rule shape matches _schema.yaml's tier_consistency
    #    (a single dict with condition/requires_glob/error).
    merged_toggles = {**defaults.get("feature_toggles", {}), **project_data.get("feature_toggles", {})}
    rule = schema.get("tier_consistency")
    if isinstance(rule, dict) and "test_strategy == 'tier'" in rule.get("condition", ""):
        if merged_toggles.get("test_strategy") == "tier":
            if not list(project_dir.glob(rule.get("requires_glob", "tier*.yaml"))):
                errors.append(f"  {rule['error']}")

    # 6. Validate every tier*.yaml against the generic tier_yaml field spec.
    field_spec = schema.get("validation", {}).get("tier_yaml", {})
    required = field_spec.get("required_fields", [])
    for fpath in sorted(project_dir.glob("tier*.yaml")):
        if fpath.name.endswith(".example"):
            continue
        data = load_yaml(fpath)
        if data is None or isinstance(data, Exception):
            continue
        errors.extend(check_required_fields(data, required, fpath.name))

    return errors


def validate_routing(config_dir: Path) -> list[str]:
    errors = []
    routing = load_yaml(config_dir / "routing.yaml")
    if routing is None:
        errors.append("routing.yaml: file not found")
        return errors
    if isinstance(routing, Exception):
        errors.append(f"routing.yaml: YAML syntax error: {routing}")
        return errors

    projects_dir = config_dir / "projects"
    seen_prefixes: dict[str, str] = {}
    seen_repos: dict[str, str] = {}
    for route in routing.get("routes", []):
        project_name = route.get("project", "")
        if not (projects_dir / project_name).is_dir():
            errors.append(f"routing.yaml: route references project '{project_name}' but config/projects/{project_name}/ does not exist")
        # Duplicate prefixes/repos across routes: first-match-wins would silently misroute
        for prefix in route.get("jira_prefixes") or []:
            if prefix in seen_prefixes:
                errors.append(f"routing.yaml: jira prefix '{prefix}' appears in both '{seen_prefixes[prefix]}' and '{project_name}' routes (first match wins — remove one)")
            else:
                seen_prefixes[prefix] = project_name
        for repo in route.get("github_repos") or []:
            if not isinstance(repo, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
                errors.append(f"routing.yaml: github_repos entry {repo!r} in route '{project_name}' is not an 'owner/repo' string")
                continue
            if repo in seen_repos:
                errors.append(f"routing.yaml: github repo '{repo}' appears in both '{seen_repos[repo]}' and '{project_name}' routes (first match wins — remove one)")
            else:
                seen_repos[repo] = project_name

    default = routing.get("default_project")
    if default is not None and not (projects_dir / str(default)).is_dir():
        errors.append(f"routing.yaml: default_project '{default}' does not exist at config/projects/{default}/")
    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <config_dir_or_project_dir> [project_name]")
        print("  python validate.py config/                    # validate all projects")
        print("  python validate.py config/projects/example/   # validate one project")
        sys.exit(1)

    target = Path(sys.argv[1])

    # Determine if target is config root or a specific project
    if (target / "_schema.yaml").exists():
        config_dir = target
        schema = load_yaml(config_dir / "_schema.yaml")
        defaults = load_yaml(config_dir / "_defaults.yaml") or {}

        if schema is None or isinstance(schema, Exception):
            print(f"FAIL: Cannot read _schema.yaml: {schema}")
            sys.exit(1)

        all_errors = []

        # Validate routing
        routing_errors = validate_routing(config_dir)
        if routing_errors:
            all_errors.append(("routing", routing_errors))

        # Validate each project
        projects_dir = config_dir / "projects"
        if not projects_dir.is_dir():
            print("FAIL: config/projects/ directory not found")
            sys.exit(1)

        for project_dir in sorted(projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            errs = validate_project(project_dir, schema, defaults)
            if errs:
                all_errors.append((project_dir.name, errs))
            else:
                print(f"  PASS: {project_dir.name}")

        if all_errors:
            print()
            for name, errs in all_errors:
                print(f"FAIL: {name}")
                for e in errs:
                    print(e)
            sys.exit(1)
        else:
            print("\nAll projects valid.")
    elif (target / "project.yaml").exists():
        # Single project directory
        config_dir = target.parent.parent
        schema = load_yaml(config_dir / "_schema.yaml")
        defaults = load_yaml(config_dir / "_defaults.yaml") or {}

        if schema is None or isinstance(schema, Exception):
            print(f"FAIL: Cannot find _schema.yaml at {config_dir}")
            sys.exit(1)

        errs = validate_project(target, schema, defaults)
        if errs:
            print(f"FAIL: {target.name}")
            for e in errs:
                print(e)
            sys.exit(1)
        else:
            print(f"PASS: {target.name}")
    else:
        print(f"Error: {target} is not a config directory or project directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
