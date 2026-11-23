#!/usr/bin/env python3
"""Project settings > Configuration (#227): where each config value comes from,
and central edits from the dashboard.

GET /api/projects/{id}/config shows each file and top-level key with the layer
that set it and what that overrides; PUT edits one central key, only where a
repo layer could also set it, and only if the project still validates.

Same conventions as tests/test_mutating_routes.py: env set before `import ui`,
globals monkeypatched per test, TestClient not entered as a context manager.
Run:
  uv run --python 3.11 --with pytest --with-requirements requirements.txt \\
      python -m pytest tests/test_project_config_view.py -q
"""
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "config"))
import ui  # noqa: E402
import layers  # noqa: E402
import validate  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)
KEY = "cfgtestkey"
HDR = {"X-API-Key": KEY}


@pytest.fixture
def qf(tmp_path, monkeypatch):
    """A config/ copy whose example project has a design-docs repo checked out
    with a root layer and an stps/sig-x/ layer."""
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    proj = cfg / "projects" / "example"
    repos = yaml.safe_load((proj / "repositories.yaml").read_text())
    repos["design_docs_repo"] = {"name": "my-docs", "org": "my-org", "full_name": "my-org/my-docs",
                                 "url": "https://github.com/my-org/my-docs", "default_branch": "main",
                                 "local_path_env": "DOCS_REPO_PATH"}
    (proj / "repositories.yaml").write_text(yaml.safe_dump(repos, sort_keys=False))
    docs = tmp_path / "docs"
    for d, desc in ((docs, "from the root layer"), (docs / "stps" / "sig-x", "from sig-x")):
        (d / ".qualityflow").mkdir(parents=True)
        (d / ".qualityflow" / "project.yaml").write_text(yaml.safe_dump(
            {"version": 1, "project_id": "example", "description": desc}))
    (docs / ".qualityflow" / "components.yaml").write_text(yaml.safe_dump(
        {"component_package_map": {"layer-comp": ["pkg/layer"]}}))
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setenv("DOCS_REPO_PATH", str(docs))
    for name, value in {"CONFIG": cfg, "OUTPUTS": out, "_API_KEY": KEY, "_rate_limits": {},
                        "_RATE_LIMIT_MAX": 10_000}.items():
        monkeypatch.setattr(ui, name, value)
    return {"cfg": cfg, "proj": proj, "docs": docs, "out": out, "repos": repos}


def record_run(qf, ticket, target):
    """What resolve.py writes for a run whose layers applied: the merged copy
    and config.resolved.yaml."""
    schema = yaml.safe_load((qf["cfg"] / "_schema.yaml").read_text())
    defaults = yaml.safe_load((qf["cfg"] / "_defaults.yaml").read_text())
    out_dir = qf["out"] / ticket / "config" / "example"
    res = layers.resolve("example", qf["proj"], qf["repos"], schema, defaults, [target], os.environ, out_dir)
    (qf["out"] / ticket / "config.resolved.yaml").write_text(yaml.safe_dump({
        "config_hash": res["config_hash"], "config_dir": f"outputs/{ticket}/config/example",
        "config_layers": res["config_layers"], "config_provenance": res["config_provenance"],
        "files": res["files"]}, sort_keys=False))


def file_row(view, name):
    return next(f for f in view["files"] if f["name"] == name)


def key_row(view, name, key):
    return next(k for k in file_row(view, name)["keys"] if k["key"] == key)


def test_repo_roots_now_when_no_run_recorded_a_layer(qf):
    view = client.get("/api/projects/example/config").json()
    assert view["ticket"] == "" and view["tickets"] == []
    assert [l["id"] for l in view["layers"]] == ["central", "my-docs:."]  # no target: no nested layer
    root = view["layers"][1]
    assert root["link"] == "https://github.com/my-org/my-docs/tree/main/.qualityflow"
    desc = key_row(view, "project.yaml", "description")
    assert desc["set_by"] == ["central", "my-docs:."] and desc["value"] == "from the root layer"
    assert desc["overrides"][0]["over"][0]["layer"] == "central"
    assert file_row(view, "project.yaml")["links"]["my-docs:."] == \
        "https://github.com/my-org/my-docs/blob/main/.qualityflow/project.yaml"
    comps = key_row(view, "components.yaml", "component_package_map")  # a map merges key by key
    assert "layer-comp" in comps["value"] and comps["set_by"] == ["central", "my-docs:."]
    assert [o["path"] for o in comps["overrides"]] == ["component_package_map.layer-comp"]
    assert comps["overrides"][0]["over"] == []  # added, nothing below it set that key


