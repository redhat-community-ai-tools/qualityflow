"""Pure-function metrics engine for the QualityFlow dashboard.

No FastAPI, no filesystem I/O, no ui.py imports — everything here takes
already-parsed `pipeline_state.yaml` dicts (and `approvals.yaml` dicts) and
returns plain dicts. ui.py owns state scanning/caching; this module owns the
math, so it can be tested and reasoned about without a server.

Every aggregate result includes `n` (sample size actually used) and `basis`:
    "measured" — read directly off recorded timestamps/usage
    "derived"  — computed from measured values (e.g. a span between them)
    "estimated" — extrapolated with a coefficient, not counted from data
Below the minimum sample size for a statistic, functions return an explicit
`unavailable_reason` instead of a number — an honest empty beats a fabricated
one.

Canonical definitions
----------------------
COMPLETED RUN: a ticket whose `stp`, `std`, and `codegen` phases (or either
legacy `go_codegen`/`python_codegen`) are all `status: completed`.

E2E CYCLE TIME: earliest phase start -> latest phase completion among a
completed run's terminal-status phases. basis: derived (measured timestamps,
span computed).

PHASE DURATION: per phase, end - start where both timestamps exist. Callers
pass a `ts_fn(phase_dict) -> (start_iso|None, end_iso|None)` callback —
ui.py passes its own `_phase_timestamps`, which already reconciles the two
writer dialects (`started`/`completed` vs `started_ts`/`finished_ts`). This
module never re-derives that reconciliation.

COST/STP: sum of usage.cost_usd over the stp+stp_review+stp_refine phases,
across every ticket whose `stp` phase is completed, divided by that ticket
count. STPs/$ is the inverse. Same shape for STD (std+std_review+std_refine).
COST/COMPLETED RUN: total cost of a completed run's phases / completed runs.
Every cost result also reports `capture_ratio` (phases-with-usage /
relevant-phases-that-ran) and `partial` (capture_ratio < 1.0) — usage is only
recorded for dashboard-run phases, so this ratio is the honesty flag for
everything else in the cost dict. basis: measured (but partial).

AUTOMATION RATE: completed runs with zero human interventions / completed
runs. A human intervention is any approval gate whose reviewer isn't the
dashboard's auto-approve stamp (see `default_is_human`), OR any `*_refine`
phase that ran, OR any phase carrying `history` (a rerun). Also reports
`human_touches_per_run`.

FIRST-PASS SUCCESS per family: STP first-pass = `stp` completed AND
`stp_review` verdict APPROVED AND no `stp_refine` ran AND `stp` has no
history. Same shape for STD. CODE first-pass = codegen completed with no
history. FULL RUN first-pass reuses ui.py's quality-trend `first_time_approve`
definition verbatim: all available verdicts APPROVED, zero refine loops, and
no human rejection recorded in approvals.

REVIEW LATENCY: for each approval gate with a human reviewer, the gap between
the gate's timestamp and the corresponding review phase's completion
timestamp (preferring the dedicated `{base}_review` phase, falling back to
the combined `{base}` phase — same fallback order as ui.py's
`_review_phase_score`). Reported as percentiles.

BOTTLENECK: each phase family's share of mean E2E cycle time across completed
runs; flagged when share > 40%. Contributors (high retry rate, a refine loop
having run) are only named when the data actually supports them.

COST ANOMALY: a (ticket, phase) cost vs. the median cost of that phase family
across tickets; flagged when > 2x median AND the baseline has >= 3 tickets.
A non-empty `history` on that phase is attached as `retry_count` — a
possible-but-not-certain reason, only ever shown when the data has it.

MIN_N (module constant, default 3): the minimum completed-run count for any
percentile-shaped statistic (cycle time, phase duration, review latency,
bottlenecks). Simple sums/counts (cost, automation, first-pass) only need
n >= 1 to report a real, honestly-labeled number.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

TsFn = Callable[[dict], tuple[str | None, str | None]]

MIN_N = 3  # below this, percentile-shaped stats report a reason, not a number.
_TERMINAL_STATUSES = ("completed", "failed", "blocked", "skipped")
_INACTIVE_STATUSES = (None, "pending", "not_started")


def to_ts(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


def _phase_cost(phase: dict) -> float | None:
    usage = phase.get("usage") if isinstance(phase, dict) else None
    cost = usage.get("cost_usd") if isinstance(usage, dict) else None
    return cost if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None


def _phase_family(name: str) -> str:
    """go_codegen/python_codegen collapse into codegen, same bucketing /api/metrics/roi uses."""
    return "codegen" if "codegen" in name else name


def _refine_ran(phases: dict, family: str) -> bool:
    entry = phases.get(f"{family}_refine")
    return isinstance(entry, dict) and entry.get("status") not in _INACTIVE_STATUSES


def default_is_human(entry: dict) -> bool:
    """An approval entry is a human action when its reviewer isn't the
    dashboard's auto-approve stamp — mirrors ui.py's _compute_value_metrics."""
    return bool(entry) and entry.get("reviewer") not in (None, "", "dashboard (auto)")


def percentile_stats(values: list[float]) -> dict | None:
    """avg/median/p50/p90/p95/min/max/n over a list of numbers. None if empty."""
    vals = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))
    n = len(vals)
    if n == 0:
        return None

    def _pct(p: float) -> float:
        if n == 1:
            return vals[0]
        k = (n - 1) * p
        lo = int(k)
        hi = min(lo + 1, n - 1)
        return vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (k - lo)

    return {
        "avg": round(sum(vals) / n, 2), "median": round(_pct(0.5), 2),
        "p50": round(_pct(0.5), 2), "p90": round(_pct(0.9), 2), "p95": round(_pct(0.95), 2),
        "min": round(vals[0], 2), "max": round(vals[-1], 2), "n": n,
    }


def is_completed_run(phases: dict) -> bool:
    if not isinstance(phases, dict):
        return False

    def _done(key: str) -> bool:
        p = phases.get(key)
        return isinstance(p, dict) and p.get("status") == "completed"

    return (_done("stp") and _done("std")
            and (_done("codegen") or _done("go_codegen") or _done("python_codegen")))


def cycle_seconds(phases: dict, ts_fn: TsFn) -> float | None:
    """Earliest start -> latest end among terminal-status phases. Caller should
    only call this for completed runs (is_completed_run) — nothing here
    enforces that, since a partial run's span is meaningless either way."""
    starts, ends = [], []
    for phase in (phases or {}).values():
        if not isinstance(phase, dict) or phase.get("status") not in _TERMINAL_STATUSES:
            continue
        start, end = ts_fn(phase)
        s, e = to_ts(start), to_ts(end)
        if s is not None:
            starts.append(s)
        if e is not None:
            ends.append(e)
    if not starts or not ends:
        return None
    span = max(ends) - min(starts)
    return round(span, 1) if span > 0 else None


