#!/usr/bin/env python3
"""Polarion -> openshift-virtualization-tests migration, one subcommand per stage.

SKILL.md next to this file is the runbook. A run directory (keep it under
outputs/, which git ignores) holds everything for one export: the frozen
CSVs, the case ledger, triage context and verdicts, team review sheets,
placement, packaged stubs, PR bodies and the Polarion reconciliation proposal.

    init       W0  freeze the exports and the tests-repo snapshot
    ledger     W1  one row per exported case row, holds, count reconciliation
    teams      --  freeze the owner-approved team map
    triage     W2  queue the requirement groups; merge the agent's verdicts
    review     W3  team sheets; import decisions; calibrate triage against them
    scenarios  W4  a std-builder scenario list per team (approved migrate rows)
    place      W4  where each stub goes: siblings, folder map, model, owner
    package    W4  split std-builder stubs into tests-repo modules, check them
    stage      W5  copy one team's package into a fresh tests-repo branch
    record-pr  W5  record the PR and where each stub ended up
    reconcile  W6  proposed Polarion Status and Automation per case, per team
    verify     W6  diff a fresh export against that proposal

Nothing here logs in to Polarion, Jira or GitHub, commits, or pushes.

Exit codes: 0 = done, 1 = checks failed (the output lists them),
2 = usage or file problem.
"""

import argparse
import ast
import collections
import configparser
import csv
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_VERSION = 1

# ------------------------------------------------------------------ constants

# field -> its header in the export; the first one present wins, and
# --col FIELD=HEADER replaces the list. Headers compare by norm(), so
# "Test Steps", "testSteps" and "test_steps" are one name.
# ponytail: Polarion's UI labels and Betelgeuse's field ids, a guess until the
# real export pins them.
COLUMNS = {
    "id": ("ID",),
    "type": ("Type",),
    "title": ("Title",),
    "status": ("Status",),
    "automation": ("Case Automation", "caseautomation", "Automation"),
    "linked": ("Linked Work Items",),
    "importance": ("Importance", "Case Importance", "caseimportance"),
    "setup": ("Setup", "Preconditions", "Prerequisites"),
    "steps": ("Test Steps", "Steps"),
    "expected": ("Expected Result", "Expected Results", "Expected"),
    "description": ("Description",),
    "component": ("Case Component", "Component", "casecomponent"),
    "subcomponent": ("Subcomponent", "Sub Component", "subcomponent"),
    "updated": ("Updated",),
    "hyperlinks": ("Hyperlinks",),
    "jira": ("Jira", "Jira Link", "Hyperlinks"),  # the requirements export; every one present is read
}
CASE_FIELDS = tuple(f for f in COLUMNS if f != "jira")
REQUIREMENT_FIELDS = ("id", "type", "title", "status", "jira")
CASE_REQUIRED = ("id", "title", "status", "automation", "linked")
REQUIREMENT_REQUIRED = ("id", "jira")
PSE_FIELDS = ("setup", "steps", "expected", "description")

# ponytail: Betelgeuse's values; --allow FIELD=VALUE[=MEANING] adds what a real
# export turns out to use. Anything else holds the case instead of guessing.
KNOWN = {"status": {"draft", "proposed", "approved", "needsupdate", "inactive"},
         "automation": {"automated", "notautomated", "manualonly"},
         # Work item types: a case, a requirement, or something else (a heading).
         "type": {"testcase", "requirement", "other"},
         # Link roles that make a linked work item the case's requirement. A
         # link with no role counts too.
         "role": {"verifies"}}
TYPE_ALIASES = {"heading": "other"}
PRIORITY = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P2"}

VERDICTS = ("migrate", "covered-by-implemented-test", "designed-as-stub", "retire-candidate",
            "manual-only-review", "needs-investigation")
DECISIONS = ("migrate", "link-existing", "retire", "hold")
# The decision a verdict predicts; manual-only-review predicts none.
EXPECTED_DECISION = {"migrate": "migrate", "covered-by-implemented-test": "link-existing",
                     "designed-as-stub": "link-existing", "retire-candidate": "retire",
                     "needs-investigation": "hold"}
UNCERTAINTY = ("low", "medium", "high")
# Jira resolutions that make a case a retirement *signal* for triage. Not a
# rule: implemented functionality can outlive an issue's resolution.
RETIRE_RESOLUTIONS = {"wontdo", "wontfix", "obsolete", "duplicate", "notabug", "rejected"}
JIRA_HOLDS = {"no-linked-requirement", "requirement-not-in-export", "requirement-without-jira",
              "invalid-jira-url", "bare-key-is-polarion-id", "bare-key-no-base",
              "wrong-jira-project", "ambiguous-jira"}

WORK_ITEM = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")
JIRA_URL = re.compile(r"https?://[^\s,;|\"'<>]+/browse/([A-Z][A-Z0-9_]*-\d+)")
# Red Hat's Jira, before and after its move to Atlassian Cloud: --jira-base
# rewrites links on either host to itself.
JIRA_HOSTS = {"issues.redhat.com", "redhat.atlassian.net"}
# One link per line, or per ';' / '|' / ', ' before the next link; a link
# starts with its work item ID, after an optional role ('verifies: ID' or
# 'verifies ID'), and may end with '(role)'.
LINK_SPLIT = re.compile(r"[\n;|]+|,\s*(?=(?:[A-Za-z][A-Za-z _-]*:\s*)?[A-Z][A-Z0-9_]*-\d+\b)")
LINK = re.compile(r"\s*(?:([A-Za-z][A-Za-z _-]*?)\s*(?::\s*|\s+))?([A-Z][A-Z0-9_]*-\d+)\b")
TEST_NODE = re.compile(r"^tests/\S+\.py::\w+(::\w+)*$")
SOURCE_REF = re.compile(r"^(https?://\S+|[\w.-]+(/[\w.-]+)?@[0-9a-f]{7,40}:[^\s:]+(:\d+(-\d+)?)?)$")
TEXT_ID = re.compile(r"""polarion\(\s*["']([A-Z][A-Z0-9_]*-\d+)["']""")
MARKERS_ENTRY = re.compile(r"""^\s*-\s*polarion\(\s*["']([^"']+)["']\s*\)\s*$""", re.M)
# The tests repo's post-merge mark-automated-polarion job (RedHatQE
# python-utility-scripts) matches added lines with this, for any project id.
# The job matches case-insensitively, so this does too.
LIVE_MARK = re.compile(r"pytest.mark.polarion.*?[A-Z][A-Z0-9_]*-[0-9]+", re.I)
HTML_TAG = re.compile(r"<\s*/?\s*(table|tbody|thead|tr|td|th|p|br|div|span|ul|ol|li|b|i|u|s|strong|em|a|img|"
                      r"pre|code|tt|h[1-6]|sup|sub|font|hr|style|script|blockquote|strike)\b[^>]*>", re.I)
LIVE_KINDS = ("decorator", "param", "pytestmark", "other", "unparsed")
BUILTIN_MARKS = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}
SKIP_DIRS = {"__pycache__", "node_modules", "venv", "site-packages"}


class Problem(Exception):
    """A usage or input problem: main prints it and exits 2."""


class Failed(Exception):
    """Checks failed: main prints every error and exits 1."""

    def __init__(self, errors):
        super().__init__("%d problem(s)" % len(errors))
        self.errors = errors


# -------------------------------------------------------------------- helpers

def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(value):
    """'Not Automated' -> 'notautomated', so labels and ids compare alike."""
    return re.sub(r"[\s_'-]", "", value or "").lower()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    """Atomic, so a crash never leaves half a ledger."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def write_csv(path, columns, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in columns})


def git(repo, *args):
    """stdout of a git command in repo, or None when it fails."""
    try:
        out = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                             text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def repo_snapshot(path, required=True):
    head = git(path, "rev-parse", "HEAD")
    if head is None:
        if required:
            raise Problem("%s is not a git checkout" % path)
        return {"path": os.path.abspath(path), "commit": None}
    return {"path": os.path.abspath(path), "commit": head,
            "branch": git(path, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(git(path, "status", "--porcelain")),
            "origin_main": git(path, "rev-parse", "--verify", "-q", "origin/main"),
            "remote": git(path, "remote", "get-url", "origin")}


def rel_path(path):
    """A tests-repo folder or file path: relative, normalised, under tests/."""
    p = os.path.normpath(str(path or "")).replace("\\", "/")
    if os.path.isabs(p) or p == ".." or p.startswith("../") or not (p == "tests" or p.startswith("tests/")):
        return None
    return p


def under(path, roots):
    return any(path == r or path.startswith(r + "/") for r in roots)


def parse_pairs(values, allowed, flag):
    out = {}
    for v in values:
        field, sep, value = v.partition("=")
        if not sep or field not in allowed or not value:
            raise Problem("%s takes FIELD=VALUE, FIELD one of: %s" % (flag, ", ".join(allowed)))
        out.setdefault(field, []).append(value)
    return out


def parse_allow(values):
    """--allow FIELD=VALUE[=MEANING] -> (known values, aliases), per field, all norm()ed.

    VALUE becomes known. MEANING maps it to a built-in value, which is how an
    export's own label for inactive, Automated or a test case is declared:
    `--allow "automation=Automated (CI)=automated"`. A bare VALUE that looks
    inactive or Automated is refused: it would make an excluded case eligible.
    A bare type is a work item that is not a test case; a bare role counts as
    a requirement link.
    """
    known = {f: set(v) for f, v in KNOWN.items()}
    alias = {f: {} for f in KNOWN}
    alias["type"].update(TYPE_ALIASES)
    for field, items in parse_pairs(values, KNOWN, "--allow").items():
        for item in items:
            value, sep, meaning = item.rpartition("=")
            if not sep:
                value, meaning = item, ""
            key, meaning = norm(value), norm(meaning)
            if meaning:
                if meaning not in KNOWN[field]:
                    raise Problem("--allow %s=%s: the meaning must be one of %s"
                                  % (field, item, ", ".join(sorted(KNOWN[field]))))
                alias[field][key] = meaning
            elif (field == "status" and "inactive" in key) or (
                    field == "automation" and "automated" in key and key != "notautomated"):
                word = "inactive" if field == "status" else "automated"
                raise Problem('--allow %s=%s looks like %s: say what it means, e.g. --allow "%s=%s=%s"'
                              % (field, value, word, field, value, word))
            elif field == "type":
                alias["type"][key] = "other"
            known[field].add(key)
    return known, alias


def canon(field, value, alias):
    """A value's built-in meaning: 'Not Automated' -> 'notautomated', or an --allow alias."""
    v = norm(value)
    return alias[field].get(v, v)


# ------------------------------------------------------------------- run dir

def run_file(run, *parts):
    return os.path.join(run, *parts)


def load_manifest(run):
    path = run_file(run, "manifest.json")
    if not os.path.exists(path):
        raise Problem("%s has no manifest.json: run `init` first" % run)
    return load_json(path)


def load_ledger(run):
    path = run_file(run, "ledger.json")
    if not os.path.exists(path):
        raise Problem("%s has no ledger.json: run `ledger` first" % run)
    return load_json(path)


LEDGER_CSV = ("row", "polarion_id", "state", "holds", "flags", "title", "status", "automation",
              "jira_url", "requirements", "existing", "team", "verdict", "decision", "folder",
              "pr", "proposed_status", "proposed_automation", "ready")


def save_ledger(run, ledger):
    save_json(run_file(run, "ledger.json"), ledger)
    flat = []
    for r in ledger["rows"]:
        src = r.get("source", {})
        cleanup = r.get("cleanup") or {}
        flat.append({
            "row": r["row"], "polarion_id": r["polarion_id"], "state": r["state"],
            "holds": " ".join(r["holds"]), "flags": " ".join(r["flags"]),
            "title": src.get("title", ""), "status": src.get("status", ""),
            "automation": src.get("automation", ""), "jira_url": r.get("jira_url") or "",
            "requirements": " ".join(x["id"] for x in r.get("requirements", [])),
            "existing": "; ".join(fmt_occ(o) for o in r.get("existing", [])),
            "team": r.get("team") or "", "verdict": (r.get("triage") or {}).get("verdict", ""),
            "decision": (r.get("decision") or {}).get("decision", ""),
            "folder": (r.get("placement") or {}).get("folder", ""),
            "pr": (r.get("pr") or {}).get("url", ""),
            "proposed_status": cleanup.get("proposed_status", ""),
            "proposed_automation": cleanup.get("proposed_automation", ""),
            "ready": "" if "ready" not in cleanup else "yes" if cleanup["ready"] else "no",
        })
    write_csv(run_file(run, "ledger.csv"), LEDGER_CSV, flat)


def tests_repo(run, override):
    path = override or (load_manifest(run).get("tests_repo") or {}).get("path")
    if not path:
        raise Problem("no tests repo: pass --tests-repo (or give one to `init`)")
    if not os.path.isdir(os.path.join(path, "tests")):
        raise Problem("%s has no tests/ directory" % path)
    return path


def load_teams(run, required=True):
    path = run_file(run, "teams.yaml")
    if not os.path.exists(path):
        if required:
            raise Problem("%s has no teams.yaml: run `teams` with the owner-approved map" % run)
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------- CSV input

def detect_encoding(path, encoding):
    """A byte-order mark wins over --encoding: Excel saves "Unicode Text" as UTF-16."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return encoding


def read_csv(path, encoding):
    """(header, delimiter, records); a record is (number, line, cells, problem).

    Empty cells past the header's end are dropped (spreadsheet writers pad
    rows); a row with fewer cells reads the missing ones as empty, and its
    cells then have fewer keys than the header.
    """
    encoding = detect_encoding(path, encoding)
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))  # rich text can hold inline images
    try:
        with open(path, encoding=encoding, newline="") as f:
            first = f.readline()
            f.seek(0)
            delimiter = max(",;\t", key=first.count)
            reader = csv.reader(f, delimiter=delimiter)
            header = [h.strip().lstrip("﻿") for h in next(reader, [])]
            while header and not header[-1]:
                header.pop()
            if not any(header):
                raise Problem("%s has no header row" % path)
            records = []
            for cells in reader:
                if not any(c.strip() for c in cells):
                    continue
                while len(cells) > len(header) and not cells[-1].strip():
                    cells.pop()
                problem = None
                if len(cells) > len(header):
                    problem = "%d fields, the header has %d" % (len(cells), len(header))
                records.append((len(records) + 1, reader.line_num, dict(zip(header, cells)), problem))
    except UnicodeDecodeError as e:
        raise Problem("%s is not valid %s (%s): re-export as UTF-8 or pass --encoding"
                      % (path, encoding, e.reason)) from None
    except csv.Error as e:
        raise Problem("%s: malformed CSV: %s" % (path, e)) from None
    return header, delimiter, records


def map_columns(header, overrides, required, path, fields=tuple(COLUMNS)):
    """field -> the header it is found under, for the fields this file carries.

    Headers compare by norm(). An --col override for a field the file does not
    carry belongs to the other file. Fails naming the export's columns.
    """
    by_norm = {}
    for h in header:
        by_norm.setdefault(norm(h), h)
    found = {}
    for field in fields:
        for name in overrides.get(field) or COLUMNS[field]:
            if norm(name) in by_norm:
                found[field] = by_norm[norm(name)]
                break
        if field in overrides and field not in found:
            raise Problem("--col %s=%s: %s has no such column; its columns: %s"
                          % (field, overrides[field][0], path, ", ".join(header)))
    missing = [f for f in required if f not in found]
    if missing:
        raise Problem("%s has no %s column (map one with --col FIELD=HEADER); its columns: %s"
                      % (path, ", ".join(missing), ", ".join(header)))
    return found


def getter(cells, columns):
    return lambda field: (cells.get(columns.get(field)) or "").strip()


class _Text(HTMLParser):
    """Rich text -> plain text, keeping line and cell breaks.

    `rows` collects table rows as (cells, every cell a <th>). Omitted </td>,
    </tr> and </table> (valid HTML) close at the next cell or row, or at the
    end. Style and script content is dropped.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.rows, self.row, self.cell, self.skip = [], [], None, None, 0
        self.row_th = self.cell_th = False

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        elif tag in ("td", "th"):
            self.end_cell()
            if self.row is None:
                self.row, self.row_th = [], True
            self.cell, self.cell_th = [], tag == "th"
        elif tag == "tr":
            self.end_row()
            self.row, self.row_th = [], True
        elif tag in ("br", "li", "p", "div") or re.fullmatch(r"h\d", tag):
            self._put("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th"):
            self.end_cell()
        elif tag in ("tr", "table"):
            self.end_row()
        if tag in ("p", "div", "li", "ul", "ol", "table") or re.fullmatch(r"h\d", tag):
            self._put("\n")

    def handle_data(self, data):
        if not self.skip:
            self._put(data)

    def end_cell(self):
        if self.cell is not None:
            self.row.append("".join(self.cell))
            self.row_th = self.row_th and self.cell_th
            self.cell = None
            self.out.append("\t")

    def end_row(self):
        self.end_cell()
        if self.row is not None:
            self.rows.append((self.row, self.row_th and bool(self.row)))
            self.row = None
            self.out.append("\n")

    def _put(self, text):
        self.out.append(text)
        if self.cell is not None:
            self.cell.append(text)


def parse_html(text):
    p = _Text()
    p.feed(text)
    p.close()
    p.end_row()
    return "".join(p.out), p.rows


def plain(text):
    text = text or ""
    if not HTML_TAG.search(text) and HTML_TAG.search(html.unescape(text)):
        text = html.unescape(text)  # rich text exported entity-escaped
    return parse_html(text)[0] if HTML_TAG.search(text) else html.unescape(text)


LIST_MARK = re.compile(r"^\s*(?:step\s*#?\d+\s*[.):]?|#?\d+[.)]|[-*•])\s+", re.I)
STEP_NUMBER = re.compile(r"^\s*(?:step\s*#?\d+\s*[.):]?|#?\d+[.)])\s+", re.I)
EXPECTED_LINE = re.compile(r"^\s*(?:expected(?:\s+results?)?|results?)\s*:\s*(.*)$", re.I)
STEP_INDEX = re.compile(r"(?:step\s*)?#?\d+[.):]?", re.I)
TABLE_STEP = {"step", "steps", "test step", "step description", "description", "action", "actions"}
TABLE_RESULT = {"expected result", "expected results", "expected", "result", "results", "expected outcome"}
TABLE_INDEX = {"", "#", "no", "no.", "nr", "number", "step #", "step no", "step no.", "step number"}


def clean(line):
    return re.sub(r"\s+", " ", LIST_MARK.sub("", line)).strip()


def lines(text):
    """Non-empty lines, without list numbering or bullets."""
    return [x for x in map(clean, (text or "").splitlines()) if x]


def plain_steps(text):
    """(steps, expected, pairs) from steps written as text.

    When the first line is numbered ("1.", "1)", "Step 1:"), an unnumbered
    line continues the step above it. "Expected: ..." is that step's result.
    """
    raw = [x for x in text.splitlines() if x.strip()]
    numbered = bool(raw) and bool(STEP_NUMBER.match(raw[0]))
    steps, results, loose = [], [], []
    for line in raw:
        e = EXPECTED_LINE.match(line)
        if e:
            if steps:
                results[-1] = " ".join(filter(None, [results[-1], clean(e.group(1))]))
            else:
                loose.append(clean(e.group(1)))
        elif numbered and steps and not STEP_NUMBER.match(line):
            if results[-1]:
                results[-1] += " " + clean(line)
            else:
                steps[-1] += " " + clean(line)
        elif clean(line):
            steps.append(clean(line))
            results.append("")
    pairs = [{"step": s, "expected": r} for s, r in zip(steps, results)] if any(results) else []
    return steps, loose + [r for r in results if r], pairs


