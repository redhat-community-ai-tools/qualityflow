"""Dashboard runs get LSP like a laptop run: the pod clones the team repos and
points each <NAME>_REPO_PATH at its checkout, and Codex runs get one
mcp-language-server per checkout (Codex has no LSP tool)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402
import ui  # noqa: E402

REPOS_YAML = """
primary_repo:
  name: tests
  org: acme
  url: https://github.com/acme/tests
  local_path_env: ACME_TESTS_REPO_PATH
  default_branch: main
additional_repos:
  - name: product
    url: https://github.com/acme/product
    local_path_env: ACME_PRODUCT_REPO_PATH
  - name: no-env
    url: https://github.com/acme/no-env
  - name: not-https
    url: git@github.com:acme/ssh.git
    local_path_env: SSH_REPO_PATH
"""


def _config(tmp_path):
    proj = tmp_path / "config" / "projects" / "acme"
    proj.mkdir(parents=True)
    (proj / "repositories.yaml").write_text(REPOS_YAML)
    return tmp_path / "config"


def test_team_repos_are_cloned_and_their_variables_set(tmp_path, monkeypatch):
    import git

    monkeypatch.setattr(ui, "CONFIG", _config(tmp_path))
    monkeypatch.setenv("QF_REPOS_DIR", str(tmp_path / "repos"))
    monkeypatch.setattr(ui, "_OPERATOR_ENV", frozenset({"ACME_PRODUCT_REPO_PATH"}))
    monkeypatch.delenv("ACME_TESTS_REPO_PATH", raising=False)
    cloned = []

    def fake_clone(url, dest, **kw):
        cloned.append((url, kw.get("branch"), kw.get("depth")))
        Path(dest, ".git").mkdir(parents=True)

    monkeypatch.setattr(git.Repo, "clone_from", staticmethod(fake_clone))
    status = ui._sync_team_repos()

    # Only https entries with a local_path_env; an operator-set variable wins.
    assert cloned == [("https://github.com/acme/tests", "main", 1)]
    assert status["repos"]["https://github.com/acme/tests"] == "ok"
    assert status["repos"]["https://github.com/acme/product"] == "operator-set"
    assert os.environ["ACME_TESTS_REPO_PATH"] == str(tmp_path / "repos" / "acme__tests")
    monkeypatch.delenv("ACME_TESTS_REPO_PATH")


def test_team_repos_off_without_repos_dir(monkeypatch):
    monkeypatch.delenv("QF_REPOS_DIR", raising=False)
    assert ui._sync_team_repos()["status"] == "off"


def test_codex_gets_one_read_only_lsp_server_per_checkout(tmp_path, monkeypatch):
    go_repo, py_repo, other = tmp_path / "go", tmp_path / "py", tmp_path / "other"
    for d in (go_repo, py_repo, other):
        d.mkdir()
    (go_repo / "go.mod").write_text("module x\n")
    (py_repo / "pyproject.toml").write_text("")
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    monkeypatch.setenv("KUBE_REPO_PATH", str(go_repo))
    monkeypatch.setenv("ACME_TESTS_REPO_PATH", str(py_repo))
    monkeypatch.setenv("DOCS_REPO_PATH", str(other))      # no language marker
    monkeypatch.setenv("GONE_REPO_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)

    args = " ".join(pipeline_runner._codex_lsp_args())
    assert 'mcp_servers.lsp_kube.args=["--workspace", "%s", "--lsp", "gopls"]' % go_repo in args
    assert ('mcp_servers.lsp_acme_tests.args=["--workspace", "%s", "--lsp", '
            '"pyright-langserver", "--", "--stdio"]' % py_repo) in args
    assert "lsp_docs" not in args and "lsp_gone" not in args
    assert "edit_file" not in args and "rename_symbol" not in args

    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: None)
    assert pipeline_runner._codex_lsp_args() == []


def test_codex_lsp_covers_the_image_languages(tmp_path, monkeypatch):
    markers = {"Cargo.toml": "rust-analyzer", "pom.xml": "jdtls",
               "tsconfig.json": "typescript-language-server", "compile_commands.json": "clangd"}
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    for i, marker in enumerate(markers):
        d = tmp_path / str(i)
        d.mkdir()
        (d / marker).write_text("")
        monkeypatch.setenv(f"R{i}_REPO_PATH", str(d))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    args = " ".join(pipeline_runner._codex_lsp_args())
    for server in markers.values():
        assert f'"--lsp", "{server}"' in args


def test_claude_gets_the_bridge_read_only(tmp_path, monkeypatch):
    import json
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module x\n")
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    monkeypatch.setenv("KUBE_REPO_PATH", str(repo))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    args = pipeline_runner._claude_lsp_args(tmp_path)
    cfg = json.loads(Path(args[0].split("=", 1)[1]).read_text())
    assert cfg["mcpServers"]["lsp_kube"]["args"] == ["--workspace", str(repo), "--lsp", "gopls"]
    assert args[1] == "--disallowedTools=mcp__lsp_kube__edit_file,mcp__lsp_kube__rename_symbol"
