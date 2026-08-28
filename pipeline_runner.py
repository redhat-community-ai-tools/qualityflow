"""Dashboard pipeline executor — a subprocess bridge to the Claude Code CLI.

The dashboard's "Run STP/STD/tests" buttons call run_phase(); it shells out to
`claude -p "/<command> <JIRA_ID>"` headless from the repo root, so it reuses the
deployed agents/commands/skills and writes artifacts to outputs/ exactly like a
human running the slash command. The dashboard (ui.py) owns state + task
bookkeeping; this module only runs the command and returns/raises.

Gated behind QF_RUNNER=cli. Unset/off returns a clear "runner disabled" error
instead of crashing, so an un-provisioned host degrades gracefully.

See SESSION-pipeline-runner-HANDOFF.md for the full contract and host prereqs.
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
_CMD = {"stp": "stp-builder", "std": "std-builder", "codegen": "generate-tests"}
_TIMEOUT = int(os.environ.get("QF_RUNNER_TIMEOUT", "1800"))  # 30 min; phases are slow


def run_phase(client, model, jira_id, phase):
    """Run one pipeline phase via the Claude Code CLI. Returns
    {"output", "verdict", "progress"}; raises on failure (ui.py shows str(e))."""
    if os.environ.get("QF_RUNNER", "").lower() != "cli":
        raise RuntimeError(
            "Dashboard runner is disabled. Set QF_RUNNER=cli and ensure the "
            "`claude` CLI + deployed .claude/ resources are present on this host. "
            "(Or run /%s %s from the CLI.)" % (_CMD.get(phase, phase), jira_id))
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
    if proc.returncode != 0:
        # Surface the real error: the stream's final result text (which carries
        # pipeline errors) plus the stderr tail, not just whichever came last.
        _, final, _ = _parse_stream(proc.stdout)
        # Drop the CLI's benign "Opus N not available — using Opus M" downgrade
        # banner: it's a warning, not the failure, and masks the real reason.
        stderr_lines = [ln for ln in (proc.stderr or "").splitlines()
                        if "not available" not in ln or "using" not in ln]
        stderr_tail = "\n".join(stderr_lines).strip()[-400:]
        detail = " | ".join(p for p in (final.strip(), stderr_tail) if p and p != "Completed")
        raise RuntimeError(f"/{cmd} {jira_id} failed (exit {proc.returncode}): {detail or 'no output'}")

    progress, final_text, usage = _parse_stream(proc.stdout)
    return {"output": final_text, "verdict": _extract_verdict(final_text),
            "progress": progress, "usage": usage}


def _parse_stream(stdout):
    """stream-json = one JSON object per line. Collect tool-use names as progress
    steps, the final result text as output, and the result event's cost/token/
    duration usage (dropping it was the cheapest lost observability in the repo)."""
    progress, final, usage = [], "", {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
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
                "cost_usd": ev.get("total_cost_usd"),
                "duration_ms": ev.get("duration_ms"),
                "num_turns": ev.get("num_turns"),
            }
    return progress, (final or "Completed"), usage


def _extract_verdict(text):
    for v in ("NEEDS_REVISION", "APPROVED_WITH_FINDINGS", "APPROVED"):
        if v in (text or ""):
            return v
    return None


if __name__ == "__main__":  # self-check: parser on a fixture, no CLI/network
    sample = "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "jira-collector"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "stp-generator"}]}}),
        json.dumps({"type": "result", "result": "STP generated. Verdict: APPROVED_WITH_FINDINGS",
                    "total_cost_usd": 0.42, "duration_ms": 1234, "num_turns": 3,
                    "usage": {"input_tokens": 100, "output_tokens": 20}}),
    ])
    prog, out, usage = _parse_stream(sample)
    assert prog == ["jira-collector", "stp-generator"], prog
    assert _extract_verdict(out) == "APPROVED_WITH_FINDINGS", out
    assert _extract_verdict("all clear") is None
    assert usage["cost_usd"] == 0.42 and usage["input_tokens"] == 100, usage
    assert usage["output_tokens"] == 20 and usage["duration_ms"] == 1234, usage
    # the benign downgrade banner must be filtered from a failure's stderr tail
    _err = "Warning: Opus: Opus 5 not available — using Opus 4.8 for this session\nreal error: boom"
    _kept = "\n".join(l for l in _err.splitlines()
                      if "not available" not in l or "using" not in l).strip()
    assert _kept == "real error: boom", _kept
    print("pipeline_runner self-check passed")
