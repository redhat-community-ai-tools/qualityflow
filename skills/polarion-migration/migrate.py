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
from html.parser import HTMLParser

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_VERSION = 1

# ------------------------------------------------------------------ constants

# field -> its header in the export; the first one present wins, and
# --col FIELD=HEADER replaces the list.
# ponytail: Polarion's UI labels and Betelgeuse's field ids, a guess until the
# real export pins them.
COLUMNS = {
    "id": ("ID",),
    "type": ("Type",),
    "title": ("Title",),
    "status": ("Status",),
    "automation": ("Automation", "Case Automation", "caseautomation"),
    "linked": ("Linked Work Items",),
    "importance": ("Importance", "Case Importance", "caseimportance"),
    "setup": ("Setup", "Preconditions"),
    "steps": ("Test Steps", "Steps"),
    "expected": ("Expected Result", "Expected Results", "Expected"),
    "description": ("Description",),
    "component": ("Case Component", "Component", "casecomponent"),
    "subcomponent": ("Subcomponent", "Sub Component", "subcomponent"),
    "updated": ("Updated",),
    "hyperlinks": ("Hyperlinks",),
    "jira": ("Jira", "Jira Link", "Hyperlinks"),  # the requirements export
}
CASE_REQUIRED = ("id", "title", "status", "automation", "linked")
REQUIREMENT_REQUIRED = ("id", "jira")

# ponytail: Betelgeuse's values; --allow FIELD=VALUE adds what a real export
# turns out to use. Anything else holds the case instead of guessing.
KNOWN = {"status": {"draft", "proposed", "approved", "needsupdate", "inactive"},
         "automation": {"automated", "notautomated", "manualonly"}}
PRIORITY = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P2"}

VERDICTS = ("migrate", "covered-by-implemented-test", "retire-candidate",
            "manual-only-review", "needs-investigation")
DECISIONS = ("migrate", "link-existing", "retire", "hold")
# The decision a verdict predicts; manual-only-review predicts none.
EXPECTED_DECISION = {"migrate": "migrate", "covered-by-implemented-test": "link-existing",
                     "retire-candidate": "retire", "needs-investigation": "hold"}
UNCERTAINTY = ("low", "medium", "high")
# Jira resolutions that make a case a retirement *signal* for triage. Not a
# rule: implemented functionality can outlive an issue's resolution.
RETIRE_RESOLUTIONS = {"wontdo", "wontfix", "obsolete", "duplicate", "notabug", "rejected"}
JIRA_HOLDS = {"no-linked-requirement", "requirement-not-in-export", "requirement-without-jira",
              "invalid-jira-url", "bare-key-is-polarion-id", "bare-key-no-base",
              "wrong-jira-project", "ambiguous-jira"}

WORK_ITEM = re.compile(r"\b[A-Z][A-Z0-9_]*-\d+\b")
JIRA_URL = re.compile(r"https?://[^\s,;|\"'<>]+/browse/([A-Z][A-Z0-9_]*-\d+)")
TEST_NODE = re.compile(r"^tests/\S+\.py::\w+(::\w+)*$")
SOURCE_REF = re.compile(r"^(https?://\S+|[\w.-]+(/[\w.-]+)?@[0-9a-f]{7,40}:[^\s:]+:\d+)$")
TEXT_ID = re.compile(r"""polarion\(\s*["']([A-Z][A-Z0-9_]*-\d+)["']""")
MARKERS_ENTRY = re.compile(r"""^\s*-\s*polarion\(\s*["']([^"']+)["']\s*\)\s*$""", re.M)
# The tests repo's post-merge mark-automated-polarion job (RedHatQE
# python-utility-scripts) matches added lines with this, for any project id.
LIVE_MARK = re.compile(r"pytest.mark.polarion.*?[A-Z][A-Z0-9_]*-[0-9]+")
HTML_TAG = re.compile(r"<\s*/?\s*(table|tbody|thead|tr|td|th|p|br|div|span|ul|ol|li|b|i|strong|em)\b[^>]*>",
                      re.I)
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

def read_csv(path, encoding):
    """(header, delimiter, records); a record is (number, line, cells, problem)."""
    try:
        with open(path, encoding=encoding, newline="") as f:
            first = f.readline()
            f.seek(0)
            delimiter = max(",;\t", key=first.count)
            reader = csv.reader(f, delimiter=delimiter)
            header = [h.strip() for h in next(reader, [])]
            if not any(header):
                raise Problem("%s has no header row" % path)
            records = []
            for cells in reader:
                if not any(c.strip() for c in cells):
                    continue
                problem = None
                if len(cells) != len(header):
                    problem = "%d fields, the header has %d" % (len(cells), len(header))
                records.append((len(records) + 1, reader.line_num,
                                dict(zip(header, cells, strict=False)), problem))
    except UnicodeDecodeError as e:
        raise Problem("%s is not valid %s (%s): re-export as UTF-8 or pass --encoding"
                      % (path, encoding, e.reason)) from None
    except csv.Error as e:
        raise Problem("%s: malformed CSV: %s" % (path, e)) from None
    return header, delimiter, records


