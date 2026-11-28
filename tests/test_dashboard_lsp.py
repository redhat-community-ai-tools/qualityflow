"""Dashboard runs get LSP like a laptop run: the pod clones the team repos and
points each <NAME>_REPO_PATH at its checkout, and Codex runs get one
mcp-language-server per checkout (Codex has no LSP tool)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QF_DEV", "1")
os.environ.setdefault("QF_OUTPUTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("QF_CONFIG_DIR", str(ROOT / "config"))
sys.path.insert(0, str(ROOT))
import pipeline_runner  # noqa: E402
import ui  # noqa: E402

REPOS_YAML = """
primary_repo:
  name: tests
  org: acme
  url: https://github.com/acme/tests
  local_path_env: ACME_TESTS_REPO_PATH
  default_branch: main
additional_repos:
  - name: product
    url: https://github.com/acme/product
    local_path_env: ACME_PRODUCT_REPO_PATH
  - name: no-env
    url: https://github.com/acme/no-env
  - name: not-https
    url: git@github.com:acme/ssh.git
    local_path_env: SSH_REPO_PATH
"""


def _config(tmp_path):
    proj = tmp_path / "config" / "projects" / "acme"
    proj.mkdir(parents=True)
    (proj / "repositories.yaml").write_text(REPOS_YAML)
    return tmp_path / "config"


def test_team_repos_are_cloned_and_their_variables_set(tmp_path, monkeypatch):
    import git

    monkeypatch.setattr(ui, "CONFIG", _config(tmp_path))
    monkeypatch.setenv("QF_REPOS_DIR", str(tmp_path / "repos"))
    monkeypatch.setattr(ui, "_OPERATOR_ENV", frozenset({"ACME_PRODUCT_REPO_PATH"}))
    monkeypatch.delenv("ACME_TESTS_REPO_PATH", raising=False)
    cloned = []

    def fake_clone(url, dest, **kw):
        cloned.append((url, kw.get("branch"), kw.get("depth")))
        Path(dest, ".git").mkdir(parents=True)

    monkeypatch.setattr(git.Repo, "clone_from", staticmethod(fake_clone))
    status = ui._sync_team_repos()

    # Only https entries with a local_path_env; an operator-set variable wins.
    assert cloned == [("https://github.com/acme/tests", "main", 1)]
    assert status["repos"]["https://github.com/acme/tests"] == "ok"
    assert status["repos"]["https://github.com/acme/product"] == "operator-set"
    assert os.environ["ACME_TESTS_REPO_PATH"] == str(tmp_path / "repos" / "acme__tests")
    monkeypatch.delenv("ACME_TESTS_REPO_PATH")


def test_team_repos_off_without_repos_dir(monkeypatch):
    monkeypatch.delenv("QF_REPOS_DIR", raising=False)
    assert ui._sync_team_repos()["status"] == "off"


def test_codex_gets_one_read_only_lsp_server_per_checkout(tmp_path, monkeypatch):
    go_repo, py_repo, other = tmp_path / "go", tmp_path / "py", tmp_path / "other"
    for d in (go_repo, py_repo, other):
        d.mkdir()
    (go_repo / "go.mod").write_text("module x\n")
    (py_repo / "pyproject.toml").write_text("")
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    monkeypatch.setenv("KUBE_REPO_PATH", str(go_repo))
    monkeypatch.setenv("ACME_TESTS_REPO_PATH", str(py_repo))
    monkeypatch.setenv("DOCS_REPO_PATH", str(other))      # no language marker
    monkeypatch.setenv("GONE_REPO_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)

    args = " ".join(pipeline_runner._codex_lsp_args())
    assert 'mcp_servers.lsp_kube.args=["--workspace", "%s", "--lsp", "gopls"]' % go_repo in args
    assert ('mcp_servers.lsp_acme_tests.args=["--workspace", "%s", "--lsp", '
            '"pyright-langserver", "--", "--stdio"]' % py_repo) in args
    assert "lsp_docs" not in args and "lsp_gone" not in args
    assert "edit_file" not in args and "rename_symbol" not in args

    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: None)
    assert pipeline_runner._codex_lsp_args() == []


def test_codex_lsp_covers_the_image_languages(tmp_path, monkeypatch):
    markers = {"Cargo.toml": "rust-analyzer", "pom.xml": "jdtls",
               "tsconfig.json": "typescript-language-server", "compile_commands.json": "clangd"}
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    for i, marker in enumerate(markers):
        d = tmp_path / str(i)
        d.mkdir()
        (d / marker).write_text("")
        monkeypatch.setenv(f"R{i}_REPO_PATH", str(d))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    args = " ".join(pipeline_runner._codex_lsp_args())
    for server in markers.values():
        assert f'"--lsp", "{server}"' in args


def test_claude_gets_the_bridge_read_only(tmp_path, monkeypatch):
    import json
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module x\n")
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    monkeypatch.setenv("KUBE_REPO_PATH", str(repo))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    args = pipeline_runner._claude_lsp_args(tmp_path)
    cfg = json.loads(Path(args[0].split("=", 1)[1]).read_text())
    assert cfg["mcpServers"]["lsp_kube"]["args"] == ["--workspace", str(repo), "--lsp", "gopls"]
    assert args[1] == "--disallowedTools=mcp__lsp_kube__edit_file,mcp__lsp_kube__rename_symbol"


def test_bridge_preloads_only_for_typescript_and_fails_calls_in_two_minutes(tmp_path, monkeypatch):
    """A pilot cluster, 2026-10-08: the bridge opened every workspace file, so
    pyright never answered on a large Python tests repo and calls waited out a
    5-minute timeout each. The patched bridge pre-opens only when asked."""
    import json
    for var in [v for v in os.environ if v.endswith("_REPO_PATH")]:
        monkeypatch.delenv(var)
    for name, marker in (("PY", "pyproject.toml"), ("TS", "tsconfig.json")):
        d = tmp_path / name
        d.mkdir()
        (d / marker).write_text("")
        monkeypatch.setenv(f"{name}_REPO_PATH", str(d))
    monkeypatch.setattr(pipeline_runner.shutil, "which", lambda name: "/usr/bin/" + name)
    args = pipeline_runner._codex_lsp_args()
    assert "mcp_servers.lsp_ts.env.MCP_LSP_PRELOAD=\"1\"" in args
    assert not any(a.startswith("mcp_servers.lsp_py.env.MCP_LSP_PRELOAD") for a in args)
    assert "mcp_servers.lsp_py.tool_timeout_sec=120" in args
    # Every bridge is read-only (no edit_file/rename_symbol).
    assert "mcp_servers.lsp_py.env.MCP_LSP_READONLY=\"1\"" in args
    cfg_args = pipeline_runner._claude_lsp_args(tmp_path)
    cfg = json.loads(Path(cfg_args[0].split("=", 1)[1]).read_text())["mcpServers"]
    assert cfg["lsp_ts"]["env"] == {"MCP_LSP_READONLY": "1", "MCP_LSP_PRELOAD": "1"}
    assert cfg["lsp_py"]["env"] == {"MCP_LSP_READONLY": "1"}


def test_lsp_calls_are_counted_from_the_stream():
    import json
    codex = [
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lsp_product",
                                            "status": "completed", "error": None}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lsp_source",
                                            "status": "failed", "error": {"message": "timed out"}}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "mcp-atlassian",
                                            "status": "completed"}},  # not a language server
        {"type": "item.started", "item": {"type": "mcp_tool_call", "server": "lsp_product"}},
    ]
    assert pipeline_runner._lsp_calls("\n".join(map(json.dumps, codex))) == {
        "ok": 1, "failed": 1, "failed_on": {"source": {"timeout": 1}}}
    claude = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "LSP"},
            {"type": "tool_use", "id": "b", "name": "mcp__lsp_kube__references"},
            {"type": "tool_use", "id": "c", "name": "Bash"}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "a"},
            {"type": "tool_result", "tool_use_id": "b", "is_error": True, "content": "unknown symbol"},
            {"type": "tool_result", "tool_use_id": "c", "is_error": True}]}},
    ]
    assert pipeline_runner._lsp_calls("\n".join(map(json.dumps, claude))) == {
        "ok": 1, "failed": 1, "failed_on": {"kube": {"error": 1}}}
    assert pipeline_runner._usage_extra({"lsp": {"ok": 0, "failed": 0}}) == {"lsp": {"ok": 0, "failed": 0}}


def test_lsp_caveat_comes_from_the_counted_calls():
    out = "LSP fallback recorded; refinement skipped."  # the words that misfired
    caveats = ui._detect_caveats
    assert caveats({"phases": {"stp": {"output": out, "lsp": {"ok": 4, "failed": 0}}}}) == []
    assert caveats({"phases": {"stp": {"output": out, "lsp": {"ok": 4, "failed": 1}}}}) \
        == ["1 of 5 LSP calls failed"]
    assert caveats({"phases": {"stp": {"output": "done", "lsp": {"ok": 0, "failed": 2}}}}) \
        == ["No LSP regression analysis"]


def test_a_bridge_timeout_names_the_server_and_the_cause_in_the_caveat():
    """#233: "4 of 21 LSP calls failed" alone sent people to the run log to find
    which repo's analysis was missing."""
    import json
    def call(server, error=None):
        return json.dumps({"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": server, "status": "failed" if error else "completed",
            "error": {"message": error} if error else None}})
    timeout = "tool call failed for `lsp_big_go/hover`: timed out awaiting tools/call after 120s"
    stream = "\n".join([call("lsp_big_go", timeout)] * 3
                       + [call("lsp_wrapper", "no identifier found")] + [call("lsp_wrapper")] * 17)
    lsp = pipeline_runner._lsp_calls(stream)
    assert lsp == {"ok": 17, "failed": 4,
                   "failed_on": {"big_go": {"timeout": 3}, "wrapper": {"error": 1}}}
    assert ui._detect_caveats({"phases": {"stp": {"output": "done", "lsp": lsp}}}) \
        == ["4 of 21 LSP calls failed (3 timeouts on big_go, 1 error on wrapper)"]
    lsp = pipeline_runner._lsp_calls(call("lsp_big_go", timeout))
    assert ui._detect_caveats({"phases": {"stp": {"output": "done", "lsp": lsp}}}) \
        == ["No LSP regression analysis (1 timeout on big_go)"]


