#!/usr/bin/env python3
"""QualityFlow pipeline state CLI.

Deterministic replacement for LLM hand-editing of pipeline_state.yaml
(audit findings AI-04 / OBS-02). Run from the QualityFlow repo root
(paths are CWD-relative: outputs/, config/).

Operations:
  init <TICKET> [--project-id ID] [--display-name NAME]
  start-phase <TICKET> <PHASE>
  complete-phase <TICKET> <PHASE> [--output PATH] [--extra YAML|-]
  record-usage <TICKET> <PHASE> --extra YAML|-   # merge usage/model onto a phase, no status change
  fail-phase <TICKET> <PHASE> --error MSG
  check <TICKET> <PHASE>          # prerequisites + approval gates + staleness
  status <TICKET>
"""

import argparse
import hashlib
import os
import sys
import tempfile
from datetime import datetime, timezone

import yaml

# One generic code-generation phase, not per-language: /generate-tests writes
# tests in whatever language(s) the repo/STD call for (config-driven), so the
# phase machine is language-agnostic. (There used to be go_codegen/python_codegen
# here; collapsed — the runner and every real run already used a single codegen.)
PHASES = ["stp", "stp_review", "stp_refine", "std", "std_review", "codegen"]

PREREQS = {
    "stp": [],
    "stp_review": ["stp"],
    "stp_refine": ["stp"],
    "std": ["stp"],
    "std_review": ["std"],
    "codegen": ["std"],
}

# downstream phase -> approval-gated prerequisite phase
GATES = {"std": "stp_review", "codegen": "std_review"}
DEFAULT_APPROVAL_GATES = ["stp_review", "std_review"]

# phase -> upstream phase whose output/output_checksum staleness is checked
STALE_UPSTREAM = {"std": "stp", "std_review": "std", "codegen": "std"}

MISSING_SUGGESTION = {
    "stp": "Run `/stp-builder {t}` first.",
    "stp_review": "Run `/review-stp {t}` to review the STP.",
    "std": "Run `/std-builder {t}` first.",
    "std_review": "Run `/review-std {t}` to review the STD.",
}

