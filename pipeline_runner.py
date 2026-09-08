"""Dashboard pipeline executor — a subprocess bridge to the Claude Code CLI or
the Cursor CLI, selected per request via `runtime` ("claude" | "cursor").

The dashboard's "Run STP/STD/tests" buttons call run_phase(); it shells out to
`claude -p "/<command> <JIRA_ID>"` (or `agent -p "/<command> <JIRA_ID>"` for
Cursor) headless from the repo root, so it reuses the deployed
agents/commands/skills and writes artifacts to outputs/ exactly like a human
running the slash command. The dashboard (ui.py) owns state + task
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
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
_CMD = {"stp": "stp-builder", "std": "std-builder", "codegen": "generate-tests",
        "stp_review": "review-stp", "std_review": "review-std",
        "stp_refine": "refine-stp"}
_DEFAULT_TIMEOUT = 1800  # 30 min; phases are slow

# P0: no token may ever be persisted (pipeline_state.yaml, on the PVC). If the
# `claude`/`agent` CLI ever echoes a rejected credential back on stderr, it
# must not survive into the RuntimeError message that ui.py's _mark_failed
# writes to disk. Covers both runtimes at the one place their error paths
# converge (see run_phase's `raise RuntimeError` below) rather than patching
# each backend separately.
_SECRET_RE = re.compile(
    r"key_[A-Za-z0-9]{20,}"           # Cursor API key
    r"|ATATT[A-Za-z0-9_\-]{10,}"      # Atlassian token
    r"|gh[ps]_[A-Za-z0-9]{20,}"       # GitHub PAT / server-to-server token
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub fine-grained PAT
    r"|AIza[A-Za-z0-9_\-]{20,}"       # Google API key
    # Per-user Vertex ADC (gcp_adc): google-auth errors can quote the file's
    # own contents, not just its path, and that file holds a refresh token
    # redeemable for cloud-platform-scoped access tokens as that person.
    r"|1//0[A-Za-z0-9_\-]{20,}"                # Google OAuth refresh token
    r"|GOCSPX-[A-Za-z0-9_\-]{10,}"             # Google OAuth client secret
    r'|"refresh_token"\s*:\s*"[^"]+"'          # ...and the JSON fields that carry
    r'|"client_secret"\s*:\s*"[^"]+"'          #    them, whatever their shape
)

# The refresh token dies with the user's Google Cloud session; Red Hat runs
# Google's 16 h default, so this is a roughly-daily event, not an edge case.
# Without this mapping it surfaces as a raw google-auth trace inside a failed
# 30-minute phase, which is the difference between a tolerable re-paste and a
# support ticket (D-02 PLAN §2).
_EXPIRED_CRED_RE = re.compile(
    r"invalid_grant|Reauthentication|Could not load the default credentials")
_EXPIRED_CRED_HINT = (
    "Vertex credential expired or revoked — run `gcloud auth application-default "
    "login` again and re-paste it in Settings (Red Hat's Google Cloud session "
    "forces reauth about every 16h)")


def _redact_secrets(text):
    """Replace known credential shapes in `text` with '[redacted]'."""
    return _SECRET_RE.sub("[redacted]", text) if text else text


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


def _env_for(creds):
    """Subprocess env for the `claude`/`agent` CLI: the process's own env, with
    the calling user's Jira/GitHub/Cursor identity overlaid when given (a
    shared dashboard's runner has no identity of its own to fall back to —
    each run must carry the clicking user's MCP credentials, resolved by the
    ${VAR} placeholders in .mcp.json). None or empty values leave the ambient
    env untouched, which is what a local `python3 pipeline_runner.py run`
    invocation relies on.

    cursor_api_key -> CURSOR_API_KEY only, never argv (fact C-1b, P0: argv is
    world-readable via /proc in a shared pod)."""
    env = os.environ.copy()
    for key, var in (("jira_username", "JIRA_USERNAME"), ("jira_token", "JIRA_API_TOKEN"),
                     ("github_token", "GITHUB_PERSONAL_ACCESS_TOKEN"),
                     ("cursor_api_key", "CURSOR_API_KEY")):
        val = (creds or {}).get(key)
        if val:
            env[var] = val
    return env


def _validated_adc(adc):
    """Return `adc` unchanged if it looks like an ADC/service-account JSON file,
    else raise ValueError. The message NEVER quotes the content — it is a Google
    refresh token, and ui.py persists str(e) on failure."""
    try:
        doc = json.loads(adc)
    except ValueError:
        raise ValueError(
            "Vertex credential is not valid JSON. Paste the whole contents of "
            "~/.config/gcloud/application_default_credentials.json (run "
            "`gcloud auth application-default login` first), not its path.")
    if not isinstance(doc, dict) or "type" not in doc:
        raise ValueError(
            "Vertex credential is JSON but not an ADC file (no \"type\" field). "
            "Re-run `gcloud auth application-default login` and paste the file "
            "it writes.")
    return adc


def run_phase(model, jira_id, phase, creds=None, runtime="claude"):
    """Run one pipeline phase via the Claude Code CLI or the Cursor CLI.
    Returns {"output", "verdict", "progress", "usage", "model"}; raises on
    failure (ui.py shows str(e)).

    runtime: "claude" (default) or "cursor" — absent/empty/unknown values
    fall back to "claude", never an error (frozen decision 7).
    creds: optional {"jira_username", "jira_token", "github_token",
    "cursor_api_key", "gcp_adc"} — the identity this one run's MCP calls
    should use (see _env_for), plus, for the claude runtime, that person's own
    Vertex ADC JSON (see the TemporaryDirectory block below). Nothing in creds
    is logged, persisted, or put in argv."""
    if runtime not in ("claude", "cursor"):
        runtime = "claude"
    if os.environ.get("QF_RUNNER", "").lower() != "cli":
        raise RuntimeError(
            "Dashboard runner is disabled. Set QF_RUNNER=cli and ensure the "
            "`claude` CLI + deployed .claude/ resources are present on this host. "
            "(Or run /%s %s from the CLI.)" % (_CMD.get(phase, phase), jira_id))
    _check_outputs_aligned()
    cmd = _CMD.get(phase)
    if not cmd:
        raise ValueError(f"No command mapping for phase {phase!r}")

    if runtime == "cursor":
        # ponytail: --approve-mcps + --trust assumed required headless (fact
        # C-1c). `agent --help` (audit-runs/.../E-01/raw/help.txt) confirms
        # both default to false ("Automatically approve all MCP servers
        # (default: false)" / "Trust the current workspace without prompting
        # (default: false)") — without them .cursor/mcp.json servers likely
        # never start and Jira/GitHub MCP calls would silently no-op, which
        # looks exactly like a clean successful run that did nothing. Still
        # UNVERIFIED end-to-end (no successful authenticated run captured
        # yet — E-01's only stream attempt hit "Authentication required").
        # Safer to over-approve on a single-tenant-per-team host (same call
        # as --dangerously-skip-permissions above) than to under-approve and
        # lose data silently. Verify: run once with vs without these two
        # flags on a ticket that needs a Jira lookup and diff the `progress`
        # tool_call names in the result — MCP tool names should appear either way.
        argv = ["agent", "-p", f"/{cmd} {jira_id}",
                "--output-format", "stream-json", "--force",
                "--approve-mcps", "--trust"]
        # Model precedence: explicit arg (UI picker) > QF_RUNNER_CURSOR_MODEL
        # env > grok-4.6 (frozen decision 4: default-with-override, never
        # unset for cursor — unlike claude, "inherit" isn't safe here since
        # cursor has no equivalent session default to fall back to).
        chosen_model = model or os.environ.get("QF_RUNNER_CURSOR_MODEL", "") or "grok-4.6"
        argv += ["--model", chosen_model]
    else:
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

    # Per-user Vertex identity: the pasted ADC becomes a file only this run can
    # name, pointed at by GOOGLE_APPLICATION_CREDENTIALS in the child's env
    # (never argv — /proc/<pid>/cmdline is world-readable). subprocess.run(env=)
    # REPLACES the child environment, so this overrides any pod-level shared
    # credential outright.
    # ponytail: TemporaryDirectory is stdlib's `finally` — the dir is 0700 and
    #   unique, and it is removed on normal exit, on FileNotFoundError, on
    #   TimeoutExpired and on any later raise. Ceiling: same-UID processes (a
    #   concurrent run's agent has a shell) can read both this 0600 file and
    #   /proc/<pid>/environ; the mode only stops a DIFFERENT uid. Real fix is a
    #   process/uid boundary per run (a Job per run) or serialized runs — not now.
    with tempfile.TemporaryDirectory(prefix="qf-gac-") as tmpdir:
        env = _env_for(creds)
        adc = (creds or {}).get("gcp_adc")
        if runtime == "claude" and adc:
            adc_path = Path(tmpdir, "adc.json")
            adc_path.write_text(_validated_adc(adc))
            adc_path.chmod(0o600)
            env["GOOGLE_APPLICATION_CREDENTIALS"] = str(adc_path)
        try:
            proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                                  text=True, timeout=_TIMEOUT, env=env)
        except FileNotFoundError:
            if runtime == "cursor":
                raise RuntimeError(
                    "`agent` (Cursor CLI) not found on PATH — install it "
                    "(curl https://cursor.com/install -fsS | bash) or unset "
                    "QF_RUNNER to disable the dashboard runner.")
            raise RuntimeError("`claude` CLI not found on PATH — install it or unset "
                               "QF_RUNNER to disable the dashboard runner.")
        except subprocess.TimeoutExpired:
            # ponytail: fact C-6 — a Feb-2026 report of `agent -p` hanging headless.
            # The existing timeout guard (shared with the claude path) is the only
            # mitigation; no cursor-specific retry/kill logic added.
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
        expired = bool(_EXPIRED_CRED_RE.search(proc.stderr or "") or _EXPIRED_CRED_RE.search(detail))
        detail = _redact_secrets(detail)
        if expired:
            detail = f"{detail} — {_EXPIRED_CRED_HINT}" if detail else _EXPIRED_CRED_HINT
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
    knows what actually ran.

    Schema-keyed to handle both backends (fact C-2): Claude Code puts tool
    calls inline in assistant.message.content[type=="tool_use"]; Cursor emits
    them as separate top-level tool_call events (subtype started/completed).
    Everything else — system.model, the terminal result.result text, and
    result.usage/total_cost_usd — uses the SAME keys on both backends, so no
    branch is needed there; a key simply absent on one backend's result event
    (e.g. Cursor has no total_cost_usd) yields None via .get(), which is the
    correct "no cost data" degrade, not a bug.
    ponytail: measured-on-docs-schema (Cursor CLI docs, no captured E-01
    sample was available when this was written — re-check
    audit-runs/RUN-2026-09-08-dual-runtime/E-01/stream.jsonl before trusting
    this in prod). The riskiest guess is the tool_call name fallback below:
    docs describe nested readToolCall/writeToolCall shapes without naming
    their fields, so a real event that doesn't carry a `function.name` falls
    back to a generic label derived from the *ToolCall key — cosmetic only,
    it can't break parsing, just makes the progress list less specific."""
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
        elif t == "tool_call" and ev.get("subtype") == "started":
            # Cursor-only event type; Claude Code never emits it. "started"
            # only (not "completed") so a call isn't counted twice.
            tc = ev.get("tool_call") or {}
            name = (tc.get("function") or {}).get("name")
            if not name:
                keys = [k for k in tc if k.endswith("ToolCall")]
                name = keys[0][:-len("ToolCall")] if keys else "step"
            progress.append(name)
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