def test_a_run_with_bridges_is_steered_off_go_hover():
    assert pipeline_runner.LSP_GUIDANCE in pipeline_runner._codex_prompt("stp-builder", "PROJ-1", "", ["lsp_src"])
    assert pipeline_runner.LSP_GUIDANCE not in pipeline_runner._codex_prompt("stp-builder", "PROJ-1")


def test_review_and_refine_runs_without_lsp_are_not_partial_analysis():
    """Only the plan and test-writing runs get LSP. CNV-79308: a plan with 16 good
    LSP calls showed "partial analysis" after Request changes, whose run said it
    had no LSP (by design)."""
    plan = {"output": "plan written", "lsp": {"ok": 16, "failed": 0}}
    no_lsp = "LSP unavailable for this run; source searches were the fallback."
    state = {"phases": {"stp": plan,
                        "stp_refine": {"output": no_lsp, "lsp": {"ok": 0, "failed": 0}},
                        "stp_review": {"output": no_lsp}}}
    assert ui._detect_caveats(state) == []
    # The plan and test-writing runs still warn.
    assert ui._detect_caveats({"phases": {"stp": {"output": "LSP unavailable, text search used"}}}) \
        == ["No LSP regression analysis"]
    assert ui._detect_caveats({"phases": {"python_codegen": {"output": "x", "lsp": {"ok": 0, "failed": 0}}}}) \
        == ["No LSP regression analysis"]