def phase_duration_map(states: list[dict], ts_fn: TsFn) -> dict[str, list[float]]:
    """family -> [duration_seconds, ...] across completed runs only, so this
    lines up with cycle_seconds' denominator (bottlenecks divides one by the other)."""
    out: dict[str, list[float]] = {}
    for state in states:
        phases = state.get("phases") or {}
        if not is_completed_run(phases):
            continue
        for name, phase in phases.items():
            if not isinstance(phase, dict):
                continue
            start, end = ts_fn(phase)
            s, e = to_ts(start), to_ts(end)
            if s is None or e is None or e <= s:
                continue
            out.setdefault(_phase_family(name), []).append(round(e - s, 1))
    return out


def slow_phases(states: list[dict], ts_fn: TsFn) -> list[dict]:
    """Phases whose duration exceeds their family's P90 — the "duration > P90"
    alert rule. Only families with >= MIN_N measured durations get a baseline;
    by construction at most ~10% of measurements can exceed P90, so this flags
    the genuine tail, not routine variance. P90 is computed over the full
    sample including the flagged value (leave-one-out isn't worth the
    complexity at these n; the flagged value only drags P90 up, making the
    rule conservative). Sorted worst-excess first."""
    by_family: dict[str, list[tuple[str, float]]] = {}
    for state in states:
        ticket = str(state.get("ticket_id") or state.get("jira_id") or "")
        phases = state.get("phases") or {}
        for name, phase in phases.items():
            if not isinstance(phase, dict) or phase.get("status") != "completed":
                continue
            start, end = ts_fn(phase)
            s, e = to_ts(start), to_ts(end)
            if s is None or e is None or e <= s:
                continue
            by_family.setdefault(_phase_family(name), []).append((ticket, round(e - s, 1)))

    findings = []
    for family, entries in by_family.items():
        if len(entries) < MIN_N:
            continue
        stats = percentile_stats([sec for _, sec in entries])
        if stats is None:
            continue
        p90 = stats["p90"]
        for ticket, seconds in entries:
            if seconds > p90:
                findings.append({
                    "jira_id": ticket, "family": family,
                    "seconds": seconds, "p90_seconds": p90, "n": stats["n"],
                    "ratio": round(seconds / p90, 2) if p90 > 0 else None,
                })
    findings.sort(key=lambda f: -(f["ratio"] or 0))
    return findings


