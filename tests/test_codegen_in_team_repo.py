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
import subprocess
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
    write(repo, "tests/api/test_qf_login.py", "def test_new(admin_client, namespace):\n    assert admin_client\n")
    res = rc.verify(repo, ["tests/api/test_qf_login.py"])
    assert res["verification"] == "passed", res
    assert "no test was run" in res["reason"]

    # An unregistered marker under --strict-markers fails, as it would in the team's CI.
    write(repo, "tests/api/test_qf_bad.py", "import pytest\n\n@pytest.mark.qf_test_id('TS-1')\n"
          "def test_bad(admin_client):\n    assert admin_client\n")
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
    write(repo, "tests/api/test_qf_ghost.py", "def test_new(admin_client, no_such_fixture):\n    assert admin_client\n")
    res = rc.verify(repo, ["tests/api/test_qf_ghost.py"])
    assert res["verification"] == "failed" and "fixtures not found: no_such_fixture" in res["reason"], res
    # The repo's CI never collects a file its discovery skips, even though
    # naming it on the command line would.
    write(repo, "tests/api/qf_login.py", "def test_new(admin_client):\n    pass\n")
    res = rc.verify(repo, ["tests/api/qf_login.py"])
    assert res["verification"] == "failed" and "test_qf_*.py" in res["reason"], res


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
    write(repo, "tests/api/test_qf_login.py", "def test_new(admin_client, namespace):\n    assert admin_client\n")
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


def test_python_cmd_prefers_the_checkouts_venv_over_uv(tmp_path):
    assert rc.python_cmd(tmp_path)[1:] == ["-m", "pytest"]
    (tmp_path / "uv.lock").write_text("")
    assert rc.python_cmd(tmp_path) == ["uv", "run", "pytest"]
    write(tmp_path, ".venv/bin/python", "")
    assert rc.python_cmd(tmp_path) == [str(tmp_path / ".venv/bin/python"), "-m", "pytest"]


HOLLOW = """import pytest

from tests.suite.constant import HEALTH

_IDS = {"TS-1": "x"}


def _contract(tid):
    assert tid in _IDS
    assert HEALTH == "/health"


def test_only_constants():
    _contract("TS-1")


class TestIds:
    def test_only_its_own_id(self):
        assert "TS-1".startswith("TS-")

    @pytest.mark.parametrize("tid", ["TS-1", "TS-2"])
    def test_parametrize_is_not_a_fixture(self, tid):
        assert tid


def test_placeholder(client):
    pytest.fail("not implemented")


def test_asserts_nothing(client):
    assert True


def test_skipped_placeholder(client):
    client.get("/health")
    pytest.skip("needs a cluster")
"""

REAL = """import pytest

from product.api import create
from tests.suite import helpers


def _make(name):
    return create(name)


def test_through_a_helper():
    assert _make("a").name == "a"


def test_fixture(client):
    assert client.get("/health").status_code == 200


def test_conditional_skip_is_fine(client):
    if not client.ready:
        pytest.skip("no cluster")
    assert client.get("/health").status_code == 200


@pytest.mark.usefixtures("cluster")
class TestWithClassFixtures:
    def test_suite_helper(self):
        assert helpers.wait_ready() is None


@pytest.mark.parametrize("ns", [{"name": "x"}], indirect=True)
def test_indirect_parametrize_is_a_fixture(ns):
    assert ns
"""


def test_hollow_tests_are_named_with_the_reason(tmp_path):
    write(tmp_path, "tests/test_qf_hollow.py", HOLLOW)
    found = rc.hollow_tests(tmp_path / "tests/test_qf_hollow.py", "tests/test_qf_hollow.py")
    assert [h.split("::")[1].split(" ")[0] for h in found] == [
        "test_only_constants", "test_placeholder", "test_asserts_nothing", "test_skipped_placeholder",
        "test_only_its_own_id", "test_parametrize_is_not_a_fixture"]
    assert "test_placeholder (fails unconditionally)" in " ".join(found)
    assert "test_skipped_placeholder (skips unconditionally)" in " ".join(found)
    write(tmp_path, "tests/test_qf_real.py", REAL)
    assert rc.hollow_tests(tmp_path / "tests/test_qf_real.py", "tests/test_qf_real.py") == []


def test_verify_fails_hollow_tests_before_running_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "python_cmd", lambda r: ["qf-no-such-tool"])
    write(tmp_path, "tests/test_qf_hollow.py", HOLLOW)
    res = rc.verify(tmp_path, ["tests/test_qf_hollow.py"])
    assert res["verification"] == "failed" and res["reason"].startswith("6 test(s) never touch the product")


PARAM_CONFTEST = """import pytest


@pytest.fixture
def ns(request, client):
    return request.param["name"]


@pytest.fixture
def server(ns):
    return ns


@pytest.fixture(params=["a"])
def own_params(request):
    return request.param


@pytest.fixture
def client():
    return 1
"""


