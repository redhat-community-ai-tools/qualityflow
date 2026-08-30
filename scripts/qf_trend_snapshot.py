#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115",
#     "uvicorn>=0.34",
#     "pyyaml>=6.0",
#     "markdown>=3.7",
#     "bleach>=6.1",
#     "gitpython>=3.1",
#     "authlib>=1.3",
#     "httpx>=0.27",
#     "itsdangerous>=2.2",
# ]
# ///
"""Append today's trend snapshot for every project with outputs.

get_metrics() already appends a trend row (_append_trend_snapshot) as a
side effect of GET /api/metrics/{project} — but only if someone happens to
open that project's dashboard page that day. This script triggers the same
call directly, so CI/cron can keep outputs/_trends/{project}.yaml current
without depending on a page view.

Run: uv run scripts/qf_trend_snapshot.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")  # ui.py refuses to import without a key otherwise
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import


def main() -> int:
    project_ids = sorted({ui._infer_project(jid) for jid in ui._scan_jira_ids()})
    if not project_ids:
        print("qf_trend_snapshot: no projects with outputs — nothing to snapshot")
        return 0
    for pid in project_ids:
        ui.get_metrics(pid)  # side effect: appends today's row to outputs/_trends/{pid}.yaml
        print(f"qf_trend_snapshot: snapshot appended for {pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