def split_steps(raw):
    """(steps, expected, pairs) from a Test Steps cell: an HTML table, or text.

    A header row (all <th>, or all known labels) names the table's columns;
    without one they are [index,] step, expected result. Any further column
    stays on its step as "Label: value", and text outside the table comes
    first as steps of its own. pairs keeps each row's step with its own
    expected result ("" when the row has none), so a step never borrows
    another row's result.
    """
    raw = raw or ""
    if not re.search(r"<t[rd]\b", raw, re.I) and re.search(r"&lt;\s*t[rd]\b", raw, re.I):
        raw = html.unescape(raw)  # rich text exported entity-escaped
    if not re.search(r"<t[rd]\b", raw, re.I):
        return plain_steps(plain(raw))
    outside = lines(plain(re.sub(r"(?is)<table\b.*?(?:</table\s*>|$)", "\n", raw)))
    steps, expected, pairs, heads = [], [], [], None
    for cells, th in parse_html(raw)[1]:
        cells = ["; ".join(lines(c)) for c in cells]
        labels = [c.lower().strip(" :") for c in cells]
        if any(cells) and (th or all(x in TABLE_STEP | TABLE_RESULT | TABLE_INDEX for x in labels)):
            heads = labels
            continue
        if not any(cells):
            continue
        if heads:
            si = next((i for i, h in enumerate(heads) if h in TABLE_STEP), None)
            ei = next((i for i, h in enumerate(heads) if h in TABLE_RESULT), None)
            skip = {i for i, h in enumerate(heads) if h in TABLE_INDEX}
        else:
            skip = {0} if len(cells) > 1 and STEP_INDEX.fullmatch(cells[0]) else set()
            rest = [i for i in range(len(cells)) if i not in skip]
            si, ei = rest[0], rest[1] if len(rest) > 1 else None
        if si is None:
            si = next((i for i in range(len(cells)) if i not in skip and i != ei), None)
        step = cells[si] if si is not None and si < len(cells) else ""
        result = cells[ei] if ei is not None and ei < len(cells) else ""
        extra = ["%s: %s" % ((heads[i] if heads and i < len(heads) and heads[i] else "note").capitalize(), c)
                 for i, c in enumerate(cells) if c and i not in skip | {si, ei}]
        step = "; ".join(filter(None, [step] + extra))
        if step:
            steps.append(step)
            pairs.append({"step": step, "expected": result})
        if result:
            expected.append(result)
    steps[:0] = outside
    pairs[:0] = [{"step": s, "expected": ""} for s in outside] if pairs else []
    return steps, expected, pairs


def normalize_pse(setup, steps, expected):
    """The case's own Preconditions/Steps/Expected, and which of them it lacks.

    Whatever a case lacks, std-builder has to propose, and the stub says so.
    """
    st, ex, pairs = split_steps(steps)
    ex += lines(plain(expected))
    pre = lines(plain(setup))
    missing = [name for name, have in (("preconditions", pre), ("steps", st), ("expected", ex))
               if not have]
    source = "complete" if not missing else "missing" if len(missing) == 3 else "partial"
    return {"preconditions": pre, "steps": st, "expected": ex, "step_results": pairs,
            "missing": missing, "source": source}


def parse_links(cell):
    """[(work item id, role)] from a Linked Work Items cell.

    One link per line, or per ';', '|' or ', ' before the next link, as
    'role: ID - title', 'role ID', 'ID - title (role)' or a bare ID. Only the
    ID that starts a link counts: an ID inside a title is title text. Roles
    are lower case, '_' read as a space.
    """
    out = []
    for part in LINK_SPLIT.split(plain(cell)):
        m = LINK.match(part)
        if not m:
            continue
        role = m.group(1) or ""
        if not role:
            s = re.search(r"\(([A-Za-z][A-Za-z _-]*)\)\s*$", part)
            role = s.group(1) if s else ""
        if m.group(2) not in [o[0] for o in out]:
            out.append((m.group(2), " ".join(role.lower().replace("_", " ").split())))
    return out


def parse_jira(cell, jira_base, polarion_ids):
    """(links, problem, bare): every Jira issue a requirement's cell links, or why none.

    With jira_base, a link on Red Hat's Jira (either host) is rewritten to it,
    and a link on another host is refused.
    """
    links, foreign = [], []
    base_host = urllib.parse.urlparse(jira_base).netloc.lower() if jira_base else None
    for m in JIRA_URL.finditer(cell or ""):
        url, key = m.group(0), m.group(1)
        if jira_base:
            if urllib.parse.urlparse(url).netloc.lower() not in JIRA_HOSTS | {base_host}:
                foreign.append(url)
                continue
            url = "%s/browse/%s" % (jira_base.rstrip("/"), key)
        if key not in [k for _, k in links]:
            links.append((url, key))
    if links:
        return links, None, False
    if foreign:
        return [], "invalid-jira-url", False
    if not (cell or "").strip():
        return [], "requirement-without-jira", False
    if "://" in cell:
        if re.search(r"jira|atlassian|/browse/", cell, re.I):
            return [], "invalid-jira-url", False
        return [], "requirement-without-jira", False
    keys = WORK_ITEM.findall(cell)
    if not keys:
        return [], "requirement-without-jira", False
    # A bare key. CNV's Polarion ids and Jira keys share the prefix, so never
    # take one that is also a Polarion work item in this export.
    if any(k in polarion_ids for k in keys):
        return [], "bare-key-is-polarion-id", True
    if not jira_base:
        return [], "bare-key-no-base", True
    return [("%s/browse/%s" % (jira_base.rstrip("/"), k), k) for k in keys], None, True


# ------------------------------------------------------------ tests-repo scan

def dotted(expr):
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return ".".join(reversed(parts))
    return None


def deco_name(d):
    return dotted(d.func if isinstance(d, ast.Call) else d) or ""


DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def assigns_test_false(stmt):
    """The target of `x.__test__ = False` ("x", or "Cls.test_m") / `__test__ = False` (""), else None."""
    if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is False):
        return None
    for t in stmt.targets:
        if isinstance(t, ast.Name) and t.id == "__test__":
            return ""
        if isinstance(t, ast.Attribute) and t.attr == "__test__" and dotted(t.value):
            return dotted(t.value)
    return None


def skip_mark(expr):
    """'skip' or 'xfail run=False' when a mark, or a list of marks, switches a test off."""
    for d in expr.elts if isinstance(expr, (ast.List, ast.Tuple)) else [expr]:
        name = deco_name(d)
        if name.endswith("mark.skip"):
            return "skip"
        if name.endswith("mark.xfail") and isinstance(d, ast.Call) and any(
                k.arg == "run" and isinstance(k.value, ast.Constant) and k.value.value is False
                for k in d.keywords):
            return "xfail run=False"
    return None


def pytestmark_off(body):
    """Why a module's or class's `pytestmark = ...` switches its tests off, or None."""
    for s in body:
        if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                                             for t in s.targets) and skip_mark(s.value):
            return skip_mark(s.value)
    return None


def why_off(node, parents, tree):
    """Why a test function/class/module is switched off, or None.

    ponytail: a skip inside one pytest.param(marks=...) and a __test__ = False
    inherited from a base class are not seen; the tests repo has neither.
    """
    if any(assigns_test_false(s) == "" for s in tree.body):
        return "module __test__ = False"
    if pytestmark_off(tree.body):
        return "module pytestmark " + pytestmark_off(tree.body)
    chain = []
    while isinstance(node, DEFS):
        chain.append(node)
        node = parents.get(node)
    for i, n in enumerate(chain):
        if isinstance(n, ast.ClassDef):
            if any(assigns_test_false(s) == "" for s in n.body):
                return "class __test__ = False"
            if pytestmark_off(n.body):
                return "class pytestmark " + pytestmark_off(n.body)
        # `name.__test__ = False` in an enclosing scope, by its dotted name there
        rel = n.name
        for scope in chain[i + 1:] + [tree]:
            if any(assigns_test_false(s) == rel for s in scope.body):
                return "%s __test__ = False" % ("class" if isinstance(n, ast.ClassDef) else "function")
            if isinstance(scope, ast.ClassDef):
                rel = "%s.%s" % (scope.name, rel)
        off = next(filter(None, map(skip_mark, n.decorator_list)), None)
        if off:
            return off
    return None


def body_statements(func):
    """Statements beyond a docstring, `pass` or `...`."""
    return [n for n in func.body
            if not (isinstance(n, ast.Pass) or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                                and (isinstance(n.value.value, str) or n.value.value is Ellipsis)))]


def fixture_args(func):
    return [x.arg for x in func.args.posonlyargs + func.args.args + func.args.kwonlyargs
            if x.arg not in ("self", "cls")]


def implemented(node):
    """A test with code, or one whose fixtures do the work (`def test_x(self, vm): pass`).

    A design stub has neither: the STD guide keeps fixture names out of Phase 1.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return bool(body_statements(node) or fixture_args(node))
    return any(implemented(n) for n in ast.walk(node)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))


def node_id(rel, node, parents):
    names = []
    while isinstance(node, DEFS):
        names.append(node.name)
        node = parents.get(node)
    return "::".join([rel] + list(reversed(names)))


def locate(call, parents):
    """(kind, the def/class/module the marker applies to, or None)."""
    node, kind = call, None
    while node in parents:
        parent = parents[node]
        if isinstance(parent, DEFS) and node in parent.decorator_list:
            return kind or "decorator", parent
        if kind is None and isinstance(parent, ast.Call) and deco_name(parent).endswith("param"):
            kind = "param"
        if isinstance(parent, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                                                  for t in parent.targets):
            return "pytestmark", parents.get(parent)
        if isinstance(parent, DEFS + (ast.Module,)):
            break
        node = parent
    return kind or "other", None


def scan_file(rel, text, collected=None):
    """Every polarion("ID") in one file, with where and how it is used."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [{"id": m.group(1), "path": rel, "line": text.count("\n", 0, m.start()) + 1,
                 "kind": "unparsed"} for m in TEXT_ID.finditer(text)]
    parents = parent_map(tree)
    out, call_lines = [], set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and deco_name(node).endswith("mark.polarion")
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and WORK_ITEM.fullmatch(node.args[0].value)):
            continue
        call_lines.update((node.lineno, node.args[0].lineno))
        kind, owner = locate(node, parents)
        occ = {"id": node.args[0].value, "path": rel, "line": node.args[0].lineno, "kind": kind}
        if owner is not None:
            occ["test"] = rel if isinstance(owner, ast.Module) else node_id(rel, owner, parents)
            occ["implemented"] = implemented(owner)
            off = why_off(owner, parents, tree)
            if off:
                occ["disabled"] = off
            if collected is not None:
                occ["collected"] = any(c == occ["test"] or c.startswith(occ["test"] + "::")
                                       for c in collected)
        out.append(occ)
    text_lines = text.splitlines()
    for m in TEXT_ID.finditer(text):
        n = text.count("\n", 0, m.start()) + 1
        if n in call_lines:
            continue
        line = text_lines[n - 1].strip()
        kind = ("comment" if line.startswith("#")
                else "markers-entry" if re.match(r"-\s*polarion\(", line) else "text")
        out.append({"id": m.group(1), "path": rel, "line": n, "kind": kind})
    return out


def scan_repo(repo, collected=None):
    """{polarion id: [occurrence]} for every polarion("ID") in a checkout."""
    found = {}
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "polarion" not in text:
                continue
            for occ in scan_file(os.path.relpath(path, repo).replace("\\", "/"), text, collected):
                found.setdefault(occ["id"], []).append(occ)
    return found


def read_collected(path):
    """Node ids from `pytest --collect-only -q` output, without parameters."""
    with open(path, encoding="utf-8") as f:
        return {re.sub(r"\[.*\]$", "", line.strip()) for line in f if "::" in line}


def fmt_occ(o):
    extra = [o["kind"]]
    if o.get("implemented"):
        extra.append("implemented")
    if o.get("disabled"):
        extra.append("disabled: " + o["disabled"])
    if o.get("collected") is False:
        extra.append("not collected")
    return "%s:%s (%s)" % (o["path"], o["line"], ", ".join(extra))


def implemented_evidence(occurrences):
    """Live markers on an implemented, enabled (and, if known, collected) test."""
    return [o for o in occurrences if o["kind"] in LIVE_KINDS and o.get("implemented")
            and not o.get("disabled") and o.get("collected") is not False]


# ------------------------------------------------------------------ W0: init

def describe_csv(path, encoding):
    encoding = detect_encoding(path, encoding)
    header, delimiter, records = read_csv(path, encoding)
    with open(path, "rb") as f:
        bom = f.read(3).startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"))
    return {"encoding": encoding, "bom": bom, "delimiter": delimiter, "header": header,
            "records": len(records)}


def cmd_init(a):
    run = a.run
    if os.path.exists(run_file(run, "manifest.json")):
        raise Problem("%s is already initialised: a new export gets a new run directory" % run)
    top = git(HERE, "rev-parse", "--show-toplevel")
    inside = top and os.path.realpath(run).startswith(os.path.realpath(top) + os.sep)
    if inside and git(HERE, "check-ignore", "-q", os.path.realpath(run)) is None:
        print("WARNING: %s is not ignored by git; raw export data could be committed. "
              "Keep runs under outputs/." % run)
    # Check everything before freezing anything, so a failed init can be re-run.
    srcs = [(role, src) for role, src in (("cases", a.cases), ("requirements", a.requirements)) if src]
    described = {}
    for role, src in srcs:
        if not os.path.isfile(src):
            raise Problem("no such file: %s" % src)
        described[role] = describe_csv(src, a.encoding)
    tests = repo_snapshot(a.tests_repo) if a.tests_repo else None
    inputs = {}
    for role, src in srcs:
        dst = run_file(run, "input", role + os.path.splitext(src)[1].lower())
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):  # left by an init that failed before its manifest
            os.chmod(dst, 0o644)
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o444)
        inputs[role] = dict(file=os.path.relpath(dst, run), source=os.path.abspath(src),
                            sha256=sha256(dst), bytes=os.path.getsize(dst), **described[role])
    manifest = {
        "tool_version": TOOL_VERSION, "created": now(),
        "export": {"query": a.query, "exported_at": a.exported_at, "exported_by": a.exported_by,
                   "note": a.note, "expect_cases": a.expect_cases},
        "single_export": not a.requirements,
        "inputs": inputs,
        "qf": repo_snapshot(HERE, required=False),
        "tests_repo": tests,
    }
    snap = manifest["tests_repo"]
    if snap and (snap["dirty"] or snap["commit"] != snap["origin_main"]):
        print("WARNING: the tests repo is %s; freeze a clean checkout of origin/main"
              % ("dirty" if snap["dirty"] else "not at origin/main"))
    save_json(run_file(run, "manifest.json"), manifest)
    for role, info in inputs.items():
        print("%s: %s, %d records, sha256 %s" % (role, info["source"], info["records"],
                                                 info["sha256"][:12]))
    if snap:
        print("tests repo: %s @ %s" % (snap["path"], snap["commit"][:12]))
    print("wrote %s" % run_file(run, "manifest.json"))
    return 0


# ---------------------------------------------------------------- W1: ledger

def resolve_jira(links, reqs, case_ids, projects, roles):
    """(requirements, unknown links, other links, (url, key) or None, holds, detail, flags).

    Only a link with a requirement role (`roles`, or none at all) names the
    case's requirement; links with other roles are kept as context.
    """
    req_links = [(w, role) for w, role in links if not role or norm(role) in roles]
    other = [{"id": w, "role": role} for w, role in links if (w, role) not in req_links]
    found = [dict(id=w, role=role, title=reqs[w]["title"], jira=[u for u, _ in reqs[w]["jira"]],
                  keys=[k for _, k in reqs[w]["jira"]], problem=reqs[w]["problem"])
             for w, role in req_links if w in reqs]
    unknown = [w for w, _ in req_links if w not in reqs and w not in case_ids]
    flags = []
    if not links:
        return found, unknown, other, None, ["no-linked-requirement"], ["no linked work items"], flags
    if not req_links:
        return (found, unknown, other, None, ["no-linked-requirement"],
                ["no link with a requirement role (%s); its links: %s" % (
                    ", ".join(sorted(roles)), ", ".join("%(id)s (%(role)s)" % o for o in other))], flags)
    if unknown:
        return (found, unknown, other, None, ["requirement-not-in-export"],
                ["linked %s; not in the requirements export" % ", ".join(unknown)], flags)
    if not found:
        return (found, unknown, other, None, ["no-linked-requirement"],
                ["its links are test cases: %s" % ", ".join(w for w, _ in req_links)], flags)
    keys = collections.OrderedDict()
    for r in found:
        for url, key in reqs[r["id"]]["jira"]:
            keys.setdefault(key, url)
        if reqs[r["id"]]["bare"] and reqs[r["id"]]["jira"]:
            flags.append("jira-from-bare-key")
    if not keys:
        codes = sorted({r["problem"] for r in found})
        return found, unknown, other, None, codes, ["%s: %s" % (r["id"], r["problem"]) for r in found], flags
    holds, detail = [], []
    wrong = [k for k in keys if projects and k.split("-")[0] not in projects]
    if wrong:
        holds.append("wrong-jira-project")
        detail.append("Jira %s is outside %s" % (", ".join(wrong), ", ".join(sorted(projects))))
    if len(keys) > 1:
        holds.append("ambiguous-jira")
        detail.append("; ".join("%s -> %s" % (r["id"], ", ".join(r["keys"]) or r["problem"])
                                for r in found))
    if any(r["problem"] for r in found):
        flags.append("other-requirement-without-jira")
    if holds:
        return found, unknown, other, None, holds, detail, flags
    key, url = next(iter(keys.items()))
    return found, unknown, other, (url, key), [], [], flags