def cost_summary(states: list[dict]) -> dict:
    completed = [s for s in states if is_completed_run(s.get("phases") or {})]
    n_completed = len(completed)

    def _walk(subset: list[dict], families: tuple[str, ...] | None = None, gate: str | None = None):
        cost = relevant = with_usage = gated_tickets = 0.0
        for state in subset:
            phases = state.get("phases") or {}
            if gate is not None:
                g = phases.get(gate)
                if not (isinstance(g, dict) and g.get("status") == "completed"):
                    continue
                gated_tickets += 1
            for name in (families if families is not None else list(phases)):
                phase = phases.get(name)
                if not isinstance(phase, dict) or phase.get("status") in _INACTIVE_STATUSES:
                    continue
                relevant += 1
                c = _phase_cost(phase)
                if c is not None:
                    with_usage += 1
                    cost += c
        return cost, relevant, with_usage, gated_tickets

    total_cost, total_relevant, total_with_usage, _ = _walk(states)
    if total_relevant == 0:
        return {"unavailable_reason": "no phases have run yet", "n": 0}

    completed_cost, _, _, _ = _walk(completed)
    stp_cost, _, _, stp_tickets = _walk(states, ("stp", "stp_review", "stp_refine"), gate="stp")
    std_cost, _, _, std_tickets = _walk(states, ("std", "std_review", "std_refine"), gate="std")
    capture_ratio = round(total_with_usage / total_relevant, 3)

    # Cost per successful artifact: an artifact (STP or STD) is "successful"
    # when it exists AND its review passed (any APPROVED* verdict — same
    # passing-verdict rule as model_breakdown). Denominator counts artifacts,
    # not tickets; numerator is the artifact families' cost only, so unreviewed
    # or NEEDS_REVISION artifacts make this ratio worse, as they should.
    approved_artifacts = 0
    for state in states:
        phases = state.get("phases") or {}
        for gate in ("stp", "std"):
            g, rev = phases.get(gate), phases.get(f"{gate}_review")
            if (isinstance(g, dict) and g.get("status") == "completed"
                    and isinstance(rev, dict)
                    and str(rev.get("verdict") or "").startswith("APPROVED")):
                approved_artifacts += 1
    artifact_cost = stp_cost + std_cost

    return {
        "n": len(states), "n_completed_runs": n_completed,
        "total": round(total_cost, 4),
        "per_completed_run": round(completed_cost / n_completed, 4) if n_completed else None,
        "per_stp": round(stp_cost / stp_tickets, 4) if stp_tickets else None,
        "stps_per_dollar": round(stp_tickets / stp_cost, 4) if stp_cost > 0 else None,
        "per_std": round(std_cost / std_tickets, 4) if std_tickets else None,
        "stds_per_dollar": round(std_tickets / std_cost, 4) if std_cost > 0 else None,
        "per_approved_artifact": round(artifact_cost / approved_artifacts, 4) if approved_artifacts else None,
        "approved_artifacts": approved_artifacts,
        "capture_ratio": capture_ratio, "partial": capture_ratio < 1.0,
        "basis": "measured",
    }