def map_columns(header, overrides, required, path):
    """field -> the header it is found under. Fails naming the export's columns."""
    lower = {h.lower(): h for h in header}
    found = {}
    for field, names in COLUMNS.items():
        for name in overrides.get(field) or names:
            if name.lower() in lower:
                found[field] = lower[name.lower()]
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
    """Rich text -> plain text, keeping line and cell breaks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.rows, self.row, self.cell = [], [], None, None

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "li"):
            self._put("\n")
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            if self.row is not None:
                self.row.append("".join(self.cell))
            self.cell = None
            self.out.append("\t")
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.out.append("\n")
        elif tag in ("p", "div", "li", "ul", "ol", "table") or re.fullmatch(r"h\d", tag):
            self._put("\n")

    def handle_data(self, data):
        self._put(data)

    def _put(self, text):
        self.out.append(text)
        if self.cell is not None:
            self.cell.append(text)


def parse_html(text):
    p = _Text()
    p.feed(text)
    p.close()
    return "".join(p.out), p.rows


def plain(text):
    return parse_html(text)[0] if HTML_TAG.search(text or "") else html.unescape(text or "")


def lines(text):
    """Non-empty lines, without list numbering or bullets."""
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(\d+[.)]|[-*•])\s+", "", line).strip()
        if line:
            out.append(re.sub(r"\s+", " ", line))
    return out


def split_steps(raw):
    """(steps, expected) from a Test Steps cell: an HTML table, or plain lines."""
    if not re.search(r"<tr\b", raw or "", re.I):
        return lines(plain(raw)), []
    steps, expected = [], []
    heads = {"", "#", "step", "steps", "step description", "description", "expected result",
             "expected results", "expected"}
    for cells in parse_html(raw)[1]:
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
        if cells and re.fullmatch(r"#?\d+\.?", cells[0]):
            cells = cells[1:]
        if not any(cells) or all(c.lower() in heads for c in cells):
            continue
        if cells[0]:
            steps.append(cells[0])
        if len(cells) > 1 and cells[1]:
            expected.append(cells[1])
    return steps, expected


def normalize_pse(setup, steps, expected):
    """The case's own Preconditions/Steps/Expected, and how complete they are."""
    st, ex = split_steps(steps)
    ex += lines(plain(expected))
    pre = lines(plain(setup))
    source = "complete" if st and ex else "partial" if (st or ex or pre) else "missing"
    return {"preconditions": pre, "steps": st, "expected": ex, "source": source}


def parse_links(cell):
    """[(work item id, role)] from a Linked Work Items cell.

    One link per line or ';'-separated part, as 'role: ID - title' or
    'ID - title (role)'; IDs after ' - ' are title text, not links.
    """
    out = []
    for part in re.split(r"[\n;]+", cell or ""):
        head = part.split(" - ", 1)[0]
        m = re.match(r"\s*([A-Za-z][A-Za-z _]*?)\s*:", head)
        role = m.group(1) if m else ""
        if not role:
            m = re.search(r"\(([A-Za-z][A-Za-z _]*)\)\s*$", part)
            role = m.group(1) if m else ""
        for wid in WORK_ITEM.findall(head):
            if wid not in [o[0] for o in out]:
                out.append((wid, role.strip().lower()))
    return out


def parse_jira(cell, jira_base, polarion_ids):
    """(links, problem, bare): every Jira issue a requirement's cell links, or why none."""
    links = []
    for m in JIRA_URL.finditer(cell or ""):
        if m.group(1) not in [k for _, k in links]:
            links.append((m.group(0), m.group(1)))
    if links:
        return links, None, False
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
    """The target of `x.__test__ = False` / `__test__ = False`, else None."""
    if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is False):
        return None
    for t in stmt.targets:
        if isinstance(t, ast.Name) and t.id == "__test__":
            return ""
        if isinstance(t, ast.Attribute) and t.attr == "__test__" and isinstance(t.value, ast.Name):
            return t.value.id
    return None


def why_off(node, parents, tree):
    """Why a test function/class/module is switched off, or None."""
    if any(assigns_test_false(s) == "" for s in tree.body):
        return "module __test__ = False"
    chain = []
    while isinstance(node, DEFS):
        chain.append(node)
        node = parents.get(node)
    for n in chain:
        if isinstance(n, ast.ClassDef) and any(assigns_test_false(s) == "" for s in n.body):
            return "class __test__ = False"
        scope = parents.get(n)
        if not isinstance(n, ast.ClassDef) and any(
                assigns_test_false(s) == n.name for s in getattr(scope, "body", [])):
            return "function __test__ = False"
        for d in n.decorator_list:
            name = deco_name(d)
            if name.endswith("mark.skip"):
                return "skip"
            if name.endswith("mark.xfail") and isinstance(d, ast.Call) and any(
                    k.arg == "run" and isinstance(k.value, ast.Constant) and k.value.value is False
                    for k in d.keywords):
                return "xfail run=False"
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
    header, delimiter, records = read_csv(path, encoding)
    with open(path, "rb") as f:
        bom = f.read(3) == b"\xef\xbb\xbf"
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
    inputs = {}
    for role, src in (("cases", a.cases), ("requirements", a.requirements)):
        if not src:
            continue
        if not os.path.isfile(src):
            raise Problem("no such file: %s" % src)
        dst = run_file(run, "input", role + os.path.splitext(src)[1].lower())
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o444)
        inputs[role] = dict(file=os.path.relpath(dst, run), source=os.path.abspath(src),
                            sha256=sha256(dst), bytes=os.path.getsize(dst),
                            **describe_csv(dst, a.encoding))
    manifest = {
        "tool_version": TOOL_VERSION, "created": now(),
        "export": {"query": a.query, "exported_at": a.exported_at, "exported_by": a.exported_by,
                   "note": a.note},
        "single_export": not a.requirements,
        "inputs": inputs,
        "qf": repo_snapshot(HERE, required=False),
        "tests_repo": repo_snapshot(a.tests_repo) if a.tests_repo else None,
    }
    if a.expect_cases is not None and inputs["cases"]["records"] != a.expect_cases:
        print("WARNING: expected %d case records, the export has %d"
              % (a.expect_cases, inputs["cases"]["records"]))
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

