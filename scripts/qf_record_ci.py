#!/usr/bin/env python3
"""Record one CI test run into outputs/{JIRA_ID}/ci/test_runs.yaml.

Parses a pytest junitxml file and appends a run record per the schema in
qf-metrics-implementation-plan.md ("CI record schema"): append-only, newest
last, capped at 50 runs (oldest dropped). stdlib xml.etree + pyyaml only.

qf_test_id per test is best-effort: read the @pytest.mark.qf_test_id(...)
decorator directly off the matching test function in
outputs/{JIRA_ID}/python-tests/{module}.py (AST-based, so decorator order
and other decorators don't matter). If that source file has no marker at all
(qf_test_id_marker: false in summary.yaml), fall back to positional mapping
against that file's `scenarios` list in summary.yaml
(scenario N -> TS-{JIRA_ID}-{N:03d}). Empty string when neither resolves.

CLI:
    python scripts/qf_record_ci.py --junit <xml> --jira-id <ID> \
        --outputs-dir outputs [--run-id X --commit Y]
    python scripts/qf_record_ci.py --scorecard --outputs-dir outputs
"""
import argparse
import ast
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import yaml

MAX_RUNS = 50


def parse_junit(xml_path):
    """Return (tests, duration_s, timestamp) from a pytest junitxml file.

    tests: [{"nodeid": "qf_foo.py::test_bar", "outcome": "passed|failed|skipped"}]
    """
    root = ET.parse(xml_path).getroot()
    # ponytail: assumes a single <testsuite> (true for one `pytest --junitxml`
    # invocation, which is how this is always called here) — aggregate across
    # multiple suites only if a caller starts merging junit files.
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    tests = []
    if suite is not None:
        for case in suite.findall("testcase"):
            classname = case.get("classname", "")
            name = case.get("name", "")
            # pytest junit classname is the dotted path <pkg...>.<module>[.<Class>].
            # Peel off a trailing Test-class component so the *module* (not the
            # class) becomes the source filename we resolve markers in.
            # ponytail: pytest convention — Test* classes are uppercase-first,
            # test_*/qf_* modules lowercase. A lowercase class or uppercase
            # module would misparse; QF generators follow the convention.
            parts = classname.split(".") if classname else []
            cls = parts.pop() if parts and parts[-1][:1].isupper() else ""
            module = parts[-1] if parts else ""
            if not module:
                nodeid = name
            elif cls:
                nodeid = f"{module}.py::{cls}::{name}"
            else:
                nodeid = f"{module}.py::{name}"
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            tests.append({"nodeid": nodeid, "outcome": outcome})
    duration_s = float(suite.get("time", 0.0)) if suite is not None else 0.0
    timestamp = suite.get("timestamp") if suite is not None else None
    return tests, duration_s, timestamp


def extract_qf_test_id_from_ast(source_text, func_name):
    """Read @pytest.mark.qf_test_id("...") off a test function's decorators."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "qf_test_id"
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    return str(dec.args[0].value)
            return ""
    return ""


def extract_qf_test_id_from_summary(summary, jira_id, module_file, func_name, source_text):
    """Fallback: no marker in source -> map by declaration order against
    summary.yaml's per-file `scenarios` list (scenario N -> TS-{JIRA}-{N:03d})."""
    entry = next((f for f in summary.get("files", []) if f.get("name") == module_file), None)
    scenarios = entry.get("scenarios") if entry else None
    if not scenarios:
        return ""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return ""
    func_order = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
    ]
    if func_name not in func_order or len(func_order) != len(scenarios):
        return ""
    return f"TS-{jira_id}-{scenarios[func_order.index(func_name)]:03d}"