def test_run_stream_file_is_redacted(tmp_path):
    f = tmp_path / "stp.jsonl"
    f.write_text('{"out": "JIRA_API_TOKEN=ATATT3xFfGF0abcdefghijklmnop OPENAI=sk-proj-abcdefghijklmnopqrstuvwx"}\n')
    pipeline_runner._redact_file(f)
    assert "ATATT" not in f.read_text() and "sk-proj" not in f.read_text()
    pipeline_runner._redact_file(tmp_path / "missing")  # best-effort, no raise


def test_regression_analysis_is_a_listed_artifact():
    jid = "LSPX-1"
    p = ui.OUTPUTS / jid / "stp" / f"{jid}_regression_analysis.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("lsp_status: ok\n")
    assert "regression_analysis" in [a["type"] for a in ui._list_artifacts(jid)]
    assert ui._artifact_path(jid, "regression_analysis") == p
    assert "regression_analysis" in (ROOT / "ui" / "index.html").read_text()
    assert f"outputs/{{JIRA_ID}}/stp/{{JIRA_ID}}_regression_analysis.yaml" in \
        (ROOT / "agents" / "regression-analyzer.md").read_text()


# ---------------------------------------------------------------------------
# Warming the language-server cache while idle (#233)
# ---------------------------------------------------------------------------

FAKE_BRIDGE = """#!{python}
import json, os, sys
log = open(os.environ["FAKE_BRIDGE_LOG"], "a")
log.write(json.dumps({{"argv": sys.argv[1:], "readonly": os.environ.get("MCP_LSP_READONLY")}}) + "\\n"); log.flush()
for line in sys.stdin:
    msg = json.loads(line)
    log.write(json.dumps(msg) + "\\n"); log.flush()
    if msg.get("id") == 1 or (msg.get("id") == 2 and not os.environ.get("FAKE_BRIDGE_HANGS")):
        print(json.dumps({{"jsonrpc": "2.0", "id": msg["id"], "result": {{}}}}), flush=True)
"""


