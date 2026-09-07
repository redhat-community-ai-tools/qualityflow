"""Laptop -> team dashboard: `pipeline_runner.py push` / `run --push`.

Nothing moved a laptop run's artifacts onto the cluster dashboard before this:
no upload client anywhere in the repo, so every top tile stayed empty however
much the team used QF. The client tars outputs/<ticket> in the type-first
layout POST /api/outputs/{id} accepts and ships it with the team key.

  * build_archive — layout contract, .previous/ and unknown subdirs excluded.
  * push_outputs — request shape, never raises, honest return value.
  * round trip — the archive lands in the dashboard's OUTPUTS tree exactly
    where the read paths look (artifacts JIRA-first, state type-first).

Run: uv run --python 3.11 --with pytest --with-requirements requirements.txt \
python -m pytest tests/test_pipeline_runner_push.py -q
"""
import io
import os
import sys
import tarfile
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", str(ROOT / "outputs"))
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402
import ui  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(ui.app)
KEY = "pushtestkey"
TICKET = "PROJ-7"


@pytest.fixture
def local(tmp_path, monkeypatch):
    """A laptop outputs/ tree for one ticket, in the canonical JIRA-first layout."""
    out = tmp_path / "laptop"
    t = out / TICKET
    (t / "stp").mkdir(parents=True)
    (t / "stp" / f"{TICKET}_test_plan.md").write_text("# plan")
    (t / "stp" / ".previous").mkdir()
    (t / "stp" / ".previous" / f"{TICKET}_test_plan.md").write_text("old")
    (t / "std" / "python-tests").mkdir(parents=True)
    (t / "std" / f"{TICKET}_test_description.yaml").write_text("scenarios: []")
    (t / "std" / "python-tests" / "test_x_stubs.py").write_text("__test__ = False")
    (t / "state").mkdir()
    (t / "state" / "pipeline_state.yaml").write_text("phases: {}")
    (t / "rust-tests").mkdir()  # not on the dashboard's allowlist
    (t / "rust-tests" / "x.rs").write_text("")
    monkeypatch.setattr(pipeline_runner, "_outputs_dir", lambda: out)
    return out


