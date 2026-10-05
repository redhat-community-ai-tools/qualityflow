#!/usr/bin/env python3
"""QualityFlow STP mechanical validator.

Deterministic replacement for LLM-performed grep/count checks
(audit finding AI-05). Validates document structure, list-item counts,
and prohibited content for a generated STP.

Usage:
    python3 skills/output-validator/validate_doc.py <stp_file> \
        [--stp-header "Expected Header"] [--yaml]

Exit codes: 0 = no errors (warnings allowed), 1 = at least one error,
2 = usage / file problem.

NOT covered here (LLM judgment, per SKILL.md): AC-scenario temporal
alignment, third-party vendor-name detection, semantic quality of
scenarios beyond the fixed forbidden-string list.
"""

import argparse
import re
import sys

import yaml

SECTIONS = [
    ("metadata", "metadata and tracking"),
    ("feature_overview", "feature overview"),
    ("section_i", "motivation and requirements review"),
    ("section_i_1", "requirement and user story review checklist"),
    ("section_i_2", "known limitations"),
    ("section_i_3", "technology and design review"),
    ("section_ii", "software test plan"),
    ("section_ii_1", "scope of testing"),
    ("section_ii_2", "test strategy"),
    ("section_ii_3", "test environment"),
    ("section_ii_3_1", "testing tools"),
    ("section_ii_4", "entry criteria"),
    ("section_ii_5", "risks"),
    ("section_iii", "test scenarios and traceability"),
    ("section_iii_1", "requirements-to-tests mapping"),
    ("section_iv", "sign-off and approval"),
]
# QF's bundled template has a "1. Requirements-to-Tests Mapping" subheading; some
# teams' templates put the mapping straight under Section III.
OPTIONAL_SECTIONS = {"section_iii_1"}

II2_CATEGORIES = [("Functional", 4), ("Non-Functional", 5),
                  ("Integration & Compatibility", 4), ("Infrastructure", 1)]
II2_TOTAL = sum(n for _, n in II2_CATEGORIES)

RISK_CATEGORIES = ["Timeline/Schedule", "Test Coverage", "Test Environment",
                   "Untestable Aspects", "Resource Constraints", "Dependencies"]

GENERIC_SCENARIOS = [
    "Verify automated tests pass in CI",
    "All tests should pass",
    "Ensure test coverage is complete",
    "Validate CI pipeline runs successfully",
]

PROHIBITED_HEADINGS = ["appendix", "glossary", "references", "summary"]

CHECKBOX = re.compile(r"^\s*- \[[ xX]\]")
CHECKED = re.compile(r"^\s*- \[[xX]\]")
BOLD_BULLET = re.compile(r"^\s*- \*\*")
REQ_ENTRY = re.compile(r"^- \*\*\[([^\]]+)\]\*\*\s*(?:--|—|-)?\s*(.*)")
IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
OLD_NUMBERING = re.compile(r"\bII\.(4\.[A-D]|[678])\b")
TOP_ITEM = re.compile(r"^- ")
SIGN_OFF = re.compile(r"\*Sign-off:\*")
# A human-only field filled with status prose instead of the template's
# [Name/Date] placeholder (pilot feedback: the placeholders went missing).
STATUS_PROSE = re.compile(
    r"\*(?:Sign-off|PM/Lead Agreement):\*\s*(?:pending|tbd|not recorded|not yet|"
    r"n/?a\b|none\b|stated in|awaiting)", re.I)
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


def split_sections(lines):
    """Return {key: (heading_index, [content lines until next known section])}."""
    hits = []  # (line_index, key)
    cursor = 0
    for i, line in enumerate(lines):
        h = heading_text(line)
        if h is None:
            continue
        for key, needle in SECTIONS[cursor:]:
            if needle in h:
                hits.append((i, key))
                cursor = [k for k, _ in SECTIONS].index(key) + 1
                break
    found = {}
    for n, (i, key) in enumerate(hits):
        end = hits[n + 1][0] if n + 1 < len(hits) else len(lines)
        found[key] = (i, lines[i + 1:end])
    return found


