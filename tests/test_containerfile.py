"""The image must carry every top-level module ui.py imports.

qf_metrics.py was never COPY'd into the image: every local test passed, the
Helm chart rendered, and /api/metrics/engineering returned 500 in-cluster for
months. This test derives the list from ui.py itself, so the next module gets
caught at PR time instead of on the route.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _top_level_modules_imported_by_ui() -> set[str]:
    src = (ROOT / "ui.py").read_text()
    names = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", src, re.M))
    return {n for n in names if (ROOT / f"{n}.py").is_file()}


def test_containerfile_copies_every_local_module_ui_imports():
    copied = " ".join(
        line for line in (ROOT / "Containerfile").read_text().splitlines()
        if line.startswith("COPY ")
    )
    missing = sorted(m for m in _top_level_modules_imported_by_ui() if f"{m}.py" not in copied)
    assert not missing, f"Containerfile does not COPY: {missing}"


def test_the_guard_actually_sees_the_known_modules():
    mods = _top_level_modules_imported_by_ui()
    assert {"qf_metrics", "review_cycle"} <= mods, mods


def test_image_installs_the_claude_cli_and_deploys_qf_resources():
    """QF_RUNNER=cli shells out to `claude -p /<command>` — the CLI binary and
    a project-scoped .claude/ (via deploy.py) both have to exist in the image,
    or every in-cluster run fails deep in a subprocess instead of at build
    time. Pinned as a build-time check since pipeline_runner.py's own guard
    (`claude` CLI not found on PATH) only fires once someone clicks Run."""
    text = (ROOT / "Containerfile").read_text()
    assert "@anthropic-ai/claude-code" in text
    assert "deploy.py" in text and "--scope project" in text
    assert "pipeline_runner.py" in text  # ui.py's `from pipeline_runner import run_phase` needs it on disk


def test_image_bakes_an_mcp_config_with_credential_placeholders():
    """.mcp.json must reference ${VAR} placeholders, not literal values — the
    literal values only ever exist per-request in pipeline_runner._env_for's
    subprocess env, never baked into the image."""
    text = (ROOT / "Containerfile").read_text()
    assert "mcp-atlassian" in text and "${JIRA_API_TOKEN}" in text
    assert "${GITHUB_PERSONAL_ACCESS_TOKEN}" in text