def _names(body: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
        return sorted(m.name for m in tar.getmembers())


def test_archive_is_type_first_and_skips_previous_and_unknown_dirs(local):
    body, n = pipeline_runner.build_archive(TICKET)
    assert n == 4
    assert _names(body) == [
        f"state/{TICKET}/pipeline_state.yaml",
        f"std/{TICKET}/{TICKET}_test_description.yaml",
        f"std/{TICKET}/python-tests/test_x_stubs.py",
        f"stp/{TICKET}/{TICKET}_test_plan.md",
    ]


def test_archive_of_a_missing_ticket_is_empty(local):
    body, n = pipeline_runner.build_archive("PROJ-404")
    assert n == 0 and _names(body) == []


@pytest.fixture
def capture_post(monkeypatch):
    calls = []

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def test_push_posts_the_archive_with_the_team_key(local, capture_post, capsys):
    assert pipeline_runner.push_outputs(TICKET, "https://qf.example.com/", "k3y") is True
    req = capture_post[0]
    assert req.full_url == f"https://qf.example.com/api/outputs/{TICKET}"
    assert req.get_method() == "POST"
    assert req.get_header("X-api-key") == "k3y"
    assert req.get_header("Content-type") == "application/gzip"
    assert len(_names(req.data)) == 4
    assert "pushed 4 file(s)" in capsys.readouterr().out


@pytest.mark.parametrize("url,key,needle", [
    ("", "k", "no dashboard URL"),
    ("https://qf.example.com", "", "QUALITYFLOW_API_KEY not set"),
])
def test_push_without_url_or_key_is_a_warning_not_a_request(local, capture_post, capsys, url, key, needle):
    assert pipeline_runner.push_outputs(TICKET, url, key) is False
    assert capture_post == []
    assert needle in capsys.readouterr().err


def test_push_of_an_empty_ticket_sends_nothing(local, capture_post, capsys):
    assert pipeline_runner.push_outputs("PROJ-404", "https://qf.example.com", "k") is False
    assert capture_post == []
    assert "nothing to push" in capsys.readouterr().err


def test_push_reports_a_rejection_instead_of_raising(local, monkeypatch, capsys):
    def reject(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "nope", {}, io.BytesIO(b'{"detail":"bad key"}'))

    monkeypatch.setattr("urllib.request.urlopen", reject)
    assert pipeline_runner.push_outputs(TICKET, "https://qf.example.com", "k") is False
    assert "HTTP 401" in capsys.readouterr().err


def test_push_subcommand_exit_code_reflects_the_push(local, monkeypatch):
    monkeypatch.setenv("QUALITYFLOW_API_KEY", "k")
    monkeypatch.setattr(pipeline_runner, "push_outputs", lambda *a: True)
    with pytest.raises(SystemExit) as ok:
        pipeline_runner.main(["push", TICKET, "--url", "https://qf.example.com"])
    assert ok.value.code == 0
    monkeypatch.setattr(pipeline_runner, "push_outputs", lambda *a: False)
    with pytest.raises(SystemExit) as bad:
        pipeline_runner.main(["push", TICKET, "--url", "https://qf.example.com"])
    assert bad.value.code == 1


def test_run_pushes_after_the_phase_when_asked(local, monkeypatch):
    """`run --push URL` ships after persist_usage; without --push (and without
    QF_DASHBOARD_URL) it stays a local run."""
    monkeypatch.setenv("QUALITYFLOW_API_KEY", "k")
    monkeypatch.delenv("QF_DASHBOARD_URL", raising=False)
    monkeypatch.setattr(pipeline_runner, "run_phase", lambda m, j, p: {"usage": {}, "verdict": "APPROVED"})
    monkeypatch.setattr(pipeline_runner, "persist_usage", lambda *a: None)
    pushed = []
    monkeypatch.setattr(pipeline_runner, "push_outputs", lambda j, u, k: pushed.append((j, u, k)) or True)
    pipeline_runner.main(["run", TICKET, "stp"])
    assert pushed == []
    pipeline_runner.main(["run", TICKET, "stp", "--push", "https://qf.example.com"])
    assert pushed == [(TICKET, "https://qf.example.com", "k")]


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    out = tmp_path / "dashboard-outputs"
    out.mkdir()
    monkeypatch.setattr(ui, "OUTPUTS", out)
    monkeypatch.setattr(ui, "_API_KEY", KEY)
    monkeypatch.setattr(ui, "_rate_limits", {})
    monkeypatch.setattr(ui, "_RATE_LIMIT_MAX", 10_000)
    monkeypatch.setattr(ui, "_metrics_cache", {})
    monkeypatch.setattr(ui, "_jira_ids_cache", (0.0, []))
    monkeypatch.setattr(ui, "_slack_pipeline_event", lambda *a, **k: None)
    return out


def test_round_trip_lands_where_the_dashboard_reads(local, dashboard):
    """The layout contract, end to end through the real upload route: artifacts
    canonicalize to outputs/{id}/{sub}/..., state stays type-first and is
    what _state_dir resolves, and the ticket shows up in the dashboard's list."""
    body, _ = pipeline_runner.build_archive(TICKET)
    r = client.post(f"/api/outputs/{TICKET}", content=body,
                    headers={"X-API-Key": KEY, "Content-Type": "application/gzip"})
    assert r.status_code == 200, r.text
    assert (dashboard / TICKET / "stp" / f"{TICKET}_test_plan.md").read_text() == "# plan"
    assert (dashboard / TICKET / "std" / "python-tests" / "test_x_stubs.py").exists()
    assert ui._state_dir(TICKET) == dashboard / "state" / TICKET
    assert (ui._state_dir(TICKET) / "pipeline_state.yaml").read_text() == "phases: {}"
    assert not (dashboard / TICKET / "stp" / ".previous").exists()
    assert TICKET in ui._scan_jira_ids()
