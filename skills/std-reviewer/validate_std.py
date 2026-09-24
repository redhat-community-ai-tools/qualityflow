#!/usr/bin/env python3
"""QualityFlow STD mechanical validator.

Deterministic replacement for the LLM-performed count, set-difference and
grep checks in the std-reviewer skill. Validates the STD YAML, its
traceability to the source STP, and the generated stub files.

Usage:
    python3 skills/std-reviewer/validate_std.py <std_yaml> \
        [--stp <stp_file>] [--stubs DIR ...] [--priority P0] [--yaml]

The STP defaults to document_metadata.stp_reference.file and the stub dirs
to the *-tests/ directories next to the STD YAML, so the common case is
just the one positional argument.

Exit codes: 0 = no errors (warnings allowed), 1 = at least one error,
2 = usage / file problem.

NOT covered here (LLM judgment, per SKILL.md): whether an Expected is
measurable, whether Steps smuggle in verification, whether a scenario
meaningfully matches its STP row, pattern correctness, PSE wording quality.
"""

import argparse
import ast
import glob
import os
import re
import sys

import yaml

TEST_ID = re.compile(r"^TS-(?P<jira>[A-Z][A-Z0-9]*-\d+)-(?P<num>\d{3})$")
STP_REQ_ENTRY = re.compile(r"^\s*- \*\*\[([^\]]+)\]\*\*")
STP_SCENARIO = re.compile(r"^\s*- \*Test Scenario:\*")
SCENARIO_LABEL = re.compile(r"\*\*(TS-[A-Za-z0-9-]*?(\d+))\*\*")
TRAILING_NUM = re.compile(r"(\d+)\s*$")
GO_TEST_START = re.compile(r"^\s*(?:PendingIt|FIt|It|t\.Run)\s*\(", re.M)
GO_TEST_ID = re.compile(r"\[test_id:([^\]]+)\]")
PSE = ("Preconditions:", "Steps:", "Expected:")
# An STD built from a Jira ticket alone (bug fixes, smaller features) has no STP,
# and then the reference line is the Jira link instead.
REFERENCE = ("STP:", "Jira:")
PRIORITIES = {"P0", "P1", "P2"}
COVERAGE_STATUS = {"NEW", "PARTIAL_COVERAGE", "EXISTING_COVERAGE"}
TYPE_COUNT_KEYS = {"unit": "unit_count", "functional": "functional_count",
                   "integration": "integration_count", "e2e": "e2e_count"}


class Report:
    def __init__(self):
        self.checks = {}
        self.errors = []
        self.warnings = []

    def ok(self, name):
        self.checks.setdefault(name, "pass")

    def warn(self, name, msg):
        self.checks.setdefault(name, "pass")
        if self.checks[name] == "pass":
            self.checks[name] = "warn"
        self.warnings.append("[%s] %s" % (name, msg))

    def fail(self, name, msg):
        self.checks[name] = "fail"
        self.errors.append("[%s] %s" % (name, msg))


def req_ids(scenario):
    ids = scenario.get("requirement_ids") or []
    if isinstance(ids, str):
        ids = [ids]
    one = scenario.get("requirement_id")
    if one and one not in ids:
        ids = list(ids) + [one]
    return [i for i in ids if i]


# ------------------------------------------------------------------ STD YAML

def check_metadata(std, rep, base_dir):
    meta = std.get("document_metadata") or {}
    for aliases in (("jira_id", "jira_issue"), ("title", "jira_summary"),
                    ("stp_reference",)):
        if not any(meta.get(a) for a in aliases):
            rep.fail("metadata.required_fields",
                     "document_metadata.%s is missing or empty" % " / ".join(aliases))
    rep.ok("metadata.required_fields")

    ref = meta.get("stp_reference")
    ref_file = ref.get("file") if isinstance(ref, dict) else ref
    if not ref_file:
        rep.fail("metadata.stp_reference_exists",
                 "stp_reference has no file path")
    elif not resolve(ref_file, base_dir):
        rep.fail("metadata.stp_reference_exists",
                 "stp_reference.file does not exist: %s" % ref_file)
    else:
        rep.ok("metadata.stp_reference_exists")
    return meta


