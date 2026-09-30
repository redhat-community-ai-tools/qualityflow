#!/usr/bin/env python3
"""Polarion export -> std-builder scenario list (std-orchestrator Step 1B).

Turns a CSV export of Polarion test cases into
outputs/{JIRA_ID}/input/{JIRA_ID}_scenarios.yaml, keeping only the cases that
still need automating:

    Status != inactive  AND  Automation != Automated

Each case keeps its Polarion id (its stubs get @pytest.mark.polarion with it)
and links its own Jira requirement: case -> the Polarion requirement it links
-> that requirement's Jira link, read from a second export (--requirements).
One export holding both item types works too: pass the same file twice.

Usage:
    python3 skills/std-orchestrator/polarion_to_scenarios.py cases.csv \
        --requirements requirements.csv \
        --jira https://issues.redhat.com/browse/CNV-70000 \
        [--tier "Tier 2"] [--tests-repo ~/openshift-virtualization-tests] \
        [--col automation="Case Automation" ...] [-o out.yaml]

--jira is the Jira issue tracking this batch: it names the output file and is
the stubs' module-level link. --tests-repo drops cases whose id already has a
polarion("...") marker in that checkout, so they are automated in code even
though Polarion says otherwise. An Excel export has to be saved as CSV first.

Exit codes: 0 = wrote the list, 1 = no case left to write, 2 = usage / file problem.
"""

import argparse
import csv
import os
import re
import sys

import yaml

# field -> its header in the export; the first one present wins, and
# --col field=Header replaces the list.
# ponytail: Polarion's UI labels, a guess until a real export pins them.
COLUMNS = {
    "id": ("ID",),
    "title": ("Title",),
    "status": ("Status",),
    "automation": ("Automation", "Case Automation"),
    "type": ("Type",),
    "linked": ("Linked Work Items",),
    "importance": ("Importance", "Case Importance"),
    "setup": ("Setup", "Preconditions"),
    "steps": ("Test Steps", "Steps"),
    "expected": ("Expected Result", "Expected Results", "Expected"),
    "jira": ("Jira", "Jira Link", "Hyperlinks"),  # requirements export only
}
CASE_COLUMNS = ("id", "title", "status", "automation", "linked")
REQUIREMENT_COLUMNS = ("id", "jira")
PRIORITY = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P2"}
WORK_ITEM = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")
JIRA_URL = re.compile(r"https?://[^\s,;|\"'<>]+/browse/([A-Z][A-Z0-9_]*-\d+)")
POLARION_MARKER = re.compile(r"""polarion\(\s*["']([A-Z][A-Z0-9_]*-\d+)["']""")


def norm(value):
    """'Not Automated' -> 'notautomated', so labels and ids compare alike."""
    return re.sub(r"[\s_-]", "", value or "").lower()


