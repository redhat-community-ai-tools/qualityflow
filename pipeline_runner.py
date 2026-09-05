"""Dashboard pipeline executor — a subprocess bridge to the Claude Code CLI.

The dashboard's "Run STP/STD/tests" buttons call run_phase(); it shells out to
`claude -p "/<command> <JIRA_ID>"` headless from the repo root, so it reuses the
deployed agents/commands/skills and writes artifacts to outputs/ exactly like a
human running the slash command. The dashboard (ui.py) owns state + task
bookkeeping; this module only runs the command and returns/raises.

Gated behind QF_RUNNER=cli. Unset/off returns a clear "runner disabled" error
instead of crashing, so an un-provisioned host degrades gracefully. Also gated
on QF_OUTPUTS_DIR being this repo's own outputs/ — the subprocess writes there
by construction (cwd=ROOT), so a divergent dashboard outputs dir is refused up
front instead of stranding every artifact in a tree nothing reads.

See SESSION-pipeline-runner-HANDOFF.md for the full contract and host prereqs.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
_CMD = {"stp": "stp-builder", "std": "std-builder", "codegen": "generate-tests",
        "stp_review": "review-stp", "std_review": "review-std",
        "stp_refine": "refine-stp"}
_DEFAULT_TIMEOUT = 1800  # 30 min; phases are slow


def _resolve_timeout():
    """QF_RUNNER_TIMEOUT in seconds, falling back to the default when it is
    malformed OR non-positive. subprocess.run(timeout=0) (or negative) fires
    immediately, so a typo'd '0'/'-5' would fail every phase with a misleading
    'timed out after 0s' — same fallback as the malformed case, plus a warning
    so the operator can see why their configured timeout didn't take effect."""
    raw = os.environ.get("QF_RUNNER_TIMEOUT")
    try:
        seconds = int(raw) if raw is not None else _DEFAULT_TIMEOUT
    except ValueError:
        seconds = 0
    if seconds <= 0:
        print("QF_RUNNER_TIMEOUT=%r is not a positive integer — using %ss"
              % (raw, _DEFAULT_TIMEOUT), file=sys.stderr)
        return _DEFAULT_TIMEOUT
    return seconds


_TIMEOUT = _resolve_timeout()


def _outputs_dir():
    """Where the dashboard reads artifacts — mirrors ui.py's OUTPUTS."""
    env = os.environ.get("QF_OUTPUTS_DIR")
    return Path(env).resolve() if env else (ROOT / "outputs").resolve()


def _check_outputs_aligned():
    """The `claude` subprocess must run with cwd=ROOT — it resolves .claude/
    resources, config/ and its own relative `outputs/{ID}/...` writes from cwd.
    So ROOT/outputs is where a run's artifacts land, full stop. If the dashboard
    reads a different tree (QF_OUTPUTS_DIR on a separate PVC), every phase this
    runner completes would sit in a tree nothing reads and the run would show
    'blocked' forever. Refuse loudly rather than produce that state."""
    outputs, native = _outputs_dir(), (ROOT / "outputs").resolve()
    if outputs != native:
        raise RuntimeError(
            "QF_OUTPUTS_DIR (%s) is not this repo's outputs/ (%s). The CLI runner "
            "writes artifacts relative to the repo root, so the dashboard would "
            "never see them. Point QF_OUTPUTS_DIR at %s (or unset it) to enable "
            "the runner." % (outputs, native, native))


