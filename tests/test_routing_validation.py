"""config/validate.py rejects a route nothing can match (e.g. the old `prefix:` shape)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _validator():
    spec = importlib.util.spec_from_file_location("qf_validate", ROOT / "config" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_route_without_prefixes_or_repos_is_an_error(tmp_path):
    (tmp_path / "projects" / "acme").mkdir(parents=True)
    (tmp_path / "routing.yaml").write_text("routes:\n  - prefix: ACME\n    project: acme\n")
    errors = _validator().validate_routing(tmp_path)
    assert any("no jira_prefixes or github_repos" in e for e in errors), errors
    (tmp_path / "routing.yaml").write_text("routes:\n  - project: acme\n    jira_prefixes: [ACME]\n")
    assert not [e for e in _validator().validate_routing(tmp_path) if "no jira_prefixes" in e]
