"""Shared model policy loading; no provider SDK or runtime-specific execution."""
import copy
from pathlib import Path

import yaml


def merge_policy(defaults, project):
    """Merge each policy section by key (runtime maps merge by runtime)."""
    policy = copy.deepcopy(defaults.get("model_policy") or {})
    for key, value in (project.get("model_policy") or {}).items():
        if isinstance(value, dict):
            policy.setdefault(key, {}).update(value)
        else:
            policy[key] = value
    return policy


def load_policy(root, issue):
    """Use first matching route, including canonical GitHub output IDs."""
    def read(path):
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    base = Path(root) / "config"
    routing = read(base / "routing.yaml")
    project = routing.get("default_project")
    for route in routing.get("routes", []):
        if (any(issue.startswith(p + "-") for p in route.get("jira_prefixes", []))
                or any(issue.startswith(repo.replace("/", "-") + "-")
                       or issue.startswith(repo + "#")
                       or issue.startswith("https://github.com/" + repo + "/issues/")
                       for repo in route.get("github_repos", []))):
            project = route.get("project")
            break
    overrides = read(base / "projects" / project / "project.yaml") if project else {}
    return merge_policy(read(base / "_defaults.yaml"), overrides)


def default_model(policy, phase, runtime):
    tier = ("review" if phase in ("stp_review", "std_review") else
            "cheap" if phase in ("collection", "formatting") else "standard")
    return (policy.get(tier) or {}).get(runtime, "")
