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
"""Self-check for the value-metrics numbers the dashboard reports.

These three pinned behaviours were all real bugs that shipped, and each is the
kind that regresses silently — the endpoint keeps returning a number, it's just
the wrong one:

  1. Coverage history is newest-first (`_store_coverage` does history.insert(0)).
     The reader must take history[1] as the previous point. Taking history[0]
     subtracts the current value from itself, so every delta reads 0.
  2. The trend series must come out chronological. Slicing history[-30:] on a
     newest-first list takes the OLDEST entries and plots them backwards.
  3. Phase durations must never be negative. They fall back to file mtimes,
     which don't survive a git sync, container rebuild or volume restore.

Run: uv run python scripts/check_value_metrics.py
"""
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _totals(pct: float, hits: int, lines: int) -> dict:
    return {"coverage": pct, "files": 1, "lines": lines, "hits": hits, "misses": lines - hits}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="qf-metrics-check-"))
    outputs, config = tmp / "outputs", tmp / "config"

    # Two coverage repos in one project, so the aggregate is exercised too:
    # 40/100 and 60/100 lines -> 100/200 = 50.0% line-weighted, NOT last-wins.
    for org_repo, (cur, prev) in {
        "a/one": ((40, 100), (20, 100)),
        "b/two": ((60, 100), (40, 100)),
    }.items():
        org, repo = org_repo.split("/")
        d = outputs / "coverage" / org / repo
        cur_t = _totals(cur[0] / cur[1] * 100, *cur)
        prev_t = _totals(prev[0] / prev[1] * 100, *prev)
        _write(d / "latest.yaml", {"totals": cur_t})
        # Newest-first, exactly as _store_coverage writes it.
        _write(d / "history.yaml", [
            {"commit": "new", "timestamp": "2026-08-24T03:00:00+00:00", "totals": cur_t},
            {"commit": "old", "timestamp": "2026-08-20T03:00:00+00:00", "totals": prev_t},
        ])

    _write(config / "projects" / "demo" / "coverage.yaml", {
        "repos": [
            {"service": "github", "org": "a", "repo": "one", "type": "primary", "language": "go"},
            {"service": "github", "org": "b", "repo": "two", "type": "secondary", "language": "go"},
        ]
    })

    # A ticket whose STP mtime predates its state `created` stamp — the exact
    # shape that was emitting a negative stp_avg_hours against real data.
    jid = "DEMO-1"
    stp = outputs / jid / "stp" / f"{jid}_test_plan.md"
    stp.parent.mkdir(parents=True, exist_ok=True)
    stp.write_text("# plan\n")
    os.utime(stp, (1_700_000_000, 1_700_000_000))  # long before `created` below
    state = {
        "ticket_id": jid,
        "project_id": "demo",
        "created": "2026-08-24T03:00:00+00:00",
        "phases": {"stp": {"status": "completed"}},
    }
    _write(outputs / jid / "state" / "pipeline_state.yaml", state)

    os.environ["QF_DEV"] = "1"  # ui.py refuses to import without a key otherwise
    os.environ["QF_OUTPUTS_DIR"] = str(outputs)
    os.environ["QF_CONFIG_DIR"] = str(config)
    sys.path.insert(0, str(ROOT))
    import ui  # noqa: E402  — env must be set before import

    m = ui._compute_value_metrics("demo", [state])
    cov, durations = m["coverage"], m["phase_durations"]

    assert cov["current_pct"] == 50.0, f"line-weighted aggregate across repos: {cov['current_pct']}"
    # Previous point is 60/200 = 30.0, so the delta is +20.0. The old reader
    # produced 0.0 here because it read history[0] as the previous entry.
    assert cov["delta"] == 20.0, f"delta must compare against the PREVIOUS upload: {cov['delta']}"
    dates = [p["date"] for p in cov["trend"]]
    assert dates == sorted(dates), f"trend must be chronological: {dates}"
    assert dates == ["2026-08-20", "2026-08-24"], f"trend lost a point: {dates}"
    assert "patch_coverage_pct" not in cov, "dead always-null key is back"

    negative = {k: v for k, v in durations.items() if isinstance(v, (int, float)) and v < 0}
    assert not negative, f"phase durations must never be negative: {negative}"

    print("value-metrics self-check passed "
          f"(coverage {cov['current_pct']}%, delta {cov['delta']:+}, trend {dates})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
