"""getting-started.py LSP step: lsp_analysis is on by default, so a missing
language server is installed when its installer exists, and the exact command
is printed when it does not."""
import importlib.util
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