def automation_summary(states: list[dict], approvals_by_ticket: dict[str, dict],
                        is_human_fn: Callable[[dict], bool] | None = None) -> dict:
    is_human = is_human_fn or default_is_human
    completed = [s for s in states if is_completed_run(s.get("phases") or {})]
    n = len(completed)
    if n == 0:
        return {"unavailable_reason": "no completed runs", "n": 0}

    zero_touch = 0
    human_touches = 0
    for state in completed:
        ticket = str(state.get("ticket_id") or state.get("jira_id") or "")
        phases = state.get("phases") or {}
        approvals = approvals_by_ticket.get(ticket) or {}
        human_actions = [e for e in approvals.values()
                         if isinstance(e, dict) and e.get("status") in ("approved", "rejected") and is_human(e)]
        human_touches += len(human_actions)
        refine_ran = any(k.endswith("_refine") and isinstance(v, dict) and v.get("status") not in _INACTIVE_STATUSES
                         for k, v in phases.items())
        has_rerun = any(isinstance(v, dict) and v.get("history") for v in phases.values())
        if not human_actions and not refine_ran and not has_rerun:
            zero_touch += 1

    return {
        "n": n, "basis": "derived",
        "automation_rate": round(zero_touch / n, 3),
        "zero_touch_runs": zero_touch,
        "human_touches_per_run": round(human_touches / n, 3),
    }


def _rate(hits: int, n: int) -> dict:
    if n == 0:
        return {"unavailable_reason": "no completed phases in this family", "n": 0}
    return {"rate": round(hits / n, 3), "n": n, "hits": hits}


def first_pass_summary(states: list[dict], approvals_by_ticket: dict[str, dict] | None = None) -> dict:
    approvals_by_ticket = approvals_by_ticket or {}
    stp_hits = std_hits = code_hits = full_hits = 0
    stp_n = std_n = code_n = full_n = 0
    # Rework is narrower than "not first-pass": it counts only actual redo work
    # (a refine loop ran, or the phase was re-run per its history) — a run that
    # merely landed APPROVED_WITH_FINDINGS misses first-pass but is NOT rework.
    stp_rework = std_rework = code_rework = 0
    for state in states:
        phases = state.get("phases") or {}
        stp, stp_review = phases.get("stp") or {}, phases.get("stp_review") or {}
        if stp.get("status") == "completed":
            stp_n += 1
            if _refine_ran(phases, "stp") or stp.get("history"):
                stp_rework += 1
            elif stp_review.get("verdict") == "APPROVED":
                stp_hits += 1

        std, std_review = phases.get("std") or {}, phases.get("std_review") or {}
        if std.get("status") == "completed":
            std_n += 1
            if _refine_ran(phases, "std") or std.get("history"):
                std_rework += 1
            elif std_review.get("verdict") == "APPROVED":
                std_hits += 1

        codegen = phases.get("codegen") or {}
        code_done = codegen.get("status") == "completed" or any(
            (phases.get(k) or {}).get("status") == "completed" for k in ("go_codegen", "python_codegen"))
        if code_done:
            code_n += 1
            if codegen.get("history"):
                code_rework += 1
            else:
                code_hits += 1

        # Full-run first-pass — same definition as /api/metrics/quality-trend's
        # first_time_approve, reused verbatim rather than re-derived.
        stp_v = stp_review.get("verdict") or stp.get("verdict")
        std_v = std_review.get("verdict") or std.get("verdict")
        verdicts = {k: v for k, v in (("stp", stp_v), ("std", std_v)) if v}
        if verdicts:
            full_n += 1
            refine_loops = sum(1 for k, v in phases.items()
                               if k.endswith("_refine") and isinstance(v, dict)
                               and v.get("status") not in _INACTIVE_STATUSES)
            ticket = str(state.get("ticket_id") or state.get("jira_id") or "")
            rejected = any(isinstance(e, dict) and e.get("status") == "rejected"
                          for e in (approvals_by_ticket.get(ticket) or {}).values())
            if all(v == "APPROVED" for v in verdicts.values()) and refine_loops == 0 and not rejected:
                full_hits += 1

    return {
        "stp": _rate(stp_hits, stp_n), "std": _rate(std_hits, std_n),
        "code": _rate(code_hits, code_n), "full_run": _rate(full_hits, full_n),
        "rework": {
            "stp": _rate(stp_rework, stp_n), "std": _rate(std_rework, std_n),
            "code": _rate(code_rework, code_n),
        },
    }