def check_counts(meta, scenarios, rep):
    """Every *_count in the metadata must match the scenario array."""
    actual = {"total_scenarios": len(scenarios)}
    for p in sorted(PRIORITIES):
        actual["%s_count" % p.lower()] = sum(
            1 for s in scenarios if s.get("priority") == p)
    actual["existing_coverage_count"] = sum(
        1 for s in scenarios if s.get("coverage_status") == "EXISTING_COVERAGE")
    actual["new_count"] = len(scenarios) - actual["existing_coverage_count"]

    types = [str(s.get("test_type", "")).strip().lower() for s in scenarios]
    if all(t in TYPE_COUNT_KEYS for t in types):
        for t, key in TYPE_COUNT_KEYS.items():
            actual[key] = types.count(t)
    elif any(meta.get(k) is not None for k in TYPE_COUNT_KEYS.values()):
        rep.warn("metadata.counts_match",
                 "unrecognized test_type values %s — per-type counts not verified"
                 % sorted(set(types) - set(TYPE_COUNT_KEYS)))

    for key, value in actual.items():
        declared = meta.get(key)
        if declared is not None and declared != value:
            rep.fail("metadata.counts_match",
                     "%s declares %s, scenarios contain %d" % (key, declared, value))

    tier_counts = meta.get("tier_counts")
    if isinstance(tier_counts, dict) and tier_counts:
        for tier, declared in tier_counts.items():
            value = sum(1 for s in scenarios
                        if str(s.get("tier", "")).startswith(str(tier)))
            if declared != value:
                rep.fail("metadata.counts_match",
                         "tier_counts[%s] declares %s, scenarios contain %d"
                         % (tier, declared, value))
    rep.ok("metadata.counts_match")


def check_scenarios(meta, scenarios, rep):
    if not scenarios:
        rep.fail("scenarios.present", "STD has no scenarios")
        return
    rep.ok("scenarios.present")

    jira_id = meta.get("jira_id") or meta.get("jira_issue")
    seen_test, seen_scenario = {}, {}
    for i, s in enumerate(scenarios):
        where = s.get("test_id") or s.get("scenario_id") or "scenario #%d" % (i + 1)

        for field in ("test_id", "test_type", "priority", "test_objective",
                      "test_steps", "assertions"):
            if not s.get(field):
                rep.fail("scenarios.required_fields",
                         "%s: %s is missing or empty" % (where, field))
        if not req_ids(s):
            rep.fail("scenarios.required_fields",
                     "%s: no requirement_id / requirement_ids" % where)

        tid = s.get("test_id")
        if tid:
            m = TEST_ID.match(str(tid))
            if not m:
                rep.fail("scenarios.test_id_format",
                         "%s: test_id is not TS-{JIRA}-{NNN}" % where)
            elif jira_id and m.group("jira") != jira_id:
                rep.fail("scenarios.test_id_format",
                         "%s: test_id carries %s but the STD is %s"
                         % (where, m.group("jira"), jira_id))
            if tid in seen_test:
                rep.fail("scenarios.unique_ids", "duplicate test_id %s" % tid)
            seen_test[tid] = True
        sid = s.get("scenario_id")
        if sid is not None:
            if sid in seen_scenario:
                rep.fail("scenarios.unique_ids", "duplicate scenario_id %s" % sid)
            seen_scenario[sid] = True

        if s.get("priority") not in PRIORITIES:
            rep.fail("scenarios.priority_values",
                     "%s: priority %r is not one of %s"
                     % (where, s.get("priority"), sorted(PRIORITIES)))
        cov = s.get("coverage_status")
        if cov is not None and cov not in COVERAGE_STATUS:
            rep.fail("scenarios.coverage_status_values",
                     "%s: coverage_status %r is not one of %s"
                     % (where, cov, sorted(COVERAGE_STATUS)))

        steps = s.get("test_steps") or {}
        if not (isinstance(steps, dict) and steps.get("test_execution")):
            rep.fail("scenarios.test_execution_present",
                     "%s: test_steps.test_execution is empty" % where)

    for name in ("scenarios.required_fields", "scenarios.test_id_format",
                 "scenarios.unique_ids", "scenarios.priority_values",
                 "scenarios.coverage_status_values",
                 "scenarios.test_execution_present"):
        rep.ok(name)


