#!/usr/bin/env python3
"""QualityFlow STP mechanical validator.

Deterministic replacement for LLM-performed grep/count checks
(audit finding AI-05). The structure checks come from the STP template the
document was built from (--template; QF's bundled template when omitted):
its sections in order, the '---' rules between them, its bold block labels,
its fixed labelled items (and the keys nested under them), and the sub-fields
its example items carry, which every real item in that block must carry too.
The rest is QF's own contract for every team: the document header, the
Section III mapping format std-orchestrator parses, and prohibited content.

With the ticket's Jira snapshot (--jira, or the {KEY}_jira_data.yaml the
jira-collector writes beside the STP), the metadata is checked against it:
Feature and Epic keys, the QE owner, and people's names spelled as in Jira.

Usage:
    python3 skills/output-validator/validate_doc.py <stp_file> \
        [--template <stp template>] [--stp-header "Expected Header"] \
        [--jira <jira_data.yaml>] [--yaml]

Exit codes: 0 = no errors (warnings allowed), 1 = at least one error,
2 = usage / file problem.

NOT covered here (LLM judgment, per SKILL.md): AC-scenario temporal
alignment, third-party vendor-name detection, semantic quality of
scenarios beyond the fixed forbidden-string list.
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

BUNDLED_TEMPLATE = (Path(__file__).resolve().parent.parent
                    / "template-engine" / "templates" / "stp-template.md")

# Section III is QF's contract, whatever the template: std-orchestrator parses it.
III_NEEDLES = ("requirements-to-tests mapping", "test scenarios and traceability")

GENERIC_SCENARIOS = [
    "Verify automated tests pass in CI",
    "All tests should pass",
    "Ensure test coverage is complete",
    "Validate CI pipeline runs successfully",
]

PROHIBITED_HEADINGS = ["appendix", "glossary", "references", "summary"]

COMMENT = re.compile(r"<!--.*?-->", re.S)
PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}|\{[A-Z_]+\}|\[[^\]]*\]")
NUMBERING = re.compile(r"^(?:section\s+)?(?:[ivx]+|\d+)(?:\.\d+)*\.?(?=[\s:-])[\s:-]*")
# ponytail: wording heuristic for "this may be left out"; a team whose template
# words it differently gets the item required, so extend the list then.
OPTIONAL = re.compile(r"if applicable|optional|remove this field", re.I)
BLOCK_LABEL = re.compile(r"^\*\*([^*]+)\*\*")
TOP_ITEM = re.compile(r"^[-*] ")
ITEM_LABEL = re.compile(r"^[-*] (?:\[[ xX]\] )?\*\*([^*]+)\*\*")
SUB_FIELD = re.compile(r"^\s+[-*] \*{1,2}([^*]+?):\*{1,2}")
NESTED_KEY = re.compile(r"^\s+[-*] ([A-Za-z][\w /&-]*):")
EMPTY = re.compile(r"^\W*(?:none|n/a)\b|no risk identified", re.I)

CHECKBOX = re.compile(r"^\s*[-*] \[[ xX]\]")
CHECKED = re.compile(r"^\s*[-*] \[[xX]\]")
REQ_ENTRY = re.compile(r"^- \*\*\[([^\]]+)\]\*\*\s*(?:--|—|-)?\s*(.*)")
IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
OLD_NUMBERING = re.compile(r"\bII\.(4\.[A-D]|[678])\b")
# A human-only field filled with status prose instead of the template's
# [Name/Date] placeholder (pilot feedback: the placeholders went missing).
STATUS_PROSE = re.compile(
    r"\*(?:Sign-off|PM/Lead Agreement):\*\s*(?:n/?a\b|none\b|stated in|"
    r"[^\n]*?\b(?:pending|tbd|not recorded|not yet|awaiting)\b)", re.I)
# "- **Feature Tracking:** [PROJ-1](...)" — a metadata line's label and value.
META_LINE = re.compile(r"^\s*- \*\*([^*]+?):\*\*\s*(.*)$", re.M)
PERSON = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][A-Za-z'-]+)+\b")
SCENARIO_LINE = re.compile(r"^\s*- \*Test Scenario:\*(.*)")
SCENARIO_ID = re.compile(r"\*\*TS-(\d+)\*\*")
CLASS_TAG = re.compile(r"\[(?:Tier [123]|unit|functional|integration|e2e)\]", re.I)
MATURITY = re.compile(r"^\s+- (DP|TP|GA):\s*(.*)$")

NFR_KEYWORDS = {
    "Security Testing": ["security", "rbac", "auth", "injection", "permission",
                         "unauthorized", "access control"],
    "Performance Testing": ["performance", "latency", "throughput", "benchmark",
                            "response time"],
    "Scale Testing": ["scale", "concurrent", "parallel", "multiple", "batch",
                      "capacity", "limit"],
    "Monitoring": ["monitor", "alert", "metric", "health", "observability",
                   "status"],
    "Upgrade Testing": ["upgrade", "migration", "version", "compatibility",
                        "backward"],
}


def heading_text(line):
    """Strip markdown heading/bold markers; return normalized text or None.

    Typography is normalized ("&" -> "and", em/en dashes -> "-") so trivial
    styling never fails the section-presence check.
    """
    if not line.lstrip().startswith("#"):
        return None
    text = line.strip().lstrip("#").strip().strip("*").strip().lower()
    return text.replace("&", "and").replace("—", "-").replace("–", "-")


def norm(text):
    """A label or heading as compared: lower case, no parenthetical, no colon."""
    text = text.strip().strip("*").strip().lower()
    text = text.replace("&", "and").replace("—", "-").replace("–", "-")
    return re.sub(r"\s*\([^)]*\)", "", text).strip(" :")


def needle(heading_line):
    """A template heading as searched for in the document: no numbering."""
    return NUMBERING.sub("", norm(heading_line.strip().lstrip("#")))


def as_pattern(line):
    """A template line with its placeholders as wildcards."""
    pieces = PLACEHOLDER.split(line.strip())
    return re.compile("^" + ".+".join(re.escape(p) for p in pieces) + r"\s*$")


def items(body):
    """Top-level list items as (first line, [lines until the next one])."""
    out = []
    for i, ln in enumerate(body):
        if TOP_ITEM.match(ln):
            block = []
            for nxt in body[i + 1:]:
                if TOP_ITEM.match(nxt) or (nxt.strip() and not nxt.startswith((" ", "\t"))):
                    break
                block.append(nxt)
            out.append((ln, block))
    return out


def blocks(body):
    """A section body split at its bold label lines (and, in a document, at
    sub-headings): [(normalized label or None, raw label line, lines)]."""
    out = [(None, "", [])]
    for ln in body:
        m = BLOCK_LABEL.match(ln)
        h = heading_text(ln)
        if m or h is not None:
            out.append((norm(m.group(1) if m else h), ln, []))
        else:
            out[-1][2].append(ln)
    return out


def read_template(text):
    """The structure rules a template states. Every heading after the first
    (the document header) is a section, except a title heading with a
    placeholder right after it."""
    lines = COMMENT.sub("", text).splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
    t = {"text": text, "header": None, "title": None, "sections": [], "rules": []}
    if not heads:
        return t
    t["header"] = lines[heads[0]]
    heads = heads[1:]
    if heads and PLACEHOLDER.search(lines[heads[0]]):
        t["title"] = lines[heads[0]]
        heads = heads[1:]
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        sec = {"needle": needle(lines[i]), "optional": bool(OPTIONAL.search(lines[i])),
               "blocks": []}
        if not any(x in sec["needle"] for x in III_NEEDLES):
            for label, raw, blines in blocks(lines[i + 1:end]):
                rule = {"label": label, "fixed": [], "keys": {}, "fields": [],
                        "optional": label is None or bool(OPTIONAL.search(raw))
                        # ponytail: "Other" is the catch-all a document adds only for a stray risk
                        or label == "other"}
                for first, kids in items(blines):
                    fields = [m.group(1) for m in map(SUB_FIELD.match, kids) if m]
                    m = ITEM_LABEL.match(first)
                    if fields and not CHECKBOX.match(first):
                        # an example item: every real item here carries its fields
                        rule["fields"] += [f for f in fields if f not in rule["fields"]]
                    elif m and not PLACEHOLDER.fullmatch(m.group(1).strip()) \
                            and not OPTIONAL.search(first):
                        lab = norm(m.group(1))
                        rule["fixed"].append(lab)
                        keys = [k.group(1) for k in map(NESTED_KEY.match, kids) if k]
                        if keys:
                            rule["keys"][lab] = keys
                sec["blocks"].append(rule)
        t["sections"].append(sec)
        for k in range(i + 1, end):
            if lines[k].strip() == "---" and n + 1 < len(heads):
                t["rules"].append((n, n + 1))
    return t


class Report:
    def __init__(self):
        self.checks = {}      # name -> "pass" | "fail" | "warn"
        self.errors = []
        self.warnings = []

    def check(self, name, ok, message=None, warn_only=False):
        if ok:
            self.checks.setdefault(name, "pass")
        elif warn_only:
            self.checks[name] = "warn"
            if message:
                self.warnings.append(message)
        else:
            self.checks[name] = "fail"
            if message:
                self.errors.append(message)
        return ok


def split_sections(lines, needles):
    """Return {needle index: (heading_index, [content lines until the next
    found section])}, matching headings in template order."""
    hits = []  # (line_index, needle index)
    cursor = 0
    for i, line in enumerate(lines):
        h = heading_text(line)
        if h is None:
            continue
        h = norm(h)
        for n in range(cursor, len(needles)):
            if needles[n] and needles[n] in h:
                hits.append((i, n))
                cursor = n + 1
                break
    found = {}
    for k, (i, n) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(lines)
        found[n] = (i, lines[i + 1:end])
    return found


def section_iii(lines):
    for want in III_NEEDLES:
        for i, ln in enumerate(lines):
            h = heading_text(ln)
            if h and want in h:
                end = next((j for j in range(i + 1, len(lines))
                            if heading_text(lines[j]) is not None), len(lines))
                return lines[i + 1:end]
    return None


def check_template(rep, lines, tmpl):
    secs = split_sections(lines, [s["needle"] for s in tmpl["sections"]])
    missing = [s["needle"] for n, s in enumerate(tmpl["sections"])
               if n not in secs and not s["optional"]]
    rep.check("structure.all_sections_present", not missing,
              "Missing/out-of-order sections: %s" % ", ".join(missing))

    bad_rules = ["%s / %s" % (tmpl["sections"][a]["needle"], tmpl["sections"][b]["needle"])
                 for a, b in tmpl["rules"] if a in secs and b in secs
                 and not any(ln.strip() == "---" for ln in lines[secs[a][0]:secs[b][0]])]
    rep.check("structure.horizontal_rules", not bad_rules,
              "Missing '---' rule between: %s" % "; ".join(bad_rules))

    no_block, no_item, no_field = [], [], []
    for n, sec in enumerate(tmpl["sections"]):
        if n not in secs:
            continue
        body = secs[n][1]
        doc_blocks = blocks(body)
        labels = {norm(m.group(1)): (ln, kids) for ln, kids in items(body)
                  for m in [ITEM_LABEL.match(ln)] if m}
        for rule in sec["blocks"]:
            mine = [b for b in doc_blocks if b[0] == rule["label"]]
            if not mine:
                if not rule["optional"]:
                    no_block.append("%s: '%s'" % (sec["needle"], rule["label"]))
                continue
            for lab in rule["fixed"]:
                if lab not in labels:
                    no_item.append("%s: '%s'" % (sec["needle"], lab))
                    continue
                have = {k.group(1) for k in map(NESTED_KEY.match, labels[lab][1]) if k}
                lost = [k for k in rule["keys"].get(lab, []) if k not in have]
                if lost:
                    no_item.append("%s: '%s' without %s" % (sec["needle"], lab, ", ".join(lost)))
                if lab == "feature maturity":
                    check_maturity(rep, labels[lab][1])
            if not rule["fields"]:
                continue
            where = "%s%s" % (sec["needle"], (" / " + rule["label"]) if rule["label"] else "")
            for _, _, blines in mine:
                real = [(ln, kids) for ln, kids in items(blines) if not CHECKBOX.match(ln)]
                if not real and not any(EMPTY.search(ln.strip().strip("-* ")) for ln in blines):
                    no_field.append("%s: no items and no 'None' statement" % where)
                for ln, kids in real:
                    if EMPTY.search(ln.strip().strip("-* ").replace("*", "")):
                        continue
                    have = {m.group(1) for m in map(SUB_FIELD.match, kids) if m}
                    lost = [f for f in rule["fields"] if f not in have]
                    if lost:
                        no_field.append("%s: %s has no %s" % (
                            where, ln.strip()[:50], ", ".join("*%s:*" % f for f in lost)))
    rep.check("structure.template_blocks", not no_block,
              "Block labels from the template missing: %s" % "; ".join(no_block))
    rep.check("content.template_items", not no_item,
              "Items from the template missing: %s" % "; ".join(no_item))
    rep.check("content.item_fields", not no_field,
              "Items without the fields the template's example items carry: %s"
              % "; ".join(no_field))


def check_maturity(rep, kids):
    # ponytail: the one value-shape rule, for a template that has the field;
    # pilot feedback had maturity explained in prose instead of a version.
    phases = {m.group(1): m.group(2).strip() for m in map(MATURITY.match, kids) if m}
    bad = [k for k, v in phases.items() if len(v) > 40 or re.search(r"[.;] \w", v) or not v]
    rep.check("content.feature_maturity", not bad,
              "Feature Maturity values must each be a version, N/A or "
              "'<value> [confirm]' — prose in %s" % ", ".join(bad))


def check_jira(rep, text, jira):
    """The metadata against the jira-collector snapshot: the generator retyped
    names and keys from memory (a pilot STP misspelled its assignee 17 times
    and swapped the Feature and Epic keys)."""
    mi = (jira or {}).get("main_issue") or {}
    meta = {norm(m.group(1)): m.group(2) for m in META_LINE.finditer(text)}
    key, parent = mi.get("key"), ((mi.get("parent_issue") or {}).get("key"))
    bad = []
    feature, epic = meta.get("feature tracking"), meta.get("epic tracking")
    if parent and feature is not None and parent not in feature:
        bad.append("Feature Tracking does not name the parent %s" % parent)
    if key and parent and epic is not None and parent in epic and key not in epic:
        bad.append("Epic Tracking names the parent %s instead of %s" % (parent, key))
    qa = (mi.get("qa_contact") or {}).get("name")
    owner = next((v for k, v in meta.items() if k.startswith("qe owner")), None)
    if qa and owner is not None and qa not in owner:
        bad.append("QE Owner is not the Jira QA contact %s" % qa)
    people = {p.get("name") for p in [mi.get("assignee") or {}, mi.get("qa_contact") or {}]
              + [i.get("assignee") or {} for i in jira.get("linked_issues") or []]
              if isinstance(p, dict) and p.get("name")}
    for found in sorted(set(PERSON.findall(text)) - people):
        near = [n for n in people if difflib.SequenceMatcher(None, found, n).ratio() >= 0.85]
        if near:
            bad.append("'%s' is spelled '%s' in Jira" % (found, near[0]))
    rep.check("content.jira_metadata", not bad,
              "Metadata disagrees with the Jira snapshot: %s" % "; ".join(bad))


def validate(text, stp_header=None, template=None, jira=None):
    tmpl = read_template(template if template is not None
                         else BUNDLED_TEMPLATE.read_text(encoding="utf-8"))
    rep = Report()
    lines = text.splitlines()
    nonempty = [ln for ln in lines if ln.strip()]

    # --- structure (from the template) -------------------------------------
    first = nonempty[0] if nonempty else ""
    if stp_header:
        rep.check("structure.document_header", first.strip() == "# " + stp_header,
                  "First line is %r, expected '# %s'" % (first, stp_header))
    elif tmpl["header"]:
        rep.check("structure.document_header", bool(as_pattern(tmpl["header"]).match(first)),
                  "First line %r does not match the template's %r" % (first, tmpl["header"]))
    else:
        rep.check("structure.document_header", first.startswith("# "),
                  "First line is not a '# ' document header: %r" % first)

    if tmpl["title"]:
        title = next((ln for ln in nonempty[1:] if heading_text(ln) is not None), "")
        rep.check("structure.feature_title", bool(as_pattern(tmpl["title"]).match(title)),
                  "Feature title %r does not match the template's %r"
                  % (title, tmpl["title"].strip()))

    check_template(rep, lines, tmpl)

    # --- Section III (QF's contract) ---------------------------------------
    entries = []
    body = section_iii(lines)
    if body is not None:
        for i, ln in enumerate(body):
            m = REQ_ENTRY.match(ln)
            if not m:
                continue
            block = []
            for nxt in body[i + 1:]:
                if REQ_ENTRY.match(nxt) or heading_text(nxt) is not None:
                    break
                block.append(nxt)
            entries.append((m.group(1), m.group(2).strip(), block))
        rep.check("structure.section_iii", True)  # no minimum enforced

        # The table layout some teams' templates use. A blank Requirement ID
        # cell continues the requirement above.
        table_bad, cols, current = [], None, None
        for ln in body:
            if not ln.strip().startswith("|"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            low = [c.lower() for c in cells]
            if cols is None:
                if any("requirement id" in c for c in low) and any("test scenario" in c for c in low):
                    cols = {k: next((i for i, c in enumerate(low) if k in c), None)
                            for k in ("requirement id", "requirement summary",
                                      "test scenario", "tier", "priority")}
                continue
            if all(set(c) <= set(":- ") for c in cells):
                continue
            get = lambda k: cells[cols[k]] if cols[k] is not None and cols[k] < len(cells) else ""  # noqa: E731
            if get("requirement id"):
                current = get("requirement id")
                entries.append((current, get("requirement summary"), []))
            if current is None or not all(get(k) for k in ("test scenario", "tier", "priority")
                                          if cols[k] is not None):
                table_bad.append(current or "(row without a requirement)")
            elif entries:
                entries[-1][2].append("*Test Scenario:* %s *Priority:* %s"
                                      % (get("test scenario"), get("priority")))
        if cols is not None:
            rep.check("content.section_iii_1_format", not table_bad,
                      "Table rows missing a scenario, tier or priority: %s"
                      % ", ".join(dict.fromkeys(table_bad)))

        bad_fmt = [jid for jid, _, block in entries
                   if not any("*Test Scenario:*" in b for b in block)
                   or not any("*Priority:*" in b for b in block)]
        rep.check("content.section_iii_1_format", not bad_fmt,
                  "Entries missing *Test Scenario:* / *Priority:* sub-items: %s"
                  % ", ".join(bad_fmt))

        summaries = [s for _, s, _ in entries]
        dupes = sorted({s for s in summaries if summaries.count(s) > 1})
        rep.check("content.unique_requirement_summaries", not dupes,
                  "Repeated requirement summaries: %s" % "; ".join(dupes))

        sec3_text = "\n".join(body)
        bad_tiers = re.findall(
            r"Tier\s*\d\s*\((?:Functional|End-to-End)\)|\bUnit Tests\b",
            sec3_text)
        rep.check("content.valid_test_tiers", not bad_tiers,
                  "Invalid tier references in Section III.1 (use inline "
                  "[Tier 1]/[Tier 2]): %s" % ", ".join(sorted(set(bad_tiers))))

        # Each scenario: its classification tag inline (std-orchestrator parses
        # it from this line) and a TS id that is unique and in document order.
        ids, untagged = [], []
        for i, ln in enumerate(body):
            m = SCENARIO_LINE.match(ln)
            if not m:
                continue
            scen = m.group(1)
            for nxt in body[i + 1:]:  # a wrapped scenario line continues it
                if re.match(r"^\s*- ", nxt) or not nxt.strip():
                    break
                scen += " " + nxt.strip()
            if not CLASS_TAG.search(scen):
                untagged.append(scen.strip()[:60])
            ids += [int(x) for x in SCENARIO_ID.findall(scen)]
        rep.check("content.scenario_classification_inline", not untagged,
                  "Scenarios without an inline [Tier N] / test-type tag (a separate "
                  "*Test Type:* line is not parsed): %s" % "; ".join(untagged[:5]))
        dup_ids = sorted({x for x in ids if ids.count(x) > 1})
        rep.check("content.scenario_ids_unique", not dup_ids,
                  "Duplicate scenario ids: %s" % ", ".join("TS-%02d" % x for x in dup_ids))
        rep.check("content.scenario_ids_sequential", ids == sorted(ids),
                  "Scenario ids are not in document order (renumber while no STD "
                  "exists): %s" % ", ".join("TS-%02d" % x for x in ids[:12]),
                  warn_only=True)
    else:
        rep.check("structure.section_iii", False, "Section III (Test Scenarios) not found")

    # --- content -----------------------------------------------------------
    rep.check("content.no_code_blocks", "```" not in text,
              "Document contains a ``` code fence block")

    found_generic = [g for g in GENERIC_SCENARIOS if g.lower() in text.lower()]
    rep.check("content.no_generic_scenarios", not found_generic,
              "Generic/meta scenarios present: %s" % "; ".join(found_generic))

    # NFR-scenario cross-reference (warning only)
    if entries:
        checked = [ln for ln in lines if CHECKED.match(ln)]
        scen_text = " ".join(s + " " + " ".join(b) for _, s, b in entries).lower()
        for item, keywords in NFR_KEYWORDS.items():
            if any(item.lower() in ln.lower() for ln in checked):
                if not any(k in scen_text for k in keywords):
                    rep.check("content.nfr_scenario_crossref", False,
                              "Strategy item '%s' is checked but no scenarios in "
                              "Section III appear to test %s-related behavior"
                              % (item, item), warn_only=True)
        rep.check("content.nfr_scenario_crossref", True)

    # --- prohibited content (unless the template itself has it) -------------
    tmpl_low = tmpl["text"].lower()
    allowed = {p for p in PROHIBITED_HEADINGS
               if any(p in s["needle"] for s in tmpl["sections"])}
    bad_heads = []
    for ln in lines:
        h = heading_text(ln)
        if h and any((h == p or h.startswith(p + " ")) and p not in allowed
                     for p in PROHIBITED_HEADINGS):
            bad_heads.append(ln.strip())
    rep.check("prohibited.sections", not bad_heads,
              "Prohibited sections present: %s" % ", ".join(bad_heads))

    old_nums = sorted(n for n in set(OLD_NUMBERING.findall(text))
                      if "II." + n not in tmpl["text"])
    rep.check("prohibited.old_numbering", not old_nums,
              "Old-style section numbering used: %s"
              % ", ".join("II." + n for n in old_nums))

    rep.check("prohibited.decision_blocks",
              not re.search(r"^\s*\*{0,2}(Decision|Justification):", text, re.M),
              "Document contains 'Decision:' or 'Justification:' blocks")

    bad_ips = []
    for m in IP_RE.finditer(text):
        octets = [int(x) for x in m.groups()]
        if any(o > 255 for o in octets):
            continue
        ip = m.group(0)
        if not ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
            bad_ips.append(ip)
    rep.check("prohibited.real_ips", not bad_ips,
              "Non-RFC-5737 IP addresses present: %s"
              % ", ".join(sorted(set(bad_ips))))

    bad_emails = [e for e in EMAIL_RE.findall(text)
                  if not e.lower().endswith(("@example.com", "@example.org",
                                             "@example.net"))]
    rep.check("prohibited.real_emails", not bad_emails,
              "Non-example email addresses present: %s"
              % ", ".join(sorted(set(bad_emails))))

    prose = sorted({m.group(0) for m in STATUS_PROSE.finditer(text)})
    rep.check("prohibited.status_prose_in_sign_offs", not prose,
              "Human-only fields filled with status text instead of the [Name/Date] "
              "placeholder: %s" % "; ".join(prose))

    if jira:
        check_jira(rep, text, jira)

    rep.check("prohibited.current_status_field",
              "current status" in tmpl_low
              or not re.search(r"^\s*- \*\*Current Status", text, re.M),
              "Removed 'Current Status' metadata field is present")

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

def _fixture():
    def boxes(*labels):
        return "\n".join("- [x] **%s**\n  - *Details:* covered" % lab for lab in labels)
    risks = "\n".join("**%s**\n\n- **Mitigation:** No risk identified — covered by II.3." % c
                      for c in ["Test Coverage", "Test Environment", "Untestable Aspects",
                                "Resource Constraints", "Dependencies"])
    return """# Test Docs