def review_completion_ts(phases: dict, gate: str, ts_fn: TsFn) -> str | None:
    """The timestamp a gate's review actually finished — dedicated `{base}_review`
    phase first, falling back to the combined `{base}` phase. Same fallback
    order as ui.py's _review_phase_score, for the same reason: real state
    files carry either dialect."""
    base = gate[:-len("_review")] if gate.endswith("_review") else gate
    for entry in (phases.get(gate), phases.get(base)):
        if isinstance(entry, dict):
            _, end = ts_fn(entry)
            if end:
                return end
    return None


def review_latency(states: list[dict], approvals_by_ticket: dict[str, dict], ts_fn: TsFn,
                    is_human_fn: Callable[[dict], bool] | None = None) -> dict:
    is_human = is_human_fn or default_is_human
    seconds: list[float] = []
    for state in states:
        ticket = str(state.get("ticket_id") or state.get("jira_id") or "")
        phases = state.get("phases") or {}
        for gate, entry in (approvals_by_ticket.get(ticket) or {}).items():
            if not isinstance(entry, dict) or not is_human(entry):
                continue
            gate_ts = to_ts(entry.get("timestamp"))
            review_ts = to_ts(review_completion_ts(phases, gate, ts_fn))
            if gate_ts is None or review_ts is None or gate_ts < review_ts:
                continue
            seconds.append(gate_ts - review_ts)
    if len(seconds) < MIN_N:
        return {"unavailable_reason": f"fewer than {MIN_N} measurable review latencies", "n": len(seconds)}
    stats = percentile_stats(seconds)
    stats["basis"] = "measured"
    return stats


def bottlenecks(states: list[dict], ts_fn: TsFn) -> dict:
    completed = [s for s in states if is_completed_run(s.get("phases") or {})]
    if len(completed) < MIN_N:
        return {"unavailable_reason": f"fewer than {MIN_N} completed runs", "n": len(completed)}

    cycles = [c for s in completed if (c := cycle_seconds(s.get("phases") or {}, ts_fn)) is not None]
    if not cycles:
        return {"unavailable_reason": "no measurable cycle times", "n": len(completed)}
    mean_cycle = sum(cycles) / len(cycles)
    durations = phase_duration_map(completed, ts_fn)

    findings = []
    for family, vals in durations.items():
        if not vals or mean_cycle <= 0:
            continue
        mean_dur = sum(vals) / len(vals)
        share = mean_dur / mean_cycle
        if share <= 0.4:
            continue
        retries = [len((s.get("phases") or {}).get(family, {}).get("history") or [])
                  for s in completed if isinstance((s.get("phases") or {}).get(family), dict)]
        mean_retries = sum(retries) / len(retries) if retries else 0.0
        refine_present = any(_refine_ran(s.get("phases") or {}, family) for s in completed)
        contributors = []
        if mean_retries > 0.3:
            contributors.append(f"high retry rate (avg {mean_retries:.1f} reruns)")
        if refine_present:
            contributors.append("refine loop present")
        findings.append({"family": family, "share": round(share, 3),
                         "mean_seconds": round(mean_dur, 1), "contributors": contributors})
    findings.sort(key=lambda f: f["share"], reverse=True)
    return {"n": len(completed), "mean_cycle_seconds": round(mean_cycle, 1),
           "findings": findings, "basis": "derived"}