def test_a_tickets_run_shows_its_nested_layer_and_what_each_overrides(qf):
    record_run(qf, "MYPROJ-7", "design_docs_repo:stps/sig-x")
    view = client.get("/api/projects/example/config").json()  # default: the newest recorded run
    assert view["ticket"] == "MYPROJ-7" and view["config_hash"].startswith("sha256:")
    assert [l["id"] for l in view["layers"]] == ["central", "my-docs:.", "my-docs:stps/sig-x"]
    desc = key_row(view, "project.yaml", "description")
    assert desc["value"] == "from sig-x"  # what the run used
    nested = next(o for o in desc["overrides"] if o["layer"] == "my-docs:stps/sig-x")
    assert [u["layer"] for u in nested["over"]] == ["central", "my-docs:."]
    assert not any(l.get("changed") for l in view["layers"])
    (qf["docs"] / "stps/sig-x/.qualityflow/project.yaml").write_text(yaml.safe_dump(
        {"version": 1, "project_id": "example", "description": "edited after the run"}))
    view = client.get("/api/projects/example/config?ticket=MYPROJ-7").json()
    assert next(l for l in view["layers"] if l["id"] == "my-docs:stps/sig-x")["changed"] is True
    assert key_row(view, "project.yaml", "description")["value"] == "edited after the run"  # what a run gets now
    assert view["config_hash"] != view["run_config_hash"] and view["target"] == "my-docs:stps/sig-x"
    # A central edit shows at once, under the layers that still win over it.
    r = client.put("/api/projects/example/config", headers=HDR,
                   json={"file": "environment.yaml", "key": "cluster_requirements", "value": "min_worker_nodes: 2"})
    assert r.status_code == 200
    view = client.get("/api/projects/example/config?ticket=MYPROJ-7").json()
    assert key_row(view, "environment.yaml", "cluster_requirements")["value"] == "min_worker_nodes: 2"
    shutil.rmtree(qf["docs"] / "stps/sig-x/.qualityflow")
    view = client.get("/api/projects/example/config?ticket=MYPROJ-7").json()
    assert next(l for l in view["layers"] if l["id"] == "my-docs:stps/sig-x")["status"] == "gone"
    assert client.get("/api/projects/example/config?ticket=NOPE-1").status_code == 404
    assert client.get("/api/projects/example/config?ticket=").json()["ticket"] == ""


def test_a_nested_layers_list_is_shown_adding_to_the_layers_below(qf):
    """A nested layer's plain list joins the lower layers' (#236): the view shows
    the joined value and says the nested layer adds to them, not that it overrides."""
    for d, marks in ((qf["docs"], ["root"]), (qf["docs"] / "stps" / "sig-x", ["sig"])):
        p = d / ".qualityflow" / "project.yaml"
        doc = yaml.safe_load(p.read_text())
        doc["stub_marks"] = marks
        p.write_text(yaml.safe_dump(doc))
    record_run(qf, "MYPROJ-8", "design_docs_repo:stps/sig-x")
    view = client.get("/api/projects/example/config?ticket=MYPROJ-8").json()
    marks = key_row(view, "project.yaml", "stub_marks")
    assert yaml.safe_load(marks["value"]) == ["root", "sig"]
    by_layer = {o["layer"]: o for o in marks["overrides"]}
    assert by_layer["my-docs:stps/sig-x"]["joins"] is True and by_layer["my-docs:."]["joins"] is False