def read_export(path, overrides, required):
    """Rows as dicts, plus the header each field was found under."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        delimiter = max(",;\t", key=f.readline().count)
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
    headers = {h.strip().lower(): h for h in reader.fieldnames or []}
    header_of = {}
    for field, names in COLUMNS.items():
        for name in (overrides[field],) if field in overrides else names:
            if name.lower() in headers:
                header_of[field] = headers[name.lower()]
                break
    missing = [f for f in required if f not in header_of]
    if missing:
        raise ValueError("%s has no %s column (use --col FIELD=HEADER); its columns: %s"
                         % (path, ", ".join(missing), ", ".join(reader.fieldnames or [])))
    return rows, header_of


def getter(row, header_of):
    return lambda field: (row.get(header_of.get(field)) or "").strip()


def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def jira_link(text, jira_base):
    """(url, key) of the first Jira link in a cell."""
    m = JIRA_URL.search(text)
    if m:
        return m.group(0), m.group(1)
    # A bare key. Never read one out of some other URL: a Polarion link
    # carries an id that looks exactly like a Jira key.
    m = WORK_ITEM.search(text) if "://" not in text else None
    return ("%s/browse/%s" % (jira_base, m.group(0)), m.group(0)) if m else (None, None)


def requirements(rows, header_of, jira_base):
    """Polarion requirement id -> (Jira url, Jira key, requirement title)."""
    reqs = {}
    for row in rows:
        get = getter(row, header_of)
        if norm(get("type")) == "testcase":
            continue
        url, key = jira_link(get("jira"), jira_base)
        if get("id") and url:
            reqs[get("id")] = (url, key, get("title"))
    return reqs


def automated_in(repo):
    """Polarion ids that already have a polarion("...") marker in a checkout."""
    ids = set()
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(root, name), encoding="utf-8", errors="replace") as f:
                    ids.update(POLARION_MARKER.findall(f.read()))
    return ids


def convert(rows, header_of, reqs, in_code=(), tier=None):
    """(scenarios, skipped): skipped maps a reason to the case ids it dropped."""
    scenarios, skipped, done = [], {}, set()
    for row in rows:
        get = getter(row, header_of)
        pid = get("id")
        if not pid or (get("type") and norm(get("type")) != "testcase"):
            continue
        url = key = summary = None
        for rid in WORK_ITEM.findall(get("linked")):
            if rid in reqs:
                url, key, summary = reqs[rid]
                break
        if norm(get("status")) == "inactive":
            reason = "inactive"
        elif norm(get("automation")) == "automated":
            reason = "automated"
        elif pid in done:
            reason = "listed twice"
        elif pid in in_code:
            reason = "already automated in code, but Polarion says it is not"
        elif not url:
            reason = "no Jira link on a linked requirement"
        else:
            reason = None
        if reason:
            skipped.setdefault(reason, []).append(pid)
            continue

        s = {"scenario_id": len(scenarios) + 1, "polarion_id": pid,
             "requirement_id": key, "jira_url": url}
        if summary:
            s["requirement_summary"] = summary
        s["tier" if tier else "test_type"] = tier or "functional"
        # ponytail: unknown importance -> P2; triage re-prioritizes anyway.
        s["priority"] = PRIORITY.get(norm(get("importance")), "P2")
        s["description"] = get("title")
        for field, column in (("preconditions", "setup"), ("steps", "steps"),
                              ("expected", "expected")):
            if lines(get(column)):
                s[field] = lines(get(column))
        scenarios.append(s)
        done.add(pid)
    return scenarios, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="?", help="CSV export of the Polarion test cases")
    ap.add_argument("--requirements", help="CSV export of the Polarion requirements "
                    "those cases link, with each requirement's Jira link")
    ap.add_argument("--jira", help="Jira issue URL tracking this batch "
                    "(https://.../browse/KEY)")
    ap.add_argument("--tier", help='tier label for every scenario, e.g. "Tier 2" '
                    "(default: test_type functional)")
    ap.add_argument("--title", default="Polarion test cases to automate")
    ap.add_argument("--tests-repo", metavar="DIR",
                    help="drop cases already carrying a polarion marker in this checkout")
    ap.add_argument("--col", action="append", default=[], metavar="FIELD=HEADER",
                    help="export header for a field; fields: %s" % ", ".join(COLUMNS))
    ap.add_argument("-o", "--out", help="default: outputs/{KEY}/input/{KEY}_scenarios.yaml")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self_test(tmp)
        return 0
    if not (args.cases and args.requirements and args.jira):
        ap.error("cases, --requirements and --jira are required")
    overrides = dict(c.split("=", 1) for c in args.col if "=" in c)
    unknown = set(overrides) - set(COLUMNS) or [c for c in args.col if "=" not in c]
    if unknown:
        ap.error("--col takes FIELD=HEADER, FIELD one of: %s" % ", ".join(COLUMNS))
    m = re.fullmatch(r"(https?://.+)/browse/([A-Z][A-Z0-9_]*-\d+)/?", args.jira)
    if not m:
        ap.error("--jira must be a Jira issue URL: https://.../browse/KEY")
    jira_base, key = m.groups()

    try:
        rows, header_of = read_export(args.cases, overrides, CASE_COLUMNS)
        req_rows, req_header_of = read_export(args.requirements, overrides,
                                              REQUIREMENT_COLUMNS)
    except (OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    in_code = automated_in(args.tests_repo) if args.tests_repo else set()
    scenarios, skipped = convert(rows, header_of,
                                 requirements(req_rows, req_header_of, jira_base),
                                 in_code, args.tier)

    for reason, ids in skipped.items():
        listed = "" if reason in ("inactive", "automated") else ": " + ", ".join(ids)
        print("skipped %d %s%s" % (len(ids), reason, listed))
    if not scenarios:
        print("no case left to migrate, nothing written")
        return 1
    out = args.out or os.path.join("outputs", key, "input", key + "_scenarios.yaml")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    doc = {
        "source": "polarion",
        "context": {
            "jira_id": key,
            "title": args.title,
            "feature_description": "Polarion test cases that are not automated yet "
                                   "(Status != inactive, Automation != Automated). Each "
                                   "keeps its Polarion id and links its own Jira requirement.",
            "jira_url": args.jira.rstrip("/"),
        },
        "scenarios": scenarios,
    }
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=1000)
    print("wrote %s: %d scenario(s)" % (out, len(scenarios)))
    return 0


def self_test(tmp):
    cases = os.path.join(tmp, "cases.csv")
    reqs = os.path.join(tmp, "reqs.csv")
    with open(cases, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Title", "Status", "Automation", "Importance",
                    "Linked Work Items", "Test Steps"])
        w.writerow(["CNV-1", "Hot-plug a disk", "Approved", "Not Automated", "Critical",
                    "verifies: CNV-100 - Disk hot-plug", "Start a VM\nHot-plug a disk"])
        w.writerow(["CNV-2", "Old flow", "Inactive", "Not Automated", "", "CNV-100", ""])
        w.writerow(["CNV-3", "Done", "Approved", "Automated", "", "CNV-100", ""])
        w.writerow(["CNV-4", "Unlinked", "Proposed", "Manual Only", "", "CNV-101", ""])
        w.writerow(["CNV-5", "In code", "Approved", "", "", "CNV-100", ""])
        w.writerow(["CNV-6", "Bare key", "approved", "notautomated", "high", "CNV-102", ""])
    # A semicolon export, as Excel writes it in some locales.
    with open(reqs, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Title", "Hyperlinks"])
        w.writerow(["CNV-100", "Disk hot-plug",
                    "https://polarion.example.com/#/workitem?id=CNV-100 "
                    "https://issues.redhat.com/browse/CNV-45678"])
        # Only a Polarion link, no Jira: its id must not be read as a Jira key.
        w.writerow(["CNV-101", "No Jira", "https://polarion.example.com/#/workitem?id=CNV-101"])
        w.writerow(["CNV-102", "Key only", "CNV-777"])
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, ".venv"))
    with open(os.path.join(repo, "test_x.py"), "w") as f:
        f.write('@pytest.mark.polarion("CNV-5")\ndef test_x(): pass\n')
    with open(os.path.join(repo, ".venv", "test_y.py"), "w") as f:
        f.write('@pytest.mark.polarion("CNV-1")\n')  # a hidden dir is not the suite

    out = os.path.join(tmp, "out", "list.yaml")
    assert main([cases, "--requirements", reqs, "--tier", "Tier 2", "--tests-repo", repo,
                 "--jira", "https://issues.redhat.com/browse/CNV-70000", "-o", out]) == 0
    with open(out, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    got = {s["polarion_id"]: s for s in doc["scenarios"]}
    assert sorted(got) == ["CNV-1", "CNV-6"], sorted(got)  # 'Not Automated' is not 'Automated'
    one = got["CNV-1"]
    assert one["jira_url"] == "https://issues.redhat.com/browse/CNV-45678"
    assert one["requirement_id"] == "CNV-45678" and one["priority"] == "P0"
    assert one["tier"] == "Tier 2" and one["steps"] == ["Start a VM", "Hot-plug a disk"]
    assert got["CNV-6"]["jira_url"] == "https://issues.redhat.com/browse/CNV-777"
    assert doc["context"]["jira_id"] == "CNV-70000"

    rows, header_of = read_export(cases, {}, CASE_COLUMNS)
    req_rows, req_header_of = read_export(reqs, {}, REQUIREMENT_COLUMNS)
    _, skipped = convert(rows, header_of,
                         requirements(req_rows, req_header_of, "https://issues.redhat.com"),
                         {"CNV-5"})
    assert skipped == {"inactive": ["CNV-2"], "automated": ["CNV-3"],
                       "no Jira link on a linked requirement": ["CNV-4"],
                       "already automated in code, but Polarion says it is not": ["CNV-5"]}, skipped

    # The list feeds std-builder, so it has to pass the scenario-list validator.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "std-reviewer"))
    import validate_std
    rep = validate_std.validate_scenarios(doc)
    assert not rep.errors, rep.errors

    # A header the export does not have is a usage error naming its columns.
    try:
        read_export(cases, {"automation": "Case Automation"}, CASE_COLUMNS)
        raise AssertionError("missing column accepted")
    except ValueError as e:
        assert "automation" in str(e) and "Linked Work Items" in str(e)
    print("self-test: OK")


if __name__ == "__main__":
    sys.exit(main())
