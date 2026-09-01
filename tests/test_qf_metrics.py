#!/usr/bin/env python3
"""Tests for qf_metrics.py — the pure-function metrics engine.

No ui.py import, no filesystem/network: every function here takes plain
dicts and returns plain dicts, so these tests just build small synthetic
`pipeline_state.yaml`-shaped dicts inline (mirroring qf_metrics.py's own
`__main__` self-check) and assert on the returned structures.

Run:
  python3 -m pytest tests/test_qf_metrics.py -q
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import qf_metrics as m  # noqa: E402


def _ts_fn(phase: dict) -> tuple:
    """Mirrors ui.py's _phase_timestamps: started_ts/finished_ts (dashboard
    writer dialect) preferred, started/completed (CLI writer dialect) as
    fallback. Reimplemented here rather than imported so this file has no
    ui.py dependency (and none of ui.py's heavy import-time deps)."""
    if not isinstance(phase, dict):
        return None, None
    start = phase.get("started_ts") or phase.get("started")
    end = phase.get("finished_ts") or phase.get("completed")
    return start, end


def _state(ticket_id: str, phases: dict) -> dict:
    return {"ticket_id": ticket_id, "phases": phases}


# ---------------------------------------------------------------------------
# percentile_stats
# ---------------------------------------------------------------------------

def test_percentile_stats_normal_list():
    ps = m.percentile_stats([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert ps == {
        "avg": 55.0, "median": 55.0, "p50": 55.0, "p90": 91.0, "p95": 95.5,
        "min": 10.0, "max": 100.0, "n": 10,
    }


def test_percentile_stats_single_value():
    ps = m.percentile_stats([42])
    assert ps == {
        "avg": 42.0, "median": 42.0, "p50": 42.0, "p90": 42.0, "p95": 42.0,
        "min": 42.0, "max": 42.0, "n": 1,
    }


def test_percentile_stats_empty_list_is_none():
    assert m.percentile_stats([]) is None


# ---------------------------------------------------------------------------
# is_completed_run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phases,expected", [
    ({"stp": {"status": "completed"}, "std": {"status": "completed"},
      "codegen": {"status": "completed"}}, True),
    ({"stp": {"status": "completed"}, "std": {"status": "completed"},
      "go_codegen": {"status": "completed"}}, True),
    ({"stp": {"status": "completed"}, "std": {"status": "completed"},
      "python_codegen": {"status": "completed"}}, True),
    ({"stp": {"status": "completed"}, "std": {"status": "in_progress"},
      "codegen": {"status": "pending"}}, False),
    ({"stp": {"status": "completed"}, "std": {"status": "completed"},
      "codegen": {"status": "failed"}}, False),
], ids=["canonical", "legacy_go_codegen", "legacy_python_codegen", "incomplete", "failed"])
def test_is_completed_run(phases, expected):
    assert m.is_completed_run(phases) is expected


# ---------------------------------------------------------------------------
# cycle_seconds
# ---------------------------------------------------------------------------

def test_cycle_seconds_dashboard_dialect():
    phases = {
        "stp": {"status": "completed",
                "started_ts": "2026-01-01T00:00:00+00:00",
                "finished_ts": "2026-01-01T01:00:00+00:00"},
        "codegen": {"status": "completed",
                    "started_ts": "2026-01-01T01:00:00+00:00",
                    "finished_ts": "2026-01-01T02:00:00+00:00"},
    }
    assert m.cycle_seconds(phases, _ts_fn) == 7200.0


def test_cycle_seconds_cli_dialect_mixed_z_and_offset():
    # One phase timestamped with a bare Z suffix, the other with an explicit
    # +00:00 offset — both must parse and combine into the same span.
    phases = {
        "stp": {"status": "completed",
                "started": "2026-01-01T00:00:00Z",
                "completed": "2026-01-01T01:00:00Z"},
        "codegen": {"status": "completed",
                    "started": "2026-01-01T01:00:00+00:00",
                    "completed": "2026-01-01T02:00:00+00:00"},
    }
    assert m.cycle_seconds(phases, _ts_fn) == 7200.0


def test_cycle_seconds_missing_timestamps_is_none():
    phases = {"stp": {"status": "completed"}}  # no started/completed at all
    assert m.cycle_seconds(phases, _ts_fn) is None


def test_cycle_seconds_zero_span_guarded():
    phases = {"stp": {"status": "completed",
                       "started": "2026-01-01T00:00:00Z",
                       "completed": "2026-01-01T00:00:00Z"}}
    assert m.cycle_seconds(phases, _ts_fn) is None


def test_cycle_seconds_negative_span_guarded():
    # Malformed data: end recorded before start. The guard (span > 0) must
    # reject this rather than return a negative duration.
    phases = {"stp": {"status": "completed",
                       "started": "2026-01-01T02:00:00Z",
                       "completed": "2026-01-01T01:00:00Z"}}
    assert m.cycle_seconds(phases, _ts_fn) is None


# ---------------------------------------------------------------------------
# cost_summary
# ---------------------------------------------------------------------------

def test_cost_summary_mixed_usage_presence():
    states = [
        _state("T-1", {
            "stp": {"status": "completed", "usage": {"cost_usd": 1.0}},
            "std": {"status": "completed", "usage": {"cost_usd": 2.0}},
            "codegen": {"status": "completed", "usage": {"cost_usd": 0.5}},
        }),
        _state("T-2", {
            "stp": {"status": "completed"},  # no usage recorded
            "std": {"status": "completed", "usage": {"cost_usd": 1.0}},
            "codegen": {"status": "completed"},  # no usage recorded
        }),
    ]
    cost = m.cost_summary(states)
    assert cost["n"] == 2
    assert cost["n_completed_runs"] == 2
    assert cost["total"] == 4.5
    assert cost["per_completed_run"] == 2.25
    # capture_ratio: 4 of 6 relevant phases carried usage.
    assert cost["capture_ratio"] == 0.667
    assert cost["partial"] is True
    assert cost["per_stp"] == 0.5  # (1.0 + 0) / 2 stp-completed tickets
    assert cost["stps_per_dollar"] == 2.0
    assert cost["per_std"] == 1.5  # (2.0 + 1.0) / 2 std-completed tickets
    assert cost["basis"] == "measured"


def test_cost_summary_no_phases_is_unavailable():
    assert m.cost_summary([]) == {"unavailable_reason": "no phases have run yet", "n": 0}
    # Same honest-empty outcome when phases exist but none have run yet.
    pending_only = [_state("T-1", {"stp": {"status": "pending"}})]
    assert m.cost_summary(pending_only) == {"unavailable_reason": "no phases have run yet", "n": 0}


def test_cost_summary_per_stp_includes_review_and_refine_phases():
    states = [_state("T-1", {
        "stp": {"status": "completed", "usage": {"cost_usd": 1.0}},
        "stp_review": {"status": "completed", "usage": {"cost_usd": 0.5}},
        "stp_refine": {"status": "completed", "usage": {"cost_usd": 0.3}},
    })]
    cost = m.cost_summary(states)
    assert cost["per_stp"] == pytest.approx(1.8)


# ---------------------------------------------------------------------------
# automation_summary
# ---------------------------------------------------------------------------

def test_automation_summary_zero_touch_vs_human_vs_refine():
    completed_phases = {
        "stp": {"status": "completed"}, "std": {"status": "completed"},
        "codegen": {"status": "completed"},
    }
    states = [
        _state("T-1", completed_phases),  # zero-touch: auto-approved only
        _state("T-2", completed_phases),  # human-approved gate
        _state("T-3", {**completed_phases,
                       "stp_refine": {"status": "completed"}}),  # refine ran, no approvals at all
    ]
    approvals = {
        "T-1": {"stp_review": {"status": "approved", "reviewer": "dashboard (auto)"}},
        "T-2": {"stp_review": {"status": "approved", "reviewer": "alice"}},
    }
    auto = m.automation_summary(states, approvals)
    assert auto["n"] == 3
    assert auto["zero_touch_runs"] == 1  # only T-1
    assert auto["automation_rate"] == round(1 / 3, 3)
    # human touches: T-1=0, T-2=1, T-3=0 -> 1 touch over 3 runs.
    assert auto["human_touches_per_run"] == round(1 / 3, 3)


def test_automation_summary_no_completed_runs_is_unavailable():
    assert m.automation_summary([], {}) == {"unavailable_reason": "no completed runs", "n": 0}


# ---------------------------------------------------------------------------
# first_pass_summary
# ---------------------------------------------------------------------------

def test_first_pass_summary_family_independence_history_and_full_run_strictness():
    states = [
        # T-1: STP needed a refine (not first-pass) while STD in the SAME
        # ticket passed clean (first-pass) -> families are independent.
        _state("T-1", {
            "stp": {"status": "completed", "history": [{"status": "failed"}]},
            "stp_review": {"status": "completed", "verdict": "NEEDS_REVISION"},
            "stp_refine": {"status": "completed"},
            "std": {"status": "completed"},
            "std_review": {"status": "completed", "verdict": "APPROVED"},
            "codegen": {"status": "completed"},
        }),
        # T-2: STD verdict APPROVED, no refine ran, but a non-empty `history`
        # on the phase itself defeats first-pass anyway.
        _state("T-2", {
            "std": {"status": "completed", "history": [{"status": "failed"}]},
            "std_review": {"status": "completed", "verdict": "APPROVED"},
        }),
        # T-3: every family is individually first-pass (APPROVED, no refine,
        # no history) yet a human rejection recorded in approvals still
        # fails full_run — full_run is stricter than the union of families.
        _state("T-3", {
            "stp": {"status": "completed"},
            "stp_review": {"status": "completed", "verdict": "APPROVED"},
            "std": {"status": "completed"},
            "std_review": {"status": "completed", "verdict": "APPROVED"},
            "codegen": {"status": "completed"},
        }),
    ]
    approvals = {"T-3": {"stp_review": {"status": "rejected", "reviewer": "alice"}}}

    fp = m.first_pass_summary(states, approvals)
    assert fp["stp"] == {"rate": 0.5, "n": 2, "hits": 1}
    assert fp["std"] == {"rate": round(2 / 3, 3), "n": 3, "hits": 2}
    assert fp["code"] == {"rate": 1.0, "n": 2, "hits": 2}
    # full_run: only T-2 is a real hit. T-1 fails on its own merits (STP
    # NEEDS_REVISION); T-3 fails despite every family passing, because of
    # the rejection -- the strictness this test is here to pin down.
    assert fp["full_run"] == {"rate": round(1 / 3, 3), "n": 3, "hits": 1}


def test_first_pass_summary_empty_states_reports_unavailable():
    fp = m.first_pass_summary([])
    for family in ("stp", "std", "code", "full_run"):
        assert fp[family]["n"] == 0
        assert "unavailable_reason" in fp[family]


# ---------------------------------------------------------------------------
# review_latency
# ---------------------------------------------------------------------------

def test_review_latency_measures_gate_minus_review_and_ignores_auto():
    states = [
        _state("T-1", {"stp_review": {"status": "completed",
                                      "started": "2026-01-01T00:55:00Z",
                                      "completed": "2026-01-01T01:00:00Z"}}),
        _state("T-2", {"std_review": {"status": "completed",
                                      "started": "2026-01-02T01:50:00Z",
                                      "completed": "2026-01-02T02:00:00Z"}}),
        _state("T-3", {"stp_review": {"status": "completed",
                                      "started": "2026-01-03T02:45:00Z",
                                      "completed": "2026-01-03T03:00:00Z"}}),
        # Auto-approved gate: would add a 1-second latency (and drag min
        # down to 1.0) if it were counted. It must be excluded entirely.
        _state("T-4", {"stp_review": {"status": "completed",
                                      "started": "2026-01-04T03:59:59Z",
                                      "completed": "2026-01-04T04:00:00Z"}}),
    ]
    approvals = {
        "T-1": {"stp_review": {"status": "approved", "reviewer": "alice",
                               "timestamp": "2026-01-01T01:05:00Z"}},   # +300s
        "T-2": {"std_review": {"status": "approved", "reviewer": "bob",
                               "timestamp": "2026-01-02T02:10:00Z"}},   # +600s
        "T-3": {"stp_review": {"status": "approved", "reviewer": "carol",
                               "timestamp": "2026-01-03T03:15:00Z"}},   # +900s
        "T-4": {"stp_review": {"status": "approved", "reviewer": "dashboard (auto)",
                               "timestamp": "2026-01-04T04:00:01Z"}},   # +1s, must be ignored
    }
    lat = m.review_latency(states, approvals, _ts_fn)
    assert lat["n"] == 3
    assert lat["min"] == 300.0  # if T-4 leaked in, min would be 1.0
    assert lat["max"] == 900.0
    assert lat["avg"] == 600.0
    assert lat["basis"] == "measured"


# ---------------------------------------------------------------------------
# bottlenecks
# ---------------------------------------------------------------------------

def _completed_run(ticket, stp_history=None, stp_refine=False):
    phases = {
        "stp": {"status": "completed",
                "started": "2026-01-01T00:00:00Z", "completed": "2026-01-01T01:00:00Z"},
        "std": {"status": "completed",
                "started": "2026-01-01T01:00:00Z", "completed": "2026-01-01T01:05:00Z"},
        "codegen": {"status": "completed",
                    "started": "2026-01-01T01:05:00Z", "completed": "2026-01-01T01:10:00Z"},
    }
    if stp_history is not None:
        phases["stp"]["history"] = stp_history
    if stp_refine:
        phases["stp_refine"] = {"status": "completed",
                                "started": "2026-01-01T01:10:00Z", "completed": "2026-01-01T01:11:00Z"}
    return _state(ticket, phases)


def test_bottlenecks_dominant_phase_flagged_with_contributors():
    states = [
        _completed_run("T-1", stp_history=[{"status": "failed"}], stp_refine=True),
        _completed_run("T-2"),
        _completed_run("T-3"),
    ]
    bn = m.bottlenecks(states, _ts_fn)
    assert bn["n"] == 3
    assert len(bn["findings"]) == 1
    finding = bn["findings"][0]
    assert finding["family"] == "stp"
    assert finding["share"] > 0.4
    assert any("retry" in c for c in finding["contributors"])
    assert any("refine" in c for c in finding["contributors"])


def test_bottlenecks_balanced_phases_no_findings():
    def _balanced_run(ticket):
        phases = {
            "stp": {"status": "completed",
                    "started": "2026-01-01T00:00:00Z", "completed": "2026-01-01T00:10:00Z"},
            "std": {"status": "completed",
                    "started": "2026-01-01T00:10:00Z", "completed": "2026-01-01T00:20:00Z"},
            "codegen": {"status": "completed",
                       "started": "2026-01-01T00:20:00Z", "completed": "2026-01-01T00:30:00Z"},
        }
        return _state(ticket, phases)

    states = [_balanced_run("T-1"), _balanced_run("T-2"), _balanced_run("T-3")]
    bn = m.bottlenecks(states, _ts_fn)
    assert bn["findings"] == []


def test_bottlenecks_contributors_empty_when_unsupported():
    # Same dominant-phase shape as the flagged test, but no history and no
    # refine anywhere -- the phase is still a bottleneck, just with no named
    # cause, since none of the data supports one.
    states = [_completed_run("T-1"), _completed_run("T-2"), _completed_run("T-3")]
    bn = m.bottlenecks(states, _ts_fn)
    assert len(bn["findings"]) == 1
    assert bn["findings"][0]["contributors"] == []


# ---------------------------------------------------------------------------
# cost_anomalies
# ---------------------------------------------------------------------------

def test_cost_anomalies_threshold_baseline_and_retry_count():
    states = [
        _state("T-1", {"stp": {"status": "completed", "usage": {"cost_usd": 1.0}},
                      "std": {"status": "completed", "usage": {"cost_usd": 1.0}}}),
        _state("T-2", {"stp": {"status": "completed", "usage": {"cost_usd": 1.0}},
                      "std": {"status": "completed", "usage": {"cost_usd": 1.0}}}),
        _state("T-3", {"stp": {"status": "completed", "usage": {"cost_usd": 1.0}}}),
        _state("T-4", {
            # stp: 4 costed tickets (n>=MIN_N), 5x median, WITH history -> flagged + retry_count.
            "stp": {"status": "completed", "usage": {"cost_usd": 5.0},
                   "history": [{"status": "failed"}, {"status": "failed"}]},
            # codegen: 4 costed tickets (n>=MIN_N), 5x median, NO history -> flagged, no retry_count.
            "codegen": {"status": "completed", "usage": {"cost_usd": 5.0}},
        }),
        _state("T-5", {"codegen": {"status": "completed", "usage": {"cost_usd": 1.0}}}),
        _state("T-6", {"codegen": {"status": "completed", "usage": {"cost_usd": 1.0}}}),
    ]
    anomalies = m.cost_anomalies(states)
    by_key = {(a["jira_id"], a["phase"]): a for a in anomalies}

    # std only has 2 costed tickets (n < MIN_N) -> never flagged, no matter the spread.
    assert not any(phase == "std" for _, phase in by_key)

    assert by_key[("T-4", "stp")]["ratio"] == 5.0
    assert by_key[("T-4", "stp")]["retry_count"] == 2
    assert by_key[("T-4", "stp")]["possible_reason"] == "reruns"

    assert by_key[("T-4", "codegen")]["ratio"] == 5.0
    assert "retry_count" not in by_key[("T-4", "codegen")]


def test_cost_anomalies_empty_states_returns_empty_list():
    assert m.cost_anomalies([]) == []


# ---------------------------------------------------------------------------
# model_breakdown
# ---------------------------------------------------------------------------

def test_model_breakdown_unknown_bucket_and_history_counted_not_costed():
    states = [_state("T-1", {
        "stp": {"status": "completed", "model": "claude-x",
               "usage": {"cost_usd": 1.0, "duration_ms": 100}, "verdict": "APPROVED"},
        "std": {"status": "completed", "usage": {"cost_usd": 2.0}},  # no model -> unknown
        "codegen": {"status": "completed", "model": "claude-x",
                   "history": [{"model": "claude-x"}, {}]},  # history: no usage ever
    })]
    mb = m.model_breakdown(states)

    # claude-x: 1 live stp phase + 1 live codegen phase + 1 history entry = n 3,
    # but only the live stp phase ever carried usage.
    assert mb["claude-x"]["n"] == 3
    assert mb["claude-x"]["cost_usd"] == {"total": 1.0, "avg": 1.0, "n": 1}
    assert mb["claude-x"]["avg_duration_ms"] == 100.0
    assert mb["claude-x"]["approval_rate"] == 1.0

    # unknown: std's live phase (no model) + codegen's second history entry (no model).
    assert mb["unknown"]["n"] == 2
    assert mb["unknown"]["cost_usd"] == {"total": 2.0, "avg": 2.0, "n": 1}
    assert mb["unknown"]["avg_duration_ms"] is None
    assert mb["unknown"]["approval_rate"] is None


def test_model_breakdown_empty_states_returns_empty_dict():
    assert m.model_breakdown([]) == {}


# ---------------------------------------------------------------------------
# Edge cases: empty states, malformed (non-crashing) phase entries, missing
# timestamps -- every function should degrade to an honest empty/None
# rather than raising.
# ---------------------------------------------------------------------------

def test_edge_case_malformed_non_core_phase_entries_do_not_crash():
    # "stp"/"std"/"codegen" are well-formed; extra phase keys are malformed
    # (non-dict) the way a corrupted or hand-edited state file might produce.
    # Every function that walks *all* phase entries guards with isinstance()
    # and must simply skip these rather than raise.
    phases = {
        "stp": {"status": "completed"},
        "std": {"status": "completed"},  # no timestamps at all
        "codegen": {"status": "completed", "usage": "not-a-dict"},
        "stp_review": [1, 2, 3],
        "extra_junk": None,
    }
    states = [_state("T-1", phases)]

    assert m.is_completed_run(phases) is True
    assert m.cycle_seconds(phases, _ts_fn) is None  # no timestamps anywhere
    durs = m.phase_duration_map(states, _ts_fn)
    assert "std" not in durs  # missing timestamps -> silently skipped, not crashed

    cost = m.cost_summary(states)
    assert cost["n"] == 1  # doesn't crash on the malformed usage/extra entries

    assert m.cost_anomalies(states) == []  # no numeric costs anywhere -> nothing to compare
    mb = m.model_breakdown(states)
    assert mb["unknown"]["n"] == 3  # stp, std, codegen all model-less; malformed entries skipped


def test_edge_case_non_dict_truthy_phase_value_does_not_crash_is_completed_run():
    # regression: a truthy non-dict phase value (corrupted/hand-edited state
    # file) must yield False, not AttributeError

    phases = {"stp": "corrupted-value", "std": {"status": "completed"},
              "codegen": {"status": "completed"}}
    assert m.is_completed_run(phases) is False


def test_edge_case_empty_states_list_across_all_aggregates():
    assert m.cost_summary([]) == {"unavailable_reason": "no phases have run yet", "n": 0}
    assert m.automation_summary([], {}) == {"unavailable_reason": "no completed runs", "n": 0}
    assert m.cost_anomalies([]) == []
    assert m.model_breakdown([]) == {}
    lat = m.review_latency([], {}, _ts_fn)
    assert "unavailable_reason" in lat
    bn = m.bottlenecks([], _ts_fn)
    assert "unavailable_reason" in bn
    fp = m.first_pass_summary([])
    assert all("unavailable_reason" in fp[k] for k in ("stp", "std", "code", "full_run"))


# ---------------------------------------------------------------------------
# per_approved_artifact, rework, slow_phases (command-center gap round)
# ---------------------------------------------------------------------------
def test_cost_per_approved_artifact_counts_only_passing_reviews():
    # T-1: STP approved-with-findings (passes), STD needs revision (fails)
    # T-2: STP strictly approved (passes), no STD
    # -> 2 approved artifacts; numerator = stp+std family costs only
    states = [
        _state("T-1", {
            "stp": {"status": "completed", "usage": {"cost_usd": 2.0}},
            "stp_review": {"status": "completed", "verdict": "APPROVED_WITH_FINDINGS"},
            "std": {"status": "completed", "usage": {"cost_usd": 4.0}},
            "std_review": {"status": "completed", "verdict": "NEEDS_REVISION"},
            "codegen": {"status": "completed", "usage": {"cost_usd": 100.0}},
        }),
        _state("T-2", {
            "stp": {"status": "completed", "usage": {"cost_usd": 1.0}},
            "stp_review": {"status": "completed", "verdict": "APPROVED"},
        }),
    ]
    cost = m.cost_summary(states)
    assert cost["approved_artifacts"] == 2
    # stp family cost 3.0 + std family cost 4.0, codegen excluded
    assert cost["per_approved_artifact"] == pytest.approx(3.5)


def test_cost_per_approved_artifact_none_when_nothing_approved():
    states = [_state("T-1", {
        "stp": {"status": "completed", "usage": {"cost_usd": 2.0}},
        "stp_review": {"status": "completed", "verdict": "NEEDS_REVISION"},
    })]
    cost = m.cost_summary(states)
    assert cost["approved_artifacts"] == 0
    assert cost["per_approved_artifact"] is None


def test_rework_counts_refine_or_rerun_but_not_findings_verdicts():
    states = [
        # rework: refine ran
        _state("T-1", {"stp": {"status": "completed"},
                       "stp_review": {"status": "completed", "verdict": "APPROVED"},
                       "stp_refine": {"status": "completed"}}),
        # rework: phase re-run (history)
        _state("T-2", {"stp": {"status": "completed", "history": [{"status": "failed"}]},
                       "stp_review": {"status": "completed", "verdict": "APPROVED"}}),
        # NOT rework: findings verdict but no redo work
        _state("T-3", {"stp": {"status": "completed"},
                       "stp_review": {"status": "completed", "verdict": "APPROVED_WITH_FINDINGS"}}),
    ]
    fp = m.first_pass_summary(states)
    assert fp["rework"]["stp"] == {"rate": pytest.approx(2 / 3, abs=1e-3), "n": 3, "hits": 2}
    # first-pass unchanged by the rework addition: only T-3 misses on verdict,
    # T-1/T-2 miss on refine/history
    assert fp["stp"]["hits"] == 0


def test_slow_phases_flags_only_above_p90_with_min_n_baseline():
    def ph(start_min, end_min):
        return {"status": "completed",
                "started_ts": f"2026-01-01T00:{start_min:02d}:00+00:00",
                "finished_ts": f"2026-01-01T00:{end_min:02d}:00+00:00"}
    # stp durations: 10, 10, 10, 50 min -> p90 = 38 min (interpolated), only T-4 above
    states = [
        _state("T-1", {"stp": ph(0, 10)}),
        _state("T-2", {"stp": ph(0, 10)}),
        _state("T-3", {"stp": ph(0, 10)}),
        _state("T-4", {"stp": ph(0, 50)}),
        # std family has only 2 measurements -> below MIN_N, never flagged
        _state("T-5", {"std": ph(0, 1)}),
        _state("T-6", {"std": ph(0, 59)}),
    ]
    findings = m.slow_phases(states, _ts_fn)
    assert [f["jira_id"] for f in findings] == ["T-4"]
    f = findings[0]
    assert f["family"] == "stp" and f["n"] == 4
    assert f["seconds"] == 3000.0 and f["seconds"] > f["p90_seconds"]


def test_slow_phases_empty_when_no_measurable_durations():
    assert m.slow_phases([], _ts_fn) == []
    assert m.slow_phases([_state("T-1", {"stp": {"status": "completed"}})], _ts_fn) == []