def run_phase(model, jira_id, phase):
    """Run one pipeline phase via the Claude Code CLI. Returns
    {"output", "verdict", "progress"}; raises on failure (ui.py shows str(e))."""
    if os.environ.get("QF_RUNNER", "").lower() != "cli":
        raise RuntimeError(
            "Dashboard runner is disabled. Set QF_RUNNER=cli and ensure the "
            "`claude` CLI + deployed .claude/ resources are present on this host. "
            "(Or run /%s %s from the CLI.)" % (_CMD.get(phase, phase), jira_id))
    _check_outputs_aligned()
    cmd = _CMD.get(phase)
    if not cmd:
        raise ValueError(f"No command mapping for phase {phase!r}")

    # stream-json emits per-step events for the progress list; --verbose is
    # required with it. Headless writes files + calls MCP tools and can't prompt,
    # so permissions must be skipped.
    # ponytail: --dangerously-skip-permissions — host is single-tenant per team.
    #   Upgrade path: ship a settings.json allowlist and drop this flag.
    argv = ["claude", "-p", f"/{cmd} {jira_id}",
            "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions"]
    # Model precedence: explicit arg (UI picker) > QF_RUNNER_MODEL env > inherit
    # the session default. Inherit is the safe fallback — a model id that isn't
    # available on the host's Vertex project makes the CLI exit 1.
    chosen_model = model or os.environ.get("QF_RUNNER_MODEL", "")
    if chosen_model:
        argv += ["--model", chosen_model]

    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        raise RuntimeError("`claude` CLI not found on PATH — install it or unset "
                           "QF_RUNNER to disable the dashboard runner.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"/{cmd} {jira_id} timed out after {_TIMEOUT}s "
                           "(raise QF_RUNNER_TIMEOUT if the phase legitimately needs longer)")
    if proc.returncode != 0:
        # Surface the real error: the stream's final result text (which carries
        # pipeline errors) plus the stderr tail, not just whichever came last.
        _, final, _, _ = _parse_stream(proc.stdout)
        # Drop the CLI's benign "Opus N not available — using Opus M" downgrade
        # banner: it's a warning, not the failure, and masks the real reason.
        stderr_lines = [ln for ln in (proc.stderr or "").splitlines()
                        if "not available" not in ln or "using" not in ln]
        stderr_tail = "\n".join(stderr_lines).strip()[-400:]
        detail = " | ".join(p for p in (final.strip(), stderr_tail) if p and p != "Completed")
        raise RuntimeError(f"/{cmd} {jira_id} failed (exit {proc.returncode}): {detail or 'no output'}")

    progress, final_text, usage, model = _parse_stream(proc.stdout)
    return {"output": final_text, "verdict": _extract_verdict(final_text),
            "progress": progress, "usage": usage, "model": model}


def _parse_stream(stdout):
    """stream-json = one JSON object per line. Collect tool-use names as progress
    steps, the final result text as output, the result event's cost/token/
    duration usage (dropping it was the cheapest lost observability in the repo),
    and the session model off the stream's first (system/init) event — the CLI
    can silently downgrade a requested model, so this is the only place that
    knows what actually ran."""
    progress, final, usage, model = [], "", {}, None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if model is None and t == "system" and ev.get("model"):
            model = ev["model"]
        if t == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    progress.append(block.get("name", "step"))
        elif t == "result":
            final = ev.get("result") or final
            # The CLI's terminal result event carries usage; keep the fields the
            # dashboard can persist for a per-run cost/latency record.
            u = ev.get("usage") or {}
            usage = {
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "cache_creation_input_tokens": u.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": u.get("cache_read_input_tokens"),
                "cost_usd": ev.get("total_cost_usd"),
                "duration_ms": ev.get("duration_ms"),
                "num_turns": ev.get("num_turns"),
            }
    return progress, (final or "Completed"), usage, model


def _usage_extra(result):
    """The state fields worth persisting from a run_phase() result: usage +
    model only. Verdict is deliberately NOT written here — the slash command's
    own complete-phase --extra already records it, and the regex-extracted one
    must not overwrite it."""
    extra = {}
    if result.get("usage"):
        extra["usage"] = result["usage"]
    if result.get("model"):
        extra["model"] = result["model"]
    return extra