def cost_anomalies(states: list[dict]) -> list[dict]:
    by_family: dict[str, list[tuple[str, float, dict]]] = {}
    for state in states:
        ticket = str(state.get("ticket_id") or state.get("jira_id") or "?")
        for name, phase in (state.get("phases") or {}).items():
            if not isinstance(phase, dict):
                continue
            cost = _phase_cost(phase)
            if cost is None:
                continue
            by_family.setdefault(_phase_family(name), []).append((ticket, cost, phase))

    anomalies = []
    for family, entries in by_family.items():
        costs = sorted(c for _, c, _ in entries)
        n = len(costs)
        if n < MIN_N:
            continue
        median = costs[n // 2] if n % 2 else (costs[n // 2 - 1] + costs[n // 2]) / 2
        if median <= 0:
            continue
        for ticket, cost, phase in entries:
            if cost <= 2 * median:
                continue
            anomaly = {"jira_id": ticket, "phase": family, "cost_usd": round(cost, 4),
                      "median_usd": round(median, 4), "ratio": round(cost / median, 2)}
            history = phase.get("history") or []
            if history:
                anomaly["retry_count"] = len(history)
                anomaly["possible_reason"] = "reruns"
            anomalies.append(anomaly)
    anomalies.sort(key=lambda a: a["ratio"], reverse=True)
    return anomalies


def model_breakdown(states: list[dict]) -> dict:
    """Group phase attempts (the live phase entry, plus its compact history
    entries) by `model`. History entries never carry `usage` (see ui.py's
    _record_phase_result — it archives status/verdict/model/finished_ts only),
    so cost/duration stats only ever reflect the live entries; n counts both."""
    groups: dict[str, dict] = {}

    def _bucket(model: str | None) -> dict:
        return groups.setdefault(model or "unknown", {
            "n": 0, "cost_total": 0.0, "cost_n": 0, "duration_total": 0.0, "duration_n": 0,
            "verdicts": {}, "approved": 0, "verdict_n": 0,
        })

    def _tally_verdict(bucket: dict, verdict: str | None) -> None:
        if not verdict:
            return
        bucket["verdicts"][verdict] = bucket["verdicts"].get(verdict, 0) + 1
        bucket["verdict_n"] += 1
        # APPROVED_WITH_FINDINGS is a passing verdict (0 critical findings) —
        # only NEEDS_REVISION fails. Strict all-APPROVED lives in first_pass.
        if verdict.startswith("APPROVED"):
            bucket["approved"] += 1

    for state in states:
        for phase in (state.get("phases") or {}).values():
            if not isinstance(phase, dict):
                continue
            b = _bucket(phase.get("model"))
            b["n"] += 1
            usage = phase.get("usage") if isinstance(phase.get("usage"), dict) else None
            if usage:
                c, d = usage.get("cost_usd"), usage.get("duration_ms")
                if isinstance(c, (int, float)) and not isinstance(c, bool):
                    b["cost_total"] += c
                    b["cost_n"] += 1
                if isinstance(d, (int, float)) and not isinstance(d, bool):
                    b["duration_total"] += d
                    b["duration_n"] += 1
            _tally_verdict(b, phase.get("verdict"))
            for h in (phase.get("history") or []):
                if not isinstance(h, dict):
                    continue
                hb = _bucket(h.get("model"))
                hb["n"] += 1
                _tally_verdict(hb, h.get("verdict"))

    return {
        model: {
            "n": b["n"],
            "cost_usd": {"total": round(b["cost_total"], 4),
                        "avg": round(b["cost_total"] / b["cost_n"], 4) if b["cost_n"] else None,
                        "n": b["cost_n"]},
            "avg_duration_ms": round(b["duration_total"] / b["duration_n"], 1) if b["duration_n"] else None,
            "verdict_counts": b["verdicts"],
            "approval_rate": round(b["approved"] / b["verdict_n"], 3) if b["verdict_n"] else None,
        }
        for model, b in groups.items()
    }


if __name__ == "__main__":  # self-check: synthetic states, no filesystem/network
    def _ts_fn(phase: dict) -> tuple[str | None, str | None]:
        return phase.get("started"), phase.get("completed")

    completed_run = {
        "ticket_id": "T-1",
        "phases": {
            "stp": {"status": "completed", "started": "2026-01-01T00:00:00+00:00",
                    "completed": "2026-01-01T01:00:00+00:00",
                    "usage": {"cost_usd": 1.0}},
            "stp_review": {"status": "completed", "verdict": "APPROVED",
                          "started": "2026-01-01T01:00:00+00:00", "completed": "2026-01-01T01:10:00+00:00"},
            "std": {"status": "completed", "verdict": "APPROVED",
                   "started": "2026-01-01T01:10:00+00:00", "completed": "2026-01-01T02:10:00+00:00",
                   "usage": {"cost_usd": 2.0}},
            "std_review": {"status": "completed", "verdict": "APPROVED",
                          "started": "2026-01-01T02:10:00+00:00", "completed": "2026-01-01T02:20:00+00:00"},
            "codegen": {"status": "completed", "started": "2026-01-01T02:20:00+00:00",
                       "completed": "2026-01-01T03:20:00+00:00", "usage": {"cost_usd": 0.5}},
        },
    }
    partial_run = {
        "ticket_id": "T-2",
        "phases": {
            "stp": {"status": "completed", "started": "2026-01-02T00:00:00+00:00",
                   "completed": "2026-01-02T00:30:00+00:00", "usage": {"cost_usd": 0.8}},
            "std": {"status": "pending"},
            "codegen": {"status": "pending"},
        },
    }
    refined_run = {
        "ticket_id": "T-3",
        "phases": {
            "stp": {"status": "completed", "started": "2026-01-03T00:00:00+00:00",
                   "completed": "2026-01-03T02:00:00+00:00", "usage": {"cost_usd": 9.0},
                   "history": [{"status": "failed"}]},
            "stp_review": {"status": "completed", "verdict": "NEEDS_REVISION",
                          "started": "2026-01-03T02:00:00+00:00", "completed": "2026-01-03T02:10:00+00:00"},
            "stp_refine": {"status": "completed", "started": "2026-01-03T02:10:00+00:00",
                          "completed": "2026-01-03T02:30:00+00:00"},
            "std": {"status": "completed", "verdict": "APPROVED",
                   "started": "2026-01-03T02:30:00+00:00", "completed": "2026-01-03T03:30:00+00:00",
                   "usage": {"cost_usd": 1.5}},
            "std_review": {"status": "completed", "verdict": "APPROVED",
                          "started": "2026-01-03T03:30:00+00:00", "completed": "2026-01-03T03:40:00+00:00"},
            "codegen": {"status": "completed", "started": "2026-01-03T03:40:00+00:00",
                       "completed": "2026-01-03T04:10:00+00:00", "usage": {"cost_usd": 0.4}},
        },
    }
    states = [completed_run, partial_run, refined_run]
    approvals = {
        "T-1": {"stp_review": {"status": "approved", "reviewer": "dashboard (auto)",
                               "timestamp": "2026-01-01T01:10:00+00:00"}},
        "T-3": {"stp_review": {"status": "approved", "reviewer": "alice",
                               "timestamp": "2026-01-03T02:15:00+00:00"},
               "std_review": {"status": "approved", "reviewer": "alice",
                              "timestamp": "2026-01-03T03:50:00+00:00"}},
    }

    assert percentile_stats([]) is None
    ps = percentile_stats([1, 2, 3, 4, 5])
    assert ps["n"] == 5 and ps["median"] == 3 and ps["min"] == 1 and ps["max"] == 5, ps

    assert is_completed_run(completed_run["phases"]) is True
    assert is_completed_run(partial_run["phases"]) is False
    assert is_completed_run(refined_run["phases"]) is True

    # completed_run's 5 phases are back-to-back (no gaps): 1h + 10m + 1h + 10m + 1h = 3h20m.
    assert cycle_seconds(completed_run["phases"], _ts_fn) == 12000.0
    # partial_run's only terminal phase is `stp` — a real span, even off a partial run;
    # callers (phase_duration_map, bottlenecks) are the ones that filter to completed runs.
    assert cycle_seconds(partial_run["phases"], _ts_fn) == 1800.0

    durs = phase_duration_map(states, _ts_fn)
    assert durs["stp"] == [3600.0, 7200.0]  # completed_run + refined_run, partial_run excluded
    assert "codegen" in durs and len(durs["codegen"]) == 2  # both completed runs

    cost = cost_summary(states)
    # total_relevant=12 phases ran across all 3 tickets, only 7 carry usage -> partial capture.
    assert cost["n_completed_runs"] == 2 and cost["capture_ratio"] == 0.583 and cost["partial"], cost
    # stp cost: T-1(1.0) + T-2(0.8) + T-3(9.0) = 10.8, over 3 tickets whose stp completed.
    assert cost["per_stp"] == 3.6, cost
    assert cost["per_completed_run"] == 7.2, cost  # (3.5 + 10.9) / 2 completed runs

    auto = automation_summary(states, approvals)
    assert auto["n"] == 2, auto  # T-1, T-3 are completed runs
    # T-1: auto-approved gate, no refine, no history -> zero-touch.
    # T-3: human-approved gates + refine ran + has history -> not zero-touch.
    assert auto["zero_touch_runs"] == 1 and auto["automation_rate"] == 0.5, auto
    assert auto["human_touches_per_run"] == 1.0, auto  # 2 human actions / 2 runs

    fp = first_pass_summary(states, approvals)
    # stp completed on all 3 tickets; only T-1 has an APPROVED stp_review with no refine/history.
    assert fp["stp"]["n"] == 3 and fp["stp"]["hits"] == 1, fp
    # full_run: T-1 and T-3 both have verdicts to judge; only T-1 is all-APPROVED with 0 refine loops.
    assert fp["full_run"]["n"] == 2 and fp["full_run"]["hits"] == 1, fp

    lat = review_latency(states, approvals, _ts_fn)
    assert lat.get("unavailable_reason"), lat  # only 2 human-reviewed gates (both on T-3) < MIN_N

    bn = bottlenecks(states, _ts_fn)
    assert bn.get("unavailable_reason"), bn  # only 2 completed runs < MIN_N

    anomalies = cost_anomalies(states)
    # stp is the only family with >= MIN_N costed tickets (1.0, 0.8, 9.0); median 1.0 ->
    # T-3's 9.0 is a 9x anomaly, and its stp phase's non-empty history becomes the reason.
    assert len(anomalies) == 1, anomalies
    assert anomalies[0]["jira_id"] == "T-3" and anomalies[0]["phase"] == "stp", anomalies
    assert anomalies[0]["retry_count"] == 1 and anomalies[0]["possible_reason"] == "reruns", anomalies

    mb = model_breakdown(states)
    # no fixture sets `model` — 14 live phases (5+3+6) + 1 history entry (T-3's stp) = 15,
    # all honestly bucketed under "unknown" rather than silently dropped.
    assert mb["unknown"]["n"] == 15, mb

    print("qf_metrics self-check passed")
