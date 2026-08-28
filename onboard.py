#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click>=8.1.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
Onboard a new project to QualityFlow.

Reads a filled-in onboarding template and generates all config files + routing entry.

Usage:
    uv run onboard.py --input my-project.yaml
    uv run onboard.py --input my-project.yaml --dry-run
    uv run onboard.py --input my-project.yaml --force     # overwrite existing
"""

import importlib.util
import shutil
import tempfile
from pathlib import Path

import click
import yaml

REQUIRED_FIELDS = [
    "project_id",
    "display_name",
    "repo_name",
    "repo_org",
    "repo_url",
    "repo_language",
    "build_system",
    "build_command",
    "jira_url",
    "jira_prefixes",
    "platform_name",
    "components",
]

CONFIG_DIR = Path(__file__).parent / "config"


def load_input(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def validate_input(data: dict) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    if "project_id" in data and " " in str(data["project_id"]):
        errors.append("project_id must not contain spaces")
    if "jira_prefixes" in data and not isinstance(data["jira_prefixes"], list):
        errors.append("jira_prefixes must be a list")
    if "components" in data and not isinstance(data["components"], dict):
        errors.append("components must be a mapping")
    return errors


def build_project_yaml(data: dict) -> dict:
    toggles = {"test_strategy": data.get("test_strategy", "auto")}
    if data.get("test_strategy") == "tier":
        toggles["tier1_tests"] = True
        toggles["tier2_tests"] = True
        toggles["tier3_tests"] = True
    doc = {
        "project_id": data["project_id"],
        "display_name": data["display_name"],
        "feature_toggles": toggles,
    }
    if data.get("description"):
        doc["description"] = data["description"]
    return doc


def build_repositories_yaml(data: dict) -> dict:
    repo = {
        "name": data["repo_name"],
        "org": data["repo_org"],
        "full_name": f"{data['repo_org']}/{data['repo_name']}",
        "url": data["repo_url"],
        "local_path_env": "SOURCE_REPO_PATH",
        "default_branch": data.get("default_branch", "main"),
        "language": data["repo_language"],
        "build_system": data["build_system"],
        "build_command": data["build_command"],
    }
    doc: dict = {"primary_repo": repo}
    if data.get("tier2_repo_name"):
        doc["tier2_repo"] = {
            "name": data["tier2_repo_name"],
            "org": data.get("tier2_repo_org", data["repo_org"]),
            "full_name": f"{data.get('tier2_repo_org', data['repo_org'])}/{data['tier2_repo_name']}",
            "default_branch": "main",
            "language": "python",
        }
    doc["pr_url_patterns"] = [
        f"https://github.com/{'{org}'}/{'{repo}'}/pull/{'{number}'}"
    ]
    return doc


def build_jira_yaml(data: dict) -> dict:
    url = data["jira_url"].rstrip("/")
    return {
        "instance": {
            "url": url,
            "browse_pattern": f"{url}/browse/{{key}}",
        },
        "prefixes": data["jira_prefixes"],
        "pr_url_scan_pattern": r"https://github.com/.*/pull/\d+",
    }


def build_components_yaml(data: dict) -> dict:
    components = data["components"]
    path_to_feature = {}
    for comp in components.values():
        for feat in comp.get("features", []):
            path_to_feature[feat["path"]] = feat["name"]
    return {
        "component_package_map": components,
        "path_to_feature": path_to_feature,
    }


def build_environment_yaml(data: dict) -> dict:
    platform: dict = {"name": data["platform_name"]}
    if data.get("platform_short_name"):
        platform["short_name"] = data["platform_short_name"]
    if data.get("cli_tools"):
        platform["cli_tools"] = data["cli_tools"]
    return {"platform": platform}


def build_pii_yaml(data: dict) -> dict:
    return {
        "allowed_product_names": data.get("pii_allowed_products", [data["platform_name"]]),
        "allowed_project_names": data.get("pii_allowed_projects", []),
        "allowed_technical_standards": [],
        "vendor_replacements": {"cloud": "Cloud Provider", "hardware": "Hardware Vendor"},
    }


def build_coverage_yaml(data: dict) -> dict:
    return {
        "repos": [
            {
                "service": "github",
                "org": data["repo_org"],
                "repo": data["repo_name"],
                "label": f"{data['repo_org']}/{data['repo_name']}",
                "type": "primary",
                "language": data["repo_language"],
                "local_path": None,
                "test_packages": ["./..."],
                "flags": ["unit-tests"],
            }
        ]
    }


def write_yaml(path: Path, doc: dict, dry_run: bool) -> None:
    content = yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
    if dry_run:
        click.secho(f"\n--- {path} ---", fg="cyan")
        click.echo(content)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def append_route(data: dict, routing_path: Path, dry_run: bool) -> None:
    """Append the project's route via a YAML round-trip (parse → mutate → dump),
    not raw string surgery — structurally safe against formatting variations.
    Note: a round-trip drops comments in routing.yaml."""
    routing = {}
    if routing_path.exists():
        routing = yaml.safe_load(routing_path.read_text()) or {}
    routes = routing.setdefault("routes", [])

    if any(isinstance(r, dict) and r.get("project") == data["project_id"] for r in routes):
        click.secho(f"Route for '{data['project_id']}' already exists in routing.yaml, skipping.", fg="yellow")
        return

    route: dict = {"project": data["project_id"], "jira_prefixes": list(data["jira_prefixes"])}
    if data.get("github_repos"):
        route["github_repos"] = list(data["github_repos"])
    routes.append(route)

    if dry_run:
        click.secho(f"\n--- append to {routing_path} ---", fg="cyan")
        click.echo(yaml.dump([route], default_flow_style=False, sort_keys=False, allow_unicode=True))
    else:
        routing_path.write_text(
            yaml.dump(routing, default_flow_style=False, sort_keys=False, allow_unicode=True))


def _load_validator():
    """Import config/validate.py fresh by file path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("qf_config_validate", CONFIG_DIR / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_project_docs(tmp_project: Path) -> list[str]:
    """Run config/validate.py's project validation against a staged project dir."""
    validator = _load_validator()
    schema = validator.load_yaml(CONFIG_DIR / "_schema.yaml")
    if schema is None or isinstance(schema, Exception):
        return [f"  Cannot read {CONFIG_DIR / '_schema.yaml'}: {schema}"]
    defaults = validator.load_yaml(CONFIG_DIR / "_defaults.yaml")
    if defaults is None or isinstance(defaults, Exception):
        defaults = {}
    return validator.validate_project(tmp_project, schema, defaults)


@click.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, path_type=Path), help="Path to filled-in onboarding YAML")
@click.option("--dry-run", is_flag=True, default=False, help="Preview generated files without writing")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing project directory")
def main(input_path: Path, dry_run: bool, force: bool) -> None:
    """Onboard a new project to QualityFlow from a template YAML file."""
    data = load_input(input_path)
    errors = validate_input(data)
    if errors:
        for e in errors:
            click.secho(f"  Error: {e}", fg="red")
        raise SystemExit(1)

    project_id = data["project_id"]
    project_dir = CONFIG_DIR / "projects" / project_id

    if project_dir.exists() and not force:
        click.secho(f"Error: {project_dir} already exists. Use --force to overwrite.", fg="red")
        raise SystemExit(1)

    click.secho(f"Onboarding project: {data['display_name']} ({project_id})", fg="blue", bold=True)
    if dry_run:
        click.secho("DRY RUN — no files will be written\n", fg="yellow")

    builders = [
        ("project.yaml", build_project_yaml),
        ("repositories.yaml", build_repositories_yaml),
        ("jira.yaml", build_jira_yaml),
        ("components.yaml", build_components_yaml),
        ("environment.yaml", build_environment_yaml),
        ("pii_exceptions.yaml", build_pii_yaml),
        ("coverage.yaml", build_coverage_yaml),
    ]

    # Build every doc up front — nothing touches config/ until validation passes.
    docs: list[tuple[str, dict]] = [(filename, builder(data)) for filename, builder in builders]
    if data.get("test_strategy") == "tier":
        for tier_cfg in data.get("tiers", []):
            tier_num = tier_cfg.get("tier_number", 1)
            docs.append((f"tier{tier_num}.yaml", {
                "enabled": tier_cfg.get("enabled", True),
                "tier": f"Tier {tier_num}",
                "display_name": tier_cfg.get("display_name", ""),
                "language": tier_cfg.get("language", "go"),
                "framework": tier_cfg.get("framework", "testing"),
            }))

    if dry_run:
        for filename, doc in docs:
            write_yaml(project_dir / filename, doc, True)
        append_route(data, CONFIG_DIR / "routing.yaml", True)
    else:
        # Stage into a temp dir, validate there, and only on success copy into
        # config/ and append the route — a validation failure must not leave a
        # half-onboarded project already wired into routing.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_project = Path(tmp) / project_id  # dir name must match project_id for validation
            tmp_project.mkdir()
            for filename, doc in docs:
                write_yaml(tmp_project / filename, doc, False)

            click.echo()
            click.secho("Validating...", fg="cyan")
            errors = validate_project_docs(tmp_project)
            if errors:
                click.secho("Validation failed — nothing was written to config/:", fg="red")
                for e in errors:
                    click.echo(e)
                raise SystemExit(1)
            click.secho(f"PASS: {project_id}", fg="green")

            shutil.copytree(tmp_project, project_dir, dirs_exist_ok=True)

        for subdir in ["patterns", "reference", "templates/stp"]:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        append_route(data, CONFIG_DIR / "routing.yaml", False)

    click.echo()
    click.secho("Done!", fg="green", bold=True)
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Deploy:  uv run deploy.py --target both")
    click.echo(f"  2. Test:    /stp-builder {data['jira_prefixes'][0]}-<ID>")


if __name__ == "__main__":
    main()