def _fake_bridge(tmp_path, monkeypatch):
    """A Go and a Python checkout, and a bridge on PATH that answers like the real one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("mcp-language-server", FAKE_BRIDGE.format(python=sys.executable)),
                       ("gopls", "#!/bin/sh\n"), ("pyright-langserver", "#!/bin/sh\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    go, py = tmp_path / "go-repo", tmp_path / "py-repo"
    go.mkdir(), py.mkdir()
    (go / "go.mod").write_text("module example.com/x\n")
    (py / "pyproject.toml").write_text("")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_BRIDGE_LOG", str(tmp_path / "bridge.log"))
    return {**os.environ, "PRODUCT_REPO_PATH": str(go), "SOURCE_REPO_PATH": str(py)}, tmp_path / "bridge.log"


def test_warm_lsp_loads_each_go_checkout_once_through_the_bridge(tmp_path, monkeypatch):
    import json

    env, log = _fake_bridge(tmp_path, monkeypatch)
    result = pipeline_runner.warm_lsp(env)
    assert list(result) == ["lsp_product"] and isinstance(result["lsp_product"], float)  # not the Python checkout
    seen = [json.loads(line) for line in log.read_text().splitlines()]
    assert seen[0]["argv"][:4] == ["--workspace", env["PRODUCT_REPO_PATH"], "--lsp", "gopls"]
    assert seen[0]["readonly"] == "1"  # started as a run starts it
    assert [m.get("method") for m in seen[1:]] == ["initialize", "notifications/initialized", "tools/call"]
    assert seen[3]["params"] == {"name": "definition", "arguments": {"symbolName": "main"}}
    assert pipeline_runner.warm_lsp(env, skip=("lsp_product",)) == {}


def test_warm_lsp_stops_when_asked_and_reports_a_bridge_that_never_answers(tmp_path, monkeypatch):
    env, _log = _fake_bridge(tmp_path, monkeypatch)
    env["FAKE_BRIDGE_HANGS"] = "1"
    calls = []
    assert pipeline_runner.warm_lsp(env, stop=lambda: calls.append(1) or len(calls) > 2) == {"lsp_product": "stopped"}
    assert pipeline_runner.warm_lsp(env, timeout=1) == {"lsp_product": "error: no reply in 1s"}


class _NoWait:
    """_shutdown_event for a test: never set, never sleeps."""
    def is_set(self):
        return False

    def wait(self, _timeout=None):
        return False


def _warm_loop(monkeypatch, results, memory_short=False):
    import time

    calls = []

    def fake_warm(env, stop=lambda: False, skip=()):
        calls.append(tuple(skip))
        stop()
        return results[min(len(calls), len(results)) - 1]
    monkeypatch.setattr(ui, "_shutdown_event", _NoWait())
    monkeypatch.setattr(ui, "_running_tasks", {})
    monkeypatch.setattr(ui, "_memory_short", lambda: memory_short)
    monkeypatch.setattr(pipeline_runner, "warm_lsp", fake_warm)
    monkeypatch.delenv("QF_REPOS_DIR", raising=False)
    monkeypatch.delenv("QF_LSP_WARM", raising=False)
    monkeypatch.setattr(ui, "_lsp_warm_status", {"status": "off"})
    ui._start_lsp_warm_loop()
    for _ in range(100):
        if ui._lsp_warm_status["status"] not in ("waiting", "warming"):
            break
        time.sleep(0.05)
    return calls


def test_dashboard_warms_once_and_retries_a_load_a_run_interrupted(monkeypatch):
    calls = _warm_loop(monkeypatch, [{"lsp_a": 3.2, "lsp_b": "stopped"}, {"lsp_b": 4.0}])
    assert calls == [(), ("lsp_a",)]  # the second pass skips what is warm
    assert ui._lsp_warm_status["status"] == "done"
    assert ui._lsp_warm_status["servers"] == {"lsp_a": 3.2, "lsp_b": 4.0}
    from fastapi.testclient import TestClient

    assert TestClient(ui.app).get("/api/status").json()["lsp_warm"]["status"] == "done"  # visible to an operator


def test_dashboard_warm_up_gives_up_when_memory_is_short_and_can_be_switched_off(monkeypatch):
    calls = _warm_loop(monkeypatch, [{"lsp_a": "stopped"}], memory_short=True)
    assert calls == [()]  # not tried again
    assert ui._lsp_warm_status["status"] == "stopped: memory is short"
    monkeypatch.setattr(ui, "_lsp_warm_status", {"status": "off"})
    monkeypatch.setenv("QF_LSP_WARM", "0")
    ui._start_lsp_warm_loop()
    assert ui._lsp_warm_status == {"status": "off"}