def persist_usage(jira_id, phase, result):
    """Best-effort: attach usage/model to the phase the slash command already
    completed. A failure here must not fail the run — the artifacts exist;
    only the observability is lost (and we say so)."""
    extra = _usage_extra(result)
    if not extra:
        print("no usage in stream result — nothing to record", file=sys.stderr)
        return
    # "python3", not sys.executable: state.py's only dependency (pyyaml) lives
    # on the system interpreter documented in SKILL.md, not necessarily on
    # whatever interpreter happened to launch this script (e.g. a bare
    # `uv run python pipeline_runner.py` with no project manifest has neither).
    proc = subprocess.run(
        ["python3", str(ROOT / "skills" / "pipeline-state" / "state.py"),
         "record-usage", jira_id, phase, "--extra", json.dumps(extra)],
        cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print("warning: usage not recorded: %s" % (proc.stderr or proc.stdout).strip(),
              file=sys.stderr)
    else:
        print(proc.stdout.strip())


def main(argv):
    """CLI entrypoint: `python3 pipeline_runner.py run <JIRA_ID> <phase> [--model M]`
    runs the phase headless exactly like the dashboard button and persists the
    usage/model the CLI reports — so CLI-first teams get the same cost capture
    as dashboard-triggered runs."""
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline_runner.py", description=main.__doc__)
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("run", help="run one phase via `claude -p` with usage capture")
    p.add_argument("jira_id")
    p.add_argument("phase", choices=sorted(_CMD))
    p.add_argument("--model", default="", help="model override (default: inherit)")
    args = ap.parse_args(argv)
    # Explicitly invoking this CLI *is* the opt-in the QF_RUNNER gate asks for;
    # the gate exists to stop the dashboard running phases on unprovisioned hosts.
    os.environ.setdefault("QF_RUNNER", "cli")
    try:
        result = run_phase(args.model, args.jira_id, args.phase)
    except (RuntimeError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(1)
    persist_usage(args.jira_id, args.phase, result)
    usage = result.get("usage") or {}
    print("%s %s: verdict=%s model=%s cost_usd=%s"
          % (args.jira_id, args.phase, result.get("verdict"),
             result.get("model"), usage.get("cost_usd")))


# A chained command's summary can MENTION a verdict it didn't reach ("refine
# runs only on NEEDS_REVISION") — a bare substring scan took the mention as the
# verdict (found on CNV-50425's first chained run). Require the verdict label
# and take the LAST labeled occurrence: after a refine loop that is the final
# verdict, not the initial one.
_VERDICT_RE = re.compile(
    r"[Vv]erdict[^A-Z]{0,40}(NEEDS_REVISION|APPROVED_WITH_FINDINGS|APPROVED)")


def _extract_verdict(text):
    labeled = _VERDICT_RE.findall(text or "")
    if labeled:
        return labeled[-1]
    # Fallback for final texts with no "verdict" label at all; longest-first so
    # APPROVED_WITH_FINDINGS is never misread as its APPROVED substring.
    for v in ("APPROVED_WITH_FINDINGS", "NEEDS_REVISION", "APPROVED"):
        if v in (text or ""):
            return v
    return None


if __name__ == "__main__" and len(sys.argv) > 1:
    main(sys.argv[1:])
    sys.exit(0)

if __name__ == "__main__":  # self-check: parser on a fixture, no CLI/network
    sample = "\n".join([
        json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "jira-collector"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "stp-generator"}]}}),
        json.dumps({"type": "result", "result": "STP generated. Verdict: APPROVED_WITH_FINDINGS",
                    "total_cost_usd": 0.42, "duration_ms": 1234, "num_turns": 3,
                    "usage": {"input_tokens": 100, "output_tokens": 20,
                              "cache_creation_input_tokens": 5, "cache_read_input_tokens": 7}}),
    ])
    prog, out, usage, model = _parse_stream(sample)
    assert prog == ["jira-collector", "stp-generator"], prog
    assert model == "claude-sonnet-5", model
    assert _extract_verdict(out) == "APPROVED_WITH_FINDINGS", out
    assert _extract_verdict("all clear") is None
    # regression (CNV-50425 first chained run): a summary that MENTIONS
    # NEEDS_REVISION while its labeled verdict is APPROVED_WITH_FINDINGS
    _chained = ("Review complete — verdict **APPROVED_WITH_FINDINGS** (0 critical). "
                "Per the workflow, `/refine-stp` runs only on `NEEDS_REVISION`, so no "
                "refinement is needed.")
    assert _extract_verdict(_chained) == "APPROVED_WITH_FINDINGS", _chained
    # after a refine loop the LAST labeled verdict is the final one
    _refined = "Initial verdict: NEEDS_REVISION ... Final verdict: APPROVED"
    assert _extract_verdict(_refined) == "APPROVED", _refined
    assert usage["cost_usd"] == 0.42 and usage["input_tokens"] == 100, usage
    assert usage["output_tokens"] == 20 and usage["duration_ms"] == 1234, usage
    assert usage["cache_creation_input_tokens"] == 5 and usage["cache_read_input_tokens"] == 7, usage
    # no system/init event in the stream -> model stays honestly None, not guessed
    _, _, _, no_model = _parse_stream(json.dumps(
        {"type": "result", "result": "ok", "usage": {}}))
    assert no_model is None, no_model
    # the benign downgrade banner must be filtered from a failure's stderr tail
    _err = "Warning: Opus: Opus 5 not available — using Opus 4.8 for this session\nreal error: boom"
    _kept = "\n".join(l for l in _err.splitlines()
                      if "not available" not in l or "using" not in l).strip()
    assert _kept == "real error: boom", _kept
    # every runnable phase must have a CLI command mapping
    assert set(_CMD) == {"stp", "std", "codegen", "stp_review", "std_review", "stp_refine"}, _CMD
    assert isinstance(_TIMEOUT, int) and _TIMEOUT > 0, _TIMEOUT
    # a non-positive QF_RUNNER_TIMEOUT must fall back exactly like a malformed
    # one — timeout=0 would fire instantly and fail every phase
    _saved_timeout = os.environ.pop("QF_RUNNER_TIMEOUT", None)
    try:
        _fallback = _resolve_timeout()  # unset -> default
        for _bad in ("nope", "0", "-5", "1.5"):
            os.environ["QF_RUNNER_TIMEOUT"] = _bad
            assert _resolve_timeout() == _fallback > 0, _bad
        os.environ["QF_RUNNER_TIMEOUT"] = "60"  # a valid value still wins
        assert _resolve_timeout() == 60
    finally:
        os.environ.pop("QF_RUNNER_TIMEOUT", None)
        if _saved_timeout is not None:
            os.environ["QF_RUNNER_TIMEOUT"] = _saved_timeout
    # usage persistence: usage+model only — verdict must never be re-written
    assert _usage_extra({"usage": {"cost_usd": 1}, "model": "m", "verdict": "APPROVED"}) \
        == {"usage": {"cost_usd": 1}, "model": "m"}
    assert _usage_extra({"usage": {}, "model": None}) == {}
    # outputs alignment: a QF_OUTPUTS_DIR pointing away from ROOT/outputs must
    # refuse, not silently write artifacts into a tree the dashboard never reads
    _saved_outputs = os.environ.pop("QF_OUTPUTS_DIR", None)
    try:
        _check_outputs_aligned()  # unset -> ROOT/outputs -> no raise
        os.environ["QF_OUTPUTS_DIR"] = "/qf-elsewhere"
        try:
            _check_outputs_aligned()
            raise AssertionError("diverged QF_OUTPUTS_DIR must raise")
        except RuntimeError:
            pass
    finally:
        os.environ.pop("QF_OUTPUTS_DIR", None)
        if _saved_outputs is not None:
            os.environ["QF_OUTPUTS_DIR"] = _saved_outputs
    print("pipeline_runner self-check passed")
