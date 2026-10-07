#!/usr/bin/env python3
"""The tests repo's real vocabulary for /generate-tests, and its offline check.

    context <checkout> <target_dir> [--language python|go]
        YAML on stdout: the fixtures every conftest.py on the path from the repo
        root to target_dir defines (plus its pytest_plugins modules), the helper
        modules sibling tests import, the markers the repo registers, and up to
        three sibling tests to copy style from. The generator may use nothing
        else from the suite: fixture names and imports are never guessed.
    verify <checkout> <file>... [--repos-yaml FILE [--slot primary_repo]]
        Collects with every fixture resolved (Python, pytest --setup-plan) or
        compiles (Go) the given files inside the checkout with the repo's own
        tooling, plus the entry's `verify: {env, args}` from repositories.yaml. YAML on stdout: verification
        passed|failed|skipped, reason, command, output tail. Exit 0 only when
        passed. Collection/compilation is the limit of an offline check: it
        never runs a test.

Paths in the output are repo-relative.
"""
import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "polarion-migration"))
from migrate import Problem, registered_markers  # noqa: E402  (pytest.ini/pyproject/tox/setup.cfg reader)

ADD_MARKER = re.compile(r"""addinivalue_line\(\s*["']markers["']\s*,\s*["']([A-Za-z_]\w*)""")
TIMEOUT = 900  # uv run may sync the repo's environment first


def rel(repo, p):
    return Path(p).resolve().relative_to(repo).as_posix()


def chain(repo, target):
    """repo root, then every directory down to target (which may not exist yet)."""
    dirs, d = [repo], repo
    for part in target.relative_to(repo).parts:
        d = d / part
        dirs.append(d)
    return dirs


def parse(path):
    try:
        return ast.parse(path.read_text(errors="replace"))
    except (SyntaxError, ValueError):
        return None


def fixture_defs(tree):
    """(name, scope) for every @pytest.fixture / @fixture function at module level."""
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            fn = call.func if call else dec
            if (isinstance(fn, ast.Attribute) and fn.attr == "fixture") or (isinstance(fn, ast.Name) and fn.id == "fixture"):
                kw = {k.arg: k.value.value for k in (call.keywords if call else [])
                      if isinstance(k.value, ast.Constant)}
                out.append((kw.get("name") or node.name, kw.get("scope", "function")))
    return out