def test_central_only_keys_are_locked_and_refused(qf):
    view = client.get("/api/projects/example/config").json()
    assert file_row(view, "jira.yaml")["lock"].startswith("Central only")
    assert file_row(view, "pii_exceptions.yaml")["lock"].startswith("Sensitive")
    assert key_row(view, "project.yaml", "display_name")["lock"] and not key_row(view, "project.yaml", "display_name")["editable"]
    assert key_row(view, "repositories.yaml", "primary_repo")["lock"].startswith("Central only")
    assert key_row(view, "project.yaml", "feature_toggles")["central_only"] == ["pr_autofix"]
    put = lambda **body: client.put("/api/projects/example/config", headers=HDR, json=body)  # noqa: E731
    assert put(file="jira.yaml", key="instance", value="https://evil.example.com").status_code == 403
    assert put(file="project.yaml", key="display_name", value="x").status_code == 403
    assert put(file="project.yaml", key="model_policy", value="{}").status_code == 403
    assert put(file="repositories.yaml", key="additional_repos", value="[]").status_code == 400
    toggles = yaml.safe_load((qf["proj"] / "project.yaml").read_text())["feature_toggles"]
    flipped = dict(toggles, pr_autofix=not toggles.get("pr_autofix", False))
    r = put(file="project.yaml", key="feature_toggles", value=yaml.safe_dump(flipped))
    assert r.status_code == 403 and "pr_autofix" in r.json()["detail"]
    assert put(file="../routing.yaml", key="routes", value="[]").status_code == 400
    assert put(file="environment.yaml", key="not_a_setting", value="1").status_code == 403


def test_a_central_edit_is_validated_then_written(qf):
    put = lambda **body: client.put("/api/projects/example/config", headers=HDR, json=body)  # noqa: E731
    assert put(file="project.yaml", key="description", value="Edited in the dashboard").status_code == 200
    assert yaml.safe_load((qf["proj"] / "project.yaml").read_text())["description"] == "Edited in the dashboard"
    assert validate.validate_project(qf["proj"], yaml.safe_load((qf["cfg"] / "_schema.yaml").read_text()),
                                     yaml.safe_load((qf["cfg"] / "_defaults.yaml").read_text())) == []
    before = (qf["proj"] / "components.yaml").read_text()
    r = put(file="components.yaml", key="component_package_map", remove=True)  # a required field
    assert r.status_code == 400 and "component_package_map" in r.json()["detail"]
    assert (qf["proj"] / "components.yaml").read_text() == before  # nothing written
    assert put(file="environment.yaml", key="platform", value="a: [unclosed").status_code == 400
    assert put(file="environment.yaml", key="version_constraints", value="kubernetes: 1.30+").status_code == 200
    assert put(file="environment.yaml", key="cluster_requirements", remove=True).status_code == 200
    env = yaml.safe_load((qf["proj"] / "environment.yaml").read_text())
    assert env["version_constraints"] == {"kubernetes": "1.30+"} and "cluster_requirements" not in env
    assert client.put("/api/projects/example/config", json={"file": "project.yaml", "key": "description",
                                                              "value": "x"}).status_code == 403  # no key


# ------------------------------------------------- config kept in a repo branch

def test_yaml_edit_text_rewrites_only_the_changed_keys():
    text = ("# Project config\nversion: 1\n\n# who to ask\nowner: alice  # the lead\nlist:\n  - a\n  - b\n"
            "\n# kept\ntail: true\n")
    old = yaml.safe_load(text)
    out = ui._yaml_edit_text(text, old, {**old, "list": ["a", "c"]})
    assert out == ("# Project config\nversion: 1\n\n# who to ask\nowner: alice  # the lead\nlist:\n- a\n- c\n"
                   "\n# kept\ntail: true\n")
    out = ui._yaml_edit_text(text, old, {k: v for k, v in old.items() if k != "owner"} | {"new": {"x": 1}})
    assert "owner" not in out and "# who to ask" in out and out.endswith("new:\n  x: 1\n")
    assert yaml.safe_load(out) == {"version": 1, "list": ["a", "b"], "tail": True, "new": {"x": 1}}
    flow = "{a: 1, b: 2}\n"  # nothing to splice: dumped whole, still exact
    assert yaml.safe_load(ui._yaml_edit_text(flow, {"a": 1, "b": 2}, {"a": 1, "b": 3})) == {"a": 1, "b": 3}


