"""Code generation works against the team's real tests repo.

skills/test-generator/repo_context.py hands the generator the suite's real
vocabulary (fixtures from the conftest chain and its pytest_plugins, helpers
sibling tests import, registered markers) and verifies the generated files
inside the checkout. The dashboard keeps the CLI's `verification` through its
own completion write, and labels code generation experimental until it passes.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import ui  # noqa: E402 — env must be set before import

spec = importlib.util.spec_from_file_location("repo_context", ROOT / "skills/test-generator/repo_context.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


@pytest.fixture
def repo(tmp_path):
    write(tmp_path, "pytest.ini", "[pytest]\naddopts = --strict-markers\nmarkers =\n    smoke: quick checks\n")
    write(tmp_path, "conftest.py", 'import pytest\npytest_plugins = ["utilities.fixtures"]\n\n'
          '@pytest.fixture(scope="session")\ndef admin_client():\n    return "root"\n')
    write(tmp_path, "utilities/__init__.py", "")
    write(tmp_path, "utilities/fixtures.py", 'import pytest\n\n@pytest.fixture(name="namespace")\n'
          'def _namespace():\n    return "ns"\n')
    write(tmp_path, "utilities/users.py", "def make_user():\n    return 1\n")
    write(tmp_path, "tests/__init__.py", "")
    write(tmp_path, "tests/api/__init__.py", "")
    write(tmp_path, "tests/api/conftest.py", 'import pytest\n\ndef pytest_configure(config):\n'
          '    config.addinivalue_line("markers", "slow: long-running")\n\n'
          '@pytest.fixture\ndef admin_client():\n    return "api"\n')
    write(tmp_path, "tests/api/test_login.py", "import os\nimport pytest\nfrom utilities.users import make_user\n\n"
          "def test_login(admin_client):\n    assert make_user()\n")
    write(tmp_path, "tests/api/test_qf_old.py", "def test_old():\n    pass\n")
    return tmp_path


def test_context_is_the_suites_real_vocabulary(repo):
    ctx = rc.python_context(repo.resolve(), (repo / "tests/api/new_feature").resolve())
    fx = {f["name"]: f for f in ctx["fixtures"]}
    # The nearest conftest wins, as in pytest; pytest_plugins modules count, by their fixture name.
    assert fx["admin_client"] == {"name": "admin_client", "file": "tests/api/conftest.py", "scope": "function"}
    assert fx["namespace"]["file"] == "utilities/fixtures.py"
    assert ctx["helpers"] == [{"module": "utilities.users", "names": ["make_user"]}]  # not os, not pytest
    assert {"smoke", "slow"} <= set(ctx["markers"]["registered"]) and ctx["markers"]["strict"]
    assert "qf_test_id" not in ctx["markers"]["registered"]
    # Siblings come from the nearest folder with tests, never QualityFlow's own.
    assert ctx["siblings"] == ["tests/api/test_login.py"]
    assert ctx["existing_conftest"] is None


def test_verify_collects_inside_the_checkout(repo, monkeypatch):
    monkeypatch.setattr(rc, "python_cmd", lambda r: [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"])
    write(repo, "tests/api/test_qf_login.py", "def test_new(admin_client, namespace):\n    pass\n")
    res = rc.verify(repo, ["tests/api/test_qf_login.py"])
    assert res["verification"] == "passed", res
    assert "no test was run" in res["reason"]

    # An unregistered marker under --strict-markers fails, as it would in the team's CI.
    write(repo, "tests/api/test_qf_bad.py", "import pytest\n\n@pytest.mark.qf_test_id('TS-1')\n"
          "def test_bad():\n    pass\n")
    res = rc.verify(repo, ["tests/api/test_qf_bad.py"])
    assert res["verification"] == "failed", res

    monkeypatch.setattr(rc, "python_cmd", lambda r: ["qf-no-such-tool"])
    res = rc.verify(repo, ["tests/api/test_qf_login.py"])
    assert (res["verification"], res["reason"]) == ("skipped", "qf-no-such-tool is not installed")


def test_verify_resolves_fixtures_and_refuses_uncollected_names(repo, monkeypatch):
    """--setup-plan, not --collect-only: an invented fixture collects fine but
    can never run. Verified on a real suite (a test copied out of the folder
    whose conftest defines its fixtures failed, in place it passed)."""
    monkeypatch.setattr(rc, "python_cmd", lambda r: [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"])
    write(repo, "tests/api/test_qf_ghost.py", "def test_new(admin_client, no_such_fixture):\n    pass\n")
    res = rc.verify(repo, ["tests/api/test_qf_ghost.py"])
    assert res["verification"] == "failed" and "fixtures not found: no_such_fixture" in res["reason"], res
    # The repo's CI never collects a file its discovery skips, even though
    # naming it on the command line would.
    write(repo, "tests/api/qf_login.py", "def test_new(admin_client):\n    pass\n")
    res = rc.verify(repo, ["tests/api/qf_login.py"])
    assert res["verification"] == "failed" and "test_*.py" in res["reason"], res


def test_verify_applies_the_repos_offline_ci_settings(repo, tmp_path_factory, monkeypatch):
    """Some suites' root conftest contacts a cluster at import; their CI sets an
    env var (and a config-file argument) to collect offline. repositories.yaml's
    verify: block carries those, so the check is the repo's own."""
    monkeypatch.setattr(rc, "python_cmd", lambda r: [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"])
    write(repo, "conftest.py", 'import os\nimport pytest\n'
          'if not os.environ.get("QF_FAKE_ARCH"):\n    raise RuntimeError("needs a cluster")\n\n'
          '@pytest.fixture\ndef admin_client():\n    return "root"\n'
          '@pytest.fixture\ndef namespace():\n    return "ns"\n'
          'def pytest_addoption(parser):\n    parser.addoption("--qf-cfg")\n')
    write(repo, "tests/api/test_qf_login.py", "def test_new(admin_client, namespace):\n    pass\n")
    res = rc.verify(repo, ["tests/api/test_qf_login.py"])
    assert res["verification"] == "failed" and "verify: {env, args}" in res["reason"], res
    cfg = tmp_path_factory.mktemp("cfg") / "repositories.yaml"
    cfg.write_text("primary_repo:\n  name: t\n  org: o\n  verify:\n"
                   "    env: {QF_FAKE_ARCH: amd64}\n    args: [--qf-cfg=x]\n")
    env, args = rc.repo_settings(str(cfg), "primary_repo")
    assert (env, args) == ({"QF_FAKE_ARCH": "amd64"}, ["--qf-cfg=x"])
    res = rc.verify(repo, ["tests/api/test_qf_login.py"], env, args)
    assert res["verification"] == "passed", res
    assert rc.repo_settings(None, "primary_repo") == ({}, [])


def test_python_cmd_uses_uv_when_the_repo_is_uv_managed(tmp_path):
    assert rc.python_cmd(tmp_path)[1:] == ["-m", "pytest"]
    (tmp_path / "uv.lock").write_text("")
    assert rc.python_cmd(tmp_path) == ["uv", "run", "pytest"]


@pytest.mark.skipif(not shutil.which("go"), reason="go toolchain not installed")
def test_verify_compiles_go(tmp_path):
    write(tmp_path, "go.mod", "module example.com/x\n\ngo 1.21\n")
    write(tmp_path, "pkg/a/a.go", "package a\n\nfunc One() int { return 1 }\n")
    write(tmp_path, "pkg/a/qf_one_test.go", 'package a\n\nimport "testing"\n\n'
          'func TestOne(t *testing.T) { if One() != 1 { t.Fatal("x") } }\n')
    assert rc.verify(tmp_path, ["pkg/a/qf_one_test.go"])["verification"] == "passed"
    write(tmp_path, "pkg/a/qf_two_test.go", 'package a\n\nimport "testing"\n\nfunc TestTwo(t *testing.T) { Two() }\n')
    assert rc.verify(tmp_path, ["pkg/a/qf_two_test.go"])["verification"] == "failed"


def test_dashboard_completion_keeps_the_clis_verification():
    """The dashboard's terminal write builds a fresh dict; it used to drop what
    `state.py complete-phase --extra` wrote in place during the same run."""
    phases = {"codegen": {"status": "in_progress", "started_ts": "s1", "actor": "jane@example.com"}}
    phases["codegen"].update(status="completed", verification="failed", verification_reason="`pytest` exited 2",
                             test_count=4, error=None)
    ui._record_phase_result(phases, "codegen", {"status": "completed", "finished_ts": "f1", "output": "log"})
    ph = phases["codegen"]
    assert (ph["verification"], ph["verification_reason"], ph["test_count"]) == ("failed", "`pytest` exited 2", 4)
    assert ph["output"] == "log" and ph["actor"] == "jane@example.com"

    # A new run's placeholder starts clean; the old result goes to history only.
    ui._record_phase_result(phases, "codegen", {"status": "in_progress", "started_ts": "s2"})
    assert "verification" not in phases["codegen"]
    # A pre-dashboard in_progress entry's fields are not carried into the placeholder either.
    stale = {"codegen": {"status": "in_progress", "verification": "passed"}}
    ui._record_phase_result(stale, "codegen", {"status": "in_progress", "started_ts": "s3"})
    assert "verification" not in stale["codegen"]


def test_dashboard_shows_verification_and_experimental_label():
    html = (ROOT / "ui" / "index.html").read_text()
    for needle in ("function codegenVerificationHtml(phase)", "function codegenExperimentalChip(phases)",
                   "codegenExperimentalChip(phases) + (status === 'completed' ? codegenVerificationHtml(phase)",
                   "escapeHtml('verification: ' + phase.verification)",
                   "nextPhase === 'codegen' && codegenExperimentalChip(phases)"):
        assert needle in html, needle
