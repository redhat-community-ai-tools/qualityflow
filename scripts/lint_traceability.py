#!/usr/bin/env python3
"""Lint STD scenario traceability ids (audit finding QE-03).

STDs generated after Wave 4a carry per-scenario `requirement_ids` and
`stp_scenario_id`. This lint globs outputs/**/std/*_test_description.yaml (plus
any tracked STD fixtures under tests/) and, for each file where ANY scenario
carries one of the new id fields, requires EVERY scenario to carry both.
Older STDs (no new id field anywhere, e.g. the CNV-80969 fixture) are exempt.

Exit status: 0 when clean or nothing to check, 1 listing offenders otherwise.
"""

import glob
import sys

import yaml

NEW_FIELDS = ("requirement_ids", "stp_scenario_id")
GLOBS = ("outputs/**/std/*_test_description.yaml", "tests/**/*_test_description.yaml")


def main() -> int:
    files = sorted({p for g in GLOBS for p in glob.glob(g, recursive=True)})
    if not files:
        print("lint_traceability: no STD files found — nothing to check")
        return 0

    offenders = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError as e:
            offenders.append(f"{path}: YAML parse error: {e}")
            continue
        scenarios = [s for s in ((doc or {}).get("scenarios") or []) if isinstance(s, dict)]
        if not any(field in s for s in scenarios for field in NEW_FIELDS):
            print(f"lint_traceability: {path}: pre-Wave-4a STD (no new id fields) — skipped")
            continue
        for s in scenarios:
            missing = [field for field in NEW_FIELDS if not s.get(field)]
            if missing:
                name = s.get("test_id") or s.get("scenario_id") or "<unnamed>"
                offenders.append(f"{path}: scenario {name}: missing {', '.join(missing)}")

    if offenders:
        print(f"lint_traceability: FAIL — {len(offenders)} offender(s):", file=sys.stderr)
        for o in offenders:
            print(f"  - {o}", file=sys.stderr)
        return 1
    print(f"lint_traceability: OK — {len(files)} STD file(s) scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