# --------------------------------------------------------------- STP tracing

def parse_stp(text):
    """Section III requirement ids and the count of test-scenario bullets."""
    def heading(line):
        """(level, text) for a markdown heading, else None."""
        stripped = line.strip()
        if not stripped.startswith("#"):
            return None
        level = len(stripped) - len(stripped.lstrip("#"))
        return level, stripped.lstrip("#").strip().strip("*").strip().lower()

    def is_section_iii(txt):
        return txt.startswith("section iii") or re.match(r"iii[.:) ]", txt)

    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        h = heading(line)
        if h and is_section_iii(h[1]):
            start, level = i, h[0]
            break
    if start is None:
        return None, 0
    ids, bullets, labels = [], 0, {}
    for line in lines[start + 1:]:
        h = heading(line)
        if h and h[0] <= level and not is_section_iii(h[1]):
            break
        m = STP_REQ_ENTRY.match(line)
        if m:
            ids.append(m.group(1).strip())
        elif STP_SCENARIO.match(line):
            bullets += 1
            label = SCENARIO_LABEL.search(line)
            if label:
                labels[int(label.group(2))] = label.group(1)
    return ids, bullets, labels


def scenario_number(s):
    """STP scenario number a scenario claims: stp_scenario_id, else test_id."""
    for value in (s.get("stp_scenario_id"), s.get("test_id")):
        m = TRAILING_NUM.search(str(value or ""))
        if m:
            return int(m.group(1))
    return None


def check_traceability(stp_text, scenarios, rep):
    stp_ids, bullets, labels = parse_stp(stp_text)
    if stp_ids is None:
        rep.warn("traceability.stp_requirements_covered",
                 "no Section III found in the STP — traceability not verified")
        return
    covered = {r for s in scenarios for r in req_ids(s)}

    missing = [i for i in stp_ids if i not in covered]
    if missing:
        rep.fail("traceability.stp_requirements_covered",
                 "STP requirements with no STD scenario: %s" % ", ".join(missing))
    rep.ok("traceability.stp_requirements_covered")

    orphans = sorted(covered - set(stp_ids))
    if orphans:
        rep.fail("traceability.no_orphan_scenarios",
                 "STD requirement ids absent from the STP: %s" % ", ".join(orphans))
    rep.ok("traceability.no_orphan_scenarios")

    if bullets and bullets != len(scenarios):
        rep.warn("traceability.scenario_counts",
                 "STP lists %d test scenarios, STD has %d" % (bullets, len(scenarios)))
    rep.ok("traceability.scenario_counts")

    # When the STP numbers its scenarios, the mapping is checkable row by row.
    if labels:
        claimed = {scenario_number(s) for s in scenarios} - {None}
        missing = [labels[n] for n in sorted(set(labels) - claimed)]
        if missing:
            rep.fail("traceability.stp_scenarios_covered",
                     "STP scenarios with no STD scenario: %s" % ", ".join(missing))
        unknown = sorted(claimed - set(labels))
        if unknown:
            rep.fail("traceability.stp_scenarios_covered",
                     "STD scenarios claim STP rows that do not exist: %s"
                     % ", ".join("#%d" % n for n in unknown))
        rep.ok("traceability.stp_scenarios_covered")


# --------------------------------------------------------------------- stubs