DISPLAY = {
    "stp": "STP Generation", "stp_review": "STP Review",
    "stp_refine": "STP Refinement", "std": "STD Generation",
    "std_review": "STD Review", "codegen": "Code Generation",
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(ticket):
    return os.path.join("outputs", ticket, "state", "pipeline_state.yaml")


def checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def die(msg, code=2):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print("warning: " + msg, file=sys.stderr)


def load_state(ticket, required=True):
    p = state_path(ticket)
    if not os.path.exists(p):
        if required:
            die("no state file for %s (%s). Run: state.py init %s"
                % (ticket, p, ticket))
        return None
    state = load_yaml(p)
    if not isinstance(state, dict) or "phases" not in state:
        die("state file %s is malformed (no `phases` mapping)" % p)
    return state


def save_state(ticket, state):
    state["updated"] = now_iso()
    atomic_write(state_path(ticket), state)


def get_phase(state, phase):
    if phase not in PHASES:
        die("unknown phase %r (valid: %s)" % (phase, ", ".join(PHASES)))
    return state["phases"].setdefault(phase, {"status": "pending", "error": None})


def approval_gates(state):
    proj = state.get("project_id")
    cfg = os.path.join("config", "projects", str(proj), "project.yaml")
    if proj and os.path.exists(cfg):
        gates = load_yaml(cfg).get("approval_gates")
        if isinstance(gates, list):
            return gates
    return DEFAULT_APPROVAL_GATES


def read_approvals(ticket):
    p = os.path.join("outputs", ticket, "state", "approvals.yaml")
    if not os.path.exists(p):
        return {}
    doc = load_yaml(p)
    return doc.get("approvals", doc) if isinstance(doc, dict) else {}


def feature_toggles():
    toggles = {}
    p = os.path.join("config", "_defaults.yaml")
    if os.path.exists(p):
        toggles.update(load_yaml(p).get("feature_toggles") or {})
    return toggles


# ---------------------------------------------------------------- operations

def op_init(args):
    p = state_path(args.ticket)
    if os.path.exists(p):
        # Read-or-init semantics (SKILL.md Operation 2): existing state wins.
        print(open(p).read(), end="")
        return
    now = now_iso()
    state = {
        "version": 1,
        "ticket_id": args.ticket,
        "project_id": args.project_id,
        "display_name": args.display_name,
        "created": now,
        "updated": now,
        "phases": {ph: {"status": "pending", "error": None} for ph in PHASES},
    }
    atomic_write(p, state)
    print("initialized %s" % p)


def parse_extra(raw):
    if raw is None:
        return {}
    text = sys.stdin.read() if raw == "-" else raw
    try:
        data = yaml.safe_load(text)  # YAML superset covers JSON too
    except yaml.YAMLError as e:
        die("could not parse --extra data: %s" % e)
    if data is None:
        return {}
    if not isinstance(data, dict):
        die("--extra data must be a mapping, got %s" % type(data).__name__)
    return data


def op_start(args):
    state = load_state(args.ticket)
    ph = get_phase(state, args.phase)
    ph["status"] = "in_progress"
    ph["started"] = now_iso()
    ph["error"] = None
    save_state(args.ticket, state)
    print("%s: %s -> in_progress" % (args.ticket, args.phase))


def op_complete(args):
    state = load_state(args.ticket)
    ph = get_phase(state, args.phase)
    if ph.get("status") != "in_progress":
        # Documented as non-fatal: re-runs are allowed, so just warn.
        warn("completing phase %r whose status is %r (expected in_progress)"
             % (args.phase, ph.get("status")))
    ph["status"] = "completed"
    ph["completed"] = now_iso()
    ph["error"] = None
    if args.output:
        ph["output"] = args.output
        if os.path.exists(args.output):
            ph["output_checksum"] = checksum(args.output)
        else:
            warn("output file %s not found; checksum not recorded" % args.output)
    ph.update(parse_extra(args.extra))
    save_state(args.ticket, state)
    print("%s: %s -> completed" % (args.ticket, args.phase))


def op_record_usage(args):
    """Merge fields (usage/model from a headless runner) onto an existing phase
    WITHOUT touching status/timestamps — the slash command already completed the
    phase; this only attaches observability the session couldn't see itself."""
    extra = parse_extra(args.extra)
    if not extra:
        die("record-usage requires --extra with at least one field")
    state = load_state(args.ticket)
    ph = get_phase(state, args.phase)
    ph.update(extra)
    save_state(args.ticket, state)
    print("%s: %s usage recorded (%s)" % (args.ticket, args.phase, ", ".join(sorted(extra))))


def op_fail(args):
    state = load_state(args.ticket)
    ph = get_phase(state, args.phase)
    ph["status"] = "failed"
    ph["error"] = args.error
    # `completed` deliberately NOT set on failure (SKILL.md Error State).
    save_state(args.ticket, state)
    print("%s: %s -> failed" % (args.ticket, args.phase))


def check_result(state, ticket, phase):
    """Return dict {valid, missing, suggestion, stale, stale_reason}."""
    if phase not in PHASES:
        die("unknown phase %r (valid: %s)" % (phase, ", ".join(PHASES)))
    phases = state["phases"]
    missing, suggestions = [], []

    for pre in PREREQS[phase]:
        if phases.get(pre, {}).get("status") != "completed":
            missing.append(pre)
            suggestions.append(MISSING_SUGGESTION[pre].format(t=ticket))

    gate = GATES.get(phase)
    if gate and gate in approval_gates(state) and gate not in missing:
        status = (read_approvals(ticket).get(gate) or {}).get("status")
        label = "STP Review" if gate == "stp_review" else "STD Review"
        cmd = "/review-stp" if gate == "stp_review" else "/review-std"
        if status == "rejected":
            missing.append(gate + " (rejected)")
            suggestions.append(
                "%s was rejected. Address the reviewer feedback and re-run "
                "`%s %s`." % (label, cmd, ticket))
        elif status != "approved":
            missing.append(gate + " (awaiting approval)")
            suggestions.append(
                "%s is awaiting human approval. Approve the reviewed artifact "
                "from the dashboard, or record it in "
                "outputs/%s/state/approvals.yaml." % (label, ticket))

    result = {"valid": not missing, "stale": False}
    if missing:
        result["missing"] = missing
        result["suggestion"] = " ".join(suggestions)

    upstream = STALE_UPSTREAM.get(phase)
    if upstream:
        up = phases.get(upstream, {})
        out, stored = up.get("output"), up.get("output_checksum")
        if out and stored and os.path.exists(out) and checksum(out) != stored:
            result["stale"] = True
            result["stale_file"] = out
            result["stale_reason"] = (
                "%s output was modified after it was recorded; downstream %s "
                "may be based on stale input" % (upstream, phase))
    return result


def op_check(args):
    state = load_state(args.ticket)
    result = check_result(state, args.ticket, args.phase)
    yaml.safe_dump(result, sys.stdout, default_flow_style=False, sort_keys=False)
    if result["stale"]:
        warn(result["stale_reason"])  # staleness informs, never blocks
    sys.exit(0 if result["valid"] else 1)


def next_step(state, ticket):
    phases = state["phases"]

    def st(p):
        return phases.get(p, {}).get("status")

    if st("stp") != "completed":
        return "Run `/stp-builder %s`" % ticket
    if st("stp_review") != "completed":
        return "Run `/review-stp %s`" % ticket
    if phases.get("stp_review", {}).get("verdict") == "NEEDS_REVISION" \
            and st("stp_refine") != "completed":
        return "Run `/refine-stp %s`" % ticket
    if st("std") != "completed":
        return "Run `/std-builder %s`" % ticket
    if st("std_review") != "completed":
        return "Run `/review-std %s`" % ticket
    if phases.get("std_review", {}).get("verdict") == "NEEDS_REVISION":
        return "Run `/refine-std %s`" % ticket
    if st("codegen") != "completed":
        t = feature_toggles()
        if t.get("tier1_tests", True) or t.get("tier2_tests", True):
            return "Run `/generate-tests %s`" % ticket
    return "Pipeline complete"


def op_status(args):
    state = load_state(args.ticket)
    phases = state["phases"]
    print("Pipeline Status: %s (%s)\n" % (args.ticket,
                                          state.get("display_name") or state.get("project_id") or "?"))
    print("%-18s %-14s %s" % ("Phase", "Status", "Details"))
    print("%-18s %-14s %s" % ("-----", "------", "-------"))
    stale_notes = []
    for ph in PHASES:
        info = phases.get(ph, {})
        status = info.get("status", "pending")
        details = ""
        if info.get("verdict"):
            f = info.get("findings") or {}
            details = str(info["verdict"])
            if f:
                details += " (%sC, %sM, %sm)" % (f.get("critical", 0),
                                                 f.get("major", 0), f.get("minor", 0))
        elif info.get("error"):
            details = "error: %s" % info["error"]
        elif isinstance(info.get("output"), str) and "\n" not in info["output"]:
            details = info["output"]
        print("%-18s %-14s %s" % (DISPLAY[ph], status, details))
        r = check_result(state, args.ticket, ph) if ph in STALE_UPSTREAM else {"stale": False}
        if r["stale"]:
            stale_notes.append(r["stale_reason"])
    print("\nNext step: %s" % next_step(state, args.ticket))
    print("Staleness: %s" % ("; ".join(stale_notes) if stale_notes else "None detected"))


# ----------------------------------------------------------------- self-test

def self_test():
    import shutil
    tmp = tempfile.mkdtemp(prefix="qf-state-test-")
    cwd = os.getcwd()
    try:
        os.chdir(tmp)
        t = "TEST-1"
        main(["init", t, "--project-id", "example", "--display-name", "Example"])
        state = load_state(t)
        assert state["ticket_id"] == t and len(state["phases"]) == len(PHASES)
        assert all(p["status"] == "pending" for p in state["phases"].values())

        main(["start-phase", t, "stp"])
        assert load_state(t)["phases"]["stp"]["status"] == "in_progress"

        os.makedirs("outputs/%s/stp" % t, exist_ok=True)
        out = "outputs/%s/stp/%s_test_plan.md" % (t, t)
        open(out, "w").write("# plan v1\n")
        main(["complete-phase", t, "stp", "--output", out,
              "--extra", '{"skills_used": ["requirement-mapper"]}'])
        stp = load_state(t)["phases"]["stp"]
        assert stp["status"] == "completed"
        assert stp["output_checksum"].startswith("sha256:")
        assert stp["skills_used"] == ["requirement-mapper"]

        # record-usage merges fields without touching status/timestamps
        completed_before = stp["completed"]
        main(["record-usage", t, "stp", "--extra",
              '{"usage": {"cost_usd": 1.5, "input_tokens": 10}, "model": "claude-sonnet-5"}'])
        stp = load_state(t)["phases"]["stp"]
        assert stp["usage"] == {"cost_usd": 1.5, "input_tokens": 10}, stp
        assert stp["model"] == "claude-sonnet-5"
        assert stp["status"] == "completed" and stp["completed"] == completed_before

        # prerequisites: stp_review now valid, std blocked by approval gate
        r = check_result(load_state(t), t, "stp_review")
        assert r["valid"], r
        r = check_result(load_state(t), t, "std")
        assert not r["valid"] and "stp_review (awaiting approval)" in r["missing"], r

        # approve the gate, complete review -> std unblocked
        main(["start-phase", t, "stp_review"])
        main(["complete-phase", t, "stp_review", "--extra",
              "verdict: APPROVED\nfindings: {critical: 0, major: 0, minor: 0}"])
        atomic_write("outputs/%s/state/approvals.yaml" % t,
                     {"approvals": {"stp_review": {"status": "approved"}}})
        r = check_result(load_state(t), t, "std")
        assert r["valid"], r

        # staleness: mutate STP after recording its checksum
        main(["start-phase", t, "std"])
        main(["complete-phase", t, "std", "--output", out])  # reuse file as std output
        open(out, "a").write("edited\n")
        r = check_result(load_state(t), t, "std_review")
        assert r["stale"], r

        # fail-phase records error, no completed timestamp
        main(["start-phase", t, "codegen"])
        main(["fail-phase", t, "codegen", "--error", "boom"])
        gc = load_state(t)["phases"]["codegen"]
        assert gc["status"] == "failed" and gc["error"] == "boom"
        assert "completed" not in gc

        main(["status", t])
        print("self-test: OK")
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="op")

    p = sub.add_parser("init")
    p.add_argument("ticket")
    p.add_argument("--project-id")
    p.add_argument("--display-name")
    p.set_defaults(fn=op_init)

    for name, fn in [("start-phase", op_start), ("fail-phase", op_fail)]:
        p = sub.add_parser(name)
        p.add_argument("ticket")
        p.add_argument("phase")
        if name == "fail-phase":
            p.add_argument("--error", required=True)
        p.set_defaults(fn=fn)

    p = sub.add_parser("complete-phase")
    p.add_argument("ticket")
    p.add_argument("phase")
    p.add_argument("--output", help="path to the phase's output artifact")
    p.add_argument("--extra",
                   help="phase-specific fields as inline YAML/JSON, or '-' for stdin")
    p.set_defaults(fn=op_complete)

    p = sub.add_parser("record-usage")
    p.add_argument("ticket")
    p.add_argument("phase")
    p.add_argument("--extra", required=True,
                   help="usage/model fields as inline YAML/JSON, or '-' for stdin")
    p.set_defaults(fn=op_record_usage)

    p = sub.add_parser("check")
    p.add_argument("ticket")
    p.add_argument("phase")
    p.set_defaults(fn=op_check)

    p = sub.add_parser("status")
    p.add_argument("ticket")
    p.set_defaults(fn=op_status)

    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if not args.op:
        parser.print_help()
        sys.exit(2)
    args.fn(args)


if __name__ == "__main__":
    main()
