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

II2_CATEGORIES = [("Functional", 4), ("Non-Functional", 5),
                  ("Integration & Compatibility", 3), ("Infrastructure", 1)]

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
    missing = [needle for key, needle in SECTIONS if key not in secs]
    rep.check("structure.all_sections_present", not missing,
              "Missing/out-of-order sections: %s" % ", ".join(missing))

    def hr_between(a, b):
        if a not in secs or b not in secs:
            return True  # missing section already reported
        return any(ln.strip() == "---" for ln in lines[secs[a][0]:secs[b][0]])

    rep.check("structure.horizontal_rules",
              hr_between("feature_overview", "section_i")
              and hr_between("section_i_3", "section_ii")
              and hr_between("section_iii_1", "section_iv"),
              "Missing '---' rule after Feature Overview, after Section I.3, "
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

    count_check("list_items.metadata", "metadata", BOLD_BULLET, 6)
    count_check("list_items.section_i_1", "section_i_1", CHECKBOX, 5)
    count_check("list_items.section_i_3", "section_i_3", CHECKBOX, 5)
    count_check("list_items.section_ii_3", "section_ii_3", BOLD_BULLET, 10)

    # II.1 Out of Scope: >=1 checkbox after the "Out of Scope" marker
    if "section_ii_1" in secs:
        body = secs["section_ii_1"][1]
        idx = next((i for i, ln in enumerate(body)
                    if "out of scope" in ln.lower()), None)
        n = count_between(body[idx + 1:], CHECKBOX) if idx is not None else 0
        rep.check("list_items.section_ii_1_out_of_scope", n >= 1,
                  "Out of Scope: found %d checkbox items, expected at least 1" % n)
    else:
        rep.check("list_items.section_ii_1_out_of_scope", False,
                  "Section II.1 not found")

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
        if total != 13:
            problems.append("total %d checkbox items, expected 13" % total)
        rep.check("list_items.section_ii_2", not problems,
                  "Section II.2: " + "; ".join(problems))
    else:
        rep.check("list_items.section_ii_2", False, "Section II.2 not found")

    # II.5: 7 top-level checkbox categories
    if "section_ii_5" in secs:
        body = secs["section_ii_5"][1]
        top = [ln for ln in body if re.match(r"^- \[[ xX]\]", ln)]
        rep.check("list_items.section_ii_5", len(top) == 7,
                  "Section II.5: found %d risk categories, expected 7" % len(top))
        # checked categories need >= 3 indented sub-items (warning only)
        for i, ln in enumerate(body):
            if not re.match(r"^- \[[xX]\]", ln):
                continue
            subs = 0
            for nxt in body[i + 1:]:
                if re.match(r"^\s+- ", nxt) or re.match(r"^\s+\* ", nxt):
                    subs += 1
                elif nxt.strip() and not nxt.startswith((" ", "\t")):
                    break
            if subs < 3:
                rep.check("content.risk_sub_items", False,
                          "Risk category %r has %d sub-items, expected 3 "
                          "(Risk, Mitigation, Impact/Status)" % (ln.strip(), subs),
                          warn_only=True)
        rep.check("content.risk_sub_items", True)
    else:
        rep.check("list_items.section_ii_5", False, "Section II.5 not found")

    # --- Section III.1 -----------------------------------------------------
    entries = []
    if "section_iii_1" in secs:
        i0, body = secs["section_iii_1"]
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
    return """# Test Docs
## **PCI Topology - Quality Engineering Plan**
### **Metadata & Tracking**
""" + "\n".join("- **Field %d:** value" % i for i in range(6)) + """
### **Feature Overview**
Some overview text.
---
## I. Motivation and Requirements Review (QE Review Guidelines)
### Section I.1 - Requirement & User Story Review Checklist
""" + boxes(5) + """
### Section I.2 - Known Limitations
- None known.
### Section I.3 - Technology and Design Review
""" + boxes(5) + """
---
## II. Software Test Plan (STP)
### Section II.1 - Scope of Testing
- [x] **Goal:** verify topology stability
**Out of Scope**
- [ ] **Hardware bring-up**
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
""" + boxes(3) + """
**Infrastructure**
""" + boxes(1) + """
### Section II.3 - Test Environment
""" + "\n".join("- **Env %d:** value" % i for i in range(10)) + """
### Section II.3.1 - Testing Tools & Frameworks
- pytest
### Section II.4 - Entry Criteria
- Build available
### Section II.5 - Risks
- [x] **Risk A**
  - Risk: something
  - Mitigation: something
  - Impact: low
""" + "\n".join("- [ ] **Risk %s**" % c for c in "BCDEFG") + """
## III. Test Scenarios & Traceability
### Section III.1 - Requirements-to-Tests Mapping
- **[PROJ-1]** -- As a user I want stable PCI topology
  - *Test Scenario:* Verify performance latency and security RBAC under
    concurrent monitoring metric scale load during upgrade migration [Tier 1]
  - *Priority:* P1
- **[PROJ-2]** -- As an admin I want alerts on failure
  - *Test Scenario:* Verify alert fires on induced failure [Tier 2]
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

    bad = good.replace("Some overview text.",
                       "Some overview text.\n```bash\nls\n```\n"
                       "IP: 10.42.15.87 mail jsmith@acme.com\nDecision: yes")
    bad = bad.replace("[Tier 2]", "Tier 2 (End-to-End)")
    rep = validate(bad)
    for name in ["content.no_code_blocks", "prohibited.real_ips",
                 "prohibited.real_emails", "prohibited.decision_blocks",
                 "content.valid_test_tiers"]:
        assert rep.checks[name] == "fail", "%s should fail: %s" % (name, rep.checks)

    # section removal detected
    rep = validate(good.replace("### Section II.4 - Entry Criteria", "### skipped"))
    assert rep.checks["structure.all_sections_present"] == "fail"
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
