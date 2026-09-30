"""Tests for deploy.py: manifest-driven pruning (never delete files this script
did not write) and symlink safety (never follow a symlink out of the source
tree). Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_deploy.py
"""
import json
import os
import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deploy  # noqa: E402

MANIFEST = ".qf-deployed.json"


def make_source(tmp_path):
    """Minimal source tree: 2 agents, 2 commands, 1 skill."""
    src = tmp_path / "src"
    (src / "agents").mkdir(parents=True)
    (src / "commands").mkdir(parents=True)
    (src / "skills" / "demo-skill").mkdir(parents=True)
    for name in ("alpha.md", "beta.md"):
        (src / "agents" / name).write_text(f"---\nname: {name}\n---\n")
    for name in ("one.md", "two.md"):
        (src / "commands" / name).write_text(f"---\nname: {name}\n---\n")
    (src / "skills" / "demo-skill" / "SKILL.md").write_text("# demo\n")
    return src


def make_home(tmp_path, monkeypatch):
    """Fake HOME with a foreign, hand-written command already in place."""
    home = tmp_path / "home"
    (home / ".claude" / "commands").mkdir(parents=True)
    (home / ".claude" / "commands" / "handwritten.md").write_text("mine, not yours\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def run(src, *extra):
    # click keeps the last --target given, so extra can override "claude".
    result = CliRunner().invoke(
        deploy.main, ["--target", "claude", "--source", str(src), *extra]
    )
    assert result.exit_code == 0, result.output
    return result.output


def test_foreign_file_survives_first_deploy(tmp_path, monkeypatch):
    src, home = make_source(tmp_path), make_home(tmp_path, monkeypatch)
    output = run(src)

    foreign = home / ".claude" / "commands" / "handwritten.md"
    assert foreign.exists(), "deploy deleted a file it never wrote"
    assert "Not pruned" in output
    assert "handwritten.md" in output.split("Not pruned")[1]

    manifest = json.loads((home / ".claude" / MANIFEST).read_text())
    assert "commands/handwritten.md" not in manifest["files"]
    assert "agents/alpha.md" in manifest["files"]


def test_manifest_driven_prune_removes_only_own_files(tmp_path, monkeypatch):
    src, home = make_source(tmp_path), make_home(tmp_path, monkeypatch)
    run(src)

    (src / "agents" / "beta.md").unlink()
    output = run(src)

    assert not (home / ".claude" / "agents" / "beta.md").exists()
    assert "beta.md" in output.split("Pruned stale files:")[1]
    assert (home / ".claude" / "commands" / "handwritten.md").exists()


def test_dry_run_writes_no_manifest_and_deletes_nothing(tmp_path, monkeypatch):
    src, home = make_source(tmp_path), make_home(tmp_path, monkeypatch)

    run(src, "--dry-run")
    assert not (home / ".claude" / MANIFEST).exists()
    assert (home / ".claude" / "commands" / "handwritten.md").exists()

    run(src)
    before = (home / ".claude" / MANIFEST).read_text()
    (src / "agents" / "beta.md").unlink()
    run(src, "--dry-run")
    assert (home / ".claude" / "agents" / "beta.md").exists()
    assert (home / ".claude" / MANIFEST).read_text() == before


def test_symlinks_are_never_followed(tmp_path, monkeypatch):
    src, home = make_source(tmp_path), make_home(tmp_path, monkeypatch)
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "id_rsa").write_text("PRIVATE KEY\n")
    (src / "skills" / "evil").symlink_to(secret, target_is_directory=True)
    (src / "skills" / "demo-skill" / "link.md").symlink_to(secret / "id_rsa")

    run(src)

    assert not (home / ".claude" / "skills" / "evil").exists()
    link = home / ".claude" / "skills" / "demo-skill" / "link.md"
    assert os.path.islink(link), "symlink inside a skill was dereferenced"


def test_codex_target_lands_skills_prompts_and_toml_agents(tmp_path, monkeypatch):
    import tomllib

    src, home = make_source(tmp_path), make_home(tmp_path, monkeypatch)
    (src / "agents" / "alpha.md").write_text(
        '---\nname: alpha\ndescription: Say "hi"\ntools: Read\nskills:\n  - x\n---\n\n# Body\n'
    )
    run(src, "--target", "codex")

    assert (home / ".agents" / "skills" / "demo-skill" / "SKILL.md").exists()
    assert (home / ".codex" / "prompts" / "one.md").exists()
    agent = tomllib.loads((home / ".codex" / "agents" / "alpha.toml").read_text())
    assert agent == {"name": "alpha", "description": 'Say "hi"',
                     "developer_instructions": "# Body\n"}
    assert "agents/beta.toml" in json.loads((home / ".codex" / MANIFEST).read_text())["files"]

    # Deleted source agent -> its stale .toml is pruned on the next run.
    (src / "agents" / "beta.md").unlink()
    run(src, "--target", "codex")
    assert not (home / ".codex" / "agents" / "beta.toml").exists()


def test_codex_project_scope_skips_prompts(tmp_path, monkeypatch):
    src, _ = make_source(tmp_path), make_home(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    output = run(src, "--target", "all", "--scope", "project", "--project-path", str(proj))

    assert (proj / ".agents" / "skills" / "demo-skill" / "SKILL.md").exists()
    assert (proj / ".codex" / "agents" / "alpha.toml").exists()
    assert not (proj / ".codex" / "prompts").exists()
    assert "commands skipped" in output
    assert (proj / ".claude" / "commands" / "one.md").exists()
    assert (proj / ".cursor" / "agents" / "alpha.md").exists()