def cmd_ledger(a):
    run = a.run
    manifest = load_manifest(run)
    path = run_file(run, "ledger.json")
    if os.path.exists(path) and not a.force:
        old = load_json(path)
        if any(r.get(k) for r in old["rows"] for k in ("triage", "decision", "placement", "pr")):
            raise Problem("the ledger already holds triage or review results; --force rebuilds it "
                          "and drops them")
    if a.jira_base and not re.fullmatch(r"https://[^/\s]+/?", a.jira_base):
        raise Problem("--jira-base takes the Jira base URL, e.g. https://redhat.atlassian.net")
    overrides = parse_pairs(a.col, COLUMNS, "--col")
    known, alias = parse_allow(a.allow)
    projects = {p.strip().upper() for p in (a.jira_projects or "").split(",") if p.strip()}

    inputs = manifest["inputs"]
    single = "requirements" not in inputs
    cases_path = run_file(run, inputs["cases"]["file"])
    header, _, records = read_csv(cases_path, inputs["cases"]["encoding"])
    cols = map_columns(header, overrides, CASE_REQUIRED + (("type",) if single else ()), cases_path,
                       CASE_FIELDS)
    if single:
        req_path, req_header, req_records = cases_path, header, records
    else:
        req_path = run_file(run, inputs["requirements"]["file"])
        req_header, _, req_records = read_csv(req_path, inputs["requirements"]["encoding"])
    req_cols = map_columns(req_header, overrides, REQUIREMENT_REQUIRED, req_path, REQUIREMENT_FIELDS)
    # Every Jira-ish column counts: an empty Jira column must not hide a link in Hyperlinks.
    jira_names = {norm(n) for n in overrides.get("jira") or COLUMNS["jira"]}
    jira_headers = [h for h in req_header if norm(h) in jira_names]

    def kind(value):
        """testcase, requirement, other, or None for a type nobody confirmed."""
        k = canon("type", value, alias)
        return k if k in KNOWN["type"] else None

    reqs, req_defects = collections.OrderedDict(), []
    for n, line, cells, problem in req_records:
        get = getter(cells, req_cols)
        if "type" in req_cols and kind(get("type")) == "testcase":
            continue
        if problem or not get("id"):
            req_defects.append("requirements row %d (line %d): %s" % (n, line, problem or "empty ID"))
            continue
        cell = "\n".join(cells.get(h) or "" for h in jira_headers)
        if get("id") in reqs:
            if reqs[get("id")]["cell"].strip() != cell.strip():
                req_defects.append("requirements row %d (line %d): %s is on an earlier row with another "
                                   "Jira link" % (n, line, get("id")))
                reqs[get("id")]["cell"] += "\n" + cell  # both links count: its cases hold as ambiguous
            continue
        reqs[get("id")] = {"title": get("title"), "status": get("status"), "cell": cell}
    case_ids = {getter(c, cols)("id") for _, _, c, _ in records} - {""}
    ids = case_ids | set(reqs)
    for req in reqs.values():
        req["jira"], req["problem"], req["bare"] = parse_jira(req.pop("cell"), a.jira_base, ids)

    repo = a.tests_repo or (manifest.get("tests_repo") or {}).get("path")
    inventory, inv_meta = {}, None
    if repo:
        collected = read_collected(a.collected) if a.collected else None
        inventory = scan_repo(repo, collected)
        inv_meta = dict(repo_snapshot(repo), collected_from=a.collected, scanned=now(),
                        ids=len(inventory))
        frozen = (manifest.get("tests_repo") or {}).get("commit")
        if frozen and inv_meta["commit"] != frozen:
            print("WARNING: the tests repo moved from %s (init) to %s"
                  % (frozen[:12], inv_meta["commit"][:12]))
        save_json(run_file(run, "inventory.json"), dict(inv_meta, occurrences=inventory))

    rows, first, non_cases, missing_reqs = [], {}, collections.Counter(), collections.Counter()
    values = {f: collections.Counter() for f in ("type", "status", "automation", "role")}
    for n, line, cells, problem in records:
        get = getter(cells, cols)
        k = None
        if "type" in cols and get("type"):
            values["type"][get("type")] += 1
            k = kind(get("type"))
            if not problem and k in ("requirement", "other"):
                non_cases[get("type")] += 1
                continue
        pid = get("id")
        row = {"row": n, "line": line, "polarion_id": pid, "state": None, "holds": [], "flags": [],
               "detail": [], "source": {f: get(f) for f in cols if f != "id"}}
        rows.append(row)
        if problem or not pid or not WORK_ITEM.fullmatch(pid):
            row["state"] = "invalid"
            row["detail"].append(problem or ("ID %r is not a work item ID" % pid if pid else "empty ID"))
            continue
        if len(cells) < len(header):
            row["flags"].append("short-row")  # its missing trailing cells read as empty
        if pid in first:
            row["state"] = "duplicate"
            row["duplicate_of"] = first[pid]["row"]
            if any(first[pid]["source"].get(f) != row["source"].get(f) for f in row["source"]):
                row["flags"].append("conflicting-duplicate")
            continue
        first[pid] = row
        status, automation = canon("status", get("status"), alias), canon("automation", get("automation"), alias)
        values["status"][get("status")] += 1
        values["automation"][get("automation")] += 1
        row["existing"] = inventory.get(pid, [])
        if any(o["kind"] in LIVE_KINDS for o in row["existing"]):
            row["flags"].append("existing-marker")
            if implemented_evidence(row["existing"]):
                row["flags"].append("implemented-in-code")
            # A live marker on a test that never runs: the post-merge job may show it Automated.
            if any(o["kind"] in LIVE_KINDS and o.get("disabled") for o in row["existing"]):
                row["flags"].append("live-marker-on-stub")
        elif row["existing"]:
            row["flags"].append("id-mentioned-in-code")
        row["pse"] = normalize_pse(get("setup"), get("steps"), get("expected"))
        links = parse_links(get("linked"))
        values["role"].update(role or "(none)" for _, role in links)
        (row["requirements"], row["unknown_links"], row["other_links"], jira, holds, detail,
         flags) = resolve_jira(links, reqs, case_ids, projects, known["role"])
        missing_reqs.update(row["unknown_links"])
        if jira:
            row["jira_url"], row["jira_key"] = jira
        if status == "inactive":
            row["state"] = "excluded"
            row["detail"].append("Status is inactive")
            continue
        if automation == "automated":
            row["state"] = "excluded"
            row["detail"].append("Automation is Automated")
            continue
        if automation == "manualonly":
            row["flags"].append("manualonly")
        if "type" in cols and get("type") and k is None:
            row["holds"].append("unexpected-type")
            row["detail"].append("Type %r is not a test case type anybody confirmed" % get("type"))
        for field, value in (("status", status), ("automation", automation)):
            if not value:
                row["holds"].append("%s-empty" % field)
                row["detail"].append("%s is empty: not a confirmed value" % field.capitalize())
            elif value not in known[field]:
                row["holds"].append("unexpected-%s" % field)
                row["detail"].append("%s %r is not one of the known values" % (field.capitalize(),
                                                                                get(field)))
        row["holds"] += holds
        row["detail"] += detail
        row["flags"] += flags
        row["state"] = "held" if row["holds"] else "resolved"

    counts = collections.Counter(r["state"] for r in rows)
    excluded = collections.Counter(r["detail"][0] for r in rows if r["state"] == "excluded")
    held = collections.Counter(h for r in rows if r["state"] == "held" for h in r["holds"])
    unaccounted = len(records) - sum(non_cases.values()) - sum(counts.values())
    ledger = {
        "tool_version": TOOL_VERSION, "created": now(),
        "columns": {"cases": cols, "requirements": req_cols, "requirement_jira": jira_headers},
        "known_values": {f: sorted(v) for f, v in known.items()},
        "aliases": {f: v for f, v in alias.items() if v},
        "jira_base": a.jira_base, "jira_projects": sorted(projects), "inventory": inv_meta,
        "counts": {"input_records": len(records), "not_a_test_case": sum(non_cases.values()),
                   "not_a_test_case_types": dict(non_cases),
                   "test_case_rows": len(rows), "states": dict(counts),
                   "excluded": dict(excluded), "holds": dict(held), "unaccounted": unaccounted},
        "values_seen": {f: dict(c) for f, c in values.items()},
        "missing_requirements": dict(missing_reqs),
        "requirement_defects": req_defects,
        "requirements": reqs,
        "rows": rows,
    }
    save_ledger(run, ledger)
    print("case columns: %s" % "; ".join("%s=%s" % kv for kv in cols.items()))
    unread = [h for h in header if h and h not in cols.values() and h not in jira_headers]
    if unread:
        print("  not read: %s" % ", ".join(unread))
    if not single:
        print("requirement columns: %s; Jira from %s" % (
            "; ".join("%s=%s" % kv for kv in req_cols.items() if kv[0] != "jira"), ", ".join(jira_headers)))
    for f in PSE_FIELDS:
        if f not in cols:
            print("WARNING: no %s column: every case reads as having none (map one with --col %s=HEADER)"
                  % (f, f))
    print("input records %21d" % len(records))
    print("  not a test case %17d  %s" % (sum(non_cases.values()), dict(non_cases) or ""))
    print("  test-case rows %18d" % len(rows))
    for reason, k in sorted(excluded.items()):
        print("    excluded (%s) %*d" % (reason, max(1, 19 - len(reason)), k))
    for state in ("resolved", "held", "duplicate", "invalid"):
        print("    %-30s %3d" % (state, counts.get(state, 0)))
    for code, k in sorted(held.items()):
        print("      hold %-24s %3d" % (code, k))
    print("unaccounted %23d" % unaccounted)
    expect = (manifest.get("export") or {}).get("expect_cases")
    if expect is not None and expect != len(rows):
        print("WARNING: the owner expects %d test cases; the export has %d test-case rows" % (expect, len(rows)))
    for field, c in values.items():
        if c:
            print("%s values seen: %s" % (field, ", ".join("%r x%d" % kv for kv in sorted(c.items()))))
    if missing_reqs:
        print("linked requirements missing from the requirements export (%d): %s" % (
            len(missing_reqs), ", ".join("%s x%d" % kv for kv in missing_reqs.most_common(20))))
    defects = [r for r in rows if r["state"] == "invalid" or "conflicting-duplicate" in r["flags"]]
    if defects or req_defects:
        print("Fix in the export before triage:")
        for r in defects:
            print("  row %d (line %d, %s): %s" % (r["row"], r["line"], r["polarion_id"] or "no ID",
                                                  ", ".join(r["detail"]) or "conflicting duplicate of row %d"
                                                  % r["duplicate_of"]))
        for d in req_defects:
            print("  " + d)
    short = [r["polarion_id"] for r in rows if "short-row" in r["flags"]]
    if short:
        print("Check in the export: %d row(s) had fewer cells than the header (read as empty): %s"
              % (len(short), ", ".join(short[:20])))
    print("wrote %s and %s" % (run_file(run, "ledger.json"), run_file(run, "ledger.csv")))
    if unaccounted:
        raise Failed(["%d input row(s) unaccounted for" % unaccounted])
    return 0


# ----------------------------------------------------------------- team map

def component_folder(row, teams):
    comp = row["source"].get("component", "")
    sub = row["source"].get("subcomponent", "")
    table = {k.lower(): v for k, v in (teams.get("components") or {}).items()}
    for key in (("%s/%s" % (comp, sub)) if sub else None, comp):
        if key and key.lower() in table:
            return rel_path(table[key.lower()])
    return None


def team_for_folder(folder, teams):
    best = None
    for name, t in teams["teams"].items():
        for root in t.get("roots") or []:
            if under(folder, [root]) and (best is None or len(root) > len(best[1])):
                best = (name, root)
    return best[0] if best else None


def check_teams(doc, repo):
    errors = []
    if not isinstance(doc, dict) or not isinstance(doc.get("teams"), dict) or not doc["teams"]:
        return ["the team map needs a `teams:` mapping"]
    for name, t in doc["teams"].items():
        if not re.fullmatch(r"[a-z0-9_-]+", str(name)):
            errors.append("team %r: use a lowercase name (letters, digits, _ -)" % name)
        t = t or {}
        roots = t.get("roots") or []
        if not roots:
            errors.append("team %s: no roots" % name)
        for r in roots:
            if rel_path(r) != r:
                errors.append("team %s: root %r is not a normalised path under tests/" % (name, r))
            elif repo and not os.path.isdir(os.path.join(repo, r)):
                errors.append("team %s: root %s does not exist in %s" % (name, r, repo))
        track = t.get("tracking_jira")
        if track and not JIRA_URL.fullmatch(track):
            errors.append("team %s: tracking_jira %r is not a Jira issue URL" % (name, track))
    owners = collections.Counter(c.lower() for t in doc["teams"].values()
                                 for c in (t or {}).get("components") or [])
    errors += ["component %r is claimed by %d teams" % (c, k) for c, k in owners.items() if k > 1]
    roots = collections.Counter(r for t in doc["teams"].values() for r in (t or {}).get("roots") or [])
    errors += ["root %s belongs to %d teams" % (r, k) for r, k in roots.items() if k > 1]
    claimed = {c.lower(): name for name, t in doc["teams"].items() for c in (t or {}).get("components") or []}
    for comp, folder in (doc.get("components") or {}).items():
        p = rel_path(folder)
        owner = p and team_for_folder(p, doc)
        if p != folder:
            errors.append("component %r: %r is not a normalised path under tests/" % (comp, folder))
        elif not owner:
            errors.append("component %r: %s is under no team's roots" % (comp, p))
        elif repo and not os.path.isdir(os.path.join(repo, p)):
            errors.append("component %r: %s does not exist in %s" % (comp, p, repo))
        elif claimed.get(comp.lower(), owner) != owner:
            errors.append("component %r: team %s claims it, but %s is %s's folder"
                          % (comp, claimed[comp.lower()], p, owner))
    return errors


