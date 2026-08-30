"""Tests for scripts/qf_record_ci.py: junitxml parsing, schema fields, the
50-run cap, and best-effort qf_test_id resolution (AST marker + summary.yaml
positional fallback). Run: uv run --with pytest --with pyyaml pytest tests/test_qf_record_ci.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import qf_record_ci as rec  # noqa: E402


SYNTHETIC_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
<testsuite name="pytest" errors="0" failures="1" skipped="1" tests="3"
           time="1.234" timestamp="2026-08-29T10:00:00+00:00" hostname="ci">
  <testcase classname="outputs.DEMO-1.python-tests.qf_foo" name="test_alpha" time="0.01" />
  <testcase classname="outputs.DEMO-1.python-tests.qf_foo" name="test_beta" time="0.01">
    <failure message="boom">AssertionError: boom</failure>
  </testcase>
  <testcase classname="outputs.DEMO-1.python-tests.qf_foo" name="test_gamma" time="0.00">
    <skipped message="not ready"/>
  </testcase>
</testsuite>
</testsuites>
"""


def write_junit(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(SYNTHETIC_JUNIT)
    return p


def test_parse_junit_counts_and_nodeids(tmp_path):
    tests, duration_s, timestamp = rec.parse_junit(write_junit(tmp_path))
    assert len(tests) == 3
    assert tests[0] == {"nodeid": "qf_foo.py::test_alpha", "outcome": "passed"}
    assert tests[1] == {"nodeid": "qf_foo.py::test_beta", "outcome": "failed"}
    assert tests[2] == {"nodeid": "qf_foo.py::test_gamma", "outcome": "skipped"}
    assert duration_s == 1.234
    assert timestamp == "2026-08-29T10:00:00+00:00"


def test_build_run_record_matches_schema(tmp_path):
    tests, duration_s, timestamp = rec.parse_junit(write_junit(tmp_path))
    record = rec.build_run_record(
        tests, duration_s, timestamp, "gh-1234567", "abc123", str(tmp_path), "DEMO-1"
    )
    assert record["run_id"] == "gh-1234567"
    assert record["commit"] == "abc123"
    assert record["date"] == "2026-08-29T10:00:00Z"
    assert record["total"] == 3
    assert record["passed"] == 1
    assert record["failed"] == 1
    assert record["skipped"] == 1
    assert record["duration_s"] == 1.2
    assert len(record["tests"]) == 3
    for t in record["tests"]:
        assert set(t) == {"nodeid", "qf_test_id", "outcome"}
    # No source files under tmp_path/DEMO-1/python-tests -> unresolved, per spec.
    assert all(t["qf_test_id"] == "" for t in record["tests"])


def test_append_run_caps_at_50_newest_last(tmp_path):
    outputs_dir = tmp_path / "outputs"
    for i in range(50):
        rec.append_run(str(outputs_dir), "DEMO-1", {"run_id": f"r{i}", "tests": []})
    path = outputs_dir / "DEMO-1" / "ci" / "test_runs.yaml"
    runs = yaml.safe_load(path.read_text())["runs"]
    assert len(runs) == 50
    assert runs[0]["run_id"] == "r0"
    assert runs[-1]["run_id"] == "r49"

    # 51st append must drop the oldest (r0), not the newest.
    rec.append_run(str(outputs_dir), "DEMO-1", {"run_id": "r50", "tests": []})
    runs = yaml.safe_load(path.read_text())["runs"]
    assert len(runs) == 50
    assert runs[0]["run_id"] == "r1"
    assert runs[-1]["run_id"] == "r50"


def test_extract_qf_test_id_from_ast_marker_present():
    source = '''
import pytest

@pytest.mark.qf_test_id("TS-DEMO-1-001")
def test_alpha():
    assert True

def test_beta():
    assert True
'''
    assert rec.extract_qf_test_id_from_ast(source, "test_alpha") == "TS-DEMO-1-001"
    assert rec.extract_qf_test_id_from_ast(source, "test_beta") == ""
    assert rec.extract_qf_test_id_from_ast(source, "test_missing") == ""


def test_resolve_qf_test_id_prefers_ast_marker(tmp_path):
    pt_dir = tmp_path / "outputs" / "DEMO-1" / "python-tests"
    pt_dir.mkdir(parents=True)
    (pt_dir / "qf_foo.py").write_text(
        'import pytest\n\n'
        '@pytest.mark.qf_test_id("TS-DEMO-1-042")\n'
        'def test_alpha():\n'
        '    assert True\n'
    )
    qf_id = rec.resolve_qf_test_id(str(tmp_path / "outputs"), "DEMO-1", "qf_foo.py::test_alpha", {})
    assert qf_id == "TS-DEMO-1-042"


def test_resolve_qf_test_id_falls_back_to_summary_positional_mapping(tmp_path):
    pt_dir = tmp_path / "outputs" / "DEMO-1" / "python-tests"
    pt_dir.mkdir(parents=True)
    # No marker at all — mirrors qf_test_id_marker: false in summary.yaml.
    (pt_dir / "qf_foo.py").write_text(
        "def test_alpha():\n    assert True\n\n\ndef test_beta():\n    assert True\n"
    )
    (pt_dir / "summary.yaml").write_text(
        yaml.safe_dump({"files": [{"name": "qf_foo.py", "scenarios": [7, 8]}]})
    )
    outputs_dir = str(tmp_path / "outputs")
    assert rec.resolve_qf_test_id(outputs_dir, "DEMO-1", "qf_foo.py::test_alpha", {}) == "TS-DEMO-1-007"
    assert rec.resolve_qf_test_id(outputs_dir, "DEMO-1", "qf_foo.py::test_beta", {}) == "TS-DEMO-1-008"
    # Unknown test in that file/nodeid -> empty, never a guess.
    assert rec.resolve_qf_test_id(outputs_dir, "DEMO-1", "qf_foo.py::test_missing", {}) == ""


def test_build_scorecard_markdown(tmp_path):
    outputs_dir = tmp_path / "outputs"
    rec.append_run(
        str(outputs_dir), "DEMO-1",
        {"run_id": "r1", "passed": 5, "failed": 1, "skipped": 0, "tests": []},
    )
    rec.append_run(
        str(outputs_dir), "DEMO-2",
        {"run_id": "r1", "passed": 3, "failed": 0, "skipped": 2, "tests": []},
    )
    body = rec.build_scorecard_markdown(str(outputs_dir))
    assert "<!-- qf-scorecard -->" in body
    assert "### QE Scorecard" in body
    assert "| DEMO-1 | 5 | 1 | 0 |" in body
    assert "| DEMO-2 | 3 | 0 | 2 |" in body
    assert "dashboard" in body.lower()


def test_build_scorecard_markdown_empty(tmp_path):
    body = rec.build_scorecard_markdown(str(tmp_path / "outputs"))
    assert "<!-- qf-scorecard -->" in body
    assert "No CI-recorded test runs" in body


def test_main_cli_end_to_end(tmp_path):
    junit = write_junit(tmp_path)
    outputs_dir = tmp_path / "outputs"
    exit_code = rec.main([
        "--junit", str(junit),
        "--jira-id", "DEMO-1",
        "--outputs-dir", str(outputs_dir),
        "--run-id", "gh-99",
        "--commit", "deadbeef",
    ])
    assert exit_code == 0
    data = yaml.safe_load((outputs_dir / "DEMO-1" / "ci" / "test_runs.yaml").read_text())
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["run_id"] == "gh-99"
    assert run["commit"] == "deadbeef"
    assert run["total"] == 3 and run["passed"] == 1 and run["failed"] == 1 and run["skipped"] == 1
