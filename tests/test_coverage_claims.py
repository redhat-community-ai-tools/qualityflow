"""validate_std.py fails an EXISTING/PARTIAL_COVERAGE claim that names a test the checkouts do not have."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_std", ROOT / "skills/std-reviewer/validate_std.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)


def _report(tmp_path, covered_by):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True, exist_ok=True)
    (repo / "pkg" / "a_test.go").write_text("package pkg\n\nfunc TestReal(t *testing.T) {}\n")
    (repo / "pkg" / "b_test.go").write_text("package pkg\n\nfunc TestElsewhere(t *testing.T) {}\n")
    rep = vs.Report()
    vs.check_covered_by([{"test_id": "TS-1", "coverage_status": "EXISTING_COVERAGE",
                          "covered_by": covered_by}], [str(repo)], rep)
    return rep


def test_claims_must_name_a_test_that_exists(tmp_path):
    ok = _report(tmp_path, [{"test_file": "pkg/a_test.go", "test_function": "TestReal"},
                            {"test_file": "pkg", "test_function": "TestElsewhere"}])  # a package dir
    assert ok.checks["coverage.claims_exist"] == "pass", ok.errors

    bad = _report(tmp_path, [{"test_file": "pkg/a_test.go", "test_function": "TestMissing"},
                             {"test_file": "pkg/a_test.go", "test_function": "TestElsewhere"},
                             {"test_file": "pkg/gone_test.go", "test_function": "TestReal"}])
    assert bad.checks["coverage.claims_exist"] == "fail"
    msg = bad.errors[0]
    assert "defines no TestMissing" in msg and "(it is in pkg/b_test.go)" in msg and "gone_test.go does not exist" in msg

    other = _report(tmp_path, [{"test_file": "controllers/x_test.go", "test_function": "TestX"}])
    assert other.checks["coverage.claims_exist"] == "warn"  # another repo: cannot verify, not a failure