# The per-ticket subdirs a team dashboard accepts on POST /api/outputs/{id}.
# Anything else under outputs/{id}/ (other {lang}-tests dirs, .previous/) is
# local-only. Keep in step with ui.py's upload allowlist.
_PUSH_SUBDIRS = ("stp", "std", "reviews", "state", "go-tests", "python-tests")


def build_archive(jira_id):
    """tar.gz of outputs/<ticket> in the type-first layout the dashboard's
    upload route accepts (stp/<ticket>/..., state/<ticket>/...). Returns
    (bytes, file_count); file_count 0 means there is nothing to ship."""
    import io
    import tarfile
    src = _outputs_dir() / jira_id
    buf, n = io.BytesIO(), 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for sub in _PUSH_SUBDIRS:
            base = src / sub
            if not base.is_dir():
                continue
            for f in sorted(p for p in base.rglob("*") if p.is_file()):
                rel = f.relative_to(base)
                if ".previous" in rel.parts:
                    continue
                tar.add(f, arcname="%s/%s/%s" % (sub, jira_id, rel.as_posix()))
                n += 1
    return buf.getvalue(), n


def push_outputs(jira_id, url, api_key):
    """Ship a ticket's artifacts (and its pipeline_state.yaml, which carries
    the recorded cost) to a team dashboard. Returns True on HTTP 2xx. Never
    raises — like persist_usage, the run already produced its artifacts
    locally; a push failure is reported, not fatal."""
    import urllib.error
    import urllib.request
    if not url:
        print("warning: no dashboard URL (--push / QF_DASHBOARD_URL) — not pushed", file=sys.stderr)
        return False
    if not api_key:
        print("warning: QUALITYFLOW_API_KEY not set — not pushed", file=sys.stderr)
        return False
    body, n = build_archive(jira_id)
    if not n:
        print("warning: nothing to push for %s under %s" % (jira_id, _outputs_dir() / jira_id),
              file=sys.stderr)
        return False
    req = urllib.request.Request(
        url.rstrip("/") + "/api/outputs/" + jira_id, data=body, method="POST",
        headers={"Content-Type": "application/gzip", "X-API-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("pushed %d file(s) for %s to %s (HTTP %s)" % (n, jira_id, url, resp.status))
            return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print("warning: dashboard rejected the push (HTTP %s): %s" % (e.code, detail), file=sys.stderr)
    except (urllib.error.URLError, OSError) as e:
        print("warning: push to %s failed: %s" % (url, e), file=sys.stderr)
    return False


def main(argv):
    """CLI entrypoint.

    `run <JIRA_ID> <phase> [--model M] [--push URL]` runs the phase headless
    exactly like the dashboard button and persists the usage/model the CLI
    reports — so CLI-first teams get the same cost capture as dashboard-
    triggered runs. `--push` (or QF_DASHBOARD_URL) then ships the ticket's
    outputs to the team dashboard.

    `push <JIRA_ID> [--url URL]` ships an existing outputs/<ticket> tree —
    the path for a ticket that was run interactively with the slash commands.
    Both read the dashboard key from QUALITYFLOW_API_KEY."""
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline_runner.py", description=main.__doc__)
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("run", help="run one phase via `claude -p` with usage capture")
    p.add_argument("jira_id")
    p.add_argument("phase", choices=sorted(_CMD))
    p.add_argument("--model", default="", help="model override (default: inherit)")
    p.add_argument("--push", metavar="URL", default=os.environ.get("QF_DASHBOARD_URL", ""),
                   help="after the phase, POST outputs/<ticket> to this dashboard "
                        "(default: $QF_DASHBOARD_URL; key from $QUALITYFLOW_API_KEY)")
    q = sub.add_parser("push", help="POST an existing outputs/<ticket> tree to a dashboard")
    q.add_argument("jira_id")
    q.add_argument("--url", default=os.environ.get("QF_DASHBOARD_URL", ""),
                   help="dashboard base URL (default: $QF_DASHBOARD_URL)")
    args = ap.parse_args(argv)
    api_key = os.environ.get("QUALITYFLOW_API_KEY", "")

    if args.op == "push":
        sys.exit(0 if push_outputs(args.jira_id, args.url, api_key) else 1)

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
    if args.push:
        push_outputs(args.jira_id, args.push, api_key)


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
