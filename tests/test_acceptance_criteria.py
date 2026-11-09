"""validate_doc.py fails a plan that never mentions what an acceptance criterion names."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_doc", ROOT / "skills/output-validator/validate_doc.py")
vd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vd)

PLAN = """# Test plan
- **[PROJ-1]** -- Admins back up VMs over IPv4 with DNS names
  - *Test Scenario:* **TS-01**: [Tier 1] Verify a VM backup completes over IPv4
**Out of Scope**
- **Restore drills** -- not tested: needs a second site
"""


def _check(acs, plan=PLAN):
    rep = vd.Report()
    vd.check_acceptance(rep, plan, {"main_issue": {"acceptance_criteria": acs}})
    return rep


def test_a_criterion_the_plan_never_mentions_fails():
    rep = _check("# Backups are encrypted with KMS keys held in an HSM\n# A VM backup completes\n")
    assert rep.checks["content.acceptance_criteria"] == "fail"
    assert "AC-1" in rep.errors[0] and "(KMS, HSM)" in rep.errors[0] and "AC-2" not in rep.errors[0]


def test_a_generic_name_present_does_not_hide_the_rest():
    rep = _check("* A GCP VM with TPM and EFI enabled migrates\n")  # VM is in the plan, the rest is not
    assert rep.checks["content.acceptance_criteria"] == "fail"


def test_some_names_missing_warns_and_one_missing_is_not_counted():
    rep = _check("1. Works over IPv6 and IPv4 with TLS and DNS\n2. Tenant CR deletion cleans up\n")
    assert rep.checks["content.acceptance_criteria"] == "warn"
    assert "(IPv6, TLS)" in rep.warnings[0] and "AC-2" not in rep.warnings[0]


def test_flattened_paragraphs_identifiers_and_headings():
    flat = ("Acceptance Criteria\n\nBackups are encrypted with KMS keys held in an HSM\n\n"
            "QE signs off; RestartRequired is never set; OPENAI_BASE_URL is honoured\n")
    assert vd.ac_items(flat)[1:] == ["Backups are encrypted with KMS keys held in an HSM",
                                     "QE signs off; RestartRequired is never set; OPENAI_BASE_URL is honoured"]
    assert vd.acronyms(vd.ac_items(flat)[2]) == []  # process word, CamelCase, snake_case
    rep = _check(flat)
    assert rep.checks["content.acceptance_criteria"] == "fail" and "AC-1 'Backups" in rep.errors[0]


def test_a_stated_exclusion_or_no_criteria_passes():
    assert _check("# Restore drills run against a DR site with RPO checks\n",
                  PLAN + "- **DR and RPO** -- not tested: no second site\n"
                  ).checks["content.acceptance_criteria"] == "pass"
    assert "content.acceptance_criteria" not in _check(None).checks
