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

    product <std.yaml> <checkout>...
        YAML on stdout: where the STD's source_constants are now (file:line in
        the first checkout, the product), and per scenario the files in each
        checkout (the product, then the tests repo) that hold most of its terms
        (its constants, literal parameter values and title words). The
        generator opens these before writing a test or declining a scenario.

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
    """(name, scope, fixture args, reads request.param) for every @pytest.fixture
    / @fixture function at module level. A fixture that reads request.param with
    no params= of its own only works when a test parametrizes it indirectly.
    ponytail: a `request.param` guarded by hasattr() still counts as a read."""
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            fn = call.func if call else dec
            if (isinstance(fn, ast.Attribute) and fn.attr == "fixture") or (isinstance(fn, ast.Name) and fn.id == "fixture"):
                keywords = call.keywords if call else []
                kw = {k.arg: k.value.value for k in keywords if isinstance(k.value, ast.Constant)}
                reads = not any(k.arg == "params" for k in keywords) and any(
                    isinstance(n, ast.Attribute) and n.attr == "param" and isinstance(n.value, ast.Name)
                    and n.value.id == "request" for n in ast.walk(node))
                args = {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs} - {"request"}
                out.append((kw.get("name") or node.name, kw.get("scope", "function"), args, reads))
    return out


def fixture_table(repo, target):
    """{name: {name, file, scope[, needs_indirect_param]}} for the conftest chain
    down to target (nearest wins, as in pytest), the conftest/plugin files read,
    and the markers they add. needs_indirect_param lists the fixtures, this one
    or any it depends on, that a test must parametrize with indirect=True."""
    fixtures, deps, markers_extra, sources = {}, {}, set(), []
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
            for name, scope, args, reads in fixture_defs(t):
                fixtures[name] = {"name": name, "file": rel(repo, f), "scope": scope}
                deps[name] = (args, reads)
            markers_extra |= set(ADD_MARKER.findall(f.read_text(errors="replace")))

    def roots(name, seen):
        args, reads = deps.get(name, ((), False))
        return ({name} if reads else set()).union(*(roots(a, seen | {a}) for a in args if a not in seen))

    for name, f in fixtures.items():
        need = roots(name, {name})
        if need:
            f["needs_indirect_param"] = sorted(need)
    return fixtures, sources, markers_extra


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
    fixtures, sources, markers_extra = fixture_table(repo, target)
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
    # The checkout's own environment first: `uv run` syncs before it runs, and
    # inside a macOS sandbox (Codex workspace-write) it panics reading the
    # system network settings before pytest starts.
    venv = repo / ".venv" / "bin" / "python"
    if venv.is_file():
        return [str(venv), "-m", "pytest"]
    if (repo / "uv.lock").is_file():
        return ["uv", "run", "pytest"]
    return [shutil.which("python") or shutil.which("python3") or "python", "-m", "pytest"]


# pytest's default python_files. A file named on the command line is collected
# even when the repo's discovery would skip it, so the repo's CI would never run
# it: refuse such a name instead of "passing" it.
# ponytail: the default pattern, not the repo's own python_files setting.
PYTEST_FILE = re.compile(r"^(test_.*|.*_test)\.py$")


def _is_pytest(node, attr):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest")


def _base(node):
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def _parametrized(decorators, indirect):
    """argnames of the @pytest.mark.parametrize calls among decorators that are
    indirect (indirect=True) or direct (no indirect=).
    ponytail: indirect=[names] counts all argnames as indirect."""
    names = set()
    for d in decorators:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "parametrize"
                and d.args and any(k.arg == "indirect" for k in d.keywords) == indirect):
            first = d.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names |= {n.strip() for n in first.value.split(",")}
            elif isinstance(first, (ast.List, ast.Tuple)):
                names |= {e.value for e in first.elts if isinstance(e, ast.Constant)}
    return names


def _fixture_args(fn):
    """The function's fixture arguments: parameters minus self/cls and minus
    values a direct (not indirect) @pytest.mark.parametrize supplies."""
    names = {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs} - {"self", "cls"}
    return names - _parametrized(fn.decorator_list, False)


