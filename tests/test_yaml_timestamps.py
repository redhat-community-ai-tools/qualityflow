"""An agent-written state file with an unquoted timestamp must not break the
dashboard: on cnv2 one approvals.yaml line 500'd /api/activity for every ticket."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import


def test_unquoted_timestamps_stay_text(tmp_path):
    f = tmp_path / "approvals.yaml"
    f.write_text("stp_review:\n  status: approved\n  timestamp: 2026-10-08T05:45:33Z\n"
                 "  day: 2026-10-08\n  count: 3\n  ok: true\n")
    data = ui._read_yaml(f)["stp_review"]
    assert data == {"status": "approved", "timestamp": "2026-10-08T05:45:33Z",
                    "day": "2026-10-08", "count": 3, "ok": True}


def test_activity_feed_survives_an_agent_written_approval():
    jid = "TSX-1"
    state = ui._state_dir(jid)
    state.mkdir(parents=True, exist_ok=True)
    (state / "approvals.yaml").write_text(
        "stp_review:\n  status: approved\n  action: approved\n  timestamp: 2026-10-08T05:45:33Z\n")
    ui._write_approvals("TSX-2", {"stp_review": {"status": "approved", "action": "approved",
                                                 "timestamp": "2026-10-07T10:00:00+00:00"}})
    ui._activity_cache = (0.0, [])
    events = ui.activity_feed(limit=50)
    stamps = [e["timestamp"] for e in events if e["jira_id"] in ("TSX-1", "TSX-2")]
    assert stamps and all(isinstance(t, str) for t in stamps)