def python_stubs(path, text, rep):
    """Returns the test ids found. Flags marker, PSE and body problems."""
    name = os.path.basename(path)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        rep.fail("stubs.parse", "%s: %s" % (name, e))
        return []
    rep.ok("stubs.parse")

    module_doc = ast.get_docstring(tree) or ""
    if not any(r in module_doc for r in REFERENCE):
        rep.fail("stubs.module_reference",
                 "%s: module docstring has no STP: or Jira: line" % name)
    if "__test__ = False" not in text:
        rep.fail("stubs.collection_disabled",
                 "%s: no __test__ = False — stubs would be collected" % name)

    ids = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test"):
            continue
        where = "%s::%s" % (name, node.name)

        marked = [d for d in node.decorator_list
                  if "qf_test_id" in ast.unparse(d)]
        if not marked:
            rep.fail("stubs.qf_test_id_marker",
                     "%s: no @pytest.mark.qf_test_id decorator" % where)
        for d in marked:
            ids += re.findall(r"['\"]([^'\"]+)['\"]", ast.unparse(d))

        doc = ast.get_docstring(node) or ""
        if not doc:
            rep.fail("stubs.pse_sections", "%s: no docstring" % where)
            continue
        missing = [s for s in PSE if s not in doc]
        # A test that only exercises a precondition-free path may omit Steps,
        # but Preconditions and Expected are never optional.
        if missing:
            rep.fail("stubs.pse_sections",
                     "%s: docstring is missing %s" % (where, ", ".join(missing)))
        if not any(r in doc for r in REFERENCE):
            rep.fail("stubs.per_test_reference",
                     "%s: docstring has no STP: or Jira: line" % where)

        body = [n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))
                and not isinstance(n, ast.Pass)]
        if body:
            rep.fail("stubs.no_implementation",
                     "%s: body contains %d statement(s) beyond the docstring"
                     % (where, len(body)))

    for check in ("stubs.module_reference", "stubs.collection_disabled",
                  "stubs.qf_test_id_marker", "stubs.pse_sections",
                  "stubs.per_test_reference", "stubs.no_implementation"):
        rep.ok(check)
    return ids


def go_stubs(path, text, rep):
    name = os.path.basename(path)
    starts = [m.start() for m in GO_TEST_START.finditer(text)]
    header = text[:starts[0]] if starts else text
    if not any(r in header for r in REFERENCE):
        rep.fail("stubs.module_reference",
                 "%s: file header has no STP: or Jira: line" % name)
    if starts and "PendingIt" not in text and "Skip(" not in text:
        rep.fail("stubs.collection_disabled",
                 "%s: no PendingIt/Skip — stubs would execute" % name)

    ids = []
    bounds = starts + [len(text)]
    for i, start in enumerate(starts):
        block = text[bounds[i - 1]:start] if i else text[:start]
        call = text[start:bounds[i + 1]]
        found = GO_TEST_ID.search(call)
        where = "%s::%s" % (name, found.group(1) if found else "test #%d" % (i + 1))
        if found:
            ids.append(found.group(1))
        missing = [s for s in PSE if s not in block]
        if missing:
            rep.fail("stubs.pse_sections",
                     "%s: comment block is missing %s" % (where, ", ".join(missing)))
        if not any(r in block for r in REFERENCE):
            rep.fail("stubs.per_test_reference",
                     "%s: comment block has no STP: or Jira: line" % where)
    if starts and not ids:
        rep.warn("stubs.coverage",
                 "%s: no [test_id:...] labels — stub coverage not verified" % name)

    for check in ("stubs.module_reference", "stubs.collection_disabled",
                  "stubs.pse_sections", "stubs.per_test_reference"):
        rep.ok(check)
    return ids


def check_stubs(dirs, scenarios, rep, priority=None):
    files = []
    for d in dirs:
        files += sorted(glob.glob(os.path.join(d, "**", "*stubs*.py"), recursive=True))
        files += sorted(glob.glob(os.path.join(d, "**", "*stubs*.go"), recursive=True))
    files = [f for f in files if "__pycache__" not in f]
    if not files:
        rep.warn("stubs.present", "no stub files found in %s" % (dirs or "(none)"))
        return
    rep.ok("stubs.present")

    found = []
    for path in files:
        text = open(path, encoding="utf-8").read()
        found += (python_stubs if path.endswith(".py") else go_stubs)(path, text, rep)

    expected = {s["test_id"] for s in scenarios
                if s.get("test_id")
                and s.get("coverage_status") != "EXISTING_COVERAGE"
                and (priority is None or s.get("priority") == priority)}
    found_set = set(found)
    if len(found) != len(found_set):
        dupes = sorted({i for i in found_set if found.count(i) > 1})
        rep.fail("stubs.coverage", "test ids used by more than one stub: %s"
                 % ", ".join(dupes))
    missing = sorted(expected - found_set)
    if missing:
        rep.fail("stubs.coverage", "scenarios with no stub: %s" % ", ".join(missing))
    orphans = sorted(found_set - expected)
    if orphans:
        rep.fail("stubs.coverage", "stubs with no STD scenario: %s" % ", ".join(orphans))
    rep.ok("stubs.coverage")


# ---------------------------------------------------------------------- glue