def cmd_teams(a):
    with open(a.file, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    repo = a.tests_repo or (load_manifest(a.run).get("tests_repo") or {}).get("path")
    errors = check_teams(doc, repo)
    if errors:
        raise Failed(errors)
    shutil.copyfile(a.file, run_file(a.run, "teams.yaml"))
    print("froze %s (sha256 %s): %d team(s), %d component folder(s), approved by %s on %s"
          % (a.file, sha256(a.file)[:12], len(doc["teams"]), len(doc.get("components") or {}),
             doc.get("approved_by") or "(nobody yet)", doc.get("approved_on") or "-"))
    return 0


# ----------------------------------------------------------------- W2: triage

def case_brief(r):
    src = r["source"]
    return {"polarion_id": r["polarion_id"], "row": r["row"], "title": src.get("title", ""),
            "status": src.get("status", ""), "automation": src.get("automation", ""),
            "component": src.get("component", ""), "updated": src.get("updated", ""),
            "pse": r.get("pse"), "description": re.sub(r"\s+", " ", plain(src.get("description", ""))),
            "hyperlinks": src.get("hyperlinks", ""), "flags": r["flags"],
            "existing": [fmt_occ(o) for o in r.get("existing", [])]}


def latest_context(run, key):
    """The newest context file for a Jira key: names sort by their UTC stamp."""
    d = run_file(run, "triage", "context")
    names = sorted(n for n in (os.listdir(d) if os.path.isdir(d) else [])
                   if n.startswith(key + "@") and n.endswith(".json"))
    return names[-1] if names else None


def cmd_triage_queue(a):
    ledger = load_ledger(a.run)
    rows = ledger["rows"]
    defects = [r for r in rows if r["state"] == "invalid" or "conflicting-duplicate" in r["flags"]]
    if defects and not a.allow_defects:
        raise Problem("%d export defect(s) (invalid or conflicting duplicate rows) — fix the export "
                      "first, or pass --allow-defects" % len(defects))
    groups = collections.OrderedDict()
    for r in rows:
        if r["state"] == "resolved":
            groups.setdefault(r["jira_key"], []).append(r)
    out = []
    for key, members in groups.items():
        req_ids = {x["id"] for r in members for x in r["requirements"]}
        ids = {r["polarion_id"] for r in members}
        siblings = [{"polarion_id": r["polarion_id"], "title": r["source"].get("title", ""),
                     "state": r["state"], "automation": r["source"].get("automation", ""),
                     "steps": r.get("pse", {}).get("steps", []),
                     "existing": [fmt_occ(o) for o in r.get("existing", [])]}
                    for r in rows if r["state"] in ("resolved", "held", "excluded")
                    and r["polarion_id"] not in ids
                    and (r.get("jira_key") == key or req_ids & {x["id"] for x in r.get("requirements", [])})]
        out.append({"jira_key": key, "jira_url": members[0]["jira_url"],
                    "requirements": sorted(req_ids), "cases": [case_brief(r) for r in members],
                    "siblings": siblings,
                    "context_file": "triage/context/%s@<UTC stamp>.json" % key,
                    "verdict_file": "triage/verdicts/%s.json" % key})
    queue = {"created": now(), "groups": out,
             "how": "skills/polarion-migration/SKILL.md, W2; agents/polarion-triager.md"}
    for d in ("context", "verdicts"):
        os.makedirs(run_file(a.run, "triage", d), exist_ok=True)
    save_json(run_file(a.run, "triage", "queue.json"), queue)
    print("queued %d requirement group(s), %d case(s) -> %s"
          % (len(out), sum(len(g["cases"]) for g in out), run_file(a.run, "triage", "queue.json")))
    held = sum(1 for r in rows if r["state"] == "held")
    if held:
        print("%d held case(s) stay out of triage; their holds name the missing data" % held)
    return 0


def test_exists(repo, node):
    """Whether tests/...py::[Class::]name names a def (in that class) in the repo."""
    path, _, rest = node.partition("::")
    full = os.path.join(repo, path)
    if not os.path.isfile(full):
        return False
    with open(full, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        body = ast.parse(text).body
    except SyntaxError:
        return re.search(r"\bdef %s\b" % re.escape(rest.split("::")[-1]), text) is not None
    for name in rest.split("::"):
        node = next((n for n in body if isinstance(n, DEFS) and n.name == name), None)
        if node is None:
            return False
        body = node.body
    return True


def check_verdicts(group, doc, ctx, ctx_name, repo=None):
    errs = []
    where = "verdicts/%s.json" % group["jira_key"]
    if doc.get("jira_key") != group["jira_key"]:
        errs.append("%s: jira_key is %r" % (where, doc.get("jira_key")))
    if doc.get("context_snapshot") != ctx_name:
        errs.append("%s: context_snapshot %r is not the latest context, %s"
                    % (where, doc.get("context_snapshot"), ctx_name))
    want = {c["polarion_id"]: c for c in group["cases"]}
    seen = set()
    for c in doc.get("cases") or []:
        pid = c.get("polarion_id")
        at = "%s %s" % (where, pid)
        if pid not in want:
            errs.append("%s: not a case of this group" % at)
            continue
        if pid in seen:
            errs.append("%s: listed twice" % at)
        seen.add(pid)
        verdict = c.get("verdict")
        if verdict not in VERDICTS:
            errs.append("%s: verdict %r is not one of %s" % (at, verdict, ", ".join(VERDICTS)))
        if not str(c.get("rationale") or "").strip():
            errs.append("%s: no rationale" % at)
        if c.get("uncertainty") not in UNCERTAINTY:
            errs.append("%s: uncertainty must be one of %s" % (at, ", ".join(UNCERTAINTY)))
        if not c.get("proposed_team"):
            errs.append("%s: no proposed_team (use \"unknown\")" % at)
        evidence = c.get("evidence") or []
        for e in evidence:
            if not (isinstance(e, dict) and str(e.get("claim") or "").strip()
                    and SOURCE_REF.match(str(e.get("source") or ""))):
                errs.append("%s: evidence %r needs a claim and a source (a URL, or "
                            "repo@commit:path:line)" % (at, e))
        if verdict != "needs-investigation" and not evidence:
            errs.append("%s: %s needs evidence" % (at, verdict))
        manual = norm(want[pid]["automation"]) == "manualonly"
        if manual and verdict != "manual-only-review":
            errs.append("%s: a manualonly case gets manual-only-review" % at)
        if ctx.get("error") and not manual and verdict != "needs-investigation":
            errs.append("%s: the Jira fetch failed (%s), so the verdict is needs-investigation"
                        % (at, ctx["error"]))
        tests = covered_list(c.get("covered_by"))
        if verdict in ("covered-by-implemented-test", "designed-as-stub") and not tests:
            errs.append("%s: %s needs covered_by: the test(s), tests/...py::name" % (at, verdict))
        if any(not TEST_NODE.match(t) for t in tests):
            errs.append("%s: covered_by names tests as tests/...py::Class::test_name, no [params]" % at)
        elif repo:
            errs += ["%s: covered_by %s is not in the tests repo" % (at, t) for t in tests
                     if not test_exists(repo, t)]
        gaps = c.get("gaps") or []
        if not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
            errs.append("%s: gaps is a list of strings" % at)
        if c.get("suggested_jira") and not JIRA_URL.fullmatch(str(c["suggested_jira"])):
            errs.append("%s: suggested_jira %r is not a Jira issue URL" % (at, c["suggested_jira"]))
    for pid in sorted(set(want) - seen):
        errs.append("%s: no verdict for %s" % (where, pid))
    return errs


def covered_list(value):
    """covered_by as a list: one test, or several (push/pull twins)."""
    if not value:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def check_context(ctx, key, name):
    """The context file's own shape and sources; its claims back the verdicts."""
    errs = []
    if ctx.get("jira_key") != key:
        errs.append("context/%s: jira_key is %r" % (name, ctx.get("jira_key")))
    if not ctx.get("fetched_at") or "error" not in ctx:
        errs.append("context/%s: needs fetched_at and error (null when the Jira fetch worked)" % name)
    for section in ("product", "tests_repo"):
        for e in ctx.get(section) or []:
            if not (isinstance(e, dict) and str(e.get("claim") or "").strip()
                    and SOURCE_REF.match(str(e.get("source") or ""))):
                errs.append("context/%s: %s entry %r needs a claim and a source" % (name, section, e))
    return errs


def context_signals(ctx):
    jira = ctx.get("jira") or {}
    out = []
    if norm(jira.get("resolution")) in RETIRE_RESOLUTIONS:
        out.append("Jira resolution %s (a signal, not a rule)" % jira.get("resolution"))
    for link in jira.get("links") or []:
        if "obsolet" in norm(link.get("type")) or "supersed" in norm(link.get("type")):
            out.append("Jira %s %s" % (link.get("type"), link.get("key")))
    for pr in ctx.get("prs") or []:
        if pr.get("reverted_by"):
            out.append("PR %s reverted by %s" % (pr.get("url"), pr.get("reverted_by")))
    return out


def cmd_triage_merge(a):
    run = a.run
    ledger = load_ledger(run)
    queue = load_json(run_file(run, "triage", "queue.json"))
    repo = (load_manifest(run).get("tests_repo") or {}).get("path")
    by_id = {r["polarion_id"]: r for r in ledger["rows"] if r["state"] == "resolved"}
    errors, merged, pending = [], 0, []
    groups = [g for g in queue["groups"] if not a.group or g["jira_key"] == a.group]
    if a.group and not groups:
        raise Problem("no group %s in the queue" % a.group)
    for g in groups:
        vpath = run_file(run, g["verdict_file"])
        if not os.path.exists(vpath):
            pending += [c["polarion_id"] for c in g["cases"]]
            continue
        ctx_name = latest_context(run, g["jira_key"])
        if not ctx_name:
            errors.append("%s: no context file in triage/context/ for its verdicts" % g["jira_key"])
            continue
        ctx = load_json(run_file(run, "triage", "context", ctx_name))
        doc = load_json(vpath)
        errs = check_context(ctx, g["jira_key"], ctx_name) + check_verdicts(g, doc, ctx, ctx_name, repo)
        errs += ["%s: %s is no longer resolved under this Jira in the ledger; re-run `triage queue`"
                 % (g["jira_key"], c["polarion_id"]) for c in g["cases"]
                 if (by_id.get(c["polarion_id"]) or {}).get("jira_key") != g["jira_key"]]
        if errs:
            errors += errs
            continue
        signals = context_signals(ctx)
        jira = {k: (ctx.get("jira") or {}).get(k) for k in ("type", "status", "resolution", "summary")}
        for c in doc["cases"]:
            row = by_id[c["polarion_id"]]
            new = {"verdict": c["verdict"], "rationale": c["rationale"], "uncertainty": c["uncertainty"],
                   "proposed_team": c["proposed_team"], "evidence": c.get("evidence") or [],
                   "covered_by": covered_list(c.get("covered_by")), "gaps": c.get("gaps") or [],
                   "suggested_jira": c.get("suggested_jira"), "context": ctx_name, "jira": jira,
                   "signals": signals, "model": doc.get("model"), "merged": now()}
            old = row.get("triage")
            if old and (old["verdict"], old["context"]) != (new["verdict"], new["context"]):
                row.setdefault("triage_history", []).append(old)
            row["triage"] = new
            merged += 1
    if a.dry_run:
        print("checked %d verdict(s); nothing written (--dry-run)" % merged)
        if errors:
            raise Failed(errors)
        return 0
    save_ledger(run, ledger)
    print("merged %d verdict(s); %d case(s) still without a verdict" % (merged, len(pending)))
    verdicts = collections.Counter(r["triage"]["verdict"] for r in by_id.values() if r.get("triage"))
    for v in VERDICTS:
        print("  %-28s %d" % (v, verdicts.get(v, 0)))
    if errors:
        raise Failed(errors)
    return 0


# ----------------------------------------------------------------- W3: review

SHEET = ("polarion_id", "team", "row", "title", "source_status", "source_automation", "state", "holds",
         "flags", "jira_url", "jira_candidates", "requirements", "existing_code", "triage_verdict",
         "triage_uncertainty", "triage_rationale", "triage_covered_by", "triage_gaps",
         "triage_suggested_jira", "triage_evidence",
         "decision", "chosen_jira", "pse_note", "existing_test", "attach_id", "retire_reason",
         "polarion_owner", "reviewer", "date", "rationale", "sheet_version")
FILL = SHEET[SHEET.index("decision"):SHEET.index("sheet_version")]
YES, NO = {"yes", "y", "true"}, {"no", "n", "false"}


def fill_value(column, value):
    """A sheet cell the way an import reads it: spreadsheets reformat dates and booleans."""
    v = (value or "").strip()
    if column == "decision":
        return v.lower()
    if column == "attach_id":
        return "yes" if v.lower() in YES else "no" if v.lower() in NO else v.lower()
    if column == "date":
        return v[:10]  # "2026-10-08 00:00:00" from a spreadsheet
    return v


def team_of(row, teams):
    """The folder map, then the teams' own components, then the triage's proposal."""
    if teams:
        folder = component_folder(row, teams)
        team = folder and team_for_folder(folder, teams)
        if team:
            return team
        comp = row["source"].get("component", "").lower()
        for name, t in teams["teams"].items():
            if comp and comp in [c.lower() for c in (t or {}).get("components") or []]:
                return name
        proposal = (row.get("triage") or {}).get("proposed_team")
        if proposal in teams["teams"]:
            return proposal
    return "unassigned"


def sheet_row(r):
    t = r.get("triage") or {}
    d = r.get("decision") or {}
    out = {"polarion_id": r["polarion_id"], "team": r.get("team") or "", "row": r["row"],
           "title": r["source"].get("title", ""),
           "source_status": r["source"].get("status", ""),
           "source_automation": r["source"].get("automation", ""), "state": r["state"],
           "holds": "; ".join(r["holds"] + r["detail"]) if r["holds"] else "",
           "flags": " ".join(r["flags"]), "jira_url": r.get("jira_url") or "",
           "jira_candidates": " ".join(u for x in r.get("requirements", []) for u in x["jira"]),
           "requirements": " ".join("%s (%s)" % (x["id"], x["role"] or "link")
                                    for x in r.get("requirements", [])),
           "existing_code": "; ".join(fmt_occ(o) for o in r.get("existing", [])),
           "triage_verdict": t.get("verdict", ""), "triage_uncertainty": t.get("uncertainty", ""),
           "triage_rationale": t.get("rationale", ""),
           "triage_covered_by": " ".join(covered_list(t.get("covered_by"))),
           "triage_gaps": " | ".join(t.get("gaps") or []),
           "triage_suggested_jira": t.get("suggested_jira") or "",
           "triage_evidence": " | ".join("%s <%s>" % (e["claim"], e["source"])
                                         for e in t.get("evidence") or [])}
    out.update({c: d.get(c, "") for c in FILL})
    out["sheet_version"] = r.get("sheet_version", "")
    return out


def cmd_review_sheets(a):
    run = a.run
    ledger = load_ledger(run)
    teams = load_teams(run, required=False)
    rows = collections.OrderedDict((r["polarion_id"], r) for r in ledger["rows"]
                                   if r["state"] in ("resolved", "held"))
    review = run_file(run, "review")
    old = sorted(n for n in (os.listdir(review) if os.path.isdir(review) else []) if n.endswith(".csv"))
    if not a.force:  # a sheet's edits that were never imported would be lost
        pending = []
        for name in old:
            for _, _, cells, _ in read_csv(os.path.join(review, name), "utf-8-sig")[2]:
                r = rows.get((cells.get("polarion_id") or "").strip())
                if r and any(fill_value(c, cells.get(c)) != fill_value(c, sheet_row(r)[c])
                             for c in ("team",) + FILL):
                    pending.append("%s %s" % (name, r["polarion_id"]))
        if pending:
            raise Problem("edits not imported yet: %s. Import them first, or --force overwrites them"
                          % ", ".join(pending))
    by_team = collections.OrderedDict()
    for r in rows.values():
        if not r.get("team_set_by"):  # a reviewer's reassignment sticks
            r["team"] = team_of(r, teams)
        by_team.setdefault(r["team"], []).append(r)
    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for team, members in by_team.items():
        for r in members:
            r["sheet_version"] = "%s@%s" % (team, version)
        path = run_file(run, "review", team + ".csv")
        write_csv(path, SHEET, [sheet_row(r) for r in members])
        print("%s: %d case(s) -> %s" % (team, len(members), path))
    for name in old:
        if name[:-len(".csv")] not in by_team:
            os.remove(os.path.join(review, name))
            print("removed %s: none of its cases is that team's any more" % name)
    save_ledger(run, ledger)
    return 0


def cmd_review_import(a):
    run = a.run
    ledger = load_ledger(run)
    repo = a.tests_repo or (load_manifest(run).get("tests_repo") or {}).get("path")
    header, _, records = read_csv(a.sheet, "utf-8-sig")
    missing = [c for c in ("polarion_id", "row", "sheet_version") + FILL if c not in header]
    if missing:
        raise Problem("%s lacks column(s) %s: regenerate it with `review sheets`"
                      % (a.sheet, ", ".join(missing)))
    rows = {r["polarion_id"]: r for r in ledger["rows"] if r["state"] in ("resolved", "held")}
    teams = load_teams(run, required=False)
    trackers = {(t or {}).get("tracking_jira") for t in ((teams or {}).get("teams") or {}).values()} - {None, ""}
    projects = set(ledger.get("jira_projects") or [])
    errors, updates, moves, seen = [], [], [], {}
    for n, _, cells, problem in records:
        get = getter(cells, {c: c for c in header})
        decision = fill_value("decision", get("decision"))
        at = "%s row %d (%s)" % (os.path.basename(a.sheet), n, get("polarion_id"))
        row = rows.get(get("polarion_id"))
        if get("polarion_id") in seen:
            errors.append("%s: also on row %d of the sheet" % (at, seen[get("polarion_id")]))
            continue
        seen[get("polarion_id")] = n
        if row and get("sheet_version") != row.get("sheet_version"):
            if any(get(c) for c in FILL) or get("team") != row.get("team"):
                errors.append("%s: comes from an older sheet (%s); the case is on %s now: fill that one"
                              % (at, get("sheet_version") or "no version", row.get("sheet_version")))
            continue
        if row and get("row") != str(row["row"]):
            errors.append("%s: the ledger has this case on row %d, the sheet says %r: it was re-sorted "
                          "or edited out of line; regenerate it" % (at, row["row"], get("row")))
            continue
        team = row.get("team") if row else None
        if row and get("team") and get("team") != row.get("team"):
            if not teams or get("team") not in teams["teams"]:
                errors.append("%s: team %r is not in teams.yaml" % (at, get("team")))
            elif not get("reviewer"):
                errors.append("%s: moving a case to another team needs a reviewer" % at)
            else:
                moves.append((row, get("team"), get("reviewer")))
                team = get("team")
        if not decision:
            if row and row.get("decision"):
                errors.append("%s: the decision cell is empty, but %s was imported: to withdraw a "
                              "decision, write hold" % (at, row["decision"]["decision"]))
            continue
        if problem or not row:
            errors.append("%s: %s" % (at, problem or "not an eligible case in the ledger"))
            continue
        if decision not in DECISIONS:
            errors.append("%s: decision %r is not one of %s" % (at, decision, ", ".join(DECISIONS)))
        for c in ("reviewer", "rationale"):
            if not get(c):
                errors.append("%s: %s is required" % (at, c))
        try:
            datetime.date.fromisoformat(fill_value("date", get("date")))
        except ValueError:
            errors.append("%s: date must be YYYY-MM-DD" % at)
        chosen = get("chosen_jira")
        if chosen and not JIRA_URL.fullmatch(chosen):
            errors.append("%s: chosen_jira %r is not a Jira issue URL" % (at, chosen))
        elif chosen in trackers:
            errors.append("%s: chosen_jira is a team's tracking Jira, not the case's own requirement" % at)
        elif chosen and projects and JIRA_URL.fullmatch(chosen).group(1).split("-")[0] not in projects:
            errors.append("%s: chosen_jira %s is outside %s" % (at, chosen, ", ".join(sorted(projects))))
        if decision == "migrate" and not (chosen or row.get("jira_url")):
            errors.append("%s: the Jira link is on hold (%s): name it in chosen_jira"
                          % (at, ", ".join(sorted(set(row["holds"]) & JIRA_HOLDS))))
        if decision == "migrate" and not (teams and team in teams["teams"]):
            errors.append("%s: migrate needs a team from teams.yaml: put it in the team cell" % at)
        if decision == "link-existing":
            test = get("existing_test")
            if not TEST_NODE.match(test):
                errors.append("%s: existing_test must be tests/...py::name" % at)
            elif repo and not test_exists(repo, test):
                errors.append("%s: %s is not in %s" % (at, test, repo))
            if fill_value("attach_id", get("attach_id")) not in ("yes", "no"):
                errors.append("%s: attach_id must be yes or no" % at)
        if decision == "retire":
            for c in ("retire_reason", "polarion_owner"):
                if not get(c):
                    errors.append("%s: retire needs %s" % (at, c))
        updates.append((row, dict({c: fill_value(c, get(c)) for c in FILL},
                                  sheet=os.path.basename(a.sheet), imported=now())))
    if errors:
        raise Failed(errors)
    for row, d in updates:
        row["decision"] = d
    for row, team, reviewer in moves:
        row["team"], row["team_set_by"] = team, reviewer
    save_ledger(run, ledger)
    decided = collections.Counter(d["decision"] for _, d in updates)
    print("imported %d decision(s) from %s: %s" % (len(updates), a.sheet, dict(decided)))
    pending = [r["polarion_id"] for r in rows.values() if not r.get("decision")]
    print("%d eligible case(s) have no decision yet" % len(pending))
    return 0


def cmd_review_calibrate(a):
    run = a.run
    ledger = load_ledger(run)
    rows = [r for r in ledger["rows"] if r.get("triage") and r.get("decision")]
    matrix = collections.defaultdict(collections.Counter)
    for r in rows:
        matrix[r["triage"]["verdict"]][r["decision"]["decision"]] += 1
    per_verdict, disagreements = {}, []
    for v in VERDICTS:
        n = sum(matrix[v].values())
        expected = EXPECTED_DECISION.get(v)
        agree = matrix[v][expected] if expected else None
        per_verdict[v] = {"reviewed": n, "expected_decision": expected, "agreed": agree,
                          "rate": round(agree / n, 2) if expected and n else None,
                          "decisions": dict(matrix[v])}
    for r in rows:
        v, d = r["triage"]["verdict"], r["decision"]["decision"]
        if EXPECTED_DECISION.get(v) and EXPECTED_DECISION[v] != d:
            disagreements.append({"polarion_id": r["polarion_id"], "verdict": v, "decision": d,
                                  "triage_rationale": r["triage"]["rationale"],
                                  "review_rationale": r["decision"]["rationale"]})
    false_retire = [x for x in disagreements if x["verdict"] == "retire-candidate"
                    and x["decision"] in ("migrate", "link-existing")]
    no_evidence = [r["polarion_id"] for r in rows
                   if r["triage"]["verdict"] == "needs-investigation" or not r["triage"]["evidence"]]
    scored = [x for x in per_verdict.values() if x["expected_decision"]]
    total = sum(x["reviewed"] for x in scored)
    report = {"created": now(), "reviewed_with_verdict": len(rows),
              "overall_agreement": round(sum(x["agreed"] for x in scored) / total, 2) if total else None,
              "per_verdict": per_verdict, "disagreements": disagreements,
              "false_retirement_proposals": false_retire, "missing_evidence": no_evidence,
              "note": "Descriptive for this sample only, not a claim of general accuracy."}
    save_json(run_file(run, "review", "calibration.json"), report)
    md = ["# Triage calibration", "", report["note"], "",
          "Reviewed cases with a triage verdict: %d. Overall agreement: %s." % (
              len(rows), "n/a" if report["overall_agreement"] is None else report["overall_agreement"]),
          "", "| Verdict | Reviewed | Expected decision | Agreed | Decisions |", "|---|---|---|---|---|"]
    for v, x in per_verdict.items():
        md.append("| %s | %d | %s | %s | %s |" % (v, x["reviewed"], x["expected_decision"] or "-",
                                                 "-" if x["agreed"] is None else x["agreed"],
                                                 ", ".join("%s %d" % kv for kv in sorted(x["decisions"].items()))))
    md += ["", "False retirement proposals: %d" % len(false_retire)]
    md += ["- %(polarion_id)s: %(verdict)s -> %(decision)s (%(review_rationale)s)" % x for x in false_retire]
    md += ["", "Disagreements: %d" % len(disagreements)]
    md += ["- %(polarion_id)s: %(verdict)s -> %(decision)s" % x for x in disagreements]
    md += ["", "Needs-investigation or no evidence: %s" % (", ".join(no_evidence) or "none")]
    with open(run_file(run, "review", "calibration.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


# ------------------------------------------------------------ W4: scenarios

def team_rows(ledger, team, decision="migrate"):
    return [r for r in ledger["rows"] if r.get("team") == team
            and (r.get("decision") or {}).get("decision") == decision]


def tracking(teams, team):
    url = (teams["teams"].get(team) or {}).get("tracking_jira")
    if not url:
        raise Problem("team %s has no tracking_jira in teams.yaml: the owner supplies one per "
                      "team batch" % team)
    return url, JIRA_URL.fullmatch(url).group(1)


def requirement_title(row, key):
    for x in row.get("requirements", []):
        if key in x["keys"]:
            return x["title"]
    return None


def cmd_scenarios(a):
    run = a.run
    ledger = load_ledger(run)
    teams = load_teams(run)
    validate_std = std_validator()
    names = [a.team] if a.team else list(teams["teams"])
    for team in names:
        if team not in teams["teams"]:
            raise Problem("no team %r in teams.yaml" % team)
        rows = team_rows(ledger, team)
        if not rows:
            print("%s: no approved migrate case; nothing to generate (a valid result)" % team)
            m = JIRA_URL.fullmatch((teams["teams"].get(team) or {}).get("tracking_jira") or "")
            stale = m and os.path.join(a.outputs, m.group(1), "input", m.group(1) + "_scenarios.yaml")
            if stale and os.path.exists(stale):
                print("WARNING: an earlier scenario list is still at %s: delete it before /std-builder" % stale)
            continue
        url, key = tracking(teams, team)
        scenarios = []
        for i, r in enumerate(rows, 1):
            jira = r["decision"].get("chosen_jira") or r["jira_url"]
            jkey = JIRA_URL.fullmatch(jira).group(1)
            s = {"scenario_id": i, "polarion_id": r["polarion_id"], "requirement_id": jkey,
                 "jira_url": jira}
            summary = requirement_title(r, jkey)
            if summary:
                s["requirement_summary"] = summary
            s["tier" if a.tier else "test_type"] = a.tier or "functional"
            importance = r["source"].get("importance", "")
            s["priority"] = PRIORITY.get(norm(importance), "P2")
            s["priority_comment"] = ("%s — Polarion importance %s" % (s["priority"], importance) if importance
                                     else "P2 — Polarion sets no importance")
            s["description"] = r["source"].get("title", "")
            for field in ("preconditions", "steps", "expected"):
                if r["pse"][field]:
                    s[field] = r["pse"][field]
            s["source_pse"] = r["pse"]["source"]
            if r["pse"]["missing"]:
                s["source_missing"] = r["pse"]["missing"]
            if any(p["expected"] for p in r["pse"]["step_results"]):
                s["step_results"] = r["pse"]["step_results"]
            if r["decision"].get("pse_note"):
                s["review_note"] = r["decision"]["pse_note"]
            desc = re.sub(r"\s+", " ", plain(r["source"].get("description", ""))).strip()
            if desc:
                s["source_description"] = desc
            scenarios.append(s)
            r["scenario"] = {"tracking_jira": url, "scenario_id": i}
        doc = {"source": "polarion",
               "context": {"jira_id": key, "title": "Polarion migration: %s" % team,
                           "feature_description": "Polarion test cases the %s team approved for "
                           "migration. Each keeps its Polarion id and links its own Jira "
                           "requirement." % team,
                           "jira_url": url},
               "scenarios": scenarios}
        rep = validate_std.validate_scenarios(doc)
        if rep.errors:
            raise Failed(["%s: %s" % (team, e) for e in rep.errors])
        out = os.path.join(a.outputs, key, "input", key + "_scenarios.yaml")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=1000)
        print("%s: %d scenario(s) -> %s (next: /std-builder %s)" % (team, len(scenarios), out, key))
    save_ledger(run, ledger)
    return 0


# ---------------------------------------------------------------- W4: place

def candidate_folders(repo, roots):
    """Existing folders under the team's roots that hold tests, with a few names each."""
    out = []
    for root in roots:
        for d, dirs, files in os.walk(os.path.join(repo, root)):
            dirs[:] = sorted(x for x in dirs if not x.startswith(".") and x not in SKIP_DIRS)
            tests = sorted(f for f in files if f.startswith("test_") and f.endswith(".py"))
            if not tests:
                continue
            names = []
            for f in tests:
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    names += re.findall(r"^\s*def (test_\w+)", fh.read(), re.M)
                if len(names) >= 3:
                    break
            out.append({"folder": os.path.relpath(d, repo).replace("\\", "/"), "modules": tests[:5],
                        "tests": names[:3]})
    return out


def read_owner_sheet(path):
    if not os.path.exists(path):
        return {}
    _, _, records = read_csv(path, "utf-8-sig")
    return {c.get("polarion_id", "").strip(): c for _, _, c, _ in records if c.get("folder", "").strip()}


def cmd_place(a):
    run = a.run
    ledger = load_ledger(run)
    teams = load_teams(run)
    if not (teams.get("approved_by") and teams.get("approved_on")):
        raise Problem("teams.yaml has no approved_by/approved_on: the team approves the "
                      "component-to-folder map before placement")
    team = a.team
    roots = (teams["teams"].get(team) or {}).get("roots") or []
    if not roots:
        raise Problem("no team %r with roots in teams.yaml" % team)
    repo = tests_repo(run, a.tests_repo)
    inventory = scan_repo(repo)
    head = git(repo, "rev-parse", "HEAD")
    rows = team_rows(ledger, team)
    candidates = candidate_folders(repo, roots)
    folders = {c["folder"] for c in candidates}
    model = {}
    mpath = run_file(run, "placement", team + ".model.json")
    if os.path.exists(mpath):
        model = {c["polarion_id"]: c for c in load_json(mpath).get("cases") or []}
    owner = read_owner_sheet(run_file(run, "placement", team + ".owner.csv"))
    approved = {r["polarion_id"] for r in rows}
    errors = ["owner sheet: %s is not an approved migrate case of %s" % (pid, team)
              for pid in sorted(set(owner) - approved)]
    errors += ["model file: %s is not an approved migrate case of %s" % (pid, team)
               for pid in sorted(set(model) - approved)]
    cases = []
    for r in rows:
        pid = r["polarion_id"]
        key = JIRA_URL.fullmatch(r["decision"].get("chosen_jira") or r["jira_url"]).group(1)
        p = {"polarion_id": pid, "layer": "unplaced", "folder": None, "confidence": None,
             "evidence": [], "candidates": []}
        sib_ids = {x["polarion_id"] for x in ledger["rows"] if x["polarion_id"] != pid
                   and x["state"] != "invalid"
                   and key in [k for q in x.get("requirements", []) for k in q["keys"]]}
        sib = [o for s in sorted(sib_ids) for o in implemented_evidence(inventory.get(s, []))]
        tally = collections.Counter(os.path.dirname(o["path"]) for o in sib)
        inside = collections.Counter({f: k for f, k in tally.items() if under(f, roots)})
        if inside:
            folder, k = inside.most_common(1)[0]
            share = k / sum(tally.values())
            p["evidence"] = ["%s (sibling %s)" % (fmt_occ(o), o["id"]) for o in sib]
            if share == 1:
                p.update(layer="sibling", folder=folder, confidence=0.95)
            elif share > 0.5:
                p.update(layer="sibling", folder=folder, confidence=0.75)
            else:
                p["candidates"] = sorted(inside)
        elif tally:
            p["evidence"] = ["siblings only outside %s: %s" % (", ".join(roots), ", ".join(sorted(tally)))]
        if p["layer"] == "unplaced":
            folder = component_folder(r, teams)
            if folder and under(folder, roots):
                p.update(layer="folder-map", folder=folder, confidence=0.9,
                         evidence=p["evidence"] + ["component %r -> %s (team-approved map)"
                                                   % (r["source"].get("component"), folder)])
        if p["layer"] == "unplaced" and pid in model:
            m = model[pid]
            choice, conf = rel_path(m.get("folder")), m.get("confidence")
            if choice not in folders:
                p["evidence"].append("model chose %r, not one of the existing candidate folders"
                                     % m.get("folder"))
            elif not isinstance(conf, (int, float)) or isinstance(conf, bool) or not a.min_confidence <= conf <= 1:
                p["evidence"].append("model chose %s at confidence %r, not between %s and 1"
                                     % (choice, conf, a.min_confidence))
            elif not m.get("cited_tests"):
                p["evidence"].append("model chose %s without citing nearby tests" % choice)
            else:
                p.update(layer="model", folder=choice, confidence=conf,
                         evidence=p["evidence"] + ["model: %s; cites %s"
                                                   % (m.get("rationale", ""), ", ".join(m["cited_tests"]))])
        if pid in owner:
            o = owner[pid]
            choice = rel_path(o.get("folder", "").strip())
            if not choice or not under(choice, roots):
                errors.append("%s: owner folder %r is not under %s" % (pid, o.get("folder"), ", ".join(roots)))
            elif not (o.get("owner", "").strip() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", o.get("date", "").strip())):
                errors.append("%s: the owner row needs owner and date (YYYY-MM-DD)" % pid)
            else:
                if p["folder"] and p["folder"] != choice:
                    p["evidence"].append("owner overrode %s (%s)" % (p["folder"], p["layer"]))
                p.update(layer="owner", folder=choice, confidence=1.0,
                         evidence=p["evidence"] + ["owner %s on %s: %s" % (o["owner"].strip(), o["date"].strip(),
                                                                           o.get("note", "").strip())])
                if not os.path.isdir(os.path.join(repo, choice)):
                    p["evidence"].append("new folder: create it in the PR")
        if p["layer"] == "unplaced":
            p["candidates"] = p["candidates"] or sorted(folders)
        cases.append(p)
        r["placement"] = {k: p[k] for k in ("layer", "folder", "confidence", "evidence")}
    counts = collections.Counter(p["layer"] for p in cases)
    doc = {"team": team, "repo": {"path": repo, "commit": head}, "roots": roots, "created": now(),
           "counts": dict(counts), "cases": cases, "candidates": candidates}
    save_json(run_file(run, "placement", team + ".json"), doc)
    save_ledger(run, ledger)
    print("%s placement: %s" % (team, ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing"))
    unplaced = [p["polarion_id"] for p in cases if p["layer"] == "unplaced"]
    if unplaced:
        print("unplaced (model, then owner): %s -> %s" % (", ".join(unplaced),
                                                       run_file(run, "placement", team + ".json")))
    if errors:
        raise Failed(errors)
    return 0


# -------------------------------------------------------------- W4: package

def registered_markers(repo):
    """(marker names the repo registers, whether it runs with --strict-markers)."""
    names, strict = set(BUILTIN_MARKS), False
    ini = os.path.join(repo, "pytest.ini")
    if os.path.exists(ini):
        cp = configparser.RawConfigParser()
        cp.read(ini, encoding="utf-8")
        if cp.has_section("pytest"):
            for line in cp.get("pytest", "markers", fallback="").splitlines():
                if line.strip():
                    names.add(re.split(r"[:(\s]", line.strip(), maxsplit=1)[0])
            strict = "--strict-markers" in cp.get("pytest", "addopts", fallback="")
    return names, strict


def test_functions(tree):
    """(function, enclosing class or None) for every test in a module."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            out.append((node, None))
        elif isinstance(node, ast.ClassDef):
            out += [(n, node) for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]
    return out


def span(node):
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return set(range(first, node.end_lineno + 1))


def markers_entry_lines(src, func, pid):
    """Lines to drop to take `- polarion("pid")` out of a test's docstring.

    The whole Markers: section goes when that entry was its only one.
    """
    doc = func.body[0] if func.body and isinstance(func.body[0], ast.Expr) else None
    if not (doc and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str)):
        return set()
    lines = range(doc.lineno, doc.end_lineno + 1)
    entry = next((n for n in lines if re.match(r"""\s*-\s*polarion\(\s*["']%s["']""" % re.escape(pid),
                                                src[n - 1])), None)
    if entry is None:
        return set()
    head = next((n for n in range(entry - 1, doc.lineno - 1, -1)
                 if re.match(r"\s*Markers:\s*$", src[n - 1])), None)
    rest = []
    for n in range(entry + 1, doc.end_lineno + 1):
        if not src[n - 1].strip() or re.match(r"\s*[A-Z][A-Za-z ]*:", src[n - 1]):
            break
        rest.append(n)
    others = head is not None and any(src[n - 1].strip() for n in range(head + 1, entry))
    if head is None or rest or others:
        return {entry}
    drop = set(range(head, entry + 1))
    if entry < doc.end_lineno and not src[entry].strip():
        drop.add(entry + 1)
    return drop


def build_module(text, tree, keep, strip, mode="markers"):
    """The module with only the tests in `keep` ({function: polarion id}).

    Drops decorators named in `strip`. The tests repo's flake8 PolarionIds
    plugin (PID001) wants a polarion decorator on every test, stubs included.
    "markers" keeps the id under the docstring's Markers: and adds
    `# noqa: PID001` to the def line; "decorator" adds @pytest.mark.polarion
    and drops the Markers: entry.
    """
    src = text.splitlines()
    drop, suffix, before = set(), {}, {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test") \
                and node not in keep:
            drop |= span(node)
            drop |= {s.lineno for s in tree.body if assigns_test_false(s) == node.name}
        elif isinstance(node, ast.ClassDef):
            tests = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name.startswith("test")]
            if tests and not any(t in keep for t in tests):
                drop |= span(node)
                continue
            for t in tests:
                if t not in keep:
                    drop |= span(t)
    for func, pid in keep.items():
        for d in func.decorator_list:
            if deco_name(d).split(".")[-1] in strip:
                drop |= set(range(d.lineno, d.end_lineno + 1))
        if mode == "decorator":
            first = min(span(func) - drop) if span(func) - drop else func.lineno
            indent = re.match(r"\s*", src[func.lineno - 1]).group(0)
            before.setdefault(first, []).append('%s@pytest.mark.polarion("%s")' % (indent, pid))
            drop |= markers_entry_lines(src, func, pid)
        elif re.search(r"#\s*noqa:\s*[\w, ]+$", src[func.lineno - 1]):
            suffix[func.lineno] = ", PID001"  # flake8 reads only the first noqa on a line
        elif not re.search(r"#\s*noqa(?!:)", src[func.lineno - 1]):
            suffix[func.lineno] = "  # noqa: PID001"
    kept = []
    for i, line in enumerate(src, 1):
        kept += before.get(i, [])
        if i not in drop:
            kept.append(line + suffix.get(i, ""))
    body = "\n".join(x for x in kept if not re.match(r"import pytest\s*$", x))
    has_import = any(re.match(r"import pytest\s*$", x) for x in kept)
    if "pytest." not in body:
        kept = [x for x in kept if not re.match(r"import pytest\s*$", x)]
    elif not has_import:
        doc = tree.body[0] if tree.body and isinstance(tree.body[0], ast.Expr) else None
        at = len([1 for n in range(doc.end_lineno) if (n + 1) not in drop]) if doc else 0
        kept[at:at] = ["", "import pytest"]
    out, blanks = [], 0
    for line in kept:
        if line.strip():
            if blanks:
                indented = line.startswith((" ", "\t"))
                out += [""] * min(blanks, 1 if indented else 2)
            out.append(line.rstrip())
            blanks = 0
        elif out:
            blanks += 1
    return "\n".join(out) + "\n"


def stub_ids(func, mode):
    """The Polarion ids a packaged stub carries, the way its policy puts them."""
    if mode == "decorator":
        return [d.args[0].value for d in func.decorator_list
                if isinstance(d, ast.Call) and deco_name(d).endswith("mark.polarion") and d.args
                and isinstance(d.args[0], ast.Constant)]
    return MARKERS_ENTRY.findall(std_validator().markers_block(ast.get_docstring(func) or ""))


def check_module(text, expected, rows, registered, strict, mode="markers"):
    """Problems with one packaged module: [str]."""
    validate = std_validator()
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return ["does not parse: %s" % e]
    errs, found, names = [], [], collections.Counter()
    parents = parent_map(tree)
    for func, cls in test_functions(tree):
        where = "%s%s" % (cls.name + "::" if cls else "", func.name)
        names[where] += 1
        if "__test__" not in (why_off(func, parents, tree) or ""):  # a skip is still collected
            errs.append("%s: would be collected; it needs __test__ = False" % where)
        if body_statements(func) or fixture_args(func):
            errs.append("%s: has an implementation or fixtures; a design stub has only its docstring"
                        % where)
        doc = ast.get_docstring(func) or ""
        pids = stub_ids(func, mode)
        if len(pids) != 1:
            errs.append("%s: needs exactly one Polarion id (%s), found %d" % (
                where, "@pytest.mark.polarion" if mode == "decorator" else "`- polarion(\"ID\")` under Markers:",
                len(pids)))
            continue
        pid = pids[0]
        found.append(pid)
        if pid not in expected:
            errs.append("%s: %s is not an approved case placed in this folder" % (where, pid))
            continue
        url = rows[pid]["decision"].get("chosen_jira") or rows[pid]["jira_url"]
        if not validate.links_jira(doc, url):
            errs.append("%s: no `Jira: %s` line for its own requirement" % (where, url))
        if len(validate.REFERENCE_LINE.findall(doc)) != 1:
            errs.append("%s: needs exactly one STP:/Jira: line" % where)
        problem = validate.source_problem(doc, {"source_pse": rows[pid]["pse"]["source"],
                                                "source_missing": rows[pid]["pse"]["missing"],
                                                "review_note": rows[pid]["decision"].get("pse_note")})
        if problem:
            errs.append("%s: %s" % (where, problem))
    errs += ["%s: defined %d times" % (n, k) for n, k in names.items() if k > 1]
    errs += ["%s: listed by %d tests" % (p, k) for p, k in collections.Counter(found).items() if k > 1]
    errs += ["%s: no stub" % p for p in sorted(set(expected) - set(found))]
    m = LIVE_MARK.search(text)
    if m and mode != "decorator":
        errs.append("a live `%s` would mark the case Automated on merge (the decision gate keeps "
                    "the id under Markers:)" % m.group(0))
    for name in sorted(set(re.findall(r"pytest\.mark\.(\w+)", text))):
        if strict and name not in registered:
            errs.append("@pytest.mark.%s is not registered and the repo runs --strict-markers" % name)
    if HTML_TAG.search(text):
        errs.append("raw HTML from the export: %s" % HTML_TAG.search(text).group(0))
    return errs


def std_validator():
    sys.path.insert(0, os.path.join(HERE, "..", "std-reviewer"))
    import validate_std
    return validate_std


def cmd_package(a):
    run = a.run
    ledger = load_ledger(run)
    teams = load_teams(run)
    team = a.team
    url, key = tracking(teams, team)
    repo = tests_repo(run, a.tests_repo)
    rows = {r["polarion_id"]: r for r in team_rows(ledger, team)}
    if not rows:
        print("%s: no approved migrate case; nothing to package" % team)
        return 0
    unplaced = [p for p, r in rows.items() if (r.get("placement") or {}).get("layer", "unplaced") == "unplaced"]
    if unplaced:
        raise Problem("not placed yet: %s (run `place`; the owner settles the rest)" % ", ".join(unplaced))
    roots = (teams["teams"].get(team) or {}).get("roots") or []
    outside = [p for p, r in rows.items() if not under(r["placement"]["folder"] or "", roots)]
    if outside:  # placed while the case was another team's
        raise Problem("placed outside %s's roots (%s): %s; re-run `place --team %s`"
                      % (team, ", ".join(roots), ", ".join(outside), team))
    std_file = a.std or os.path.join(a.outputs, key, "std", key + "_test_description.yaml")
    stub_dir = a.stubs or os.path.join(a.outputs, key, "std", "python-tests")
    with open(std_file, encoding="utf-8") as f:
        std = yaml.safe_load(f)
    by_test_id = {s.get("test_id"): s for s in std.get("scenarios") or []}
    registered, strict = registered_markers(repo)
    strip = {"qf_test_id"} - registered
    out_dir = run_file(run, "package", team)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    errors, files, seen, removed = [], [], {}, set()
    existing = scan_repo(repo)
    for stub in sorted(glob_py(stub_dir)):
        with open(stub, encoding="utf-8") as f:
            text = f.read()
        tree = ast.parse(text)
        groups = collections.OrderedDict()
        for func, _ in test_functions(tree):
            tid = next(iter(re.findall(r"\[(TS-[A-Za-z0-9-]+)\]", ast.get_docstring(func) or "")), None)
            pid = (by_test_id.get(tid) or {}).get("polarion_id")
            if not pid:
                pids = MARKERS_ENTRY.findall(std_validator().markers_block(ast.get_docstring(func) or ""))
                pid = pids[0] if len(pids) == 1 else None
            where = "%s::%s" % (os.path.basename(stub), func.name)
            if pid not in rows:
                errors.append("%s: %s is not an approved migrate case of %s" % (where, pid, team))
                continue
            if pid in seen:
                errors.append("%s: %s is already stubbed by %s" % (where, pid, seen[pid]))
                continue
            seen[pid] = where
            groups.setdefault(rows[pid]["placement"]["folder"], []).append((func, pid))
        name = a.module or re.sub(r"_stubs(?=\.py$)", "", os.path.basename(stub))
        for folder, members in groups.items():
            target = "%s/%s" % (folder, name)
            module = build_module(text, tree, dict(members), strip, a.polarion_marker)
            # Only an older stub still carries one: stub-generator no longer emits it.
            removed |= strip & {deco_name(d).split(".")[-1] for f, _ in members for d in f.decorator_list}
            expected = {p for _, p in members}
            errs = check_module(module, expected, rows, registered, strict, a.polarion_marker)
            if target in [f["path"] for f in files]:
                errs.append("two stub modules would both become %s: pass a different --module" % target)
            if os.path.exists(os.path.join(repo, target)):
                errs.append("%s already exists in the tests repo: pick another name with --module" % target)
            clash = [p for p in glob_py(os.path.join(repo, "tests"), recursive=True)
                     if os.path.basename(p) == name]
            if clash and not os.path.exists(os.path.join(repo, folder, "__init__.py")):
                errs.append("%s: module name already used at %s and %s has no __init__.py"
                            % (target, os.path.relpath(clash[0], repo), folder))
            for p in expected:
                if existing.get(p):
                    errs.append("%s: %s already appears in the tests repo: %s"
                                % (target, p, "; ".join(fmt_occ(o) for o in existing[p])))
            errors += ["%s: %s" % (target, e) for e in errs]
            dst = os.path.join(out_dir, target)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(module)
            mod_tree = ast.parse(module) if not errs else None
            tests = []
            for func, cls in (test_functions(mod_tree) if mod_tree else []):
                pid = stub_ids(func, a.polarion_marker)[0]
                node = "%s::%s%s" % (target, cls.name + "::" if cls else "", func.name)
                tests.append({"node": node, "polarion_id": pid,
                              "jira_url": rows[pid]["decision"].get("chosen_jira") or rows[pid]["jira_url"]})
                rows[pid]["package"] = {"path": target, "node": node, "polarion_marker": a.polarion_marker}
            files.append({"path": target, "source": stub, "tests": tests})
    for pid in sorted(set(rows) - set(seen)):
        errors.append("%s: approved for migration but no stub in %s" % (pid, stub_dir))
    manifest = {"team": team, "tracking_jira": url, "created": now(), "std": std_file,
                "repo": {"path": repo, "commit": git(repo, "rev-parse", "HEAD")},
                "stripped_markers": sorted(removed), "polarion_marker": a.polarion_marker,
                "valid": not errors, "errors": errors,
                "files": files}
    save_json(os.path.join(out_dir, "manifest.json"), manifest)
    save_ledger(run, ledger)
    print("%s: %d module(s), %d stub(s) -> %s" % (team, len(files), sum(len(f["tests"]) for f in files), out_dir))
    if removed:
        print("removed @pytest.mark.%s: the tests repo does not register it" % ", ".join(sorted(removed)))
    if errors:
        raise Failed(errors)
    return 0


def glob_py(d, recursive=False):
    out = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in SKIP_DIRS] if recursive else []
        out += [os.path.join(root, f) for f in files
                if f.endswith(".py") and f not in ("__init__.py", "conftest.py")]
    return out


# ----------------------------------------------------------------- W5: stage

def cmd_stage(a):
    run = a.run
    ledger = load_ledger(run)
    team = a.team
    pkg = run_file(run, "package", team)
    manifest_path = os.path.join(pkg, "manifest.json")
    if not os.path.exists(manifest_path):
        raise Problem("no package for %s: run `package` first" % team)
    manifest = load_json(manifest_path)
    if not manifest["valid"]:
        raise Problem("the %s package failed its checks; fix and re-run `package`" % team)
    # The package must still match the team's decisions and placements.
    want = {r["polarion_id"]: (r.get("placement") or {}).get("folder") for r in team_rows(ledger, team)}
    got = {t["polarion_id"]: os.path.dirname(f["path"]) for f in manifest["files"] for t in f["tests"]}
    if want != got:
        changed = sorted(p for p in set(want) | set(got) if want.get(p) != got.get(p))
        raise Problem("the %s package no longer matches the ledger (%s): re-run `place` and `package`"
                      % (team, ", ".join(changed)))
    co = a.checkout
    if git(co, "rev-parse", "HEAD") is None:
        raise Problem("%s is not a git checkout" % co)
    if git(co, "status", "--porcelain"):
        raise Problem("%s has uncommitted changes: stage into a clean, fresh checkout" % co)
    base = git(co, "rev-parse", "HEAD")
    origin = git(co, "rev-parse", "--verify", "-q", "origin/main")
    if origin != base:
        raise Problem("%s is at %s, origin/main is %s: fetch, and stage from a checkout of origin/main"
                      % (co, base[:12], (origin or "missing")[:12]))
    key = JIRA_URL.fullmatch(manifest["tracking_jira"]).group(1)
    branch = a.branch or "polarion-migration/%s-%s" % (team, key.lower())
    if git(co, "rev-parse", "--verify", "-q", "refs/heads/" + branch):
        raise Problem("branch %s already exists in %s" % (branch, co))
    # Re-run the inventory against the new base: the repo may have moved.
    inventory = scan_repo(co)
    by_id = {r["polarion_id"]: r for r in team_rows(ledger, team)}
    errors = []
    paths = [f["path"] for f in manifest["files"]]
    for f in manifest["files"]:
        if os.path.exists(os.path.join(co, f["path"])):
            errors.append("%s already exists on the new base" % f["path"])
        owned = all(by_id[t["polarion_id"]]["placement"]["layer"] == "owner" for t in f["tests"])
        if not owned and not os.path.isdir(os.path.join(co, os.path.dirname(f["path"]))):
            errors.append("%s: folder %s is missing on the new base" % (f["path"], os.path.dirname(f["path"])))
        for t in f["tests"]:
            if inventory.get(t["polarion_id"]):
                errors.append("%s now appears on the new base: %s" % (
                    t["polarion_id"], "; ".join(fmt_occ(o) for o in inventory[t["polarion_id"]])))
    if errors:
        raise Failed(errors)
    if git(co, "switch", "-c", branch) is None:
        raise Problem("could not create branch %s in %s" % (branch, co))
    for p in paths:
        os.makedirs(os.path.dirname(os.path.join(co, p)), exist_ok=True)  # an owner-approved new folder
        shutil.copyfile(os.path.join(pkg, p), os.path.join(co, p))
    git(co, "add", "--", *paths)
    staged = sorted((git(co, "diff", "--cached", "--name-only") or "").splitlines())
    if staged != sorted(paths):
        errors.append("staged files differ from the package: %s" % ", ".join(sorted(set(staged) ^ set(paths))))
    results = []
    if a.checks:
        if shutil.which("pre-commit"):
            proc = subprocess.run(["pre-commit", "run", "--files"] + paths, cwd=co, capture_output=True, text=True)
            results.append(("pre-commit run --files %s" % " ".join(paths), proc.returncode,
                            (proc.stdout + proc.stderr)[-2000:]))
            git(co, "add", "--", *paths)  # hooks may have reformatted
        else:
            results.append(("pre-commit run --files ...", None, "pre-commit is not installed"))
        # Collection with the repo's own pytest and markers, minus its cluster
        # setup (conftest.py and --tc-file need a cluster): proves the stubs
        # import, stay uncollected, and use only registered marks.
        python = os.path.join(co, ".venv", "bin", "python")
        cmd = ["-m", "pytest", "-o", "addopts=--strict-markers", "-p", "no:cacheprovider",
               "--noconftest", "--collect-only", "-q"] + paths
        if os.path.exists(python):
            proc = subprocess.run([python] + cmd, cwd=co, capture_output=True, text=True)
            # 5 = no tests collected: what disabled stubs give. 0 means a stub was collected.
            code = 0 if proc.returncode == 5 else proc.returncode or 1
            results.append(("pytest " + " ".join(cmd[2:]), code, (proc.stdout + proc.stderr)[-2000:]))
        else:
            results.append(("pytest --collect-only (strict markers)", None,
                            "no .venv in the checkout; run `uv sync` there first"))
    body = pr_body(ledger, team, manifest, branch, base, results)
    os.makedirs(run_file(run, "pr", team), exist_ok=True)
    with open(run_file(run, "pr", team, "PR_BODY.md"), "w", encoding="utf-8") as f:
        f.write(body)
    for f in manifest["files"]:
        for t in f["tests"]:
            row = next(r for r in ledger["rows"]
                       if r["polarion_id"] == t["polarion_id"] and r["state"] in ("resolved", "held"))
            row["stage"] = {"branch": branch, "base": base, "checkout": os.path.abspath(co), "staged": now()}
    save_ledger(run, ledger)
    print("staged %d file(s) on branch %s in %s (base %s)" % (len(paths), branch, co, base[:12]))
    for cmd, code, _ in results:
        print("check: %s -> %s" % (cmd, "not run" if code is None else "exit %d" % code))
    print("PR body: %s" % run_file(run, "pr", team, "PR_BODY.md"))
    print("next (by hand, after review of the diff): git -C %s commit -s; push; open the PR with that body"
          % co)
    if errors or any(code for _, code, _ in results):
        raise Failed(errors or ["a check failed; see the PR body"])
    return 0


def pr_body(ledger, team, manifest, branch, base, results):
    by_id = {r["polarion_id"]: r for r in ledger["rows"] if r["state"] in ("resolved", "held")}
    tests = [t for f in manifest["files"] for t in f["tests"]]
    out = ["## Polarion migration: %s design stubs (%d cases)" % (team, len(tests)), "",
           "Tracking: %s" % manifest["tracking_jira"], "",
           "These are **design stubs** (Phase 1, `__test__ = False`), not tests that run. Each one "
           "carries a Polarion test case that was not automated, its own Jira requirement, and its "
           "steps from Polarion; a `Source:` line marks any section that Polarion lacked and "
           "QualityFlow proposed.", "",
           "| Polarion | Jira requirement | Stub | Decision |", "|---|---|---|---|"]
    for t in tests:
        d = by_id[t["polarion_id"]]["decision"]
        jira_key = JIRA_URL.fullmatch(t["jira_url"]).group(1)
        out.append("| %s | [%s](%s) | `%s` | %s (%s, %s) |" % (
            t["polarion_id"], jira_key, t["jira_url"], t["node"], d["decision"], d["reviewer"], d["date"]))
    out += ["", "### Polarion IDs and state", ""]
    if manifest.get("polarion_marker") == "decorator":
        out.append("- Each stub carries its case's real `@pytest.mark.polarion(\"ID\")`, as this "
                   "repository's polarion lint requires. On merge, the `mark-automated-polarion` job "
                   "marks these cases Automated: the Polarion owner approved counting a design stub as "
                   "Automated.")
    else:
        out.append("- Each stub lists its Polarion ID under its docstring `Markers:` as "
                   "`polarion(\"ID\")`, and its `def` line carries `# noqa: PID001`: there is no "
                   "`@pytest.mark.polarion` decorator yet, so the post-merge `mark-automated-polarion` "
                   "job leaves these cases as they are. The Phase 2 PR that implements a test turns "
                   "the entry into the real decorator and drops the noqa, as "
                   "docs/SOFTWARE_TEST_DESCRIPTION.md describes for `Markers:`.")
    if manifest["stripped_markers"]:
        out.append("- Removed `@pytest.mark.%s`: this repository runs pytest with `--strict-markers` "
                   "and does not register it." % ", ".join(manifest["stripped_markers"]))
    out += ["", "### Validation", "",
            "- QualityFlow package checks passed: syntax, every stub excluded from collection, docstring "
            "only, one Polarion ID and its own `Jira:` line per stub, no duplicate IDs against base "
            "`%s`, no raw export markup." % base[:12]]
    for cmd, code, tail in results:
        out.append("- `%s`: %s" % (cmd, "not run (%s)" % tail if code is None else "exit %d" % code))
    out.append("- Collection: `tox -e pytest-check-x86` (CI).")
    others = collections.Counter(
        (r.get("decision") or {}).get("decision") or ("held" if r["state"] == "held" else "no decision")
        for r in by_id.values()
        if r.get("team") == team and (r.get("decision") or {}).get("decision") != "migrate")
    if others:
        out += ["", "### Not in this PR", ""]
        out += ["- %s: %d case(s)" % kv for kv in sorted(others.items())]
        out.append("- Retired, linked and held cases go to the Polarion owner as a separate proposal.")
    out.append("")
    return "\n".join(out)


def cmd_record_pr(a):
    run = a.run
    ledger = load_ledger(run)
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+", a.url):
        raise Problem("--url must be a GitHub pull request URL")
    rows = [r for r in ledger["rows"] if r.get("team") == a.team and r.get("stage")]
    if not rows:
        raise Problem("no staged case for team %s" % a.team)
    inventory = scan_repo(a.checkout) if a.checkout else {}
    problems = []
    for r in rows:
        r["pr"] = {"url": a.url, "state": a.state, "commit": a.commit, "recorded": now()}
        if a.checkout:
            occ = inventory.get(r["polarion_id"], [])
            where = [o for o in occ if o["kind"] == "markers-entry" or o["kind"] in LIVE_KINDS]
            r["stub_location"] = ["%s:%s" % (o["path"], o["line"]) for o in where]
            if not where:
                problems.append("%s: no stub carrying it in %s" % (r["polarion_id"], a.checkout))
            elif r.get("package") and where[0]["path"] != r["package"]["path"]:
                r["pr"]["moved_from"] = r["package"]["path"]
            if (r.get("package") or {}).get("polarion_marker") != "decorator" and any(
                    o["kind"] in LIVE_KINDS and not o.get("implemented") for o in occ):
                problems.append("%s: its stub got a live @pytest.mark.polarion in review, so the post-merge "
                                "job marks the case Automated: take the decorator out (the Markers: entry "
                                "stays) and have the Polarion owner set it back" % r["polarion_id"])
    save_ledger(run, ledger)
    print("recorded %s (%s) for %d case(s)" % (a.url, a.state, len(rows)))
    if problems:
        raise Failed(problems)
    return 0


# -------------------------------------------------------------- W6: reconcile

RECONCILE = ("polarion_id", "team", "original_status", "original_automation", "decision", "jira_url",
             "evidence", "proposed_status", "proposed_automation", "reason", "ready_to_apply")


def propose(r, inventory, sync_verified):
    """The Polarion change one case's decision and the code on main support.

    Automated needs the real ID on main: an implemented test, or (decorator
    policy) the merged stub's live decorator. The post-merge job that sets
    Automated also sets Status approved, so both are proposed.
    """
    d = r.get("decision") or {}
    occ = inventory.get(r["polarion_id"], [])
    impl = implemented_evidence(occ)
    live_stub = [o for o in occ if o["kind"] in LIVE_KINDS and not o.get("implemented")]
    policy = (r.get("package") or {}).get("polarion_marker")
    p = {"proposed_status": "", "proposed_automation": "", "ready": False, "reason": "",
         "evidence": "; ".join(fmt_occ(o) for o in impl or live_stub) or (r.get("pr") or {}).get("url", "")}
    later = "" if sync_verified else "; ready once the owner verifies how the sync marks it"
    decision = d.get("decision")
    if not decision:
        p["reason"] = "no team decision yet"
    elif decision == "hold":
        p["reason"] = "held: %s" % d.get("rationale")
    elif decision == "retire" and impl:
        p["reason"] = ("retired, but implemented test %s still carries the ID: the team settles it"
                       % impl[0].get("test", impl[0]["path"]))
    elif decision == "retire":
        p.update(proposed_status="inactive", ready=True,
                 reason="team-approved retirement: %s (Polarion owner %s)" % (d.get("retire_reason"),
                                                                            d.get("polarion_owner")))
    elif impl:
        p.update(proposed_status="approved", proposed_automation="automated", ready=bool(sync_verified),
                 reason="implemented test %s carries the real ID" % impl[0].get("test", impl[0]["path"]) + later)
    elif decision == "migrate" and policy == "decorator" and (r.get("pr") or {}).get("state") == "merged" \
            and live_stub:
        p.update(proposed_status="approved", proposed_automation="automated", ready=bool(sync_verified),
                 reason="stub %s with the real decorator merged; the owner chose to count stubs as "
                 "Automated" % live_stub[0].get("test", live_stub[0]["path"]) + later)
    elif decision == "migrate" and policy and policy != "decorator" and live_stub:
        p.update(proposed_automation="notautomated",
                 reason="its stub %s has a live @pytest.mark.polarion, which the post-merge job turns into "
                 "Automated: take the decorator out, then set it back" % fmt_occ(live_stub[0]))
    elif decision == "link-existing":
        test = d.get("existing_test")
        if any(o.get("test") == test for o in inventory.get(r["polarion_id"], [])):
            p["reason"] = "the ID is on %s, which is not implemented yet: pending until it is" % test
        else:
            p["reason"] = ("attach the ID to %s first" if d.get("attach_id") == "yes" else
                           "covered by %s without its ID: the team decides attach or retire") % test
    elif any(o["kind"] == "markers-entry" or o["kind"] in LIVE_KINDS for o in occ):
        p["reason"] = ("stub only (an end-state gap): it stays active until a Phase 2 test with the "
                       "real ID is merged")
    else:
        p["reason"] = "approved for migration; no stub with its ID on main yet (PR: %s)" % (
            (r.get("pr") or {}).get("state") or "none recorded")
    return p


def cmd_reconcile(a):
    run = a.run
    ledger = load_ledger(run)
    repo = tests_repo(run, a.tests_repo)
    inventory = scan_repo(repo)
    head = git(repo, "rev-parse", "HEAD")
    per_team, audit = collections.OrderedDict(), []
    for r in ledger["rows"]:
        if r["state"] in ("invalid", "duplicate"):
            continue
        src = r["source"]
        if r["state"] == "excluded":
            if norm(src.get("automation")) == "automated" and not implemented_evidence(
                    inventory.get(r["polarion_id"], [])):
                audit.append({"polarion_id": r["polarion_id"], "original_status": src.get("status", ""),
                              "original_automation": src.get("automation", ""),
                              "jira_url": r.get("jira_url") or "",
                              "code": "; ".join(fmt_occ(o) for o in inventory.get(r["polarion_id"], [])) or "none",
                              "note": "Automated in Polarion, no implemented test with this ID at %s"
                                      % (head or "")[:12]})
            continue
        p = propose(r, inventory, a.sync_verified)
        r["cleanup"] = dict(p, at=head, created=now())
        team = r.get("team") or "unassigned"
        per_team.setdefault(team, []).append({
            "polarion_id": r["polarion_id"], "team": team, "original_status": src.get("status", ""),
            "original_automation": src.get("automation", ""),
            "decision": (r.get("decision") or {}).get("decision", ""),
            "jira_url": (r.get("decision") or {}).get("chosen_jira") or r.get("jira_url") or "",
            "evidence": p["evidence"], "proposed_status": p["proposed_status"],
            "proposed_automation": p["proposed_automation"], "reason": p["reason"],
            "ready_to_apply": "yes" if p["ready"] else "no"})
    for team, rows in per_team.items():
        write_csv(run_file(run, "reconcile", team + ".csv"), RECONCILE, rows)
        ready = sum(1 for x in rows if x["ready_to_apply"] == "yes")
        print("%s: %d case(s), %d ready to apply -> %s" % (team, len(rows), ready,
                                                         run_file(run, "reconcile", team + ".csv")))
    write_csv(run_file(run, "reconcile", "audit_automated_without_code.csv"),
              ("polarion_id", "original_status", "original_automation", "jira_url", "code", "note"), audit)
    print("audit: %d case(s) Automated in Polarion with no implemented test in %s" % (len(audit), repo))
    save_ledger(run, ledger)
    return 0


def cmd_verify(a):
    run = a.run
    ledger = load_ledger(run)
    enc = load_manifest(run)["inputs"]["cases"]["encoding"]
    header, _, records = read_csv(a.export, enc)
    overrides = parse_pairs(a.col, COLUMNS, "--col")
    cols = map_columns(header, overrides, ("id", "status", "automation"), a.export)
    fresh = {}
    for _, _, cells, _ in records:
        get = getter(cells, cols)
        if get("id") and not ("type" in cols and get("type") and norm(get("type")) != "testcase"):
            fresh[get("id")] = (get("status"), get("automation"))
    results = collections.Counter()
    problems, known = [], set()
    for r in ledger["rows"]:
        if r["state"] in ("invalid", "duplicate"):
            continue
        pid = r["polarion_id"]
        known.add(pid)
        if pid not in fresh:
            problems.append("%s: missing from the fresh export" % pid)
            continue
        want = [r["source"].get("status", ""), r["source"].get("automation", "")]
        c = r.get("cleanup") or {}
        if c.get("ready"):
            want = [c.get("proposed_status") or want[0], c.get("proposed_automation") or want[1]]
        got = fresh[pid]
        if [norm(x) for x in want] == [norm(x) for x in got]:
            results["applied as proposed" if c.get("ready") else "unchanged as expected"] += 1
        else:
            problems.append("%s: expected Status %r / Automation %r, the export has %r / %r%s" % (
                pid, want[0], want[1], got[0], got[1], "" if c.get("ready") else " (not a proposed change)"))
    new = sorted(set(fresh) - known)
    report = {"created": now(), "export": os.path.abspath(a.export), "sha256": sha256(a.export),
              "results": dict(results), "problems": problems, "new_ids": new}
    save_json(run_file(run, "reconcile", "verify.json"), report)
    for k, v in sorted(results.items()):
        print("%-24s %d" % (k, v))
    if new:
        print("not in the ledger (new in this export): %s" % ", ".join(new))
    if problems:
        raise Failed(problems)
    print("the fresh export matches the ledger")
    return 0


# ----------------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="run the built-in end-to-end check")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, helptext):
        p = sub.add_parser(name, help=helptext, description=helptext)
        p.add_argument("run", help="run directory, e.g. outputs/polarion/2026-10-sample")
        p.set_defaults(fn=fn)
        return p

    p = add("init", cmd_init, "W0: freeze the exports and the tests-repo snapshot")
    p.add_argument("--cases", required=True, help="CSV export of the test cases")
    p.add_argument("--requirements", help="CSV export of the requirements they link "
                   "(omit when one export holds both item types)")
    p.add_argument("--tests-repo", help="a clean checkout of openshift-virtualization-tests at origin/main")
    p.add_argument("--query", help="the Polarion query the export came from")
    p.add_argument("--exported-at", help="when it was exported")
    p.add_argument("--exported-by", help="who exported it")
    p.add_argument("--note")
    p.add_argument("--expect-cases", type=int, help="the case count the owner expects")
    p.add_argument("--encoding", default="utf-8-sig")

    p = add("ledger", cmd_ledger, "W1: build the case ledger and reconcile the counts")
    p.add_argument("--col", action="append", default=[], metavar="FIELD=HEADER",
                   help="export header for a field; fields: %s" % ", ".join(COLUMNS))
    p.add_argument("--allow", action="append", default=[], metavar="FIELD=VALUE[=MEANING]",
                   help="accept a status, automation, type or role value once the owner confirms it; "
                        "MEANING maps it to a built-in one, e.g. \"automation=Automated (CI)=automated\"")
    p.add_argument("--jira-base", help="Jira base URL, e.g. https://redhat.atlassian.net: bare keys and links "
                   "on either Red Hat Jira host become {base}/browse/KEY")
    p.add_argument("--jira-projects", help="comma-separated Jira projects a requirement may link, e.g. CNV")
    p.add_argument("--tests-repo", help="override the checkout frozen by init")
    p.add_argument("--collected", help="output of `pytest --collect-only -q` in the tests repo")
    p.add_argument("--force", action="store_true", help="rebuild even if triage/review results exist")

    p = add("teams", cmd_teams, "freeze the owner-approved team map (teams.yaml)")
    p.add_argument("file")
    p.add_argument("--tests-repo")

    p = add("triage", None, "W2: queue requirement groups, or merge the agent's verdicts")
    p.add_argument("action", choices=("queue", "merge"))
    p.add_argument("--allow-defects", action="store_true")
    p.add_argument("--group", help="merge: only this Jira key's group")
    p.add_argument("--dry-run", action="store_true", help="merge: check, write nothing")

    p = add("review", None, "W3: team sheets, decision import, calibration")
    p.add_argument("action", choices=("sheets", "import", "calibrate"))
    p.add_argument("sheet", nargs="?", help="the filled sheet, for import")
    p.add_argument("--tests-repo")
    p.add_argument("--force", action="store_true")

    p = add("scenarios", cmd_scenarios, "W4: std-builder scenario lists for approved migrate cases")
    p.add_argument("--team")
    p.add_argument("--tier", help='tier label for every scenario, e.g. "Tier 2"')
    p.add_argument("--outputs", default="outputs", help="QF outputs root")

    p = add("place", cmd_place, "W4: place each approved stub")
    p.add_argument("--team", required=True)
    p.add_argument("--tests-repo")
    p.add_argument("--min-confidence", type=float, default=0.7)

    p = add("package", cmd_package, "W4: split std-builder stubs into tests-repo modules")
    p.add_argument("--team", required=True)
    p.add_argument("--tests-repo")
    p.add_argument("--std", help="STD YAML (default outputs/{KEY}/std/{KEY}_test_description.yaml)")
    p.add_argument("--stubs", help="stub dir (default outputs/{KEY}/std/python-tests)")
    p.add_argument("--module", help="module file name in each folder (default: the stub's, without _stubs)")
    p.add_argument("--polarion-marker", choices=("markers", "decorator"), default="markers",
                   help="markers (default, the decision gate): the id under Markers: plus `# noqa: PID001`; "
                        "decorator: @pytest.mark.polarion on the stub, only on the owner's say-so")
    p.add_argument("--outputs", default="outputs")

    p = add("stage", cmd_stage, "W5: copy a team's package into a fresh tests-repo branch")
    p.add_argument("--team", required=True)
    p.add_argument("--checkout", required=True, help="a clean checkout to branch from")
    p.add_argument("--branch")
    p.add_argument("--checks", action="store_true", help="run pre-commit on the staged files")

    p = add("record-pr", cmd_record_pr, "W5: record a team's PR and where its stubs ended up")
    p.add_argument("--team", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--state", required=True, choices=("open", "merged", "closed"))
    p.add_argument("--commit")
    p.add_argument("--checkout", help="a checkout of the merged result, to find the stubs")

    p = add("reconcile", cmd_reconcile, "W6: proposed Polarion changes per team")
    p.add_argument("--tests-repo", help="a checkout of the current main")
    p.add_argument("--sync-verified", action="store_true",
                   help="the owner verified how the sync marks an implemented test Automated")

    p = add("verify", cmd_verify, "W6: diff a fresh export against the proposal")
    p.add_argument("export")
    p.add_argument("--col", action="append", default=[], metavar="FIELD=HEADER")
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self_test(tmp)
        return 0
    if not a.cmd:
        ap.print_help()
        return 2
    fn = a.fn or {("triage", "queue"): cmd_triage_queue, ("triage", "merge"): cmd_triage_merge,
                  ("review", "sheets"): cmd_review_sheets, ("review", "import"): cmd_review_import,
                  ("review", "calibrate"): cmd_review_calibrate}[(a.cmd, a.action)]
    if a.cmd == "review" and a.action == "import" and not a.sheet:
        ap.error("review import needs the filled sheet")
    try:
        return fn(a)
    except Problem as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except Failed as e:
        for err in e.errors:
            print("FAIL: %s" % err, file=sys.stderr)
        return 1


# ------------------------------------------------------------------ self-test

def self_test(tmp):
    """The whole flow, W0-W6, on a synthetic export and a throwaway tests repo."""
    def sh(cwd, *cmd):
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)

    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def ok(*argv):
        code = main(list(argv))
        assert code == 0, (argv, code)

    def fails(code, *argv):
        got = main(list(argv))
        assert got == code, (argv, got)

    # A tests repo: an implemented sibling (CNV-3), a parametrised one (CNV-14),
    # a disabled stub with a live marker (CNV-5), and a Markers: mention (CNV-12).
    repo = os.path.join(tmp, "ovt")
    write(os.path.join(repo, "pytest.ini"),
          "[pytest]\naddopts =\n    --strict-markers\nmarkers =\n    # General\n    polarion: Store polarion test ID\n")
    write(os.path.join(repo, "tests", "__init__.py"), "")
    write(os.path.join(repo, "tests", "network", "__init__.py"), "")
    write(os.path.join(repo, "tests", "network", "hotplug", "__init__.py"), "")
    write(os.path.join(repo, "tests", "network", "hotplug", "test_hotplug.py"),
          'import pytest\n\n\n@pytest.mark.polarion("CNV-3")\ndef test_hotplug_nic(vm):\n'
          '    """Hot-plug a NIC."""\n    assert vm.nics\n\n\n'
          '@pytest.mark.parametrize("x", [pytest.param(1, marks=pytest.mark.polarion("CNV-14"))])\n'
          'def test_param(x):\n    assert x\n')
    write(os.path.join(repo, "tests", "network", "bridge", "__init__.py"), "")
    write(os.path.join(repo, "tests", "network", "bridge", "test_bridge.py"),
          'import pytest\n\n\nclass TestBridge:\n    __test__ = False\n\n'
          '    @pytest.mark.polarion("CNV-5")\n    def test_bridge(self):\n        """Stub."""\n\n\n'
          'def test_other():\n    """\n    Markers:\n        - polarion("CNV-12")\n    """\n\n\n'
          'test_other.__test__ = False\n')
    write(os.path.join(repo, "tests", "storage", "__init__.py"), "")
    write(os.path.join(repo, "tests", "storage", "test_disk.py"), "def test_disk():\n    assert True\n")
    sh(repo, "git", "init", "-q", "-b", "main")
    sh(repo, "git", "-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A")
    sh(repo, "git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "base")

    inv = scan_repo(repo)
    assert inv["CNV-3"][0]["kind"] == "decorator" and inv["CNV-3"][0]["implemented"]
    assert inv["CNV-14"][0]["kind"] == "param" and inv["CNV-14"][0]["test"].endswith("::test_param")
    assert inv["CNV-5"][0]["disabled"] == "class __test__ = False" and not inv["CNV-5"][0]["implemented"]
    assert inv["CNV-12"][0]["kind"] == "markers-entry"
    assert implemented_evidence(inv["CNV-3"]) and not implemented_evidence(inv["CNV-5"])
    # Tests switched off by a module pytestmark, or by `Cls.__test__ = False` after the class.
    off = scan_file("tests/x/test_s.py", 'import pytest\n\npytestmark = [pytest.mark.skip(reason="r")]\n\n\n'
                    '@pytest.mark.polarion("CNV-30")\ndef test_a(vm):\n    """A."""\n')
    assert off[0]["disabled"] == "module pytestmark skip" and not implemented_evidence(off)
    off = scan_file("tests/x/test_l.py", 'import pytest\n\n\nclass TestL:\n    @pytest.mark.polarion("CNV-31")\n'
                    '    def test_b(self, vm):\n        pass\n\n\nTestL.__test__ = False\n')
    assert off[0]["disabled"] == "class __test__ = False"

    # Links: several per cell, a role with no colon, an ID inside a title.
    assert parse_links("verifies: CNV-1 - A, verifies: CNV-2 - B") == [("CNV-1", "verifies"), ("CNV-2", "verifies")]
    assert parse_links("verifies CNV-1; relates_to: CNV-2 - see CNV-3") == [("CNV-1", "verifies"),
                                                                          ("CNV-2", "relates to")]
    assert parse_links("CNV-1 - Hot-plug, unplug (verifies)<br/>CNV-4") == [("CNV-1", "verifies"), ("CNV-4", "")]
    # Steps: a header row names the columns, a further column stays on its step, an index
    # column is dropped, text outside the table is kept, and unclosed cells close.
    st, ex, _ = split_steps("<p>Use two workers</p><table><tr><th>Step</th><th>Expected Result</th>"
                            "<th>Notes</th></tr><tr><td>Start the VM<td>VM runs<td>RHEL 9</table>")
    assert st == ["Use two workers", "Start the VM; Notes: RHEL 9"] and ex == ["VM runs"], (st, ex)
    assert split_steps("<table><tr><td>Step 1</td><td>Boot</td><td>Up</td></tr></table>")[:2] == (["Boot"], ["Up"])
    assert plain_steps("1. Create a VM\n   with two NICs\nExpected: both attached\n2. Ping") == (
        ["Create a VM with two NICs", "Ping"], ["both attached"],
        [{"step": "Create a VM with two NICs", "expected": "both attached"}, {"step": "Ping", "expected": ""}])
    assert plain("Prepare<div>Attach</div><style>p{x}</style>").split() == ["Prepare", "Attach"]
    assert plain("&lt;p&gt;A VM&lt;/p&gt;").strip() == "A VM"
    # Jira: --jira-base takes in the old Red Hat host; another host is refused.
    assert parse_jira("https://issues.redhat.com/browse/CNV-7?focusedId=1", "https://redhat.atlassian.net",
                      set())[0] == [("https://redhat.atlassian.net/browse/CNV-7", "CNV-7")]
    assert parse_jira("https://jira.example.org/browse/CNV-7", "https://redhat.atlassian.net", set())[1] \
        == "invalid-jira-url"
    # --allow: a label that means Automated has to say so.
    _, alias = parse_allow(["automation=Automated (CI)=automated", "type=Heading"])
    assert canon("automation", "Automated (CI)", alias) == "automated" and canon("type", "Heading", alias) == "other"
    try:
        parse_allow(["automation=Automated (CI)"])
        raise AssertionError("a bare Automated-looking value must be refused")
    except Problem:
        pass
    # A def line that already has a noqa gets PID001 added to it: flake8 reads one noqa per line.
    src = 'class T:\n    __test__ = False\n\n    def test_x(self):  # noqa: E501\n        """Doc."""\n'
    t = ast.parse(src)
    assert "# noqa: E501, PID001" in build_module(src, t, {t.body[0].body[1]: "CNV-1"}, set())

    steps_html = ("<table><tr><th>#</th><th>Step</th><th>Expected Result</th></tr>"
                  "<tr><td>1</td><td>Start a VM</td><td>VM is Running</td></tr>"
                  "<tr><td>2</td><td>Hot-plug a NIC</td><td>NIC is attached</td></tr></table>")
    cases = os.path.join(tmp, "cases.csv")
    with open(cases, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Type", "Title", "Status", "Case Automation", "Case Importance",
                    "Linked Work Items", "Test Steps", "Case Component", "Description", "Setup"])
        rows = [
            ("CNV-1", "Test Case", "Hot-plug a NIC", "Approved", "Not Automated", "Critical",
             "verifies: CNV-100 - NIC hot-plug", steps_html, "Networking", "<p>Plug it</p>"),
            ("CNV-2", "Test Case", "Old flow", "Inactive", "Not Automated", "", "verifies: CNV-100", "", "", ""),
            ("CNV-3", "Test Case", "Done", "Approved", "Automated", "", "verifies: CNV-100", "", "", ""),
            ("CNV-4", "Test Case", "Manual, no Jira", "Approved", "Manual Only", "", "verifies: CNV-101", "", "", ""),
            ("CNV-5", "Test Case", "Stubbed already", "Approved", "notautomated", "high", "CNV-100", "", "", ""),
            ("CNV-6", "Test Case", "Two features", "Proposed", "Not Automated", "",
             "verifies: CNV-102\nverifies: CNV-103", "", "", ""),
            ("CNV-7", "Test Case", "Blank automation", "Approved", "", "", "verifies: CNV-100", "", "", ""),
            ("CNV-8", "Test Case", "Lost requirement", "Approved", "Not Automated", "",
             "verifies: CNV-104", "", "", ""),
            ("", "Test Case", "No id", "Approved", "Not Automated", "", "", "", "", ""),
            ("CNV-1", "Test Case", "Hot-plug a NIC", "Approved", "Not Automated", "Critical",
             "verifies: CNV-100 - NIC hot-plug", steps_html, "Networking", "<p>Plug it</p>"),
            ("CNV-9", "Test Case", "Odd status", "Weird", "Not Automated", "", "verifies: CNV-100", "", "", ""),
            ("CNV-10", "Test Case", "Manual check", "Approved", "manualonly", "", "verifies: CNV-100", "", "", ""),
            ("CNV-11", "Test Case", "Bad link", "Approved", "Not Automated", "", "verifies: CNV-105", "", "", ""),
            ("CNV-12", "Test Case", "Bare key", "Approved", "Not Automated", "", "verifies: CNV-106", "", "", ""),
            ("CNV-13", "Test Case", "Other project", "Approved", "Not Automated", "", "verifies: CNV-107", "",
             "Storage", ""),
            ("CNV-15", "Test Case", "Automated, no code", "Approved", "Automated", "", "verifies: CNV-100", "", "", ""),
            ("CNV-100", "Requirement", "NIC hot-plug", "Approved", "", "", "", "", "", ""),
        ]
        w.writerows(r + ("A running VM" if r[0] == "CNV-1" else "",) for r in rows)
    reqs = os.path.join(tmp, "reqs.csv")
    with open(reqs, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")  # Excel writes semicolons in some locales
        w.writerow(["ID", "Title", "Hyperlinks"])
        w.writerow(["CNV-100", "NIC hot-plug", "https://polarion.example.com/#/workitem?id=CNV-100 "
                    "https://redhat.atlassian.net/browse/CNV-45678"])
        w.writerow(["CNV-101", "No Jira", "https://polarion.example.com/#/workitem?id=CNV-101"])
        w.writerow(["CNV-102", "Feature A", "https://redhat.atlassian.net/browse/CNV-50001"])
        w.writerow(["CNV-103", "Feature B", "https://redhat.atlassian.net/browse/CNV-50002"])
        w.writerow(["CNV-105", "Mangled", "https://redhat.atlassian.net/jira/software/CNV"])
        w.writerow(["CNV-106", "Bare key", "CNV-100"])
        w.writerow(["CNV-107", "Elsewhere", "https://redhat.atlassian.net/browse/OTHER-1"])
    run = os.path.join(tmp, "run")

    # W0
    ok("init", run, "--cases", cases, "--requirements", reqs, "--tests-repo", repo,
       "--query", "type:testcase AND project:CNV", "--exported-at", "2026-10-06")
    man = load_manifest(run)
    assert man["inputs"]["cases"]["records"] == 17 and man["inputs"]["requirements"]["delimiter"] == ";"
    assert man["inputs"]["cases"]["sha256"] == sha256(cases) and man["tests_repo"]["commit"]
    fails(2, "init", run, "--cases", cases)  # a run is frozen once
    retry = os.path.join(tmp, "run-retry")
    fails(2, "init", retry, "--cases", cases, "--tests-repo", os.path.join(tmp, "nowhere"))
    ok("init", retry, "--cases", cases)  # the failed attempt froze nothing

    # W1
    fails(2, "ledger", run, "--col", "automation=Nope")  # a header the export lacks
    ok("ledger", run, "--jira-projects", "CNV")
    led = load_ledger(run)
    by = {}
    for r in led["rows"]:
        by.setdefault(r["polarion_id"], r)
    c = led["counts"]
    assert c["input_records"] == 17 and c["not_a_test_case"] == 1 and c["unaccounted"] == 0
    assert c["states"] == {"resolved": 3, "excluded": 3, "held": 8, "invalid": 1, "duplicate": 1}, c
    assert by["CNV-1"]["jira_url"] == "https://redhat.atlassian.net/browse/CNV-45678"
    assert by["CNV-1"]["pse"]["steps"] == ["Start a VM", "Hot-plug a NIC"]
    assert by["CNV-1"]["pse"]["expected"] == ["VM is Running", "NIC is attached"]
    assert by["CNV-1"]["pse"]["step_results"][1] == {"step": "Hot-plug a NIC", "expected": "NIC is attached"}
    assert by["CNV-1"]["pse"]["source"] == "complete" and by["CNV-6"]["pse"]["source"] == "missing"
    assert by["CNV-5"]["state"] == "resolved" and "existing-marker" in by["CNV-5"]["flags"]
    assert "live-marker-on-stub" in by["CNV-5"]["flags"]
    assert "implemented-in-code" not in by["CNV-5"]["flags"]  # a disabled stub proves nothing
    assert by["CNV-10"]["state"] == "resolved" and "manualonly" in by["CNV-10"]["flags"]
    holds = {p: by[p]["holds"] for p in by if by[p]["state"] == "held"}
    assert holds == {"CNV-4": ["requirement-without-jira"], "CNV-6": ["ambiguous-jira"],
                     "CNV-7": ["automation-empty"], "CNV-8": ["requirement-not-in-export"],
                     "CNV-9": ["unexpected-status"], "CNV-11": ["invalid-jira-url"],
                     "CNV-12": ["bare-key-is-polarion-id"], "CNV-13": ["wrong-jira-project"]}, holds
    assert [r["state"] for r in led["rows"] if r["polarion_id"] == "CNV-1"] == ["resolved", "duplicate"]

    # W1 on one combined export with a field-id header, a padded header, a short row, a
    # requirement on two rows, other link roles, a missing requirement and types nobody confirmed.
    edge = os.path.join(tmp, "edge.csv")
    with open(edge, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Type", "Title", "Status", "Case Automation", "linkedWorkItems", "testSteps",
                    "Hyperlinks", ""])
        w.writerows([
            ("CNV-21", "Test Case", "Two", "Approved", "Not Automated", "verifies: CNV-200 - A, verifies: CNV-201 - B",
             "", "", ""),
            ("CNV-22", "Test Case", "Related", "Approved", "Not Automated", "relates_to: CNV-200 - A", "", "", ""),
            ("CNV-23", "Test Case", "Lost", "Approved", "Not Automated", "verifies: CNV-200\nverifies: CNV-299",
             "", "", ""),
            ("CNV-24", "Test Cases", "Odd type", "Approved", "Not Automated", "verifies: CNV-200", "", "", ""),
            ("CNV-25", "Test Case", "CI", "Approved", "Automated (CI)", "verifies: CNV-200", "1. Boot", "", ""),
            ("CNV-26", "Test Case", "Twice", "Approved", "Not Automated", "verifies: CNV-202 - C", ""),
            ("CNV-27", "Test Case", "Old host", "Approved", "Not Automated", "verifies: CNV-200 - A", "", "", ""),
            ("CNV-200", "Requirement", "A", "", "", "", "", "https://issues.redhat.com/browse/CNV-70000", ""),
            ("CNV-201", "Requirement", "B", "", "", "", "", "https://redhat.atlassian.net/browse/CNV-70001", ""),
            ("CNV-202", "Requirement", "C", "", "", "", "", "https://redhat.atlassian.net/browse/CNV-70002", ""),
            ("CNV-202", "Requirement", "C", "", "", "", "", "https://redhat.atlassian.net/browse/CNV-70003", ""),
            ("CNV-203", "Heading", "Section", "", "", "", "", "", ""),
        ])
    erun = os.path.join(tmp, "edge-run")
    ok("init", erun, "--cases", edge, "--tests-repo", repo)
    fails(2, "ledger", erun, "--allow", "automation=Automated (CI)")  # would make it eligible
    ok("ledger", erun, "--jira-base", "https://redhat.atlassian.net", "--allow",
       "automation=Automated (CI)=automated")
    eled = load_ledger(erun)
    e = {r["polarion_id"]: r for r in eled["rows"]}
    assert eled["counts"]["not_a_test_case"] == 5 and eled["columns"]["cases"]["steps"] == "testSteps"
    assert e["CNV-21"]["holds"] == ["ambiguous-jira"]
    assert e["CNV-22"]["holds"] == ["no-linked-requirement"] and e["CNV-22"]["other_links"][0]["role"] == "relates to"
    assert e["CNV-23"]["holds"] == ["requirement-not-in-export"]
    assert e["CNV-24"]["holds"] == ["unexpected-type"] and e["CNV-25"]["state"] == "excluded"
    assert e["CNV-26"]["holds"] == ["ambiguous-jira"] and "short-row" in e["CNV-26"]["flags"]
    assert e["CNV-27"]["jira_url"] == "https://redhat.atlassian.net/browse/CNV-70000"

    # W2
    fails(2, "triage", run, "queue")  # the invalid row blocks triage
    ok("triage", run, "queue", "--allow-defects")
    queue = load_json(run_file(run, "triage", "queue.json"))
    assert [g["jira_key"] for g in queue["groups"]] == ["CNV-45678"]
    group = queue["groups"][0]
    assert [x["polarion_id"] for x in group["cases"]] == ["CNV-1", "CNV-5", "CNV-10"]
    assert "CNV-3" in [s["polarion_id"] for s in group["siblings"]]
    ctx_name = "CNV-45678@20261006T100000Z.json"
    ctx = {"jira_key": "CNV-45678", "fetched_at": "2026-10-06T10:00:00Z", "error": None,
           "jira": {"summary": "NIC hot-plug", "type": "Story", "status": "Closed", "resolution": "Done"},
           "product": [{"claim": "hot-plug is in the API", "source": "the docs"}]}
    save_json(run_file(run, "triage", "context", ctx_name), ctx)
    ev = [{"claim": "Jira story is Done", "source": "https://redhat.atlassian.net/browse/CNV-45678"}]
    stub_test = "tests/network/bridge/test_bridge.py::TestBridge::test_bridge"
    verdicts = {"jira_key": "CNV-45678", "context_snapshot": ctx_name, "model": "claude-opus-5-5",
                "cases": [dict(polarion_id="CNV-1", verdict="migrate", rationale="Shipped, untested.",
                               uncertainty="low", proposed_team="network", evidence=ev,
                               gaps=["no IPv6 variant in the case"]),
                          dict(polarion_id="CNV-5", verdict="designed-as-stub", rationale="A stub has it.",
                               uncertainty="low", proposed_team="network", evidence=ev),
                          dict(polarion_id="CNV-10", verdict="retire-candidate", rationale="Manual check.",
                               uncertainty="high", proposed_team="network", evidence=ev)]}
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    # A context source that is not a link, a stub verdict naming no stub, a manualonly case
    # that is not manual-only-review: all refused.
    fails(1, "triage", run, "merge")
    ctx["product"] = [{"claim": "hot-plug is in the API", "source": "kubevirt/kubevirt@abcdef1:pkg/hotplug.go:10-12"},
                      {"claim": "no e2e test drains a node", "source": "kubevirt/kubevirt@abcdef1:tests/"}]
    save_json(run_file(run, "triage", "context", ctx_name), ctx)
    verdicts["cases"][1]["covered_by"] = stub_test
    verdicts["cases"][2]["verdict"] = "manual-only-review"
    verdicts["cases"][0]["evidence"] = [{"claim": "trust me", "source": "my notes"}]
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    fails(1, "triage", run, "merge")  # evidence needs a URL or repo@commit:path[:line]
    verdicts["cases"][0]["evidence"] = ev
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    # When the Jira fetch fails, a manualonly case stays manual-only-review.
    bad = dict(ctx, error="CNV-45678: 404")
    assert not [e for e in check_verdicts(group, verdicts, bad, ctx_name) if "CNV-10" in e]
    assert [e for e in check_verdicts(group, verdicts, bad, ctx_name) if "CNV-1:" in e or "CNV-1 " in e]
    ok("triage", run, "merge", "--group", "CNV-45678", "--dry-run")
    assert not load_ledger(run)["rows"][0].get("triage")
    ok("triage", run, "merge")
    assert load_ledger(run)["rows"][0]["triage"]["verdict"] == "migrate"
    assert load_ledger(run)["rows"][0]["triage"]["gaps"] == ["no IPv6 variant in the case"]

    # Team map, W3
    teams_file = os.path.join(tmp, "teams.yaml")
    write(teams_file, yaml.safe_dump({
        "teams": {"network": {"roots": ["tests/network"], "reviewer": "net-lead",
                              "tracking_jira": "https://redhat.atlassian.net/browse/CNV-80001"},
                  "storage": {"roots": ["tests/storage"], "reviewer": "sto-lead",
                              "components": ["Storage"]}},
        "components": {"Networking": "tests/network/hotplug"},
        "approved_by": "net-lead", "approved_on": "2026-10-07"}))
    ok("teams", run, teams_file)
    ok("review", run, "sheets")
    sheet = run_file(run, "review", "network.csv")
    _, _, recs = read_csv(sheet, "utf-8-sig")
    assert sorted(cells["polarion_id"] for _, _, cells, _ in recs) == ["CNV-1", "CNV-10", "CNV-5"]
    assert {c["polarion_id"]: c["triage_covered_by"] for _, _, c, _ in recs}["CNV-5"] == stub_test
    unassigned = run_file(run, "review", "unassigned.csv")
    assert os.path.exists(unassigned)
    _, _, recs = read_csv(run_file(run, "review", "storage.csv"), "utf-8-sig")
    assert [cells["polarion_id"] for _, _, cells, _ in recs] == ["CNV-13"]  # the team's own component

    def fill(path, decisions):
        header, _, recs = read_csv(path, "utf-8-sig")
        out = []
        for _, _, cells, _ in recs:
            cells.update(decisions.get(cells["polarion_id"], {}))
            out.append(cells)
        write_csv(path, header, out)

    sign = {"reviewer": "net-lead", "date": "2026-10-08", "rationale": "reviewed"}
    fill(sheet, {"CNV-1": dict(sign, decision="migrate"),
                 "CNV-5": dict(sign, decision="migrate", reviewer=""),
                 "CNV-10": dict(sign, decision="retire", retire_reason="covered by manual QE",
                                polarion_owner="cnv-polarion-owner")})
    fails(1, "review", run, "import", sheet)  # CNV-5 has no reviewer: nothing is imported
    assert not any(r.get("decision") for r in load_ledger(run)["rows"])
    fill(sheet, {"CNV-5": dict(sign, decision="migrate")})
    ok("review", run, "import", sheet)
    stale = os.path.join(tmp, "network-before-regeneration.csv")
    shutil.copyfile(sheet, stale)
    # A held case: the team names the Jira the hold was about, never the batch's tracking Jira.
    fill(unassigned, {"CNV-6": dict(sign, decision="migrate")})
    fails(1, "review", run, "import", unassigned)  # ambiguous Jira: chosen_jira is required
    fill(unassigned, {"CNV-6": dict(sign, decision="migrate", team="network",
                                    chosen_jira="https://redhat.atlassian.net/browse/CNV-80001")})
    fails(1, "review", run, "import", unassigned)
    fill(unassigned, {"CNV-6": dict(sign, decision="migrate", team="network", date="2026-10-08 00:00:00",
                                    chosen_jira="https://redhat.atlassian.net/browse/CNV-50001",
                                    pse_note="Use a VM with two NICs")})
    ok("review", run, "import", unassigned)  # a spreadsheet's date-time reads as its date
    ok("review", run, "sheets")  # the reviewer's team assignment survives a regeneration
    assert "CNV-6" in [c["polarion_id"] for _, _, c, _ in read_csv(sheet, "utf-8-sig")[2]]
    fails(1, "review", run, "import", stale)  # its rows come from the sheet before the regeneration
    fill(sheet, {"CNV-10": {"decision": ""}})
    fails(1, "review", run, "import", sheet)  # an emptied cell does not withdraw a decision: hold does
    fails(2, "review", run, "sheets")  # and a regeneration would lose that edit
    fill(sheet, {"CNV-10": {"decision": "retire"}})
    ok("review", run, "calibrate")
    cal = load_json(run_file(run, "review", "calibration.json"))
    assert cal["per_verdict"]["migrate"]["agreed"] == 1 and cal["overall_agreement"] == 0.5, cal
    assert [d["polarion_id"] for d in cal["disagreements"]] == ["CNV-5"]  # the team chose migrate

    # W4: scenario list.
    outputs = os.path.join(tmp, "outputs")
    ok("scenarios", run, "--team", "network", "--tier", "Tier 2", "--outputs", outputs)
    with open(os.path.join(outputs, "CNV-80001", "input", "CNV-80001_scenarios.yaml"), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    got = {s["polarion_id"]: s for s in doc["scenarios"]}
    assert sorted(got) == ["CNV-1", "CNV-5", "CNV-6"]
    assert got["CNV-6"]["jira_url"].endswith("/CNV-50001") and got["CNV-1"]["source_pse"] == "complete"
    assert got["CNV-5"]["source_pse"] == "missing" and "steps" not in got["CNV-5"]
    assert got["CNV-6"]["review_note"] == "Use a VM with two NICs"
    assert got["CNV-6"]["source_missing"] == ["preconditions", "steps", "expected"]
    assert got["CNV-1"]["step_results"][0] == {"step": "Start a VM", "expected": "VM is Running"}
    ok("scenarios", run, "--team", "storage", "--outputs", outputs)  # zero cases is a valid result

    # W4: placement. CNV-1 and CNV-5 sit with sibling CNV-3; CNV-6 has neither.
    ok("place", run, "--team", "network")
    plan = {p["polarion_id"]: p for p in load_json(run_file(run, "placement", "network.json"))["cases"]}
    assert plan["CNV-1"]["layer"] == "sibling" and plan["CNV-1"]["folder"] == "tests/network/hotplug"
    assert plan["CNV-6"]["layer"] == "unplaced" and "tests/network/bridge" in plan["CNV-6"]["candidates"]
    save_json(run_file(run, "placement", "network.model.json"), {"cases": [
        {"polarion_id": "CNV-6", "folder": "tests/network/nowhere", "confidence": 0.9,
         "rationale": "x", "cited_tests": ["tests/network/bridge/test_bridge.py::test_other"]}]})
    ok("place", run, "--team", "network")  # a folder outside the candidates is refused
    assert load_json(run_file(run, "placement", "network.json"))["counts"]["unplaced"] == 1
    save_json(run_file(run, "placement", "network.model.json"), {"cases": [
        {"polarion_id": "CNV-6", "folder": "tests/network/bridge", "confidence": 0.8,
         "rationale": "bridge tests", "cited_tests": ["tests/network/bridge/test_bridge.py::test_other"]}]})
    ok("place", run, "--team", "network")
    plan = {p["polarion_id"]: p for p in load_json(run_file(run, "placement", "network.json"))["cases"]}
    assert plan["CNV-6"]["layer"] == "model" and plan["CNV-6"]["folder"] == "tests/network/bridge"

    # W4: std-builder's output for the batch (what /std-builder CNV-80001 writes).
    std_dir = os.path.join(outputs, "CNV-80001", "std")
    save_std = {"document_metadata": {"jira_id": "CNV-80001"}, "scenarios": [
        {"test_id": "TS-CNV-80001-%03d" % i, "polarion_id": p} for i, p in enumerate(["CNV-1", "CNV-5", "CNV-6"], 1)]}
    write(os.path.join(std_dir, "CNV-80001_test_description.yaml"), yaml.safe_dump(save_std))

    def stub(i, pid, url, name, note=""):
        return ('    @pytest.mark.qf_test_id("TS-CNV-80001-%03d")\n    def %s(self):\n        """\n'
                '        Test that it works. [TS-CNV-80001-%03d]\n\n        Jira: %s\n%s\n        Markers:\n'
                '            - polarion("%s")\n\n        Preconditions:\n            - A VM\n\n'
                '        Steps:\n            1. Act\n\n        Expected:\n            - It works\n        """\n'
                % (i, name, i, url, note, pid))
    stubs = ('"""\nPolarion migration: network\n\nJira: https://redhat.atlassian.net/browse/CNV-80001\n"""\n'
             'import pytest\n\n\nclass TestMigrated:\n    """\n    Migrated cases.\n    """\n\n'
             '    __test__ = False\n\n'
             + stub(1, "CNV-1", "https://redhat.atlassian.net/browse/CNV-45678", "test_hotplug_nic_cold") + "\n"
             + stub(2, "CNV-5", "https://redhat.atlassian.net/browse/CNV-45678", "test_bridge_stub") + "\n"
             + stub(3, "CNV-6", "https://redhat.atlassian.net/browse/CNV-50001", "test_feature_a",
                    "        Source: Polarion CNV-6 lists no preconditions, steps or expected result; all are\n"
                    "        proposed. Steps corrected in team review.\n"))
    write(os.path.join(std_dir, "python-tests", "test_polarion_network_stubs.py"), stubs)
    fails(1, "package", run, "--team", "network", "--outputs", outputs)  # CNV-5 already in the repo
    led = load_ledger(run)
    assert "CNV-5" in " ".join(load_json(run_file(run, "package", "network", "manifest.json"))["errors"])
    # The team takes the triage's advice after all: CNV-5 links the stub that has its ID.
    fill(sheet, {"CNV-5": dict(sign, decision="link-existing", existing_test=stub_test, attach_id="no")})
    ok("review", run, "import", sheet)
    ok("review", run, "calibrate")
    assert load_json(run_file(run, "review", "calibration.json"))["overall_agreement"] == 1.0
    write(os.path.join(std_dir, "python-tests", "test_polarion_network_stubs.py"),
          stubs.replace(stub(2, "CNV-5", "https://redhat.atlassian.net/browse/CNV-45678",
                             "test_bridge_stub") + "\n", ""))
    ok("package", run, "--team", "network", "--outputs", outputs)
    pm = load_json(run_file(run, "package", "network", "manifest.json"))
    assert pm["valid"] and pm["stripped_markers"] == ["qf_test_id"]
    assert sorted(f["path"] for f in pm["files"]) == ["tests/network/bridge/test_polarion_network.py",
                                                      "tests/network/hotplug/test_polarion_network.py"]
    with open(run_file(run, "package", "network", "tests/network/bridge/test_polarion_network.py")) as f:
        module = f.read()
    assert "qf_test_id" not in module and "import pytest" not in module and "CNV-1\"" not in module
    assert 'polarion("CNV-6")' in module and "__test__ = False" in module
    assert "def test_feature_a(self):  # noqa: PID001" in module  # the repo's polarion lint
    # A live marker on a stub is refused: the post-merge job would mark it Automated.
    rows_by = {"CNV-6": next(r for r in load_ledger(run)["rows"]
                             if r["polarion_id"] == "CNV-6" and r["state"] == "held")}
    live = module.replace("    def test_feature_a", '    @pytest.mark.polarion("CNV-6")\n    def test_feature_a')
    assert any("Automated on merge" in e for e in check_module(live, {"CNV-6"}, rows_by, {"polarion"}, True))
    # The owner's other choice: the real decorator on each stub, as the repo's lint asks.
    ok("package", run, "--team", "network", "--outputs", outputs, "--polarion-marker", "decorator")
    with open(run_file(run, "package", "network", "tests/network/bridge/test_polarion_network.py")) as f:
        decorated = f.read()
    assert '    @pytest.mark.polarion("CNV-6")\n    def test_feature_a(self):\n' in decorated, decorated
    assert '- polarion("CNV-6")' not in decorated and "Markers:" not in decorated
    assert "import pytest" in decorated and "noqa" not in decorated
    # stub-generator no longer emits qf_test_id: nothing is removed, or reported as removed.
    stub_file = os.path.join(std_dir, "python-tests", "test_polarion_network_stubs.py")
    with open(stub_file) as f:
        write(stub_file, re.sub(r'    @pytest\.mark\.qf_test_id\("[^"]*"\)\n', "", f.read()))
    ok("package", run, "--team", "network", "--outputs", outputs)  # back to the default for W5
    assert load_json(run_file(run, "package", "network", "manifest.json"))["stripped_markers"] == []

    # W5: stage into a fresh clone, then record the merged PR.
    co = os.path.join(tmp, "checkout")
    sh(tmp, "git", "clone", "-q", repo, co)
    behind = os.path.join(tmp, "checkout-local")
    sh(tmp, "git", "clone", "-q", repo, behind)
    sh(behind, "git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty",
       "-m", "local")
    fails(2, "stage", run, "--team", "network", "--checkout", behind)  # not at origin/main
    ok("stage", run, "--team", "network", "--checkout", co)
    assert git(co, "rev-parse", "--abbrev-ref", "HEAD") == "polarion-migration/network-cnv-80001"
    staged = sorted((git(co, "diff", "--cached", "--name-only") or "").splitlines())
    assert staged == sorted(f["path"] for f in pm["files"])
    with open(run_file(run, "pr", "network", "PR_BODY.md"), encoding="utf-8") as f:
        body = f.read()
    assert "CNV-80001" in body and "CNV-6" in body and "link-existing: 1" in body and "retire: 1" in body
    sh(co, "git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "stubs")
    ok("record-pr", run, "--team", "network", "--url", "https://github.com/RedHatQE/openshift-virtualization-tests/pull/1",
       "--state", "merged", "--commit", git(co, "rev-parse", "HEAD"), "--checkout", co)
    loc = next(r for r in load_ledger(run)["rows"] if r["polarion_id"] == "CNV-1")["stub_location"]
    path, _, line = loc[0].partition(":")
    with open(os.path.join(co, path), encoding="utf-8") as f:
        assert 'polarion("CNV-1")' in f.read().splitlines()[int(line) - 1], loc

    # W6: the proposal, then a fresh export that applied it.
    ok("reconcile", run, "--tests-repo", co)
    _, _, recs = read_csv(run_file(run, "reconcile", "network.csv"), "utf-8")
    prop = {c["polarion_id"]: c for _, _, c, _ in recs}
    assert prop["CNV-10"]["proposed_status"] == "inactive" and prop["CNV-10"]["ready_to_apply"] == "yes"
    assert prop["CNV-1"]["ready_to_apply"] == "no" and "end-state gap" in prop["CNV-1"]["reason"]
    assert "not implemented yet" in prop["CNV-5"]["reason"], prop["CNV-5"]  # the stub has its ID
    _, _, recs = read_csv(run_file(run, "reconcile", "audit_automated_without_code.csv"), "utf-8")
    assert [c["polarion_id"] for _, _, c, _ in recs] == ["CNV-15"]
    fresh = os.path.join(tmp, "fresh.csv")
    with open(cases, encoding="utf-8-sig") as f:
        text = f.read()
    write(fresh, text.replace("CNV-10,Test Case,Manual check,Approved", "CNV-10,Test Case,Manual check,Inactive"))
    ok("verify", run, fresh)
    write(fresh, text)  # the retirement was not applied
    fails(1, "verify", run, fresh)
    # A retirement that an implemented test contradicts is not ready; Automated needs the ID
    # on main, and comes with Status approved (the post-merge job sets both).
    retire = {"decision": "retire", "retire_reason": "x", "polarion_owner": "o"}
    assert not propose({"polarion_id": "CNV-3", "decision": retire}, inv, True)["ready"]
    p = propose({"polarion_id": "CNV-3", "decision": {"decision": "link-existing", "existing_test": "x"}}, inv, True)
    assert (p["proposed_status"], p["proposed_automation"], p["ready"]) == ("approved", "automated", True)
    p = propose({"polarion_id": "CNV-6", "decision": {"decision": "migrate"}, "package": {"polarion_marker": "decorator"},
                 "pr": {"state": "merged"}}, {}, True)
    assert not p["proposed_automation"] and "no stub" in p["reason"], p
    print("self-test: OK")


if __name__ == "__main__":
    sys.exit(main())