class FakeGitHub:
    """The GitHub calls _config_change makes, against an in-memory repo."""

    def __init__(self, files):
        self.files = dict(files)          # path -> text on the config branch
        self.commits, self.prs, self.tokens = [], [], set()

    def install(self, monkeypatch):
        def api(method, url, token, data=None):
            self.tokens.add(token)
            if "/git/ref/heads/" in url:
                return {"object": {"sha": "sha-%d" % len(self.commits)}}
            if "/git/commits/" in url:
                return {"tree": {"sha": "tree"}}
            raise AssertionError(url)
        monkeypatch.setattr(ui, "_github_api", api)
        monkeypatch.setattr(ui, "_github_resolve_fork", lambda repo, token: repo)
        monkeypatch.setattr(ui, "_github_find_pr", lambda repo, head, token: (
            {"url": self.prs[-1], "number": len(self.prs), "state": "open"} if self.prs else {"number": 0}))
        monkeypatch.setattr(ui, "_github_create_branch", lambda *a: None)
        monkeypatch.setattr(ui.qf_pr, "github_get", lambda url, token: (
            {"content": __import__("base64").b64encode(self.files[p].encode()).decode()}
            if (p := url.split("/contents/")[1].split("?")[0]) in self.files else None))

        def tree(repo, base, files, token):
            self.pending = files
            return "tree-new"
        monkeypatch.setattr(ui, "_github_create_tree", tree)

        def commit(repo, message, tree_sha, parent, token):
            self.commits.append(message)
            for f in self.pending:
                self.files[f["path"]] = f["content"]
            return "commit-%d" % len(self.commits)
        monkeypatch.setattr(ui, "_github_create_commit", commit)
        monkeypatch.setattr(ui, "_github_update_ref", lambda *a: None)

        def create_pr(repo, head, base, title, body, token):
            assert (repo, head, base) == ("my-org/qualityflow", "qualityflow/config-example", "team")
            self.prs.append("https://github.com/my-org/qualityflow/pull/7")
            return {"url": self.prs[-1], "number": 1, "state": "open"}
        monkeypatch.setattr(ui, "_github_create_pr", create_pr)


def test_with_config_in_a_repo_an_edit_opens_a_pr_and_changes_nothing_here(qf, monkeypatch):
    """A deployment whose config dir is baked into its image (QF_CONFIG_PR_REPO):
    an edit commits to the project's config PR, opened on the first edit and
    reused after; the files here are untouched until it merges and deploys."""
    monkeypatch.setenv("QF_CONFIG_PR_REPO", "my-org/qualityflow")
    monkeypatch.setenv("QF_CONFIG_PR_BRANCH", "team")
    proj_text = "# identity\n" + (qf["proj"] / "project.yaml").read_text()
    gh = FakeGitHub({"config/projects/example/project.yaml": proj_text,
                     "config/projects/example/repositories.yaml": (qf["proj"] / "repositories.yaml").read_text()})
    gh.install(monkeypatch)
    before = {p.name: p.read_text() for p in qf["proj"].glob("*.yaml")}
    hdr = {**HDR, "X-GitHub-Token": "ghp_editor"}

    r = client.put("/api/projects/example/config", headers=hdr,
                   json={"file": "project.yaml", "key": "description", "value": "From the dashboard"})
    assert r.status_code == 200, r.text
    assert r.json()["config_pr"] == {"url": "https://github.com/my-org/qualityflow/pull/7", "number": 1}
    committed = gh.files["config/projects/example/project.yaml"]
    assert committed.startswith("# identity\n")  # the file's comments are kept
    assert yaml.safe_load(committed)["description"] == "From the dashboard"
    assert "description" in gh.commits[0] and gh.tokens == {"ghp_editor"}

    r = client.put("/api/projects/example/toggles", headers=hdr, json={"feature_toggles": {"lsp_analysis": False}})
    assert r.status_code == 200 and r.json()["config_pr"]["number"] == 1  # the same PR collects it
    assert yaml.safe_load(gh.files["config/projects/example/project.yaml"])["feature_toggles"]["lsp_analysis"] is False
    assert len(gh.prs) == 1 and len(gh.commits) == 2
    assert {p.name: p.read_text() for p in qf["proj"].glob("*.yaml")} == before  # nothing changed here

    view = client.get("/api/projects/example/config?ticket=").json()
    assert view["edits_via"] == {"repo": "my-org/qualityflow", "branch": "team"}
    r = client.post("/api/projects", headers=hdr, json={"project_id": "newproj", "display_name": "New"})
    assert r.status_code == 409 and "my-org/qualityflow" in r.json()["detail"]
    monkeypatch.setattr(ui, "_GITHUB_TOKEN", "")
    monkeypatch.setattr(ui, "_members_isolated", lambda: False)
    r = client.put("/api/projects/example/config", headers=HDR,
                   json={"file": "project.yaml", "key": "description", "value": "No token"})
    assert r.status_code == 400 and "GitHub token" in r.json()["detail"]