def _usefixtures(decorators):
    return {a.value for d in decorators if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and d.func.attr == "usefixtures" for a in d.args if isinstance(a, ast.Constant)}


def _tests(tree):
    """(test function, the decorators that apply to it: its own, its class's, pytestmark's)."""
    fn_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    module = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets):
            module += n.value.elts if isinstance(n.value, (ast.List, ast.Tuple)) else [n.value]
    out = [(n, n.decorator_list + module) for n in tree.body if isinstance(n, fn_types)]
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.startswith("Test")):
        out += [(m, m.decorator_list + cls.decorator_list + module) for m in cls.body if isinstance(m, fn_types)]
    return [(fn, decs) for fn, decs in out if fn.name.startswith("test")]


def unparametrized(path, shown, fixtures):
    """Tests that use a fixture needing request.param (see fixture_table) without
    parametrizing it indirectly: they collect, and --setup-plan resolves them,
    but every one errors at setup on a real run."""
    found = []
    for fn, decs in _tests(ast.parse(Path(path).read_text())):
        need = set()
        for name in _fixture_args(fn) | _usefixtures(decs):
            need |= set(fixtures.get(name, {}).get("needs_indirect_param", ()))
        missing = sorted(need - _parametrized(decs, True))
        if missing:
            found.append("%s::%s (parametrize %s with indirect=True, as the sibling tests do)"
                         % (shown, fn.name, ", ".join(missing)))
    return found


