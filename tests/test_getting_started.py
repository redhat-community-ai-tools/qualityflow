"""getting-started.py LSP step: lsp_analysis is on by default, so a missing
language server is installed when its installer exists, and the exact command
is printed when it does not."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "getting_started", Path(__file__).resolve().parent.parent / "getting-started.py")
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)


def test_lsp_setup_installs_with_installer_and_prints_command_without(monkeypatch, capsys):
    ran = []
    installed = set()

    def fake_run(cmd, *a, **k):
        ran.append(cmd)
        installed.add("gopls")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(gs.shutil, "which",
                        lambda name: f"/bin/{name}" if name == "go" or name in installed else None)
    monkeypatch.setattr(gs.subprocess, "run", fake_run)

    gs.run_lsp_setup({"gopls": True, "pyright-langserver": True}, yes=True)

    out = capsys.readouterr().out
    assert ran == [["go", "install", "golang.org/x/tools/gopls@latest"]]
    assert "gopls installed" in out
    assert "needs `npm` first, then run: npm install -g pyright" in out


def test_lsp_setup_silent_when_nothing_missing(capsys):
    gs.run_lsp_setup({"gopls": False, "pyright-langserver": False}, yes=True)
    assert capsys.readouterr().out == ""


def test_enmaas_codex_migration_backs_up_and_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "ENMAAS_DIR", tmp_path / "enmaas")
    monkeypatch.setattr(gs, "ENMAAS_KEY_FILE", tmp_path / "enmaas" / "key")
    monkeypatch.setattr(gs, "ENMAAS_MANIFEST", tmp_path / "enmaas" / "qf-migration.json")
    import pipeline_runner
    monkeypatch.setattr(pipeline_runner.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": json.dumps(
        {"models": [{"slug": "gpt-5.5", "apply_patch_tool_type": "freeform", "tool_mode": "x"}]})})())
    codex = tmp_path / ".codex"
    codex.mkdir()
    original = 'model = "gpt-5.6-luna"\n'
    (codex / "config.toml").write_text(original)

    gs.migrate_codex_to_enmaas(codex)

    config = (codex / "config.toml").read_text()
    assert config.startswith(original) and 'env_key = "ENMAAS_KEY"' in config
    assert 'model_provider = "enmaas"' in (codex / "enmaas.config.toml").read_text()
    hosted = [m for m in json.loads((codex / "enmaas-models.json").read_text())["models"]
              if m["slug"].startswith("rits/")]
    assert len(hosted) == 2 and {m["apply_patch_tool_type"] for m in hosted} == {None}

    gs.rollback_enmaas()
    assert sorted(p.name for p in codex.iterdir()) == ["config.toml"]
    assert (codex / "config.toml").read_text() == original
