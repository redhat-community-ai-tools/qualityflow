"""Repo config layers: .qualityflow/ in the repo checkouts (issue #198).

Each test runs the real resolver on a copy of config/ (the QF_CONFIG_DIR-style
pattern of test_config_validate.py: resolve.py reads the config/ two levels
above itself) whose example project has three repo checkouts under tmp_path.
Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_config_layers.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "config"))
from merge import merge  # noqa: E402

SLOTS = {"primary_repo": "SOURCE_REPO_PATH", "tier2_repo": "TESTS_REPO_PATH", "design_docs_repo": "DOCS_REPO_PATH"}


def copy_qf(dst):
    shutil.copytree(REPO / "config", dst / "config")
    resolver = dst / "skills/project-resolver/resolve.py"
    resolver.parent.mkdir(parents=True)
    shutil.copy(REPO / "skills/project-resolver/resolve.py", resolver)
    return dst


@pytest.fixture
def qf(tmp_path):
    """A QualityFlow copy whose example project has a primary, tier2 and
    design-docs repo, each with an (empty) checkout under tmp_path."""
    root = copy_qf(tmp_path / "qf")
    repos = {slot: {"name": "my-" + slot.removesuffix("_repo").replace("_", "-"), "org": "my-org",
                    "local_path_env": env} for slot, env in SLOTS.items()}
    for slot in SLOTS:
        (tmp_path / slot).mkdir()
    (root / "config/projects/example/repositories.yaml").write_text(yaml.safe_dump(repos))
    return root


def env(tmp_path):
    clean = {k: v for k, v in os.environ.items() if not k.endswith("_REPO_PATH")}
    return {**clean, **{var: str(tmp_path / slot) for slot, var in SLOTS.items()}}


def resolve(root, *args, environ=None):
    return subprocess.run([sys.executable, str(root / "skills/project-resolver/resolve.py"), "MYPROJ-1", *args],
                          capture_output=True, text=True, cwd=root, env=environ)


def context(root, tmp_path, *args):
    out = resolve(root, *args, environ=env(tmp_path))
    assert out.returncode == 0, out.stderr
    return yaml.safe_load(out.stdout)["project_context"], out.stderr


def layer(d, project=None, files=None, project_id="example", version=1):
    qf = d / ".qualityflow"
    qf.mkdir(parents=True, exist_ok=True)
    (qf / "project.yaml").write_text(yaml.safe_dump({"version": version, "project_id": project_id, **(project or {})}))
    for rel, data in (files or {}).items():
        (qf / rel).parent.mkdir(parents=True, exist_ok=True)
        (qf / rel).write_text(data if isinstance(data, str) else yaml.safe_dump(data))
    return qf


def edit_central(root, name, change):
    path = root / "config/projects/example" / name
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ------------------------------------------------------------- merge engine

def test_merge_semantics():
    base = {"a": {"x": 1, "y": 2}, "s": "old", "l": [1, 2], "gone": {"k": 1},
            "by_id": [{"id": "p", "v": 1, "keep": True}, {"id": "q", "v": 2}],
            "by_name": [{"name": "a", "v": 1}]}
    over = {"a": {"y": 3, "z": {"deep": True}}, "s": "new", "l": [9], "gone": None,
            "by_id": [{"id": "q", "v": 5}, {"id": "r", "v": 6}], "by_name": [{"name": "b", "v": 2}],
            "app": {"merge": "append", "value": [3]}}
    assert merge(base, over) == {
        "a": {"x": 1, "y": 3, "z": {"deep": True}}, "s": "new", "l": [9],
        "by_id": [{"id": "p", "v": 1, "keep": True}, {"id": "q", "v": 5}, {"id": "r", "v": 6}],
        "by_name": [{"name": "a", "v": 1}, {"name": "b", "v": 2}], "app": [3]}
    assert base["a"] == {"x": 1, "y": 2}, "merge must not modify its input"
    assert merge({"l": [1]}, {"l": {"merge": "append", "value": [2]}}) == {"l": [1, 2]}
    assert merge({"t": [{"id": "a"}]}, {"t": {"merge": "replace", "value": [{"id": "b"}]}}) == {"t": [{"id": "b"}]}
    assert merge({"t": [{"id": "a"}, "x"]}, {"t": [{"id": "a", "v": 1}]}) == {"t": [{"id": "a", "v": 1}]}
    with pytest.raises(ValueError, match="merge directive"):
        merge({}, {"l": {"merge": "prepend", "value": [1]}})


# ------------------------------------------------------- backward compat

def test_no_qualityflow_is_unchanged(tmp_path):
    """No .qualityflow/ anywhere: the context is byte-identical to the one the
    resolver printed before repo config layers existed (golden file), with or
    without checkouts, and nothing is written under outputs/."""
    root = copy_qf(tmp_path / "qf")
    golden = (REPO / "tests/golden/example_project_context.yaml").read_text()
    clean = {k: v for k, v in os.environ.items() if not k.endswith("_REPO_PATH")}
    out = resolve(root, environ=clean)
    assert out.returncode == 0, out.stderr
    assert out.stdout == golden
    (tmp_path / "checkout").mkdir()
    out = resolve(root, "--target", str(tmp_path / "checkout"),
                  environ={**clean, "SOURCE_REPO_PATH": str(tmp_path / "checkout")})
    assert out.stdout == golden and out.stderr == ""
    assert not (root / "outputs").exists()


# ---------------------------------------------------------------- precedence

def test_deepest_dir_wins_and_repo_root_beats_central(qf, tmp_path):
    tests = tmp_path / "tier2_repo"
    layer(tests, {"feature_toggles": {"lsp_analysis": False}, "versioning": {"product_name": "Root"},
                  "stp_document": {"header": "Root plan"}},
          {"components.yaml": {"component_package_map": {"api": {"package_path": "tests/api/"}}},
           "templates/stp/stp-template.md": "# repo template\n"})
    layer(tests / "tests", {"versioning": {"product_name": "Tests"}})
    layer(tests / "tests/e2e", {"versioning": {"product_name": "E2E", "platform_name": "K8s"}})

    ctx, err = context(qf, tmp_path, "--target", str(tests / "tests/e2e/test_new.py"))
    assert ctx["versioning"] == {"product_name": "E2E", "platform_name": "K8s", "current_version": "N/A"}
    assert ctx["feature_toggles"]["lsp_analysis"] is False
    assert ctx["stp_header"] == "Root plan"
    assert [layer["id"] for layer in ctx["config_layers"]] == [
        "my-tier2:tests/e2e", "my-tier2:tests", "my-tier2:.", "central"]
    assert ctx["config_provenance"]["project.yaml:versioning.product_name"] == "my-tier2:tests/e2e"
    assert ctx["config_provenance"]["project.yaml:feature_toggles.lsp_analysis"] == "my-tier2:."
    assert ctx["config_provenance"]["templates/stp/stp-template.md"] == "my-tier2:."
    assert "config: project.yaml:versioning.product_name from my-tier2:tests/e2e" in err

    # Downstream agents read config_dir: the merged files are there.
    assert ctx["config_dir"] == "outputs/MYPROJ-1/config/example"
    merged = qf / ctx["config_dir"]
    components = yaml.safe_load((merged / "components.yaml").read_text())
    assert components["component_package_map"]["api"] == {
        "package_path": "tests/api/",
        "features": [{"name": "REST API", "path": "pkg/api/handlers/"},
                     {"name": "Authentication", "path": "pkg/api/auth/"}]}
    assert "core" in components["component_package_map"]  # central keys the layer did not touch
    assert (merged / "templates/stp/stp-template.md").read_text() == "# repo template\n"
    assert (merged / "jira.yaml").read_text() == (qf / "config/projects/example/jira.yaml").read_text()

    # Every .qualityflow/ above the target applies, the deeper one winning.
    ctx, _ = context(qf, tmp_path, "--target", str(tests / "tests/unit"))
    assert ctx["versioning"]["product_name"] == "Tests"
    ctx, _ = context(qf, tmp_path)  # no target: repo roots only
    assert ctx["versioning"]["product_name"] == "Root"
    # Several targets: their deepest common directory.
    ctx, _ = context(qf, tmp_path, "--target", str(tests / "tests/e2e/a.py"), "--target", str(tests / "tests/e2e/b/c.py"))
    assert ctx["versioning"]["product_name"] == "E2E"
    # <repo>:<path> names the checkout by repo slot, type or name.
    assert context(qf, tmp_path, "--target", "tier2_repo:tests/e2e/x.py")[0]["versioning"]["product_name"] == "E2E"
    assert context(qf, tmp_path, "--target", "my-tier2:tests/unit")[0]["versioning"]["product_name"] == "Tests"
    assert context(qf, tmp_path, "--target", "no-such-repo:tests/e2e")[0]["versioning"]["product_name"] == "Root"


def test_repo_roots_follow_config_sources(qf, tmp_path):
    layer(tmp_path / "primary_repo", {"stp_document": {"header": "Primary"}})
    layer(tmp_path / "tier2_repo", {"stp_document": {"header": "Tests"}})
    layer(tmp_path / "tier2_repo/tests", {"stp_document": {"header": "Nested"}})
    target = str(tmp_path / "tier2_repo/tests/x.py")

    assert context(qf, tmp_path)[0]["stp_header"] == "Primary"  # default order: primary first
    # The target's repo root beats the other repo roots.
    assert [x["id"] for x in context(qf, tmp_path, "--target", str(tmp_path / "tier2_repo"))[0]["config_layers"]] == [
        "my-tier2:.", "my-primary:.", "central"]

    def sources(value):
        edit_central(qf, "repositories.yaml", lambda d: d.update(config_sources=value))

    sources({"order": ["tier2_repo", "primary_repo"]})
    assert context(qf, tmp_path)[0]["stp_header"] == "Tests"
    sources({"nested": False})
    assert context(qf, tmp_path, "--target", target)[0]["stp_header"] == "Tests"
    sources({"exclude": ["tier2_repo"]})
    assert context(qf, tmp_path, "--target", target)[0]["stp_header"] == "Primary"
    sources({"exclude": ["my-primary", "tier2"]})  # by repo name or type, like the overlay's `only`
    ctx, _ = context(qf, tmp_path)
    assert "config_layers" not in ctx and ctx["config_dir"] == "config/projects/example"


def test_null_additional_repos(qf, tmp_path):
    """A hand-written `additional_repos:` with nothing under it is null: it
    must not break resolution now that every run reads the repo list."""
    (qf / "config/projects/example/repositories.yaml").write_text(yaml.safe_dump({
        "primary_repo": {"name": "my-repo", "org": "my-org", "local_path_env": "SOURCE_REPO_PATH"},
        "additional_repos": None}))
    assert context(qf, tmp_path)[0]["config_dir"] == "config/projects/example"
    layer(tmp_path / "primary_repo", {"stp_document": {"header": "Mine"}})
    ctx, _ = context(qf, tmp_path, "--target", "primary:docs")
    assert ctx["stp_header"] == "Mine" and ctx["config_layers"][0]["id"] == "my-repo:."


def test_ticket_overlay_outranks_repo_layers(qf, tmp_path):
    """Layer 1, the ticket overlay, picks the repos: an excluded repo's
    .qualityflow/ is not read, and `paths` moves a checkout."""
    layer(tmp_path / "tier2_repo", {"stp_document": {"header": "Tests"}})
    overlay = qf / "outputs/MYPROJ-1/repositories.overlay.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("only: [primary]\n")
    ctx, _ = context(qf, tmp_path)
    assert ctx["stp_header"] == "Test Plan" and "config_layers" not in ctx
    elsewhere = tmp_path / "fork"
    layer(elsewhere, {"stp_document": {"header": "Fork"}})
    overlay.write_text(yaml.safe_dump({"paths": {"my-primary": str(elsewhere)}}))
    assert context(qf, tmp_path)[0]["stp_header"] == "Fork"


# -------------------------------------------------------------- trust boundary

def test_unknown_keys_are_errors(qf, tmp_path):
    layer(tmp_path / "tier2_repo", files={"components.yaml": {"component_pakage_map": {}}})
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1
    assert "my-tier2:./.qualityflow/components.yaml: key 'component_pakage_map' is not allowed" in out.stderr

    shutil.rmtree(tmp_path / "tier2_repo/.qualityflow")
    layer(tmp_path / "tier2_repo/tests", {"feature_toggles": {"pii_sanitisation": True}})
    out = resolve(qf, "--target", str(tmp_path / "tier2_repo/tests"), environ=env(tmp_path))
    assert out.returncode == 1 and "unknown feature toggle 'pii_sanitisation'" in out.stderr
    # A key the central file already uses is known even when the schema does not list it.
    shutil.rmtree(tmp_path / "tier2_repo/tests/.qualityflow")
    edit_central(qf, "environment.yaml", lambda d: d.update(storage={"class": "standard"}))
    layer(tmp_path / "tier2_repo", files={"environment.yaml": {"storage": {"class": "fast"}}})
    assert context(qf, tmp_path)[0]["config_provenance"] == {"environment.yaml:storage.class": "my-tier2:."}


@pytest.mark.parametrize("rel", ["jira.yaml", "github.yaml", "repositories.yaml",
                                 "polarion-migration/profile.yaml", "pii_exceptions.yaml", "notes.txt"])
def test_denied_files_are_errors(qf, tmp_path, rel):
    layer(tmp_path / "primary_repo", files={rel: {"x": 1}})
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1, out.stdout
    assert f"my-primary:./.qualityflow/{rel}: not allowed in a repo config layer" in out.stderr
    assert not (qf / "outputs/MYPROJ-1/config").exists()


def test_pii_exceptions_need_the_central_opt_in(qf, tmp_path):
    layer(tmp_path / "primary_repo", files={"pii_exceptions.yaml": {"allowed_product_names": ["MyProduct"]}})
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and "config_sources.allow_sensitive" in out.stderr
    edit_central(qf, "repositories.yaml", lambda d: d.update(config_sources={"allow_sensitive": ["pii_exceptions.yaml"]}))
    ctx, _ = context(qf, tmp_path)
    merged = yaml.safe_load((qf / ctx["config_dir"] / "pii_exceptions.yaml").read_text())
    assert merged["allowed_product_names"] == ["MyProduct"]


@pytest.mark.parametrize("key", ["display_name", "review_sla", "model_policy", "stakeholders", "approval_gates"])
def test_denied_project_keys_are_errors(qf, tmp_path, key):
    layer(tmp_path / "primary_repo", {key: {"x": 1}})
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and f"project.yaml: key {key!r} is not allowed here" in out.stderr


def test_security_toggles_only_ratchet_up(qf, tmp_path):
    layer(tmp_path / "primary_repo", {"feature_toggles": {"pii_sanitization": False, "stp_review": False,
                                                          "lsp_analysis": False}})
    ctx, err = context(qf, tmp_path)
    assert ctx["feature_toggles"]["pii_sanitization"] is True
    assert ctx["feature_toggles"]["stp_review"] is True
    assert ctx["feature_toggles"]["lsp_analysis"] is False  # not security-relevant: applies
    assert "config warning: my-primary:.: feature_toggles.pii_sanitization: False ignored" in err
    assert any("pii_sanitization" in w for w in ctx["config_layers"][0]["warnings"])
    assert "project.yaml:feature_toggles.pii_sanitization" not in ctx["config_provenance"]

    # Raising is allowed: central off, layer on.
    edit_central(qf, "project.yaml", lambda d: d["feature_toggles"].update(pii_sanitization=False))
    shutil.rmtree(tmp_path / "primary_repo/.qualityflow")
    layer(tmp_path / "primary_repo", {"feature_toggles": {"pii_sanitization": True}})
    assert context(qf, tmp_path)[0]["feature_toggles"]["pii_sanitization"] is True


def test_project_id_mismatch_is_skipped(qf, tmp_path):
    layer(tmp_path / "primary_repo", {"stp_document": {"header": "Theirs"}}, project_id="other-project")
    ctx, err = context(qf, tmp_path)
    assert ctx["stp_header"] == "Test Plan" and ctx["config_dir"] == "config/projects/example"
    assert ctx["config_layers"][0]["status"] == "skipped_mismatch"
    assert "config_hash" not in ctx and "declares project_id 'other-project'" in err


@pytest.mark.parametrize("marker", [{"version": 2, "project_id": "example"}, {"project_id": "example"},
                                    {"version": 1}, None])
def test_layer_without_identity_marker_is_an_error(qf, tmp_path, marker):
    qf_dir = layer(tmp_path / "primary_repo", files={"components.yaml": {"component_package_map": {}}})
    if marker is None:
        (qf_dir / "project.yaml").unlink()
    else:
        (qf_dir / "project.yaml").write_text(yaml.safe_dump(marker))
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and "needs project.yaml with version: 1" in out.stderr


def test_no_path_escape(qf, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "components.yaml").write_text("component_package_map: {}\n")
    qf_dir = layer(tmp_path / "primary_repo")
    (qf_dir / "components.yaml").symlink_to(outside / "components.yaml")
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and "symlinks are not allowed" in out.stderr
    shutil.rmtree(qf_dir)
    layer(outside)
    (tmp_path / "primary_repo/.qualityflow").symlink_to(outside / ".qualityflow")
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and "resolves outside the checkout" in out.stderr


def test_merged_result_is_validated(qf, tmp_path):
    layer(tmp_path / "primary_repo", {"scenario_tiers": [{"tier": "Functional", "description": "x"}]})
    out = resolve(qf, environ=env(tmp_path))
    assert out.returncode == 1 and "merged config is invalid" in out.stderr and "scenario_tiers" in out.stderr


# ---------------------------------------------------------- determinism

def test_config_hash_is_stable_and_follows_the_repo_config(qf, tmp_path):
    qf_dir = layer(tmp_path / "primary_repo", {"versioning": {"current_version": "1.0"}})
    first, _ = context(qf, tmp_path)
    again, _ = context(qf, tmp_path)
    assert first["config_hash"] == again["config_hash"] and first["config_hash"].startswith("sha256:")
    resolved = yaml.safe_load((qf / "outputs/MYPROJ-1/config.resolved.yaml").read_text())
    assert resolved["config_hash"] == first["config_hash"]
    assert resolved["files"]["project.yaml"]["versioning"] == {"current_version": "1.0"}
    (qf_dir / "project.yaml").write_text(yaml.safe_dump(
        {"version": 1, "project_id": "example", "versioning": {"current_version": "2.0"}}))
    assert context(qf, tmp_path)[0]["config_hash"] != first["config_hash"]
    # Layer removed: the next run carries no stale resolved config.
    shutil.rmtree(qf_dir)
    ctx, _ = context(qf, tmp_path)
    assert "config_hash" not in ctx
    assert not (qf / "outputs/MYPROJ-1/config.resolved.yaml").exists()
    assert not (qf / "outputs/MYPROJ-1/config").exists()


# --------------------------------------------------------------- tooling

def validate_repo(qf, checkout):
    return subprocess.run([sys.executable, str(qf / "config/validate.py"), "--repo", str(checkout)],
                          capture_output=True, text=True)


def test_validate_repo_lints_every_layer(qf, tmp_path):
    checkout = tmp_path / "tier2_repo"
    proc = validate_repo(qf, checkout)
    assert proc.returncode == 1 and "no .qualityflow/" in proc.stdout
    layer(checkout, {"feature_toggles": {"pii_sanitization": False}})
    layer(checkout / "tests/e2e", files={"tier1.yaml": {"enabled": True, "tier": "Tier 1",
                                                        "language": "python", "framework": "pytest"}})
    proc = validate_repo(qf, checkout)
    assert proc.returncode == 0, proc.stdout
    assert "PASS: tier2_repo:./.qualityflow" in proc.stdout
    assert "PASS: tier2_repo:tests/e2e/.qualityflow" in proc.stdout
    assert "warning: feature_toggles.pii_sanitization" in proc.stdout
    (checkout / "tests/e2e/.qualityflow/jira.yaml").write_text("instance: {}\n")
    proc = validate_repo(qf, checkout)
    assert proc.returncode == 1 and "tests/e2e/.qualityflow/jira.yaml: not allowed" in proc.stdout


def test_scaffold_repo_writes_a_valid_layer(qf, tmp_path):
    checkout = tmp_path / "tier2_repo"
    proc = subprocess.run([sys.executable, str(REPO / "onboard.py"), "--scaffold-repo", str(checkout),
                           "--project-id", "example"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    marker = yaml.safe_load((checkout / ".qualityflow/project.yaml").read_text())
    assert marker == {"version": 1, "project_id": "example"}
    assert (checkout / ".qualityflow/README.md").exists()
    assert validate_repo(qf, checkout).returncode == 0
    proc = subprocess.run([sys.executable, str(REPO / "onboard.py"), "--scaffold-repo", str(checkout),
                           "--project-id", "example"], capture_output=True, text=True)
    assert proc.returncode == 1 and "already exists" in proc.stdout


def test_config_sources_block_is_validated(qf, tmp_path):
    run = [sys.executable, str(qf / "config/validate.py"), str(qf / "config")]
    edit_central(qf, "repositories.yaml", lambda d: d.update(config_sources={
        "nested": "yes", "allow_sensitive": ["jira.yaml"], "order": "primary_repo"}))
    proc = subprocess.run(run, capture_output=True, text=True)
    assert proc.returncode == 1
    for msg in ("config_sources.nested must be true or false", "config_sources.order must be a list",
                "config_sources.allow_sensitive may only name pii_exceptions.yaml"):
        assert msg in proc.stdout, proc.stdout


def test_json_schema_matches_the_allowlist():
    schema = json.loads((REPO / "schemas/qualityflow.schema.json").read_text())
    rules = yaml.safe_load((REPO / "config/_schema.yaml").read_text())["config_layers"]
    defaults = yaml.safe_load((REPO / "config/_defaults.yaml").read_text())
    assert set(schema["properties"]) == set(rules["project_keys"])
    assert set(schema["properties"]["feature_toggles"]["properties"]) == set(defaults["feature_toggles"])