## **PCI Topology - Quality Engineering Plan**
### **Metadata & Tracking**
- **Enhancement(s):** VEP 1
- **Feature Tracking:** PROJ-1
- **Epic Tracking:** PROJ-2
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: v5.1.0 [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** sig-network
- **Participating SIGs:** None

**Document Conventions (if applicable):**

- **PCI:** device topology term
### **Feature Overview**
Some overview text.
---
## I. Motivation and Requirements Review (QE Review Guidelines)
### Section I.1 - Requirement & User Story Review Checklist
""" + boxes("Review Requirements", "Understand Value and Customer Use Cases", "Testability",
            "Acceptance Criteria", "Non-Functional Requirements (NFRs)") + """
### Section I.2 - Known Limitations
- **IPv6 is not supported**
  - Upstream non-goal
  - *Sign-off:* [Name/Date]
### Section I.3 - Technology and Design Review
""" + boxes("Developer Handoff/QE Kickoff", "Technology Challenges", "API Extensions",
            "Test Environment Needs", "Topology Considerations") + """
## II. Software Test Plan (STP)
### Section II.1 - Scope of Testing
Topology stability for admins.

**Testing Goals**

- **[P0]** As an admin, verify topology stability

**Out of Scope**

- **Hardware bring-up**
  - *Rationale:* Owned by the hardware team
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **No SR-IOV NICs in the lab**
  - *Sign-off:* [Name/Date]
### Section II.2 - Test Strategy
**Functional**
""" + boxes("Functional Testing", "Automation Testing", "Regression Testing",
            "Self-Validation Testing") + """
**Non-Functional**
- [x] **Performance Testing** — latency
- [x] **Scale Testing** — concurrent ops
- [x] **Security Testing** — RBAC checks
- [ ] **Usability Testing** — n/a
- [x] **Monitoring** — metrics
**Integration & Compatibility**
""" + boxes("Compatibility Testing", "Upgrade Testing", "Dependencies",
            "Cross Integrations") + """
**Infrastructure**
""" + boxes("Cloud Testing") + """
### Section II.3 - Test Environment
""" + "\n".join("- **%s:** value" % f for f in [
        "Cluster Topology", "Platform & Product Version(s)", "CPU Virtualization",
        "Compute Resources", "Special Hardware", "Storage", "Network",
        "Required Operators", "Platform", "Special Configurations"]) + """
### Section II.3.1 - Testing Tools & Frameworks
- **Test Framework:** pytest
- **CI/CD:** N/A
- **Other Tools:** N/A
### Section II.4 - Entry Criteria
- [ ] Build available
### Section II.5 - Risks
**Timeline/Schedule**

- **Risk:** build may slip
  - **Mitigation:** prioritize P0
  - *Estimated impact on schedule:* 2 weeks
  - *Sign-off:* [Name/Date]

""" + risks + """
---
## III. Test Scenarios & Traceability
### Section III.1 - Requirements-to-Tests Mapping
- **[PROJ-1]** -- As a user I want stable PCI topology
  - *Test Scenario:* **TS-01**: Verify performance latency and security RBAC under
    concurrent monitoring metric scale load during upgrade migration [Tier 1]
    - *Priority:* P1
- **[PROJ-2]** -- As an admin I want alerts on failure
  - *Test Scenario:* **TS-02**: [Tier 2] Verify alert fires on induced failure
    - *Priority:* P2
---
## Section IV - Sign-off and Approval
- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name / @github-handle]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name / @github-handle]
"""


# A team template unlike QF's: other sections, a table sign-off, an example
# item whose *Owner:* field every real item must then carry.
_OTHER_TEMPLATE = """# {PROJECT_NAME} — {FEATURE_TITLE} Quality Engineering Plan

