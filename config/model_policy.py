"""Shared per-ticket config loading (model policy, feature toggles); no provider
SDK or runtime-specific execution."""
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


def _read(path):
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def _project_config(root, issue):
    """(_defaults.yaml, project.yaml) for `issue`: first matching route,
    including canonical GitHub output IDs; project {} when unrouted."""
    base = Path(root) / "config"
    routing = _read(base / "routing.yaml")
    project = routing.get("default_project")
    for route in routing.get("routes", []):
        if (any(issue.startswith(p + "-") for p in route.get("jira_prefixes", []))
                or any(issue.startswith(repo.replace("/", "-") + "-")
                       or issue.startswith(repo + "#")
                       or issue.startswith("https://github.com/" + repo + "/issues/")
                       for repo in route.get("github_repos", []))):
            project = route.get("project")
            break
    return _read(base / "_defaults.yaml"), (_read(base / "projects" / project / "project.yaml") if project else {})


def load_policy(root, issue):
    return merge_policy(*_project_config(root, issue))


def feature_toggles(root, issue):
    """The project's feature toggles over the defaults (flat keys, as project-resolver merges them)."""
    defaults, project = _project_config(root, issue)
    return {**(defaults.get("feature_toggles") or {}), **(project.get("feature_toggles") or {})}


def default_model(policy, phase, runtime):
    tier = ("review" if phase in ("stp_review", "std_review") else
            "cheap" if phase in ("collection", "formatting") else "standard")
    return (policy.get(tier) or {}).get(runtime, "")