def resolve(path, base_dir):
    """STD paths are written repo-root-relative; accept either anchor."""
    for candidate in (path, os.path.join(base_dir, path)):
        if os.path.exists(candidate):
            return candidate
    return None


def validate(std, base_dir, stp_text=None, stub_dirs=(), priority=None):
    rep = Report()
    scenarios = std.get("scenarios") or []
    meta = check_metadata(std, rep, base_dir)
    check_counts(meta, scenarios, rep)
    check_scenarios(meta, scenarios, rep)
    if stp_text is not None:
        check_traceability(stp_text, scenarios, rep)
    check_stubs(list(stub_dirs), scenarios, rep, priority)
    return rep


def render(rep, as_yaml):
    failed = sum(1 for v in rep.checks.values() if v == "fail")
    doc = {
        "validation_results": {
            "valid": failed == 0,
            "checks": {k: ("pass" if v == "pass" else v.upper())
                       for k, v in sorted(rep.checks.items())},
            "errors": rep.errors,
            "warnings": rep.warnings,
        },
        "total_checks": len(rep.checks),
        "passed": sum(1 for v in rep.checks.values() if v == "pass"),
        "failed": failed,
        "warnings": len(rep.warnings),
    }
    if as_yaml:
        yaml.safe_dump(doc, sys.stdout, default_flow_style=False, sort_keys=False)
    else:
        for k, v in sorted(rep.checks.items()):
            print("%-45s %s" % (k, "PASS" if v == "pass" else v.upper()))
        for e in rep.errors:
            print("ERROR: " + e)
        for w in rep.warnings:
            print("WARNING: " + w)
        print("total=%d passed=%d failed=%d warnings=%d"
              % (doc["total_checks"], doc["passed"], failed, len(rep.warnings)))
    return failed


# ----------------------------------------------------------------- self-test

GOOD_STUB = '''"""
Feature Tests

STP: stp.md
Jira: CNV-1
"""
import pytest


class TestFeature:
    """Tests."""
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-1-001")
    def test_one(self):
        """
        Test that one thing happens. [TS-CNV-1-001]

        STP: stp.md

        Preconditions:
            - A running thing

        Steps:
            1. Do it

        Expected:
            - It happened
        """
'''

GOOD_STP = """## Section III: Test Scenarios & Traceability

- **[REQ-1]** — A requirement.
  - *Test Scenario:* **TS-CNV-1-001**: Verify the thing — **Category:** Functional — **Priority:** P0
"""


def _std():
    return {
        "document_metadata": {
            "jira_id": "CNV-1", "title": "T",
            "stp_reference": {"file": "stp.md"},
            "total_scenarios": 1, "p0_count": 1,
        },
        "scenarios": [{
            "test_id": "TS-CNV-1-001", "requirement_id": "REQ-1",
            "test_type": "functional", "priority": "P0", "coverage_status": "NEW",
            "test_objective": {"title": "one thing"},
            "test_steps": {"test_execution": [{"action": "Do it"}]},
            "assertions": [{"description": "It happened"}],
        }],
    }