def resolve_jira(links, reqs, case_ids, projects):
    """(requirements, unknown links, (url, key) or None, holds, detail, flags)."""
    found = [dict(id=w, role=role, title=reqs[w]["title"], jira=[u for u, _ in reqs[w]["jira"]],
                  keys=[k for _, k in reqs[w]["jira"]], problem=reqs[w]["problem"])
             for w, role in links if w in reqs]
    unknown = [w for w, _ in links if w not in reqs and w not in case_ids]
    flags = []
    if not links:
        return found, unknown, None, ["no-linked-requirement"], ["no linked work items"], flags
    if not found:
        return (found, unknown, None, ["requirement-not-in-export"],
                ["linked %s; none is in the requirements export" % ", ".join(w for w, _ in links)], flags)
    keys = collections.OrderedDict()
    for r in found:
        for url, key in reqs[r["id"]]["jira"]:
            keys.setdefault(key, url)
        if reqs[r["id"]]["bare"] and reqs[r["id"]]["jira"]:
            flags.append("jira-from-bare-key")
    if not keys:
        codes = sorted({r["problem"] for r in found})
        return found, unknown, None, codes, ["%s: %s" % (r["id"], r["problem"]) for r in found], flags
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
        return found, unknown, None, holds, detail, flags
    key, url = next(iter(keys.items()))
    return found, unknown, (url, key), [], [], flags


