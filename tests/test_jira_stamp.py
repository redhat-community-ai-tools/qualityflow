"""skills/jira-parser/stamp.py puts Jira's own text into a shortened snapshot."""
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("stamp", ROOT / "skills/jira-parser/stamp.py")
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)

JIRA = {
    "PROJ-1": {"summary": "Serve omni models", "description": "AC5: expose vllm:kv_cache_usage_perc\n...",
               "comment": {"comments": [{"author": {"displayName": "Ann"}, "created": "2026-10-01",
                                         "body": "TTS uses /v1/audio/speech, see https://github.com/o/r/pull/7"}]}},
    "PROJ-2": {"summary": "Parent", "description": "full parent text", "comment": {"comments": []}},
}


def test_stamp_restores_text_and_keeps_other_fields(tmp_path, monkeypatch):
    def fetch(key):
        if key not in JIRA:
            raise PermissionError("403")
        return JIRA[key]
    monkeypatch.setattr(stamp, "fetch", fetch)
    snap = tmp_path / "PROJ-1_jira_data.yaml"
    snap.write_text(yaml.safe_dump({
        "main_issue": {"key": "PROJ-1", "summary": "omni", "description": "one line", "status": "New"},
        "linked_issues": [{"key": "PROJ-2", "description": "short", "link_type": "clones"},
                          {"key": "OTHER-9", "description": "kept"}]}))
    assert stamp.main(str(snap)) == 0
    d = yaml.safe_load(snap.read_text())
    m = d["main_issue"]
    assert m["description"].startswith("AC5: expose vllm:kv_cache_usage_perc") and m["status"] == "New"
    assert m["comments"] == [{"author": "Ann", "created": "2026-10-01", "body": JIRA["PROJ-1"]["comment"]["comments"][0]["body"],
                              "pr_urls_found": ["https://github.com/o/r/pull/7"]}]
    assert d["linked_issues"][0] == {"key": "PROJ-2", "description": "full parent text", "link_type": "clones",
                                     "summary": "Parent"}
    assert d["linked_issues"][1]["description"] == "kept"  # unreadable: left as written