def plugin_modules(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytest_plugins"
                                                for t in node.targets):
            v = node.value
            items = v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
            return [e.value for e in items if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def module_file(repo, module):
    base = repo.joinpath(*module.split("."))
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.is_file():
            return p
    return None


def siblings_dir(repo, target, pattern):
    """target, or its nearest ancestor (inside the repo) that holds tests."""
    for d in reversed(chain(repo, target)):
        if d.is_dir() and any(d.glob(pattern)):
            return d
    return None


def python_context(repo, target):
    fixtures, markers_extra, sources = {}, set(), []
    for d in chain(repo, target):
        conf = d / "conftest.py"
        tree = conf.is_file() and parse(conf)
        if not tree:
            continue
        files = [(conf, tree)] + [(f, parse(f)) for f in filter(None, (module_file(repo, m)
                                                                       for m in plugin_modules(tree)))]
        for f, t in files:
            if not t:
                continue
            sources.append(rel(repo, f))
            for name, scope in fixture_defs(t):
                fixtures[name] = {"name": name, "file": rel(repo, f), "scope": scope}  # nearest wins, as in pytest
            markers_extra |= set(ADD_MARKER.findall(f.read_text(errors="replace")))
    names, strict = registered_markers(str(repo))

    sib_dir = siblings_dir(repo, target, "test_*.py") or siblings_dir(repo, target, "*_test.py")
    sibs = sorted(p for p in (sib_dir.glob("*.py") if sib_dir else [])
                  if (p.name.startswith("test_") or p.name.endswith("_test.py")) and not p.name.startswith("test_qf_"))
    helpers = {}
    for s in sibs:
        tree = parse(s)
        for node in ast.walk(tree) if tree else []:
            if isinstance(node, ast.ImportFrom):
                mod = "." * node.level + (node.module or "")
                local = node.level or module_file(repo, node.module or "") or (repo / (node.module or "").split(".")[0]).is_dir()
                if local and node.module != "conftest":
                    helpers.setdefault(mod, set()).update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if module_file(repo, a.name) or (repo / a.name.split(".")[0]).is_dir():
                        helpers.setdefault(a.name, set())
    return {
        "fixtures": sorted(fixtures.values(), key=lambda f: f["name"]),
        "fixture_sources": sources,
        "existing_conftest": rel(repo, target / "conftest.py") if (target / "conftest.py").is_file() else None,
        "helpers": [{"module": m, "names": sorted(n)} for m, n in sorted(helpers.items())],
        "markers": {"registered": sorted(names | markers_extra), "strict": strict},
        # ponytail: first three by name, not "most similar"; rank by shared fixtures if style drifts.
        "siblings": [rel(repo, s) for s in sibs[:3]],
    }


def go_context(repo, target):
    gomod = repo / "go.mod"
    m = re.search(r"(?m)^module\s+(\S+)", gomod.read_text()) if gomod.is_file() else None
    module = m.group(1) if m else None
    sib_dir = siblings_dir(repo, target, "*_test.go")
    sibs = sorted(sib_dir.glob("*_test.go")) if sib_dir else []
    sibs = [s for s in sibs if not s.name.startswith("qf_")]
    imports, tags, packages = set(), set(), set()
    for s in sibs:
        text = s.read_text(errors="replace")
        blocks = re.findall(r"(?ms)^import\s*\((.*?)\)", text) + re.findall(r'(?m)^import\s+(?:[\w.]+\s+)?("[^"]+")', text)
        imports |= {i for i in re.findall(r'"([^"\s]+)"', "\n".join(blocks)) if module and i.startswith(module)}
        tags |= set(re.findall(r"(?m)^//go:build\s+(.+)$", text))
        packages |= set(re.findall(r"(?m)^package\s+(\w+)", text))
    return {"module": module, "helpers": [{"module": i} for i in sorted(imports)],
            "build_tags": sorted(tags), "packages": sorted(packages),
            "siblings": [rel(repo, s) for s in sibs[:3]]}


def op_context(a):
    repo = Path(a.checkout).resolve()
    if not repo.is_dir():
        sys.exit("no tests repo checkout at %s: set the repo's local_path_env to a clone" % a.checkout)
    target = (repo / a.target_dir).resolve()
    if repo != target and repo not in target.parents:
        sys.exit("target directory %s is outside the checkout %s" % (a.target_dir, repo))
    ctx = {"checkout": repo.name, "target_dir": rel(repo, target) if target != repo else ".",
           "language": a.language}
    try:
        ctx.update(python_context(repo, target) if a.language == "python" else go_context(repo, target))
    except Problem as e:
        sys.exit(str(e))
    yaml.safe_dump(ctx, sys.stdout, sort_keys=False, default_flow_style=False)


def run(cmd, cwd, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT,
                           env={**os.environ, **(env or {})})
    except FileNotFoundError:
        return None, "%s is not installed" % cmd[0]
    except subprocess.TimeoutExpired:
        return None, "timed out after %ds" % TIMEOUT
    return p.returncode, (p.stdout + p.stderr)


def python_cmd(repo):
    if (repo / "uv.lock").is_file():
        return ["uv", "run", "pytest"]
    venv = repo / ".venv" / "bin" / "python"
    py = str(venv) if venv.is_file() else (shutil.which("python") or shutil.which("python3") or "python")
    return [py, "-m", "pytest"]


# pytest's default python_files. A file named on the command line is collected
# even when the repo's discovery would skip it, so the repo's CI would never run
# it: refuse such a name instead of "passing" it.
# ponytail: the default pattern, not the repo's own python_files setting.
PYTEST_FILE = re.compile(r"^(test_.*|.*_test)\.py$")


def repo_settings(repos_yaml, slot):
    """The `verify:` block of one repositories.yaml entry: {env: {..}, args: [..]}.
    What the repo's own CI does to collect offline (e.g. an env var that stops
    its conftest from contacting a cluster, a config-file argument)."""
    if not repos_yaml:
        return {}, []
    data = yaml.safe_load(Path(repos_yaml).read_text()) or {}
    block = (data.get(slot) or {}).get("verify") or {}
    env = {str(k): str(v) for k, v in (block.get("env") or {}).items()}
    return env, [str(a) for a in (block.get("args") or [])]


def verify(repo, files, env=None, args=()):
    """{verification, reason, command, output}: the offline check, run inside the checkout.

    Python: `pytest --setup-plan` — collects AND resolves every fixture a test
    asks for, without running anything. `--collect-only` let a test with a
    misspelled or invented fixture pass, which is the mistake this check exists
    to catch."""
    repo = Path(repo).resolve()
    files = [rel(repo, repo / f) for f in files]
    py = [f for f in files if f.endswith(".py")]
    go = sorted({str(Path(f).parent) for f in files if f.endswith(".go")})
    if not py and not go:
        return {"verification": "skipped", "reason": "no offline check for these files: " + ", ".join(files)}
    unnamed = [f for f in py if not PYTEST_FILE.match(Path(f).name)]
    if unnamed:
        return {"verification": "failed", "command": "", "output": "",
                "reason": "pytest would not collect these in the repo's CI (name them test_*.py): "
                          + ", ".join(unnamed)}
    cmds = [(python_cmd(repo) + list(args) + ["--setup-plan", "-q"] + py, py)] if py else []
    for d in go:
        cmds += [(["go", "vet", "./" + d], []), (["go", "test", "-run", "xxx", "-count=0", "./" + d], [])]
    for cmd, planned in cmds:
        code, out = run(cmd, repo, env)
        res = {"command": " ".join(cmd), "output": "\n".join(out.splitlines()[-30:]) if code is not None else ""}
        if code is None:
            return dict(res, verification="skipped", reason=out)
        if "No module named pytest" in out or "Failed to spawn: `pytest`" in out:
            return dict(res, verification="skipped", reason="pytest is not installed in the repo's environment")
        if code == 5 and planned:
            return dict(res, verification="failed", reason="no tests collected from " + ", ".join(planned))
        if code != 0:
            reason = "`%s` exited %d" % (" ".join(cmd[:3]), code)
            missing = sorted(set(re.findall(r"fixture '([^']+)' not found", out)))
            if missing:
                reason += "; fixtures not found: " + ", ".join(missing)
            elif "while loading conftest" in out:
                reason += ("; the repo's conftest.py failed to load — if it needs a cluster or "
                           "config to import, set what the repo's CI sets to collect offline under "
                           "this repo's verify: {env, args} in repositories.yaml")
            return dict(res, verification="failed", reason=reason)
    return dict(res, verification="passed", reason=" and ".join(
        w for w, on in (("collected with every fixture resolved", py), ("compiled", go)) if on)
        + "; no test was run")


def op_verify(a):
    env, args = repo_settings(a.repos_yaml, a.slot)
    res = verify(a.checkout, a.files, env, args)
    yaml.safe_dump(res, sys.stdout, sort_keys=False, default_flow_style=False)
    sys.exit(0 if res["verification"] == "passed" else 1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="op", required=True)
    c = sub.add_parser("context")
    c.add_argument("checkout")
    c.add_argument("target_dir")
    c.add_argument("--language", choices=("python", "go"), default="python")
    c.set_defaults(fn=op_context)
    v = sub.add_parser("verify")
    v.add_argument("checkout")
    v.add_argument("files", nargs="+")
    v.add_argument("--repos-yaml", help="the project's repositories.yaml: its entry's verify: block "
                   "(env, args) is applied, as the repo's own CI does to collect offline")
    v.add_argument("--slot", default="primary_repo", help="which entry (default primary_repo)")
    v.set_defaults(fn=op_verify)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