def resolve_qf_test_id(outputs_dir, jira_id, nodeid, summary_cache):
    module_file, _, func_full = nodeid.partition("::")
    # func_full may be "method" or "Class::method" — take the leaf, drop any
    # parametrize suffix. ast.walk finds the method by name inside its class.
    func_name = func_full.rsplit("::", 1)[-1].split("[", 1)[0]
    src_path = Path(outputs_dir) / jira_id / "python-tests" / module_file
    if not func_name or not src_path.is_file():
        return ""
    source_text = src_path.read_text()
    qf_id = extract_qf_test_id_from_ast(source_text, func_name)
    if qf_id:
        return qf_id
    if jira_id not in summary_cache:
        summary_path = Path(outputs_dir) / jira_id / "python-tests" / "summary.yaml"
        summary_cache[jira_id] = (
            yaml.safe_load(summary_path.read_text()) if summary_path.is_file() else {}
        ) or {}
    return extract_qf_test_id_from_summary(
        summary_cache[jira_id], jira_id, module_file, func_name, source_text
    )


def _date_from_timestamp(timestamp):
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_run_record(tests, duration_s, timestamp, run_id, commit, outputs_dir, jira_id):
    summary_cache = {}
    return {
        "run_id": run_id,
        "date": _date_from_timestamp(timestamp),
        "commit": commit,
        "total": len(tests),
        "passed": sum(1 for t in tests if t["outcome"] == "passed"),
        "failed": sum(1 for t in tests if t["outcome"] == "failed"),
        "skipped": sum(1 for t in tests if t["outcome"] == "skipped"),
        "duration_s": round(duration_s, 1),
        "tests": [
            {
                "nodeid": t["nodeid"],
                "qf_test_id": resolve_qf_test_id(outputs_dir, jira_id, t["nodeid"], summary_cache),
                "outcome": t["outcome"],
            }
            for t in tests
        ],
    }


def append_run(outputs_dir, jira_id, record):
    """Append `record` into outputs/{jira_id}/ci/test_runs.yaml. Append-only,
    newest last, capped at MAX_RUNS (oldest dropped)."""
    ci_dir = Path(outputs_dir) / jira_id / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    path = ci_dir / "test_runs.yaml"
    data = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {"runs": []}
    data.setdefault("runs", []).append(record)
    data["runs"] = data["runs"][-MAX_RUNS:]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def build_scorecard_markdown(outputs_dir):
    """Per-ticket passed/failed/skipped from each latest recorded run, as the
    body of the sticky PR "QE Scorecard" comment."""
    rows = []
    for path in sorted(Path(outputs_dir).glob("*/ci/test_runs.yaml")):
        jira_id = path.parent.parent.name
        data = yaml.safe_load(path.read_text()) or {}
        runs = data.get("runs") or []
        if not runs:
            continue
        r = runs[-1]
        rows.append((jira_id, r.get("passed", 0), r.get("failed", 0), r.get("skipped", 0)))

    lines = ["<!-- qf-scorecard -->", "### QE Scorecard", ""]
    if rows:
        lines += ["| Ticket | Passed | Failed | Skipped |", "|---|---|---|---|"]
        lines += [f"| {j} | {p} | {f} | {s} |" for j, p, f, s in rows]
    else:
        lines.append("_No CI-recorded test runs yet under `outputs/*/ci/test_runs.yaml`._")
    lines += [
        "",
        "Details (per-test outcomes, trends) live in the QF dashboard — this comment is a summary only.",
    ]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--junit", help="path to a pytest --junitxml output file")
    p.add_argument("--jira-id", help="ticket id, e.g. CNV-50425")
    p.add_argument("--outputs-dir", default="outputs")
    p.add_argument("--run-id", default=None)
    p.add_argument("--commit", default="")
    p.add_argument(
        "--scorecard",
        action="store_true",
        help="print the QE Scorecard markdown across outputs/*/ci/test_runs.yaml and exit",
    )
    args = p.parse_args(argv)

    if args.scorecard:
        print(build_scorecard_markdown(args.outputs_dir))
        return 0

    if not args.junit or not args.jira_id:
        p.error("--junit and --jira-id are required unless --scorecard is given")

    run_id = args.run_id or f"local-{int(datetime.now(timezone.utc).timestamp())}"
    tests, duration_s, timestamp = parse_junit(args.junit)
    record = build_run_record(
        tests, duration_s, timestamp, run_id, args.commit, args.outputs_dir, args.jira_id
    )
    path = append_run(args.outputs_dir, args.jira_id, record)
    print(
        f"recorded {len(tests)} tests "
        f"({record['passed']} passed, {record['failed']} failed, {record['skipped']} skipped) -> {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
