"""A run that falls back from LSP to text search must say so in one line the
dashboard flags. Before, runs fell back silently and nobody could tell a
traced STP from a grep one."""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import

LINE = "LSP unavailable (no server for .py — npm install -g pyright) — used text search"


def test_dashboard_flags_the_lsp_unavailable_line():
    state = {"phases": {"stp": {"output": f"Phase 3 Complete\n{LINE}\n"}}}
    assert "No LSP regression analysis" in ui._detect_caveats(state)


def test_every_lsp_instruction_uses_the_flagged_wording():
    files = ["skills/lsp-tracer/SKILL.md", "agents/regression-analyzer.md",
             "agents/stp-builder.md", "agents/qualityflow.md"]
    for f in files:
        text = (ROOT / f).read_text()
        assert re.search(r"LSP unavailable \(<reason>\) — used text search", text), f