def cmd_ledger(a):
    run = a.run
    manifest = load_manifest(run)
    path = run_file(run, "ledger.json")
    if os.path.exists(path) and not a.force:
        old = load_json(path)
        if any(r.get(k) for r in old["rows"] for k in ("triage", "decision", "placement", "pr")):
            raise Problem("the ledger already holds triage or review results; --force rebuilds it "
                          "and drops them")
    overrides = parse_pairs(a.col, COLUMNS, "--col")
    extra = parse_pairs(a.allow, KNOWN, "--allow")
    known = {f: KNOWN[f] | {norm(v) for v in extra.get(f, [])} for f in KNOWN}
    projects = {p.strip() for p in (a.jira_projects or "").split(",") if p.strip()}

    inputs = manifest["inputs"]
    single = "requirements" not in inputs
    cases_path = run_file(run, inputs["cases"]["file"])
    header, _, records = read_csv(cases_path, inputs["cases"]["encoding"])
    cols = map_columns(header, overrides, CASE_REQUIRED + (("type",) if single else ()), cases_path)
    if single:
        req_path, req_records = cases_path, records
        req_cols = map_columns(header, overrides, REQUIREMENT_REQUIRED, cases_path)
    else:
        req_path = run_file(run, inputs["requirements"]["file"])
        req_header, _, req_records = read_csv(req_path, inputs["requirements"]["encoding"])
        req_cols = map_columns(req_header, overrides, REQUIREMENT_REQUIRED, req_path)

    reqs, req_defects = collections.OrderedDict(), []
    for n, _, cells, problem in req_records:
        get = getter(cells, req_cols)
        if "type" in req_cols and norm(get("type")) == "testcase":
            continue
        if problem or not get("id"):
            req_defects.append("requirements row %d: %s" % (n, problem or "empty ID"))
            continue
        reqs[get("id")] = {"title": get("title"), "status": get("status"), "cell": get("jira")}
    case_ids = {getter(c, cols)("id") for _, _, c, _ in records} - {""}
    for req in reqs.values():
        req["jira"], req["problem"], req["bare"] = parse_jira(req.pop("cell"), a.jira_base,
                                                              case_ids | set(reqs))

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

    rows, first, non_cases = [], {}, 0
    values = {"status": collections.Counter(), "automation": collections.Counter()}
    for n, line, cells, problem in records:
        get = getter(cells, cols)
        if "type" in cols and get("type") and norm(get("type")) != "testcase":
            non_cases += 1
            continue
        pid = get("id")
        row = {"row": n, "line": line, "polarion_id": pid, "state": None, "holds": [], "flags": [],
               "detail": [], "source": {f: get(f) for f in cols if f != "id"}}
        rows.append(row)
        if problem or not pid:
            row["state"] = "invalid"
            row["detail"].append(problem or "empty ID")
            continue
        if pid in first:
            row["state"] = "duplicate"
            row["duplicate_of"] = first[pid]["row"]
            if any(first[pid]["source"].get(f) != row["source"].get(f) for f in row["source"]):
                row["flags"].append("conflicting-duplicate")
            continue
        first[pid] = row
        status, automation = norm(get("status")), norm(get("automation"))
        values["status"][get("status")] += 1
        values["automation"][get("automation")] += 1
        row["existing"] = inventory.get(pid, [])
        if any(o["kind"] in LIVE_KINDS for o in row["existing"]):
            row["flags"].append("existing-marker")
            if implemented_evidence(row["existing"]):
                row["flags"].append("implemented-in-code")
        elif row["existing"]:
            row["flags"].append("id-mentioned-in-code")
        row["pse"] = normalize_pse(get("setup"), get("steps"), get("expected"))
        (row["requirements"], row["unknown_links"], jira, holds, detail,
         flags) = resolve_jira(parse_links(get("linked")), reqs, case_ids, projects)
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
    unaccounted = len(records) - non_cases - sum(counts.values())
    ledger = {
        "tool_version": TOOL_VERSION, "created": now(),
        "columns": {"cases": cols, "requirements": req_cols},
        "known_values": {f: sorted(v) for f, v in known.items()},
        "jira_base": a.jira_base, "jira_projects": sorted(projects), "inventory": inv_meta,
        "counts": {"input_records": len(records), "not_a_test_case": non_cases,
                   "test_case_rows": len(rows), "states": dict(counts),
                   "excluded": dict(excluded), "holds": dict(held), "unaccounted": unaccounted},
        "values_seen": {f: dict(c) for f, c in values.items()},
        "requirement_defects": req_defects,
        "requirements": reqs,
        "rows": rows,
    }
    save_ledger(run, ledger)
    print("input records %21d" % len(records))
    print("  not a test case %17d" % non_cases)
    print("  test-case rows %18d" % len(rows))
    for reason, k in sorted(excluded.items()):
        print("    excluded: %-20s %3d" % (reason, k))
    for state in ("resolved", "held", "duplicate", "invalid"):
        print("    %-30s %3d" % (state, counts.get(state, 0)))
    for code, k in sorted(held.items()):
        print("      hold %-24s %3d" % (code, k))
    print("unaccounted %23d" % unaccounted)
    for field, c in values.items():
        print("%s values seen: %s" % (field, ", ".join("%r x%d" % kv for kv in sorted(c.items()))))
    defects = [r for r in rows if r["state"] == "invalid" or "conflicting-duplicate" in r["flags"]]
    if defects or req_defects:
        print("Fix in the export before triage:")
        for r in defects:
            print("  row %d (%s): %s" % (r["row"], r["polarion_id"] or "no ID",
                                         ", ".join(r["detail"]) or "conflicting duplicate of row %d"
                                         % r["duplicate_of"]))
        for d in req_defects:
            print("  " + d)
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
    for comp, folder in (doc.get("components") or {}).items():
        p = rel_path(folder)
        if p != folder:
            errors.append("component %r: %r is not a normalised path under tests/" % (comp, folder))
        elif not team_for_folder(p, doc):
            errors.append("component %r: %s is under no team's roots" % (comp, p))
        elif repo and not os.path.isdir(os.path.join(repo, p)):
            errors.append("component %r: %s does not exist in %s" % (comp, p, repo))
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
        siblings = [{"polarion_id": r["polarion_id"], "state": r["state"],
                     "automation": r["source"].get("automation", ""),
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
    save_json(run_file(a.run, "triage", "queue.json"), queue)
    print("queued %d requirement group(s), %d case(s) -> %s"
          % (len(out), sum(len(g["cases"]) for g in out), run_file(a.run, "triage", "queue.json")))
    held = sum(1 for r in rows if r["state"] == "held")
    if held:
        print("%d held case(s) stay out of triage; their holds name the missing data" % held)
    return 0


def check_verdicts(group, doc, ctx, ctx_name):
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
        if norm(want[pid]["automation"]) == "manualonly" and verdict != "manual-only-review":
            errs.append("%s: a manualonly case gets manual-only-review" % at)
        if ctx.get("error") and verdict != "needs-investigation":
            errs.append("%s: the context fetch failed (%s), so the verdict is needs-investigation"
                        % (at, ctx["error"]))
        if verdict == "covered-by-implemented-test" and not TEST_NODE.match(str(c.get("covered_by") or "")):
            errs.append("%s: covered_by must name the test, tests/...py::name" % at)
    for pid in sorted(set(want) - seen):
        errs.append("%s: no verdict for %s" % (where, pid))
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
        errs = check_verdicts(g, doc, ctx, ctx_name)
        errs += ["%s: %s is no longer resolved in the ledger; re-run `triage queue`"
                 % (g["jira_key"], c["polarion_id"]) for c in g["cases"] if c["polarion_id"] not in by_id]
        if errs:
            errors += errs
            continue
        signals = context_signals(ctx)
        jira = {k: (ctx.get("jira") or {}).get(k) for k in ("type", "status", "resolution", "summary")}
        for c in doc["cases"]:
            row = by_id[c["polarion_id"]]
            new = {"verdict": c["verdict"], "rationale": c["rationale"], "uncertainty": c["uncertainty"],
                   "proposed_team": c["proposed_team"], "evidence": c.get("evidence") or [],
                   "covered_by": c.get("covered_by"), "context": ctx_name, "jira": jira,
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
         "triage_uncertainty", "triage_rationale", "triage_evidence",
         "decision", "chosen_jira", "existing_test", "attach_id", "retire_reason", "polarion_owner",
         "reviewer", "date", "rationale")
FILL = SHEET[SHEET.index("decision"):]


def team_of(row, teams):
    """Component map first, then the triage's proposal, else unassigned."""
    if teams:
        folder = component_folder(row, teams)
        team = folder and team_for_folder(folder, teams)
        if team:
            return team
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
           "triage_evidence": " | ".join("%s <%s>" % (e["claim"], e["source"])
                                         for e in t.get("evidence") or [])}
    out.update({c: d.get(c, "") for c in FILL})
    return out


def cmd_review_sheets(a):
    run = a.run
    ledger = load_ledger(run)
    teams = load_teams(run, required=False)
    by_team = collections.OrderedDict()
    for r in ledger["rows"]:
        if r["state"] not in ("resolved", "held"):
            continue
        if not r.get("team_set_by"):  # a reviewer's reassignment sticks
            r["team"] = team_of(r, teams)
        by_team.setdefault(r["team"], []).append(r)
    imported = {r["polarion_id"] for r in ledger["rows"] if r.get("decision")}
    for team, rows in by_team.items():
        path = run_file(run, "review", team + ".csv")
        if os.path.exists(path) and not a.force:
            _, _, old = read_csv(path, "utf-8-sig")
            if any(cells.get("decision", "").strip() and cells.get("polarion_id") not in imported
                   for _, _, cells, _ in old):
                raise Problem("%s has decisions that are not imported yet: import it first, "
                              "or --force overwrites it" % path)
        write_csv(path, SHEET, [sheet_row(r) for r in rows])
        print("%s: %d case(s) -> %s" % (team, len(rows), path))
    save_ledger(run, ledger)
    return 0


def cmd_review_import(a):
    run = a.run
    ledger = load_ledger(run)
    repo = a.tests_repo or (load_manifest(run).get("tests_repo") or {}).get("path")
    header, _, records = read_csv(a.sheet, "utf-8-sig")
    missing = [c for c in ("polarion_id",) + FILL if c not in header]
    if missing:
        raise Problem("%s lacks column(s) %s: regenerate it with `review sheets`"
                      % (a.sheet, ", ".join(missing)))
    rows = {r["polarion_id"]: r for r in ledger["rows"] if r["state"] in ("resolved", "held")}
    teams = load_teams(run, required=False)
    errors, updates, moves = [], [], []
    for n, _, cells, problem in records:
        get = getter(cells, {c: c for c in header})
        decision = get("decision").lower()
        at = "%s row %d (%s)" % (os.path.basename(a.sheet), n, get("polarion_id"))
        row = rows.get(get("polarion_id"))
        if row and get("team") and get("team") != row.get("team"):
            if not teams or get("team") not in teams["teams"]:
                errors.append("%s: team %r is not in teams.yaml" % (at, get("team")))
            elif not get("reviewer"):
                errors.append("%s: moving a case to another team needs a reviewer" % at)
            else:
                moves.append((row, get("team"), get("reviewer")))
        if not decision:
            continue
        if problem or not row:
            errors.append("%s: %s" % (at, problem or "not an eligible case in the ledger"))
            continue
        if decision not in DECISIONS:
            errors.append("%s: decision %r is not one of %s" % (at, decision, ", ".join(DECISIONS)))
        for c in ("reviewer", "rationale"):
            if not get(c):
                errors.append("%s: %s is required" % (at, c))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", get("date")):
            errors.append("%s: date must be YYYY-MM-DD" % at)
        chosen = get("chosen_jira")
        if chosen and not JIRA_URL.fullmatch(chosen):
            errors.append("%s: chosen_jira %r is not a Jira issue URL" % (at, chosen))
        if decision == "migrate" and not (chosen or row.get("jira_url")):
            errors.append("%s: the Jira link is on hold (%s): name it in chosen_jira"
                          % (at, ", ".join(sorted(set(row["holds"]) & JIRA_HOLDS))))
        if decision == "link-existing":
            test = get("existing_test")
            if not TEST_NODE.match(test):
                errors.append("%s: existing_test must be tests/...py::name" % at)
            elif repo:
                path, _, name = test.partition("::")
                text = ""
                if os.path.isfile(os.path.join(repo, path)):
                    with open(os.path.join(repo, path), encoding="utf-8") as f:
                        text = f.read()
                if not re.search(r"\bdef %s\b" % re.escape(name.split("::")[-1]), text):
                    errors.append("%s: %s is not in %s" % (at, test, repo))
            if get("attach_id").lower() not in ("yes", "no"):
                errors.append("%s: attach_id must be yes or no" % at)
        if decision == "retire":
            for c in ("retire_reason", "polarion_owner"):
                if not get(c):
                    errors.append("%s: retire needs %s" % (at, c))
        updates.append((row, dict({c: get(c) for c in FILL}, decision=decision,
                                  attach_id=get("attach_id").lower(),
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
            s["priority"] = PRIORITY.get(norm(r["source"].get("importance")), "P2")
            s["description"] = r["source"].get("title", "")
            for field in ("preconditions", "steps", "expected"):
                if r["pse"][field]:
                    s[field] = r["pse"][field]
            s["source_pse"] = r["pse"]["source"]
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
    errors = ["owner sheet: %s is not an approved migrate case of %s" % (pid, team)
              for pid in sorted(set(owner) - {r["polarion_id"] for r in rows})]
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
            elif not isinstance(conf, (int, float)) or conf < a.min_confidence:
                p["evidence"].append("model chose %s at confidence %s, under %s"
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


def build_module(text, tree, keep, strip):
    """The module with only the tests in `keep`, minus decorators named in `strip`."""
    drop = set()
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
    for func in keep:
        for d in func.decorator_list:
            if deco_name(d).split(".")[-1] in strip:
                drop |= set(range(d.lineno, d.end_lineno + 1))
    src = text.splitlines()
    kept = [line for i, line in enumerate(src, 1) if i not in drop]
    body = "\n".join(x for x in kept if not re.match(r"import pytest\s*$", x))
    if "pytest." not in body:
        kept = [x for x in kept if not re.match(r"import pytest\s*$", x)]
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


def check_module(text, expected, rows, registered, strict):
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
        if not why_off(func, parents, tree):
            errs.append("%s: would be collected; it needs __test__ = False" % where)
        if body_statements(func) or fixture_args(func):
            errs.append("%s: has an implementation or fixtures; a design stub has only its docstring"
                        % where)
        doc = ast.get_docstring(func) or ""
        pids = MARKERS_ENTRY.findall(doc)
        if len(pids) != 1:
            errs.append("%s: needs exactly one `- polarion(\"ID\")` under Markers:, found %d"
                        % (where, len(pids)))
            continue
        pid = pids[0]
        found.append(pid)
        if pid not in expected:
            errs.append("%s: %s is not an approved case placed in this folder" % (where, pid))
            continue
        url = rows[pid]["decision"].get("chosen_jira") or rows[pid]["jira_url"]
        if not validate.links_jira(doc, url):
            errs.append("%s: no `Jira: %s` line for its own requirement" % (where, url))
        if rows[pid]["pse"]["source"] != "complete" and not re.search(r"^\s*Source:", doc, re.M):
            errs.append("%s: Polarion had no steps or expected result; a `Source:` line must say "
                        "which sections are proposed" % where)
    errs += ["%s: defined %d times" % (n, k) for n, k in names.items() if k > 1]
    errs += ["%s: listed by %d tests" % (p, k) for p, k in collections.Counter(found).items() if k > 1]
    errs += ["%s: no stub" % p for p in sorted(set(expected) - set(found))]
    m = LIVE_MARK.search(text)
    if m:
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
    errors, files, seen = [], [], {}
    existing = scan_repo(repo)
    for stub in sorted(glob_py(stub_dir)):
        with open(stub, encoding="utf-8") as f:
            text = f.read()
        tree = ast.parse(text)
        groups = collections.OrderedDict()
        for func, _ in test_functions(tree):
            tid = next((d.args[0].value for d in func.decorator_list if isinstance(d, ast.Call)
                        and deco_name(d).endswith("qf_test_id") and d.args
                        and isinstance(d.args[0], ast.Constant)), None)
            pid = (by_test_id.get(tid) or {}).get("polarion_id")
            if not pid:
                pids = MARKERS_ENTRY.findall(ast.get_docstring(func) or "")
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
            module = build_module(text, tree, {f for f, _ in members}, strip)
            expected = {p for _, p in members}
            errs = check_module(module, expected, rows, registered, strict)
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
                pid = MARKERS_ENTRY.findall(ast.get_docstring(func) or "")[0]
                node = "%s::%s%s" % (target, cls.name + "::" if cls else "", func.name)
                tests.append({"node": node, "polarion_id": pid,
                              "jira_url": rows[pid]["decision"].get("chosen_jira") or rows[pid]["jira_url"]})
                rows[pid]["package"] = {"path": target, "node": node}
            files.append({"path": target, "source": stub, "tests": tests})
    for pid in sorted(set(rows) - set(seen)):
        errors.append("%s: approved for migration but no stub in %s" % (pid, stub_dir))
    manifest = {"team": team, "tracking_jira": url, "created": now(), "std": std_file,
                "repo": {"path": repo, "commit": git(repo, "rev-parse", "HEAD")},
                "stripped_markers": sorted(strip), "valid": not errors, "errors": errors,
                "files": files}
    save_json(os.path.join(out_dir, "manifest.json"), manifest)
    save_ledger(run, ledger)
    print("%s: %d module(s), %d stub(s) -> %s" % (team, len(files), sum(len(f["tests"]) for f in files), out_dir))
    if strip:
        print("removed @pytest.mark.%s: the tests repo does not register it" % ", ".join(sorted(strip)))
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
    co = a.checkout
    if git(co, "rev-parse", "HEAD") is None:
        raise Problem("%s is not a git checkout" % co)
    if git(co, "status", "--porcelain"):
        raise Problem("%s has uncommitted changes: stage into a clean, fresh checkout" % co)
    base = git(co, "rev-parse", "HEAD")
    origin = git(co, "rev-parse", "--verify", "-q", "origin/main")
    if origin and origin != base:
        print("WARNING: %s is at %s, origin/main is %s; fetch and branch from origin/main"
              % (co, base[:12], origin[:12]))
    key = JIRA_URL.fullmatch(manifest["tracking_jira"]).group(1)
    branch = a.branch or "polarion-migration/%s-%s" % (team, key.lower())
    if git(co, "rev-parse", "--verify", "-q", "refs/heads/" + branch):
        raise Problem("branch %s already exists in %s" % (branch, co))
    # Re-run the inventory against the new base: the repo may have moved.
    inventory = scan_repo(co)
    errors = []
    paths = [f["path"] for f in manifest["files"]]
    for f in manifest["files"]:
        if os.path.exists(os.path.join(co, f["path"])):
            errors.append("%s already exists on the new base" % f["path"])
        if not os.path.isdir(os.path.join(co, os.path.dirname(f["path"]))):
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
        out.append("| %s | [%s](%s) | `%s` | migrate (%s, %s) |" % (
            t["polarion_id"], jira_key, t["jira_url"], t["node"], d["reviewer"], d["date"]))
    out += ["", "### Polarion IDs and state", "",
            "- Each stub lists its Polarion ID under its docstring `Markers:` as `polarion(\"ID\")`. "
            "There is no `@pytest.mark.polarion` decorator yet, so the post-merge "
            "`mark-automated-polarion` job leaves these cases as they are. The Phase 2 PR that "
            "implements a test turns the entry into the real decorator, as "
            "docs/SOFTWARE_TEST_DESCRIPTION.md describes for `Markers:`."]
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
    missing = []
    for r in rows:
        r["pr"] = {"url": a.url, "state": a.state, "commit": a.commit, "recorded": now()}
        if a.checkout:
            where = [o for o in inventory.get(r["polarion_id"], []) if o["kind"] == "markers-entry"]
            r["stub_location"] = ["%s:%s" % (o["path"], o["line"]) for o in where]
            if not where:
                missing.append(r["polarion_id"])
            elif r.get("package") and where[0]["path"] != r["package"]["path"]:
                r["pr"]["moved_from"] = r["package"]["path"]
    save_ledger(run, ledger)
    print("recorded %s (%s) for %d case(s)" % (a.url, a.state, len(rows)))
    if missing:
        raise Failed(["%s: no `polarion(\"%s\")` Markers: entry in %s" % (p, p, a.checkout) for p in missing])
    return 0


# -------------------------------------------------------------- W6: reconcile

RECONCILE = ("polarion_id", "team", "original_status", "original_automation", "decision", "jira_url",
             "evidence", "proposed_status", "proposed_automation", "reason", "ready_to_apply")


def propose(r, inventory, sync_verified):
    d = r.get("decision") or {}
    impl = implemented_evidence(inventory.get(r["polarion_id"], []))
    p = {"proposed_status": "", "proposed_automation": "", "ready": False, "reason": "",
         "evidence": "; ".join(fmt_occ(o) for o in impl) or (r.get("pr") or {}).get("url", "")}
    decision = d.get("decision")
    if not decision:
        p["reason"] = "no team decision yet"
    elif decision == "hold":
        p["reason"] = "held: %s" % d.get("rationale")
    elif decision == "retire":
        p.update(proposed_status="inactive", ready=True,
                 reason="team-approved retirement: %s (Polarion owner %s)" % (d.get("retire_reason"),
                                                                            d.get("polarion_owner")))
    elif impl:
        p.update(proposed_automation="automated", ready=bool(sync_verified),
                 reason="implemented test %s carries the real ID" % impl[0].get("test", impl[0]["path"])
                 + ("" if sync_verified else "; ready once the owner verifies how the sync marks it"))
    elif decision == "link-existing":
        p["reason"] = ("attach the ID to %s first" if d.get("attach_id") == "yes" else
                       "covered by %s without its ID: the team decides attach or retire") % d.get("existing_test")
    else:
        p["reason"] = ("stub only (an end-state gap): it stays active until a Phase 2 test with the "
                       "real ID is merged")
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
    p.add_argument("--allow", action="append", default=[], metavar="FIELD=VALUE",
                   help="accept another status or automation value once the owner confirms it")
    p.add_argument("--jira-base", help="Jira base URL for bare keys, e.g. https://redhat.atlassian.net")
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

    steps_html = ("<table><tr><th>#</th><th>Step</th><th>Expected Result</th></tr>"
                  "<tr><td>1</td><td>Start a VM</td><td>VM is Running</td></tr>"
                  "<tr><td>2</td><td>Hot-plug a NIC</td><td>NIC is attached</td></tr></table>")
    cases = os.path.join(tmp, "cases.csv")
    with open(cases, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Type", "Title", "Status", "Case Automation", "Case Importance",
                    "Linked Work Items", "Test Steps", "Case Component", "Description"])
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
            ("CNV-13", "Test Case", "Other project", "Approved", "Not Automated", "", "verifies: CNV-107", "", "", ""),
            ("CNV-15", "Test Case", "Automated, no code", "Approved", "Automated", "", "verifies: CNV-100", "", "", ""),
            ("CNV-100", "Requirement", "NIC hot-plug", "Approved", "", "", "", "", "", ""),
        ]
        w.writerows(rows)
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
    assert by["CNV-5"]["state"] == "resolved" and "existing-marker" in by["CNV-5"]["flags"]
    assert "implemented-in-code" not in by["CNV-5"]["flags"]  # a disabled stub proves nothing
    assert by["CNV-10"]["state"] == "resolved" and "manualonly" in by["CNV-10"]["flags"]
    holds = {p: by[p]["holds"] for p in by if by[p]["state"] == "held"}
    assert holds == {"CNV-4": ["requirement-without-jira"], "CNV-6": ["ambiguous-jira"],
                     "CNV-7": ["automation-empty"], "CNV-8": ["requirement-not-in-export"],
                     "CNV-9": ["unexpected-status"], "CNV-11": ["invalid-jira-url"],
                     "CNV-12": ["bare-key-is-polarion-id"], "CNV-13": ["wrong-jira-project"]}, holds
    assert [r["state"] for r in led["rows"] if r["polarion_id"] == "CNV-1"] == ["resolved", "duplicate"]

    # W2
    fails(2, "triage", run, "queue")  # the invalid row blocks triage
    ok("triage", run, "queue", "--allow-defects")
    queue = load_json(run_file(run, "triage", "queue.json"))
    assert [g["jira_key"] for g in queue["groups"]] == ["CNV-45678"]
    group = queue["groups"][0]
    assert [x["polarion_id"] for x in group["cases"]] == ["CNV-1", "CNV-5", "CNV-10"]
    assert "CNV-3" in [s["polarion_id"] for s in group["siblings"]]
    ctx_name = "CNV-45678@20261006T100000Z.json"
    save_json(run_file(run, "triage", "context", ctx_name),
              {"jira_key": "CNV-45678", "fetched_at": "2026-10-06T10:00:00Z", "error": None,
               "jira": {"summary": "NIC hot-plug", "type": "Story", "status": "Closed", "resolution": "Done"}})
    ev = [{"claim": "Jira story is Done", "source": "https://redhat.atlassian.net/browse/CNV-45678"}]
    verdicts = {"jira_key": "CNV-45678", "context_snapshot": ctx_name, "model": "claude (work Vertex)",
                "cases": [dict(polarion_id="CNV-1", verdict="migrate", rationale="Shipped, untested.",
                               uncertainty="low", proposed_team="network", evidence=ev),
                          dict(polarion_id="CNV-5", verdict="migrate", rationale="Only a stub has the ID.",
                               uncertainty="medium", proposed_team="network", evidence=ev),
                          dict(polarion_id="CNV-10", verdict="retire-candidate", rationale="Manual check.",
                               uncertainty="high", proposed_team="network", evidence=ev)]}
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    fails(1, "triage", run, "merge")  # manualonly must be manual-only-review
    verdicts["cases"][2]["verdict"] = "manual-only-review"
    verdicts["cases"][0]["evidence"] = [{"claim": "trust me", "source": "my notes"}]
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    fails(1, "triage", run, "merge")  # evidence needs a URL or repo@commit:path:line
    verdicts["cases"][0]["evidence"] = ev
    save_json(run_file(run, "triage", "verdicts", "CNV-45678.json"), verdicts)
    ok("triage", run, "merge", "--group", "CNV-45678", "--dry-run")
    assert not load_ledger(run)["rows"][0].get("triage")
    ok("triage", run, "merge")
    assert load_ledger(run)["rows"][0]["triage"]["verdict"] == "migrate"

    # Team map, W3
    teams_file = os.path.join(tmp, "teams.yaml")
    write(teams_file, yaml.safe_dump({
        "teams": {"network": {"roots": ["tests/network"], "reviewer": "net-lead",
                              "tracking_jira": "https://redhat.atlassian.net/browse/CNV-80001"},
                  "storage": {"roots": ["tests/storage"], "reviewer": "sto-lead"}},
        "components": {"Networking": "tests/network/hotplug"},
        "approved_by": "net-lead", "approved_on": "2026-10-07"}))
    ok("teams", run, teams_file)
    ok("review", run, "sheets")
    sheet = run_file(run, "review", "network.csv")
    _, _, recs = read_csv(sheet, "utf-8-sig")
    assert sorted(cells["polarion_id"] for _, _, cells, _ in recs) == ["CNV-1", "CNV-10", "CNV-5"]
    unassigned = run_file(run, "review", "unassigned.csv")
    assert os.path.exists(unassigned)

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
    # A held case: the team names the Jira the hold was about.
    fill(unassigned, {"CNV-6": dict(sign, decision="migrate")})
    fails(1, "review", run, "import", unassigned)  # ambiguous Jira: chosen_jira is required
    fill(unassigned, {"CNV-6": dict(sign, decision="migrate", team="network",
                                    chosen_jira="https://redhat.atlassian.net/browse/CNV-50001")})
    ok("review", run, "import", unassigned)
    ok("review", run, "sheets")  # the reviewer's team assignment survives a regeneration
    assert "CNV-6" in [c["polarion_id"] for _, _, c, _ in read_csv(sheet, "utf-8-sig")[2]]
    ok("review", run, "calibrate")
    cal = load_json(run_file(run, "review", "calibration.json"))
    assert cal["per_verdict"]["migrate"]["agreed"] == 2 and cal["overall_agreement"] == 1.0, cal

    # W4: scenario list.
    outputs = os.path.join(tmp, "outputs")
    ok("scenarios", run, "--team", "network", "--tier", "Tier 2", "--outputs", outputs)
    with open(os.path.join(outputs, "CNV-80001", "input", "CNV-80001_scenarios.yaml"), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    got = {s["polarion_id"]: s for s in doc["scenarios"]}
    assert sorted(got) == ["CNV-1", "CNV-5", "CNV-6"]
    assert got["CNV-6"]["jira_url"].endswith("/CNV-50001") and got["CNV-1"]["source_pse"] == "complete"
    assert got["CNV-5"]["source_pse"] == "missing" and "steps" not in got["CNV-5"]
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
                    "        Source: Polarion CNV-6 lists no steps or expected result; both are proposed.\n"))
    write(os.path.join(std_dir, "python-tests", "test_polarion_network_stubs.py"), stubs)
    fails(1, "package", run, "--team", "network", "--outputs", outputs)  # CNV-5 already in the repo
    led = load_ledger(run)
    assert "CNV-5" in " ".join(load_json(run_file(run, "package", "network", "manifest.json"))["errors"])
    # The team links CNV-5's case to that stub instead; re-run the batch without it.
    for r in led["rows"]:
        if r["polarion_id"] == "CNV-5" and r["state"] == "resolved":
            r["decision"].update(decision="link-existing",
                                 existing_test="tests/network/bridge/test_bridge.py::TestBridge::test_bridge",
                                 attach_id="yes")
    save_ledger(run, led)
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
    # A live marker on a stub is refused: the post-merge job would mark it Automated.
    rows_by = {"CNV-6": next(r for r in load_ledger(run)["rows"]
                             if r["polarion_id"] == "CNV-6" and r["state"] == "held")}
    live = module.replace("    def test_feature_a", '    @pytest.mark.polarion("CNV-6")\n    def test_feature_a')
    assert any("Automated on merge" in e for e in check_module(live, {"CNV-6"}, rows_by, {"polarion"}, True))

    # W5: stage into a fresh clone, then record the merged PR.
    co = os.path.join(tmp, "checkout")
    sh(tmp, "git", "clone", "-q", repo, co)
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
    assert "attach the ID" in prop["CNV-5"]["reason"]
    _, _, recs = read_csv(run_file(run, "reconcile", "audit_automated_without_code.csv"), "utf-8")
    assert [c["polarion_id"] for _, _, c, _ in recs] == ["CNV-15"]
    fresh = os.path.join(tmp, "fresh.csv")
    with open(cases, encoding="utf-8-sig") as f:
        text = f.read()
    write(fresh, text.replace("CNV-10,Test Case,Manual check,Approved", "CNV-10,Test Case,Manual check,Inactive"))
    ok("verify", run, fresh)
    write(fresh, text)  # the retirement was not applied
    fails(1, "verify", run, fresh)
    print("self-test: OK")


if __name__ == "__main__":
    sys.exit(main())