def test_vocabulary_marks_fixtures_that_need_an_indirect_parametrize(tmp_path):
    """--setup-plan never runs a fixture body, so a fixture that reads
    request.param resolves fine and errors on every real run unless the test
    parametrizes it (42 of 119 luna tests on opendatahub-tests)."""
    write(tmp_path, "conftest.py", PARAM_CONFTEST)
    fx = {f["name"]: f for f in rc.python_context(tmp_path, tmp_path / "tests")["fixtures"]}
    assert fx["ns"]["needs_indirect_param"] == ["ns"]
    assert fx["server"]["needs_indirect_param"] == ["ns"]  # through the fixture it depends on
    assert "needs_indirect_param" not in fx["own_params"] and "needs_indirect_param" not in fx["client"]


def test_verify_fails_tests_that_would_error_at_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "python_cmd", lambda r: ["qf-no-such-tool"])
    write(tmp_path, "conftest.py", PARAM_CONFTEST)
    write(tmp_path, "tests/test_qf_server.py", """import pytest


def test_bare(server):
    assert server


@pytest.mark.parametrize("ns", [{"name": "x"}], indirect=True)
def test_parametrized(server):
    assert server


@pytest.mark.parametrize("ns", [{"name": "x"}], indirect=True)
class TestOnTheClass:
    def test_inherits(self, server):
        assert server
""")
    res = rc.verify(tmp_path, ["tests/test_qf_server.py"])
    assert res["verification"] == "failed" and res["reason"].startswith("1 test(s) would error at setup"), res
    assert res["output"] == "tests/test_qf_server.py::test_bare (parametrize ns with indirect=True, as the sibling tests do)"


def test_verify_refuses_the_teams_own_files(repo):
    """A run listed the team's existing tests as its output, unchanged."""
    res = rc.verify(repo, ["tests/api/test_login.py"])
    assert res["verification"] == "failed" and res["reason"].startswith("not QualityFlow files"), res
    assert res["reason"].endswith("tests/api/test_login.py")
    # A conftest.py the run added is ours; one the repo tracks is not.
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(git + ["add", "tests/api/conftest.py"], cwd=repo, check=True)
    subprocess.run(git + ["commit", "-qm", "suite"], cwd=repo, check=True)
    write(repo, "tests/new/conftest.py", "")
    subprocess.run(git + ["add", "tests/new/conftest.py"], cwd=repo, check=True)  # staged is still new
    res = rc.verify(repo, ["tests/api/conftest.py", "tests/new/conftest.py"])
    assert res["reason"].endswith(": tests/api/conftest.py"), res


@pytest.mark.skipif(not shutil.which("go"), reason="go toolchain not installed")
def test_verify_compiles_go(tmp_path):
    write(tmp_path, "go.mod", "module example.com/x\n\ngo 1.21\n")
    write(tmp_path, "pkg/a/a.go", "package a\n\nfunc One() int { return 1 }\n")
    write(tmp_path, "pkg/a/qf_one_test.go", 'package a\n\nimport "testing"\n\n'
          'func TestOne(t *testing.T) { if One() != 1 { t.Fatal("x") } }\n')
    assert rc.verify(tmp_path, ["pkg/a/qf_one_test.go"])["verification"] == "passed"
    write(tmp_path, "pkg/a/qf_two_test.go", 'package a\n\nimport "testing"\n\nfunc TestTwo(t *testing.T) { Two() }\n')
    assert rc.verify(tmp_path, ["pkg/a/qf_two_test.go"])["verification"] == "failed"


def test_verify_fails_files_missing_from_the_checkout(tmp_path):
    """A run wrote its Go test to a wrong path; `go test -c` built the package
    without it and the check said "compiled"."""
    write(tmp_path, "go.mod", "module example.com/x\n\ngo 1.21\n")
    write(tmp_path, "pkg/a/a.go", "package a\n")
    for f in ("pkg/a/qf_one_test.go", "tests/test_qf_one.py"):
        res = rc.verify(tmp_path, [f])
        assert res["verification"] == "failed" and res["reason"].endswith(": " + f), res


@pytest.mark.skipif(not shutil.which("go"), reason="go toolchain not installed")
def test_verify_go_never_runs_testmain(tmp_path):
    """A suite's TestMain that starts envtest or a database must not run: compile only."""
    write(tmp_path, "go.mod", "module example.com/x\n\ngo 1.21\n")
    write(tmp_path, "pkg/a/a.go", "package a\n\nfunc One() int { return 1 }\n")
    write(tmp_path, "pkg/a/main_test.go", 'package a\n\nimport (\n\t"os"\n\t"testing"\n)\n\n'
          'func TestMain(m *testing.M) { os.Exit(3) }\n')
    write(tmp_path, "pkg/a/qf_one_test.go", 'package a\n\nimport "testing"\n\n'
          'func TestOne(t *testing.T) { if One() != 1 { t.Fatal("x") } }\n')
    res = rc.verify(tmp_path, ["pkg/a/qf_one_test.go"])
    assert res["verification"] == "passed", res
    assert not list(tmp_path.rglob("*.test"))


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