## Section I: Motivation & Requirements Review

### I.1 — Requirements Checklist

- [ ] **Acceptance criteria defined**
- [ ] **Scope is bounded**

### I.2 — Known Limitations

- **[Limitation]**
  - *Owner:* [Name]

## Section II: Software Test Plan

{SCOPE}

---

## Section III: Test Scenarios & Traceability

{SCENARIOS}

## Section IV: Sign-off & Approval

| Role | Name | Date |
|------|------|------|
"""

_OTHER_DOC = """# Acme — Widget Sync Quality Engineering Plan

## Section I: Motivation & Requirements Review

### I.1 — Requirements Checklist

- [x] **Acceptance criteria defined**
- [x] **Scope is bounded**

### I.2 — Known Limitations

- **No offline mode**
  - *Owner:* [Name]

## Section II: Software Test Plan

Sync between two widgets.

---

## Section III: Test Scenarios & Traceability

- **[PROJ-7]** — As a user I want widgets to sync
  - *Test Scenario:* **TS-01**: [functional] Verify a change on one widget reaches the other
    - *Priority:* P0

## Section IV: Sign-off & Approval

| Role | Name | Date |
|------|------|------|
| QE Lead | | |
"""


def self_test():
    good = _fixture()
    rep = validate(good)
    fails = {k: v for k, v in rep.checks.items() if v == "fail"}
    assert not fails, "clean fixture should pass, got: %s / %s" % (fails, rep.errors)
    assert not rep.warnings, rep.warnings

    bad = good.replace("Some overview text.",
                       "Some overview text.\n```bash\nls\n```\n"
                       "IP: 10.42.15.87 mail jsmith@acme.com\nDecision: yes")
    bad = bad.replace("[Tier 2]", "Tier 2 (End-to-End)")
    rep = validate(bad)
    for name in ["content.no_code_blocks", "prohibited.real_ips",
                 "prohibited.real_emails", "prohibited.decision_blocks",
                 "content.valid_test_tiers", "content.scenario_classification_inline"]:
        assert rep.checks[name] == "fail", "%s should fail: %s" % (name, rep.checks)

    # section removal detected
    rep = validate(good.replace("### Section II.4 - Entry Criteria", "### skipped"))
    assert rep.checks["structure.all_sections_present"] == "fail"

    # The pilot-feedback regressions, one by one, each caught by a rule the
    # bundled template states.
    cases = {
        # Feature Maturity explained in prose, or a phase dropped
        "content.feature_maturity": good.replace(
            "  - GA: v5.1.0 [confirm]",
            "  - GA: TBD — the general GA label does not establish offline GA."),
        "content.template_items": good.replace("  - TP: N/A\n", ""),
        # a sign-off placeholder replaced by status text
        "prohibited.status_prose_in_sign_offs": good.replace(
            "  - *PM/Lead Agreement:* [Name/Date]", "  - *PM/Lead Agreement:* Pending."),
        "content.item_fields": good.replace(
            "  - Upstream non-goal\n  - *Sign-off:* [Name/Date]", "  - Upstream non-goal"),
        "structure.template_blocks": good.replace("**Test Limitations**", ""),
    }
    for name, doc in cases.items():
        rep = validate(doc)
        assert rep.checks.get(name) == "fail", "%s should fail: %s" % (name, rep.errors)
    for doc in [good.replace("- **No SR-IOV NICs in the lab**\n  - *Sign-off:* [Name/Date]",
                             "- **No SR-IOV NICs in the lab**"),
                good.replace("  - *Rationale:* Owned by the hardware team\n", ""),
                good.replace("  - *Sign-off:* [Name/Date]\n\n**Test", "\n**Test")]:
        assert validate(doc).checks["content.item_fields"] == "fail"
    rep = validate(good.replace("- [x] **Scale Testing** — concurrent ops\n", ""))
    assert rep.checks["content.template_items"] == "fail"
    rep = validate(good.replace("**TS-02**", "**TS-01**"))
    assert rep.checks["content.scenario_ids_unique"] == "fail"
    rep = validate(good.replace("**TS-01**", "**TS-09**"))
    assert rep.checks["content.scenario_ids_sequential"] == "warn"
    # the rule sits before Section III, not before Section II
    rep = validate(good.replace("---\n## III.", "## III."))
    assert rep.checks["structure.horizontal_rules"] == "fail"
    # "None" stands in for the items of a block whose example items carry fields
    rep = validate(good.replace("- **IPv6 is not supported**\n  - Upstream non-goal\n"
                                "  - *Sign-off:* [Name/Date]",
                                "None — reviewed and confirmed with [Name/Date]."))
    assert rep.checks["content.item_fields"] == "pass", rep.errors

    # The table layout, from a template with no mapping subheading: scenarios in
    # a table whose blank Requirement ID cells continue the row above.
    bundled = BUNDLED_TEMPLATE.read_text(encoding="utf-8")
    no_sub = bundled.replace("#### **1. Requirements-to-Tests Mapping**\n", "")
    head, _, tail = good.partition("### Section III.1 - Requirements-to-Tests Mapping\n")
    table = ("| Requirement ID | Requirement Summary | Test Scenario(s) | Tier | Priority |\n"
             "|:--|:--|:--|:--|:--|\n"
             "| PROJ-1 | As a user I want stable PCI topology | Verify latency under load | 1 | P1 |\n"
             "| | | Verify RBAC blocks a non-admin | 2 | P2 |\n")
    tabled = head + table + tail[tail.index("---"):]
    rep = validate(tabled, template=no_sub)
    fails = {k: v for k, v in rep.checks.items() if v == "fail"}
    assert not fails, "table layout should pass: %s / %s" % (fails, rep.errors)
    rep = validate(tabled.replace("| 2 | P2 |", "| 2 | |"), template=no_sub)
    assert rep.checks["content.section_iii_1_format"] == "fail"
    # QF's own template still wants its mapping subheading
    assert validate(tabled).checks["structure.all_sections_present"] == "fail"

    # A team with its own template is held to that template, not QF's.
    rep = validate(_OTHER_DOC, template=_OTHER_TEMPLATE)
    fails = {k: v for k, v in rep.checks.items() if v == "fail"}
    assert not fails, "own-template doc should pass: %s / %s" % (fails, rep.errors)
    assert validate(_OTHER_DOC).checks["structure.all_sections_present"] == "fail"
    rep = validate(_OTHER_DOC.replace("  - *Owner:* [Name]\n", ""), template=_OTHER_TEMPLATE)
    assert rep.checks["content.item_fields"] == "fail"
    rep = validate(_OTHER_DOC.replace("- [x] **Scope is bounded**\n", ""),
                   template=_OTHER_TEMPLATE)
    assert rep.checks["content.template_items"] == "fail"
    rep = validate(_OTHER_DOC.replace("Widget Sync Quality", "Widget Sync Test"),
                   template=_OTHER_TEMPLATE)
    assert rep.checks["structure.document_header"] == "fail"
    # The metadata against the Jira snapshot (pilot: swapped keys, retyped names).
    jira = {"main_issue": {"key": "PROJ-2", "parent_issue": {"key": "PROJ-1"},
                           "assignee": {"name": "Jane Smithson"},
                           "qa_contact": {"name": "Sam Rivers"}}}
    meta_doc = good.replace("- **QE Owner(s):** [Name]", "- **QE Owner(s):** Sam Rivers")
    rep = validate(meta_doc, jira=jira)
    assert rep.checks["content.jira_metadata"] == "pass", rep.errors
    for doc in [meta_doc.replace("- **Feature Tracking:** PROJ-1", "- **Feature Tracking:** PROJ-2"),
                meta_doc.replace("Sam Rivers", "[Name]"),
                meta_doc + "\nApproval: Jane Smithsen\n"]:
        assert validate(doc, jira=jira).checks["content.jira_metadata"] == "fail", doc[-80:]
    # status text anywhere in a sign-off, not only at its start
    rep = validate(good.replace("  - *Sign-off:* [Name/Date]",
                                "  - *Sign-off:* Approval pending — the feature assignee", 1))
    assert rep.checks["prohibited.status_prose_in_sign_offs"] == "fail"
    print("self-test: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="STP markdown file to validate")
    ap.add_argument("--template", help="the STP template the document was built from "
                    "(default: template-engine's bundled templates/stp-template.md)")
    ap.add_argument("--stp-header", help="expected document header "
                    "(project_context.stp_header), without the leading '# '")
    ap.add_argument("--jira", help="the ticket's jira-collector snapshot "
                    "(default: {KEY}_jira_data.yaml beside the STP, when present)")
    ap.add_argument("--yaml", action="store_true", help="YAML report output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        self_test()
        return
    if not args.file:
        ap.error("file is required (or use --self-test)")
    try:
        text = open(args.file, encoding="utf-8").read()
        template = open(args.template, encoding="utf-8").read() if args.template else None
        jira_path = args.jira or str(Path(args.file).with_name(
            Path(args.file).name.replace("_test_plan.md", "_jira_data.yaml")))
        jira = (yaml.safe_load(open(jira_path, encoding="utf-8"))
                if args.jira or (jira_path != args.file and Path(jira_path).is_file()) else None)
    except (OSError, yaml.YAMLError) as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
    failed = render(validate(text, args.stp_header, template, jira), args.yaml)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