def self_test(tmp):
    os.makedirs(os.path.join(tmp, "python-tests"), exist_ok=True)
    stub = os.path.join(tmp, "python-tests", "test_feature_stubs.py")
    open(os.path.join(tmp, "stp.md"), "w").write(GOOD_STP)
    open(stub, "w").write(GOOD_STUB)
    dirs = [os.path.join(tmp, "python-tests")]

    rep = validate(_std(), tmp, GOOD_STP, dirs)
    assert not rep.errors, rep.errors
    assert rep.checks["stubs.coverage"] == "pass"

    two_rows = GOOD_STP + ("  - *Test Scenario:* **TS-CNV-1-002**: Verify the "
                           "other thing — **Category:** Functional — **Priority:** P1\n")
    rep = validate(_std(), tmp, two_rows, dirs)
    assert rep.checks["traceability.stp_scenarios_covered"] == "fail"
    assert "TS-CNV-1-002" in " ".join(rep.errors)

    bad = _std()
    bad["document_metadata"]["total_scenarios"] = 2
    assert validate(bad, tmp, GOOD_STP, dirs).checks["metadata.counts_match"] == "fail"

    bad = _std()
    bad["scenarios"][0]["test_id"] = "TS-CNV-2-001"
    rep = validate(bad, tmp, GOOD_STP, dirs)
    assert rep.checks["scenarios.test_id_format"] == "fail"
    assert rep.checks["stubs.coverage"] == "fail"   # stub now orphaned

    bad = _std()
    bad["scenarios"][0]["requirement_id"] = "REQ-NOPE"
    bad["scenarios"][0].pop("requirement_ids", None)
    rep = validate(bad, tmp, GOOD_STP, dirs)
    assert rep.checks["traceability.no_orphan_scenarios"] == "fail"
    assert rep.checks["traceability.stp_requirements_covered"] == "fail"

    open(stub, "w").write(GOOD_STUB.replace("        STP: stp.md\n\n", ""))
    rep = validate(_std(), tmp, GOOD_STP, dirs)
    assert rep.checks["stubs.per_test_reference"] == "fail"
    assert rep.checks["stubs.module_reference"] == "pass"  # header still there

    # No STP: the Jira link is the reference, and both checks still pass.
    open(stub, "w").write(GOOD_STUB.replace("STP: stp.md", "Jira: https://j/CNV-1"))
    rep = validate(_std(), tmp, GOOD_STP, dirs)
    assert rep.checks["stubs.per_test_reference"] == "pass", rep.errors
    assert rep.checks["stubs.module_reference"] == "pass"

    open(stub, "w").write(GOOD_STUB.rstrip() + "\n        assert True\n")
    assert validate(_std(), tmp, GOOD_STP, dirs).checks["stubs.no_implementation"] == "fail"

    open(stub, "w").write(GOOD_STUB.replace('    @pytest.mark.qf_test_id("TS-CNV-1-001")\n', ""))
    rep = validate(_std(), tmp, GOOD_STP, dirs)
    assert rep.checks["stubs.qf_test_id_marker"] == "fail"
    assert rep.checks["stubs.coverage"] == "fail"   # scenario now has no stub

    go = os.path.join(tmp, "go-tests")
    os.makedirs(go, exist_ok=True)
    open(os.path.join(go, "feature_stubs_test.go"), "w").write('''/*
Feature Tests

STP: stp.md
*/
var _ = Describe("x", func() {
    /*
    STP: stp.md

    Preconditions:
        - A thing
    Steps:
        1. Do it
    Expected:
        - It happened
    */
    PendingIt("[test_id:TS-CNV-1-001] should work", func() {
        Skip("Phase 1")
    })
})
''')
    rep = validate(_std(), tmp, GOOD_STP, [go])
    assert not rep.errors, rep.errors
    print("self-test: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="STD YAML file to validate")
    ap.add_argument("--stp", help="STP markdown file "
                    "(default: document_metadata.stp_reference.file)")
    ap.add_argument("--stubs", nargs="*", metavar="DIR",
                    help="stub directories (default: *-tests/ next to the STD)")
    ap.add_argument("--priority", choices=sorted(PRIORITIES),
                    help="stubs were generated with this priority filter")
    ap.add_argument("--yaml", action="store_true", help="YAML report output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self_test(tmp)
        return
    if not args.file:
        ap.error("file is required (or use --self-test)")
    try:
        std = yaml.safe_load(open(args.file, encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
    if not isinstance(std, dict):
        print("error: %s is not a YAML mapping" % args.file, file=sys.stderr)
        sys.exit(2)

    base_dir = os.path.dirname(os.path.abspath(args.file))
    stp_path = args.stp
    if stp_path is None:
        ref = (std.get("document_metadata") or {}).get("stp_reference")
        stp_path = ref.get("file") if isinstance(ref, dict) else ref
    stp_text = None
    if stp_path:
        found = resolve(stp_path, base_dir)
        if found:
            stp_text = open(found, encoding="utf-8").read()
        else:
            print("warning: STP not found at %s — traceability not checked"
                  % stp_path, file=sys.stderr)

    stub_dirs = args.stubs
    if stub_dirs is None:
        stub_dirs = sorted(d for d in glob.glob(os.path.join(base_dir, "*-tests"))
                           if os.path.isdir(d))

    failed = render(validate(std, base_dir, stp_text, stub_dirs, args.priority),
                    args.yaml)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