def test_product_search_lists_the_interface_files_per_scenario(tmp_path):
    prod, suite = tmp_path / "product", tmp_path / "suite"
    write(prod, "api/tenant_types.go", "package v1\n\nconst Kind = \"Tenant\"\n\nconst DefaultName = \"default-tenant\"\n")
    write(prod, "ctrl/gateway.go", "// gateway not found: activation blocked\nfunc reconcileGateway() {}\n")
    write(prod, "README.md", "Tenant default-tenant gateway activation\n")
    subprocess.run(["git", "init", "-q", str(prod)], check=True)
    subprocess.run(["git", "-C", str(prod), "add", "."], check=True)
    write(suite, "tests/tenancy/utils.py", "def aitenant_from_spec(name='default-tenant'):\n    return name\n")
    std = {"source_constants": [
               {"name": "TenantKind", "value": "Tenant", "source_file": "api/tenant_types.go", "line": 2},
               {"name": "Gone", "value": "no-such-value", "source_file": "api/old.go", "line": 9}],
           "scenarios": [{"test_id": "TS-1", "test_objective": {"title": "Verify missing gateway blocks activation"},
                          "test_data": {"parameters": {
                              "name": {"value": "default-tenant", "source_constant_ref": "TenantKind"},
                              "contract": "<TBD: released API>"}}}]}
    out = rc.product_refs(std, [prod.resolve(), suite.resolve()])
    assert out["constants"][0]["now"] == "api/tenant_types.go:3"
    assert out["constants"][1]["now"] == "not found in product"
    sc = out["scenarios"]["TS-1"]
    assert "verify" not in sc["terms"] and "gateway" in sc["terms"] and not any("TBD" in t for t in sc["terms"])
    assert [f.split(":")[0] for f in sc["product"]] == ["api/tenant_types.go", "ctrl/gateway.go"]  # docs skipped
    assert sc["suite"] == ["tests/tenancy/utils.py:1 (Tenant, default-tenant)"]  # no git: plain grep


def test_verify_fails_product_refs_the_checkout_does_not_have(tmp_path, monkeypatch):
    """A plan built from an open PR cites rules the checked-out commit lacks
    (13 of 15 tests for one ticket expected an unmerged alert)."""
    monkeypatch.setattr(rc, "python_cmd", lambda r: ["qf-no-such-tool"])
    product = tmp_path / "product"
    write(product, "deploy/rules.yaml", "groups: []\n")
    write(tmp_path, "tests/test_qf_ok.py", "def test_x(client):\n    assert client.get('/') == 200\n")
    refs = ["deploy/rules.yaml:1", "deploy/rules.yaml:40", "deploy/new-alert.yaml:3"]
    res = rc.verify(tmp_path, ["tests/test_qf_ok.py"], refs=refs, roots=[product])
    assert res["verification"] == "failed" and res["output"] == "deploy/rules.yaml:40\ndeploy/new-alert.yaml:3"
    assert rc.missing_refs(refs[:1], [product]) == []


IMPORTS_TEAM_TESTS = """import pytest
from starlette.testclient import TestClient

from tests.gemini.test_chat import TestGeminiChat, chat_payload
from .test_e2e import test_round_trip
from tests.gemini.utils import TestData


class TestQfGemini(TestGeminiChat):
    def test_new_case(self, client):
        assert client.chat(chat_payload()).ok
"""


def test_verify_fails_a_file_that_imports_the_teams_tests(tmp_path, monkeypatch):
    """pytest collects imported Test classes and test functions, so the team's
    tests ran a second time under the generated file (RHAISTRAT-1245: 9 classes,
    23 tests). Helpers from a test module, and Test* names from other modules, pass."""
    monkeypatch.setattr(rc, "python_cmd", lambda r: ["qf-no-such-tool"])
    write(tmp_path, "tests/gemini/test_qf_gemini.py", IMPORTS_TEAM_TESTS)
    found = rc.imported_tests(tmp_path / "tests/gemini/test_qf_gemini.py", "f.py")
    assert found == ["f.py: TestGeminiChat from tests.gemini.test_chat", "f.py: test_round_trip from .test_e2e"]
    res = rc.verify(tmp_path, ["tests/gemini/test_qf_gemini.py"])
    assert res["verification"] == "failed" and "imported from the team's test modules" in res["reason"]