def count_between(lines, pattern):
    return sum(1 for ln in lines if pattern.match(ln))


def validate(text, stp_header=None):
    rep = Report()
    lines = text.splitlines()
    nonempty = [ln for ln in lines if ln.strip()]

    # --- structure ---------------------------------------------------------
    first = nonempty[0] if nonempty else ""
    if stp_header:
        rep.check("structure.document_header", first.strip() == "# " + stp_header,
                  "First line is %r, expected '# %s'" % (first, stp_header))
    else:
        rep.check("structure.document_header", first.startswith("# "),
                  "First line is not a '# ' document header: %r" % first)

    title_re = re.compile(r"^## \*\*.+ - Quality Engineering Plan\*\*\s*$")
    title = next((ln for ln in nonempty[1:] if ln.startswith("##")), "")
    rep.check("structure.feature_title", bool(title_re.match(title)),
              "Feature title %r does not match '## **<Title> - Quality "
              "Engineering Plan**'" % title)

    secs = split_sections(lines)
    iii_key = "section_iii_1" if "section_iii_1" in secs else "section_iii"
    missing = [needle for key, needle in SECTIONS
               if key not in secs and key not in OPTIONAL_SECTIONS]
    rep.check("structure.all_sections_present", not missing,
              "Missing/out-of-order sections: %s" % ", ".join(missing))

    def hr_between(a, b):
        if a not in secs or b not in secs:
            return True  # missing section already reported
        return any(ln.strip() == "---" for ln in lines[secs[a][0]:secs[b][0]])

    rep.check("structure.horizontal_rules",
              hr_between("feature_overview", "section_i")
              and hr_between("section_ii_5", "section_iii")
              and hr_between(iii_key, "section_iv"),
              "Missing '---' rule after Feature Overview, before Section III, "
              "or before Section IV")

    # --- list-item counts --------------------------------------------------
    def count_check(name, key, pattern, expected, at_least=False):
        if key not in secs:
            rep.check(name, False, "Section for %s not found" % name)
            return
        n = count_between(secs[key][1], pattern)
        ok = n >= expected if at_least else n == expected
        rep.check(name, ok, "%s: found %d items, expected %s%d"
                  % (name, n, "at least " if at_least else "", expected))

    # Metadata fields end where Document Conventions begins (its terms are
    # bold bullets too).
    if "metadata" in secs:
        body = secs["metadata"][1]
        cut = next((i for i, ln in enumerate(body) if "document conventions" in ln.lower()),
                   len(body))
        fields = [ln for ln in body[:cut] if re.match(r"^- \*\*", ln)]
        rep.check("list_items.metadata", len(fields) >= 7,
                  "list_items.metadata: found %d top-level fields, expected at least 7 "
                  "(Enhancement, Feature Tracking, Epic Tracking, Feature Maturity, QE "
                  "Owner, Owning SIG, Participating SIGs)" % len(fields))
        fm = next((i for i, ln in enumerate(body[:cut])
                   if re.match(r"^- \*\*Feature Maturity:?\*\*", ln)), None)
        phases, bad = {}, []
        if fm is not None:
            for ln in body[fm + 1:cut]:
                m = MATURITY.match(ln)
                if not m:
                    if TOP_ITEM.match(ln):
                        break
                    continue
                phases[m.group(1)] = m.group(2).strip()
            bad = [k for k, v in phases.items()
                   if len(v) > 40 or re.search(r"[.;] \w", v) or not v]
        rep.check("content.feature_maturity",
                  fm is not None and set(phases) == {"DP", "TP", "GA"} and not bad,
                  "Feature Maturity must be a top-level metadata field with exactly DP/TP/GA "
                  "sub-items, each a version, N/A or '<value> [confirm]' — found %s%s"
                  % (sorted(phases) if fm is not None else "no Feature Maturity field",
                     ("; prose in " + ", ".join(bad)) if bad else ""))
    else:
        rep.check("list_items.metadata", False, "Metadata section not found")
    count_check("list_items.section_i_1", "section_i_1", CHECKBOX, 5)
    count_check("list_items.section_i_3", "section_i_3", CHECKBOX, 5)
    count_check("list_items.section_ii_3", "section_ii_3", BOLD_BULLET, 10)

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

    def is_none(body):
        return any(ln.strip().lower().startswith("none") for ln in body)

    # II.1 Out of Scope and Test Limitations
    if "section_ii_1" in secs:
        body = secs["section_ii_1"][1]
        low = [ln.lower() for ln in body]
        oos = next((i for i, ln in enumerate(low) if "out of scope" in ln), None)
        tl = next((i for i, ln in enumerate(low)
                   if i > (oos or 0) and "test limitations" in ln), None)
        oos_body = body[oos + 1:tl] if oos is not None else []
        oos_items = items(oos_body)
        rep.check("list_items.section_ii_1_out_of_scope", bool(oos_items) or is_none(oos_body),
                  "Out of Scope: no items and no 'None' statement")
        missing = [ln.strip() for ln, blk in oos_items
                   if not any("*Rationale:*" in x for x in blk)
                   or not any("*PM/Lead Agreement:*" in x for x in blk)]
        rep.check("content.out_of_scope_fields", not missing,
                  "Out of Scope items missing *Rationale:* / *PM/Lead Agreement:*: %s"
                  % "; ".join(missing))
        rep.check("structure.test_limitations", tl is not None,
                  "Section II.1 has no 'Test Limitations' block")
        tl_body = body[tl + 1:] if tl is not None else []
        unsigned = [ln.strip() for ln, blk in items(tl_body)
                    if not any(SIGN_OFF.search(x) for x in [ln] + blk)]
        rep.check("content.test_limitation_sign_offs", not unsigned,
                  "Test Limitations without a *Sign-off:* line: %s" % "; ".join(unsigned))
    else:
        rep.check("list_items.section_ii_1_out_of_scope", False,
                  "Section II.1 not found")

    # I.2 Known Limitations: every limitation carries its sign-off line
    if "section_i_2" in secs:
        body = secs["section_i_2"][1]
        lims = items(body)
        unsigned = [ln.strip() for ln, blk in lims
                    if not any(SIGN_OFF.search(x) for x in [ln] + blk)]
        rep.check("content.known_limitation_sign_offs",
                  (bool(lims) or is_none(body)) and not unsigned,
                  "Known Limitations without a *Sign-off:* line: %s"
                  % ("; ".join(unsigned) or "no items and no 'None' statement"))

    # II.2 categories
    if "section_ii_2" in secs:
        body = secs["section_ii_2"][1]
        cat_names = [c for c, _ in II2_CATEGORIES]
        markers = []  # (index, category)
        for i, ln in enumerate(body):
            plain = ln.strip().strip("#").strip().strip("*").strip().rstrip(":")
            if plain in cat_names:
                markers.append((i, plain))
        counts = {}
        for m, (i, cat) in enumerate(markers):
            end = markers[m + 1][0] if m + 1 < len(markers) else len(body)
            counts[cat] = count_between(body[i + 1:end], CHECKBOX)
        problems = []
        for cat, want in II2_CATEGORIES:
            if cat not in counts:
                problems.append("category '%s' heading missing" % cat)
            elif counts[cat] != want:
                problems.append("category '%s' has %d items, expected %d"
                                % (cat, counts[cat], want))
        total = sum(counts.values())
        if total != II2_TOTAL:
            problems.append("total %d checkbox items, expected %d" % (total, II2_TOTAL))
        rep.check("list_items.section_ii_2", not problems,
                  "Section II.2: " + "; ".join(problems))
    else:
        rep.check("list_items.section_ii_2", False, "Section II.2 not found")

    # II.5: the six risk categories as bold labels; a stated risk carries a
    # mitigation and a sign-off, a category with no risk still says why.
    if "section_ii_5" in secs:
        body = secs["section_ii_5"][1]
        labels = {}
        for i, ln in enumerate(body):
            plain = ln.strip().strip("*").strip().rstrip(":")
            if plain in RISK_CATEGORIES + ["Other"] and ln.strip().startswith("**"):
                labels[plain] = i
        order = sorted(labels.items(), key=lambda kv: kv[1])
        problems = ["category '%s' missing" % c for c in RISK_CATEGORIES if c not in labels]
        for n, (cat, i) in enumerate(order):
            end = order[n + 1][1] if n + 1 < len(order) else len(body)
            blk = "\n".join(body[i + 1:end])
            if "Mitigation:" not in blk:
                problems.append("'%s' has no Mitigation" % cat)
            if "**Risk:**" in blk and not SIGN_OFF.search(blk):
                problems.append("'%s' states a risk without a *Sign-off:* line" % cat)
        rep.check("list_items.section_ii_5", not problems,
                  "Section II.5: " + "; ".join(problems))
    else:
        rep.check("list_items.section_ii_5", False, "Section II.5 not found")

    # --- Section III.1 -----------------------------------------------------
    entries = []
    if iii_key in secs:
        i0, body = secs[iii_key]
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
        rep.check("list_items.section_iii", True)  # no minimum enforced

        # The table layout the design-docs rules also accept. A blank
        # Requirement ID cell continues the requirement above.
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
        rep.check("list_items.section_iii", False, "Section III.1 not found")

    # --- content -----------------------------------------------------------
    rep.check("content.no_code_blocks", "```" not in text,
              "Document contains a ``` code fence block")

    found_generic = [g for g in GENERIC_SCENARIOS if g.lower() in text.lower()]
    rep.check("content.no_generic_scenarios", not found_generic,
              "Generic/meta scenarios present: %s" % "; ".join(found_generic))

    # NFR-scenario cross-reference (warning only)
    if "section_ii_2" in secs and entries:
        strategy_text = [ln for ln in secs["section_ii_2"][1] if CHECKED.match(ln)]
        scen_text = " ".join(s + " " + " ".join(b) for _, s, b in entries).lower()
        for item, keywords in NFR_KEYWORDS.items():
            if any(item.lower() in ln.lower() for ln in strategy_text):
                if not any(k in scen_text for k in keywords):
                    rep.check("content.nfr_scenario_crossref", False,
                              "Strategy item '%s' is checked but no scenarios in "
                              "Section III appear to test %s-related behavior"
                              % (item, item), warn_only=True)
        rep.check("content.nfr_scenario_crossref", True)

    # --- prohibited content ------------------------------------------------
    bad_heads = []
    for ln in lines:
        h = heading_text(ln)
        if h and any(h == p or h.startswith(p + " ") for p in PROHIBITED_HEADINGS):
            bad_heads.append(ln.strip())
    rep.check("prohibited.sections", not bad_heads,
              "Prohibited sections present: %s" % ", ".join(bad_heads))

    old_nums = sorted(set(OLD_NUMBERING.findall(text)))
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

    rep.check("prohibited.current_status_field",
              not re.search(r"^\s*- \*\*Current Status", text, re.M),
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
    def boxes(n, label="Item"):
        return "\n".join("- [x] **%s %d:** covered" % (label, i + 1)
                         for i in range(n))
    risks = "\n".join("**%s**\n\n- **Mitigation:** No risk identified — covered by II.3."
                      % c for c in RISK_CATEGORIES[1:])
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
""" + boxes(5) + """
### Section I.2 - Known Limitations
- **IPv6 is not supported**
  - Upstream non-goal
  - *Sign-off:* [Name/Date]
### Section I.3 - Technology and Design Review
""" + boxes(5) + """
## II. Software Test Plan (STP)
### Section II.1 - Scope of Testing
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
""" + boxes(4) + """
**Non-Functional**
- [x] **Performance Testing:** latency
- [x] **Scale Testing:** concurrent ops
- [x] **Security Testing:** RBAC checks
- [ ] **Usability:** n/a
- [x] **Monitoring:** metrics
**Integration & Compatibility**
""" + boxes(4) + """
**Infrastructure**
""" + boxes(1) + """
### Section II.3 - Test Environment
""" + "\n".join("- **Env %d:** value" % i for i in range(10)) + """
### Section II.3.1 - Testing Tools & Frameworks
- pytest
### Section II.4 - Entry Criteria
- Build available
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
- **Reviewer:** [Name / @github-username]
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

    # The pilot-feedback regressions, one by one.
    cases = {
        # Feature Maturity nested / explained in prose
        "content.feature_maturity": good.replace(
            "  - GA: v5.1.0 [confirm]",
            "  - GA: TBD — the general GA label does not establish offline GA."),
        # a sign-off placeholder replaced by status text
        "prohibited.status_prose_in_sign_offs": good.replace(
            "  - *PM/Lead Agreement:* [Name/Date]", "  - *PM/Lead Agreement:* Pending."),
        "content.known_limitation_sign_offs": good.replace(
            "  - Upstream non-goal\n  - *Sign-off:* [Name/Date]", "  - Upstream non-goal"),
        "content.test_limitation_sign_offs": good.replace(
            "- **No SR-IOV NICs in the lab**\n  - *Sign-off:* [Name/Date]",
            "- **No SR-IOV NICs in the lab**"),
        "structure.test_limitations": good.replace("**Test Limitations**", ""),
        "content.out_of_scope_fields": good.replace(
            "  - *Rationale:* Owned by the hardware team\n", ""),
        "list_items.section_ii_5": good.replace("  - *Sign-off:* [Name/Date]\n\n**Test", "\n**Test"),
        "list_items.section_ii_2": good.replace("- [x] **Scale Testing:** concurrent ops\n", ""),
        "content.scenario_ids_unique": good.replace("**TS-02**", "**TS-01**"),
    }
    for name, doc in cases.items():
        rep = validate(doc)
        assert rep.checks.get(name) == "fail", "%s should fail: %s" % (name, rep.errors)
    rep = validate(good.replace("**TS-01**", "**TS-09**"))
    assert rep.checks["content.scenario_ids_sequential"] == "warn"

    # The table layout: no mapping subheading, scenarios in a table
    # whose blank Requirement ID cells continue the row above.
    head, _, tail = good.partition("### Section III.1 - Requirements-to-Tests Mapping\n")
    table = ("| Requirement ID | Requirement Summary | Test Scenario(s) | Tier | Priority |\n"
             "|:--|:--|:--|:--|:--|\n"
             "| PROJ-1 | As a user I want stable PCI topology | Verify latency under load | 1 | P1 |\n"
             "| | | Verify RBAC blocks a non-admin | 2 | P2 |\n")
    tabled = head + table + tail[tail.index("---"):]
    rep = validate(tabled)
    fails = {k: v for k, v in rep.checks.items() if v == "fail"}
    assert not fails, "table layout should pass: %s / %s" % (fails, rep.errors)
    rep = validate(tabled.replace("| 2 | P2 |", "| 2 | |"))
    assert rep.checks["content.section_iii_1_format"] == "fail"
    # the rule sits before Section III, not before Section II
    rep = validate(good.replace("---\n## III.", "## III."))
    assert rep.checks["structure.horizontal_rules"] == "fail"
    print("self-test: OK")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="STP markdown file to validate")
    ap.add_argument("--stp-header", help="expected document header "
                    "(project_context.stp_header), without the leading '# '")
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
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
    failed = render(validate(text, args.stp_header), args.yaml)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
