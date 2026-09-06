"""The image must carry every top-level module ui.py imports.

qf_metrics.py was never COPY'd into the image: every local test passed, the
Helm chart rendered, and /api/metrics/engineering returned 500 in-cluster for
months. This test derives the list from ui.py itself, so the next module gets
caught at PR time instead of on the route.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Deliberately not in the image: the chart refuses runner.enabled because the
# image ships neither pipeline_runner.py nor the `claude` CLI (see the fail()
# guard in deploy/helm/qualityflow-dashboard/templates/configmap.yaml). ui.py
# imports it lazily and only when QF_RUNNER=cli.
NOT_SHIPPED = {"pipeline_runner"}


def _top_level_modules_imported_by_ui() -> set[str]:
    src = (ROOT / "ui.py").read_text()
    names = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", src, re.M))
    return {n for n in names if (ROOT / f"{n}.py").is_file()} - NOT_SHIPPED


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
