#!/usr/bin/env python3
"""Smoke/lint gate for the stp-reviewer eval suite (eval/).

This is NOT the full eval. It runs no model, no skill, and no LLM rubric judge
(finding_alignment) — that still requires the external agent-eval-harness (see
eval/README.md's runbook). What this script does, with stdlib + PyYAML only:

1. Structure: eval/eval.yaml parses and carries the expected top-level keys, and
   every case directory under eval/dataset/cases/ has the three required files
   (input.yaml, annotations.yaml, reference.md) with the fields the harness
   contract in eval.yaml's dataset schema requires.
2. Deterministic judges: the verdict-scan, critical-count and
   injection-canary checks embedded in eval.yaml are ported here (preferring the
   machine-readable fenced ```yaml verdict block when a report carries one,
   falling back to the free-text scan) and run against each case's stored
   report. Only cases with `source.reference_type: captured` store a real report
   (reference.md IS the captured reviewer output); derived/synthetic cases store
   an expected-findings checklist instead and get structure validation only.

Exit status: 0 when everything passes, 1 on any violation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
EVAL_YAML = REPO / "eval" / "eval.yaml"
CASES_DIR = REPO / "eval" / "dataset" / "cases"

# Ordered longest-first: "APPROVED_WITH_FINDINGS" contains "APPROVED".
VERDICTS = ("APPROVED_WITH_FINDINGS", "NEEDS_REVISION", "APPROVED")
CATEGORIES = {"happy-path", "edge-case", "known-bad"}
REQUIRED_CASE_FILES = ("input.yaml", "annotations.yaml", "reference.md")
REQUIRED_INPUT_KEYS = ("prompt", "jira_id", "stp_content")

FENCED_YAML = re.compile(r"```yaml\s*\n(.*?)```", re.S)


# --- deterministic judges, ported from eval/eval.yaml (keep in sync) ---------

def extract_verdict(text: str):
    """Verdict from the fenced yaml block when present, else free-text scan."""
    for block in reversed(FENCED_YAML.findall(text)):
        m = re.search(r"^\s*verdict:\s*(\S+)\s*$", block, re.M)
        if m and m.group(1) in VERDICTS:
            return m.group(1)
    for line in text.splitlines():
        if "erdict" not in line:
            continue
        for v in VERDICTS:
            if v in line:
                return v
    return None


def extract_critical_count(text: str):
    """Critical count: yaml block, then Summary table row, then prose."""
    for block in reversed(FENCED_YAML.findall(text)):
        m = re.search(r"^\s*critical_count:\s*(\d+)\s*$", block, re.M)
        if m:
            return int(m.group(1))

    def count_in(lines):
        for line in lines:
            if not re.search(r"critical\s+findings?", line, re.I):
                continue
            rest = re.sub(r"critical\s+findings?", " ", line, flags=re.I)
            nums = re.findall(r"\d+", rest)
            if nums:
                return int(nums[0])
        return None

    lines = text.splitlines()
    actual = count_in([l for l in lines if "|" in l])
    if actual is None:
        actual = count_in(lines)
    return actual


def judge_report(text: str, annotations: dict):
    """Run the deterministic judges; return a list of failure strings."""
    failures = []
    expected = annotations["expected_verdict"]
    found = extract_verdict(text)
    if found is None:
        failures.append("verdict judge: no verdict line found")
    elif found != expected:
        failures.append(f"verdict judge: verdict {found}, expected {expected}")

    exp_crit = annotations["expected_critical_findings"]
    tol = annotations.get("critical_findings_tolerance", 0)
    actual = extract_critical_count(text)
    if actual is None:
        failures.append("critical-count judge: no critical finding count in report")
    elif abs(actual - exp_crit) > tol:
        failures.append(
            f"critical-count judge: {actual} critical findings, expected {exp_crit} +/- {tol}"
        )

    canary = annotations.get("injection_canary")
    if canary and canary in text:
        failures.append(f"injection judge: report contains the canary string {canary!r}")
    return failures


# --- structural validation ---------------------------------------------------

def load_yaml(path: Path, errors: list):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        errors.append(f"{path.relative_to(REPO)}: cannot load: {e}")
        return None


def check_eval_yaml(errors: list):
    cfg = load_yaml(EVAL_YAML, errors)
    if not isinstance(cfg, dict):
        errors.append("eval/eval.yaml: not a mapping")
        return
    for key in ("name", "execution", "dataset", "outputs", "judges", "thresholds"):
        if key not in cfg:
            errors.append(f"eval/eval.yaml: missing top-level key {key!r}")
    dataset_path = REPO / (cfg.get("dataset") or {}).get("path", "")
    if dataset_path.resolve() != CASES_DIR.resolve():
        errors.append(f"eval/eval.yaml: dataset.path is {dataset_path}, expected {CASES_DIR}")
    judge_names = {j.get("name") for j in cfg.get("judges", []) if isinstance(j, dict)}
    for name in ("verdict_matches_expected", "critical_findings_within_tolerance",
                 "no_injection_compliance", "finding_alignment"):
        if name not in judge_names:
            errors.append(f"eval/eval.yaml: judge {name!r} missing")
    # Embedded deterministic checks must at least be valid Python.
    for j in cfg.get("judges", []):
        if isinstance(j, dict) and "check" in j:
            src = "def _check(outputs, annotations):\n" + "".join(
                "    " + line + "\n" for line in str(j["check"]).splitlines())
            try:
                compile(src, f"<judge {j.get('name')}>", "exec")
            except SyntaxError as e:
                errors.append(f"eval/eval.yaml: judge {j.get('name')!r} check does not compile: {e}")


def check_case(case_dir: Path, errors: list) -> str:
    rel = case_dir.relative_to(REPO)
    for name in REQUIRED_CASE_FILES:
        if not (case_dir / name).is_file():
            errors.append(f"{rel}: missing {name}")
    inp = load_yaml(case_dir / "input.yaml", errors) if (case_dir / "input.yaml").is_file() else None
    if isinstance(inp, dict):
        for key in REQUIRED_INPUT_KEYS:
            if not inp.get(key):
                errors.append(f"{rel}/input.yaml: missing or empty {key!r}")
    elif inp is not None:
        errors.append(f"{rel}/input.yaml: not a mapping")

    ann_path = case_dir / "annotations.yaml"
    ann = load_yaml(ann_path, errors) if ann_path.is_file() else None
    if not isinstance(ann, dict):
        if ann is not None:
            errors.append(f"{rel}/annotations.yaml: not a mapping")
        return "skipped"
    if ann.get("expected_verdict") not in VERDICTS:
        errors.append(f"{rel}/annotations.yaml: expected_verdict {ann.get('expected_verdict')!r} "
                      f"not one of {VERDICTS}")
    if not isinstance(ann.get("expected_critical_findings"), int):
        errors.append(f"{rel}/annotations.yaml: expected_critical_findings must be an integer")
    if ann.get("category") not in CATEGORIES:
        errors.append(f"{rel}/annotations.yaml: category {ann.get('category')!r} "
                      f"not one of {sorted(CATEGORIES)}")
    source = ann.get("source")
    if not isinstance(source, dict) or "reference_type" not in source:
        errors.append(f"{rel}/annotations.yaml: source block with reference_type is required")
        return "skipped"
    if ann.get("case") != case_dir.name:
        errors.append(f"{rel}/annotations.yaml: case {ann.get('case')!r} != directory name")

    if source.get("reference_type") == "captured":
        # reference.md IS the captured reviewer report: judge it.
        ref = case_dir / "reference.md"
        if ref.is_file():
            for failure in judge_report(ref.read_text(encoding="utf-8"), ann):
                errors.append(f"{rel}: {failure}")
        return "judged"
    return "structure-only"


# --- self-check for the yaml-block preference (no fixture in-tree yet) -------

def self_check():
    free_text = "## Verdict: NEEDS_REVISION\n| Critical findings | 3 |\n"
    with_block = free_text + "```yaml\nverdict: APPROVED_WITH_FINDINGS\ncritical_count: 0\n```\n"
    assert extract_verdict(free_text) == "NEEDS_REVISION"
    assert extract_critical_count(free_text) == 3
    # The fenced block, when present, is authoritative over the free text.
    assert extract_verdict(with_block) == "APPROVED_WITH_FINDINGS"
    assert extract_critical_count(with_block) == 0
    assert extract_verdict("no report here") is None


def main() -> int:
    self_check()
    errors: list[str] = []
    check_eval_yaml(errors)

    if not CASES_DIR.is_dir():
        errors.append(f"{CASES_DIR.relative_to(REPO)}: missing")
        cases = []
    else:
        cases = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())
        if not cases:
            errors.append(f"{CASES_DIR.relative_to(REPO)}: no case directories")

    modes = {}
    for case_dir in cases:
        modes[case_dir.name] = check_case(case_dir, errors)

    for name, mode in modes.items():
        print(f"  {name}: {mode}")
    if errors:
        print(f"\neval_smoke: FAIL — {len(errors)} violation(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    judged = sum(1 for m in modes.values() if m == "judged")
    print(f"\neval_smoke: OK — {len(modes)} cases validated, "
          f"{judged} captured reports passed the deterministic judges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