def hollow_tests(path, shown):
    """Generated tests that pass while testing nothing: ["file::test (why)"].

    A test is hollow when it takes no fixture and calls nothing imported from
    the suite or the product, directly or through a helper in the same file
    (it can only assert its own constants or ids), or when its body calls
    pytest.fail/skip/xfail outside any condition, only passes, or only asserts a
    constant. A skipped placeholder reports as skipped, never as a failure, so it
    reads as coverage. A scenario that cannot be implemented stays
    a pending stub instead.
    ponytail: Python only, and a test that uses a fixture only to check it is
    not None still passes."""
    tree = ast.parse(Path(path).read_text())
    product = set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            product |= {(a.asname or a.name).split(".")[0] for a in n.names
                        if a.name.split(".")[0] not in sys.stdlib_module_names | {"pytest"}}
        elif isinstance(n, ast.ImportFrom) and (n.level or (n.module or "").split(".")[0]
                                                not in sys.stdlib_module_names | {"pytest"}):
            product |= {a.asname or a.name for a in n.names}
    funcs = {f.name: f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def reaches(fn, seen):
        for c in ast.walk(fn):
            if not isinstance(c, ast.Call):
                continue
            b = _base(c.func)
            if b in product:
                return True
            name = c.func.id if isinstance(c.func, ast.Name) else (
                c.func.attr if isinstance(c.func, ast.Attribute) and b in ("self", "cls") else None)
            if name in funcs and name not in seen and reaches(funcs[name], seen | {name}):
                return True
        return False

    found = []
    for fn, decs in _tests(tree):
        body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        stop = next((a for s in body for a in ("fail", "skip", "xfail")
                     if isinstance(s, ast.Expr) and _is_pytest(s.value, a)), None)
        if stop:
            why = {"fail": "fails", "skip": "skips", "xfail": "xfails"}[stop] + " unconditionally"
        elif all(isinstance(s, ast.Pass) or isinstance(s, ast.Assert) and isinstance(s.test, ast.Constant)
                 for s in body):
            why = "asserts nothing"
        elif not _fixture_args(fn) and not _usefixtures(decs) and not reaches(fn, {fn.name}):
            why = "uses no fixture and calls nothing from the suite or the product"
        else:
            continue
        found.append("%s::%s (%s)" % (shown, fn.name, why))
    return found


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


def missing_refs(refs, roots):
    """The `file:line` refs (summary.yaml product_refs) that no checkout has: the file is
    absent, or shorter than the line. A plan built from an open PR cites code the
    checked-out commit does not have; tests written against it fail on the product."""
    out = []
    for ref in refs:
        path, _, line = str(ref).rpartition(":")
        if not path:
            path, line = line, "0"
        n = int(re.match(r"\d*", line).group() or 0)
        if not any((Path(r) / path).is_file() and
                   (n == 0 or len((Path(r) / path).read_text(errors="replace").splitlines()) >= n)
                   for r in roots):
            out.append(str(ref))
    return out


def verify(repo, files, env=None, args=(), refs=(), roots=()):
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
    # A file that is not in the checkout was never checked: go test -c builds the
    # package without it and says "compiled" (seen when a run wrote to a wrong path).
    missing = [f for f in files if not (repo / f).is_file()]
    if missing:
        return {"verification": "failed", "command": "", "output": "",
                "reason": "not in the checkout (write each file at its target_path): " + ", ".join(missing)}
    unnamed = [f for f in py if not PYTEST_FILE.match(Path(f).name) and Path(f).name != "conftest.py"]
    if unnamed:
        return {"verification": "failed", "command": "", "output": "",
                "reason": "pytest would not collect these in the repo's CI (name them test_qf_*.py): "
                          + ", ".join(unnamed)}
    # Generated files carry the qf_ marker, or are a conftest.py the run added;
    # any other file is the team's own, which a run must never list as output.
    def ours(f):
        name = Path(f).name
        if name == "conftest.py":
            return run(["git", "cat-file", "-e", "HEAD:" + f], repo)[0] != 0  # not in the checked-out commit
        return name.startswith("test_qf_") if name.endswith(".py") else name.startswith("qf_")
    foreign = [f for f in py + [f for f in files if f.endswith(".go")] if not ours(f)]
    if foreign:
        return {"verification": "failed", "command": "", "output": "",
                "reason": "not QualityFlow files (generated tests are named test_qf_*.py / qf_*_test.go; "
                          "never list or edit the team's own tests): " + ", ".join(foreign)}

    missing = missing_refs(refs, [repo, *roots])
    if missing:
        return {"verification": "failed", "command": "", "output": "\n".join(missing),
                "reason": "%d product_refs are not in the checkouts (code not on the checked-out "
                          "commit, e.g. an open PR): %s; test only what the checkout has and list the "
                          "rest under not_implemented" % (len(missing), ", ".join(missing[:5]))}

    def fail(found, why):
        return {"verification": "failed", "command": "", "output": "\n".join(found),
                "reason": "%d test(s) %s: %s" % (len(found), why,
                                                 ", ".join(found[:5]) + (" ..." if len(found) > 5 else ""))}
    hollow = [h for f in py for h in hollow_tests(repo / f, f)]
    if hollow:
        return fail(hollow, "never touch the product; implement them or leave those scenarios "
                            "as pending stubs (not_implemented in summary.yaml)")
    unparam = [u for f in py for u in unparametrized(repo / f, f, fixture_table(repo, (repo / f).parent)[0])]
    if unparam:
        return fail(unparam, "would error at setup")
    cmds = [(python_cmd(repo) + list(args) + ["--setup-plan", "-q"] + py, py)] if py else []
    for d in go:
        # `go test -c` builds the test binary without running it: `go test -run xxx`
        # still ran TestMain, which starts envtest or a database container.
        cmds += [(["go", "vet", "./" + d], []), (["go", "test", "-c", "-o", os.devnull, "./" + d], [])]
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
    refs = [r for rs in ((yaml.safe_load(open(a.summary)) or {}).get("product_refs") or {}).values()
            for r in rs or []] if a.summary else []
    res = verify(a.checkout, a.files, env, args, refs, a.product)
    yaml.safe_dump(res, sys.stdout, sort_keys=False, default_flow_style=False)
    sys.exit(0 if res["verification"] == "passed" else 1)


# Words a scenario title shares with every other scenario: not search terms.
STOP = set("""verify verifies check checks ensure ensures should their there which while with without
after before every other given using returns return correct correctly expected scenario tests
works work valid invalid create creates created still about through between different single
""".split())


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def scenario_terms(sc, constants):
    """Search terms for one STD scenario: (term, weight). Constants and literal
    values name the interface exactly (weight 3); title words only narrow it."""
    terms = {}
    for d in _walk(sc):
        ref = d.get("source_constant_ref")
        if ref in constants:
            terms[str(constants[ref]["value"])] = 3
            terms[ref] = 3
        v = d.get("value")
        if isinstance(v, str) and len(v) >= 3 and not v.startswith("<TBD"):
            terms[v] = 3
    title = (sc.get("test_objective") or {}).get("title") or sc.get("title") or ""
    for w in re.findall(r"[A-Za-z][A-Za-z_-]{4,}", title):
        if w.lower() not in STOP and w.lower() not in {t.lower() for t in terms}:
            terms[w.lower()] = 1
    return terms


def grep_files(repo, term, cache):
    """Repo-relative files that contain term (case-insensitive, fixed string)."""
    if (repo, term) not in cache:
        # Code and config only: docs pages repeat every term and point at no interface.
        code, out = run(["git", "grep", "-l", "-i", "-I", "-F", "-e", term, "--", ".", ":!*.md", ":!*.rst"], repo)
        if code is None or code > 1:  # not a git checkout
            code, out = run(["grep", "-rlIiF", "--exclude-dir=.git", "--exclude-dir=.venv",
                             "--exclude-dir=node_modules", "--exclude=*.md", "--exclude=*.rst", "--", term, "."], repo)
        cache[(repo, term)] = {l.removeprefix("./") for l in out.splitlines() if l} if code == 0 else set()
    return cache[(repo, term)]


def first_line(repo, f, terms):
    try:
        lines = (repo / f).read_text(errors="replace").splitlines()
    except OSError:
        return f
    low = [t.lower() for t in sorted(terms, key=len, reverse=True)]
    return next(("%s:%d" % (f, i) for i, l in enumerate(lines, 1) if any(t in l.lower() for t in low)), f)


def product_refs(std, repos, top=8):
    """{constants: [...], scenarios: {test_id: {terms, <checkout>: [file:line (terms)]}}}.
    ponytail: lexical ranking by weighted distinct terms; an LSP lookup of each
    constant's references would be sharper."""
    constants = {c["name"]: c for c in std.get("source_constants") or [] if c.get("name")}
    cache = {}
    out = {"constants": [], "scenarios": {}}
    for c in constants.values():
        repo, f, line = repos[0], c.get("source_file"), c.get("line")
        val = str(c.get("value", ""))
        lines = (repo / f).read_text(errors="replace").splitlines() if f and (repo / f).is_file() else []
        at = next(("%s:%d" % (f, i) for i, l in enumerate(lines, 1) if val and val in l), None)
        if at is None:
            hits = sorted(grep_files(repo, val, cache))[:5] if val else []
            at = (("moved: " if lines else "seen in: ") + ", ".join(hits)) if hits else "not found in %s" % repo.name
        out["constants"].append({"name": c["name"], "value": val, "stp_said": "%s:%s" % (f, line), "now": at})
    for sc in std.get("scenarios") or []:
        terms = scenario_terms(sc, constants)
        res = {"terms": sorted(terms)}
        for repo in repos:
            score = {}
            for t, w in terms.items():
                for f in grep_files(repo, t, cache):
                    score.setdefault(f, {})[t] = w
            best = sorted(score, key=lambda f: (-sum(score[f].values()), -len(score[f]), f))[:top]
            res[repo.name] = ["%s (%s)" % (first_line(repo, f, score[f]), ", ".join(sorted(score[f])))
                              for f in best]
        out["scenarios"][str(sc.get("test_id") or sc.get("scenario_id"))] = res
    return out


def op_product(a):
    repos = [Path(c).resolve() for c in a.checkouts]
    missing = [str(r) for r in repos if not r.is_dir()]
    if missing:
        sys.exit("no checkout at " + ", ".join(missing))
    std = yaml.safe_load(Path(a.std).read_text()) or {}
    yaml.safe_dump(product_refs(std, repos), sys.stdout, sort_keys=False, default_flow_style=False, width=200)


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
    v.add_argument("--summary", help="summary.yaml: every product_refs file:line must exist in a checkout")
    v.add_argument("--product", action="append", default=[], help="a product checkout the refs may point into")
    v.set_defaults(fn=op_verify)
    r = sub.add_parser("product")
    r.add_argument("std", help="the STD YAML")
    r.add_argument("checkouts", nargs="+", help="the product checkout first, then the tests repo checkout")
    r.set_defaults(fn=op_product)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
