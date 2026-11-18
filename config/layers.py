"""Repo config layers: .qualityflow/ directories in the checkouts of a project's
configured repos (config/README.md "Repo config layers").

Precedence, highest first: the ticket's repositories.overlay.yaml (repos only),
.qualityflow/ in the target path's ancestors (deepest first), the target repo's
root, the other repo roots in config_sources.order, the central project dir,
_defaults.yaml. A checkout is untrusted input: load_layer applies the identity
marker, the file and key allowlists and the toggle ratchet from _schema.yaml
`config_layers` before anything is merged.
"""
import copy
import fnmatch
import hashlib
import os
import re
import shutil
from pathlib import Path

import yaml

import validate
from merge import leaves, merge
from repository_overlay import entries

LAYER_DIR = ".qualityflow"


def checkout(repo, env):
    path = repo.get("local_path") or env.get(repo.get("local_path_env") or "")
    return Path(path).resolve() if path and Path(path).is_dir() else None


def _names(kind, repo):
    # What config_sources.order/exclude may name a repo by, as the overlay's `only`.
    return {kind, f"{kind}_repo", f"{kind}_repos", repo.get("name")}


def discover(repositories, targets, env, default_order):
    """Layer dirs found in the checkouts, highest precedence first, as
    (source, repo name, checkout root, dir holding .qualityflow/)."""
    sources = repositories.get("config_sources") or {}
    order = sources.get("order") or default_order
    exclude = set(sources.get("exclude") or [])

    def rank(entry):
        return next((i for i, o in enumerate(order) if o in _names(*entry)), len(order))

    roots = [(repo.get("name") or kind, root) for kind, repo in sorted(entries(repositories), key=rank)
             if not _names(kind, repo) & exclude and (root := checkout(repo, env))]

    def path(t):  # a path, or <repo>:<path in its checkout> (repo named as in `order`)
        name, sep, rel = t.partition(":")
        if not sep or os.path.isabs(t):
            return Path(t).resolve()
        root = next((checkout(r, env) for k, r in entries(repositories) if name in _names(k, r)), None)
        return (root / rel).resolve() if root else None

    found = []
    # Several targets (a PR's changed files): their deepest common directory.
    paths = [p for p in map(path, targets) if p]
    target = Path(os.path.commonpath(paths)) if paths else None
    home = max((r for r in roots if target and target.is_relative_to(r[1])),
               key=lambda r: len(r[1].parts), default=None)
    if home:
        name, root = home
        d = target if target.is_dir() else target.parent
        while sources.get("nested", True) and d != root:
            if (d / LAYER_DIR).is_dir():
                found.append(("repo_dir", name, root, d))
            d = d.parent
        roots.remove(home)
        roots.insert(0, home)
    return found + [("repo_root", name, root, root) for name, root in roots if (root / LAYER_DIR).is_dir()]


def central(project_dir, project_id, defaults, repositories):
    """What a layer is checked against. project_id None accepts the declared one.
    Without a central project (validate.py --repo against the schema alone) a
    layer's context repos are checked for shape, not against an org allowlist."""
    project = validate.load_yaml(project_dir / "project.yaml") if project_dir else None
    project = project if isinstance(project, dict) else {}
    repos = repositories if isinstance(repositories, dict) else {}
    sources = repos.get("config_sources") or {}
    own = [r for _, r in entries(repos)]
    return {"dir": project_dir, "project_id": project_id,
            "toggles": {**defaults.get("feature_toggles", {}), **(project.get("feature_toggles") or {})},
            "allow_sensitive": sources.get("allow_sensitive") or [],
            # Context repos a layer may add (#226): orgs the central repos already
            # use, plus config_sources.layer_repo_orgs.
            "layer_repo_orgs": None if not project_dir else
                {o for o, _ in map(repo_ident, own) if o}
                | {str(o).lower() for o in sources.get("layer_repo_orgs") or []},
            "allow_ref": bool(sources.get("allow_ref_from_layers")),
            "central_envs": {r["local_path_env"]: repo_ident(r) for r in own if r.get("local_path_env")}}


_REPO_URL = re.compile(r"https://([^/\s]+)/([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:[/#?].*)?")


def repo_url(url):
    """(host, org, repo) of an https repository URL (a file URL in it counts), else None."""
    m = _REPO_URL.fullmatch(str(url or ""))
    return (m[1].lower(), m[2].lower(), m[3].lower()) if m else None


def repo_ident(repo):
    """(org, repo) a repositories.yaml entry names: its url, else full_name, else org + name."""
    u = repo_url(repo.get("url"))
    if u:
        return u[1:]
    org, _, name = str(repo.get("full_name") or "").partition("/")
    if name:
        return org.lower(), name.lower()
    return str(repo.get("org") or "").lower() or None, str(repo.get("name") or "").lower()


# What a layer's repositories.yaml may say (#226): read-only context repos. Where
# generated tests land (primary_repo, tier2_repo), the STP repo, repo_files and
# config_sources stay central: a checked-in file never redirects a run.
_LAYER_REPO_KEYS = {"name", "org", "full_name", "url", "default_branch", "language", "local_path_env", "description"}
_LAYER_REF_KEYS = {"ref", "branch"}
_REPO_PATH_ENV = re.compile(r"[A-Z][A-Z0-9_]*_REPO_PATH")


def _layer_repo_errors(where, doc, rules, policy):
    repos = doc.get("additional_repos")
    if not isinstance(repos, list):
        return [f"{where}: additional_repos must be a list of repositories"]
    errors = []
    allowed = _LAYER_REPO_KEYS | (_LAYER_REF_KEYS if policy["allow_ref"] else set())
    for i, r in enumerate(repos):
        at = f"{where}: additional_repos[{i}]"
        if not isinstance(r, dict) or not isinstance(r.get("name"), str) or not r["name"]:
            errors.append(f"{at}: each entry needs a name")
            continue
        at += f" ({r['name']})"
        errors += [f"{at}: key {k!r} is not allowed in a repo config layer" + (
            " unless the central repositories.yaml sets config_sources.allow_ref_from_layers: true"
            if k in _LAYER_REF_KEYS else "") for k in r if k not in allowed]
        url = repo_url(r.get("url"))
        if not url:
            errors.append(f"{at}: url must be https://<host>/<org>/<repo>")
        else:
            host, org, name = url
            if host not in rules["layer_repos"]["hosts"]:
                errors.append(f"{at}: host {host!r} is not one of {', '.join(rules['layer_repos']['hosts'])}")
            if policy["layer_repo_orgs"] is not None and org not in policy["layer_repo_orgs"]:
                errors.append(f"{at}: org {org!r} is not allowed: the central repositories.yaml names the orgs "
                              "layers may add repos from in config_sources.layer_repo_orgs (its own repos' orgs count)")
            if r.get("org") and str(r["org"]).lower() != org or r.get("full_name") and str(r["full_name"]).lower() != f"{org}/{name}":
                errors.append(f"{at}: org/full_name do not match the url")
        env = r.get("local_path_env")
        if env is not None and not (isinstance(env, str) and _REPO_PATH_ENV.fullmatch(env)):
            errors.append(f"{at}: local_path_env must look like NAME_REPO_PATH")
        elif env in policy["central_envs"] and policy["central_envs"][env] != (url[1:] if url else None):
            errors.append(f"{at}: local_path_env {env} is already the checkout of another configured repo")
    return errors


def _append_repos(base, doc, layer_id, owner):
    """A layer's context repos appended to `base` by name. Re-declaring a known
    repo is fine when it is the same repo (the earlier entry stays); naming
    another repo the same is an error."""
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    known = {r.get("name"): r for _, r in entries(out)}
    added = []
    for r in doc["additional_repos"]:
        old = known.get(r["name"])
        if old is not None:
            if repo_ident(old) != repo_ident(r):
                raise ValueError(f"repo {r['name']!r} is already {'/'.join(filter(None, repo_ident(old)))} "
                                 f"(from {owner.get(r['name'], 'central')}); a layer may add repos, not change one")
            continue
        known[r["name"]] = r
        owner[r["name"]] = layer_id
        added.append(copy.deepcopy(r))
    out["additional_repos"] = (out.get("additional_repos") or []) + added
    return out, [r["name"] for r in added]


def _match(rel, pattern):
    if pattern.endswith("/**"):
        return rel.startswith(pattern[:-2])
    parts, pats = rel.split("/"), pattern.split("/")
    return len(parts) == len(pats) and all(map(fnmatch.fnmatchcase, parts, pats))


def _known_keys(rel, schema, central_dir):
    """Top-level keys a layer may set in a file: the schema's, plus the central file's own."""
    if rel == "project.yaml":
        return set(schema["config_layers"]["project_keys"])
    if rel == "repositories.yaml":
        return {"additional_repos"}
    name = "tier" if _match(rel, "tier*.yaml") else "patterns" if rel.startswith("patterns/") else rel[:-len(".yaml")]
    spec = schema.get("validation", {}).get(f"{name}_yaml", {})
    keys = {f.split(".")[0] for k in ("required_fields", "optional_fields", "optional_sections") for f in spec.get(k, [])}
    own = validate.load_yaml(central_dir / rel) if central_dir else None
    return keys | set(own) if isinstance(own, dict) else keys


def load_layer(found, schema, policy):
    """One .qualityflow/ through the trust boundary.

    Returns (entry, docs, files): its config_layers entry, the YAML files to
    deep-merge, and the files copied whole. Raises ValueError naming every problem.
    """
    source, repo, root, d = found
    rules = schema["config_layers"]
    qf = d / LAYER_DIR
    rel_dir = d.relative_to(root).as_posix()
    where = f"{repo}:{rel_dir}/{LAYER_DIR}"
    if not qf.resolve().is_relative_to(root):
        raise ValueError(f"{where}: resolves outside the checkout")
    errors, paths = [], {}
    for dirpath, dirnames, filenames in os.walk(qf):
        for name in sorted(dirnames + filenames):
            p = Path(dirpath, name)
            rel = p.relative_to(qf).as_posix()
            if p.is_symlink():  # values are data only: nothing may point out of the layer
                errors.append(f"{where}/{rel}: symlinks are not allowed in a repo config layer")
            elif p.is_file():
                paths[rel] = p
    if errors:
        raise ValueError("\n".join(errors))
    digest = hashlib.sha256()
    for rel in sorted(paths):
        digest.update(rel.encode() + b"\0" + paths[rel].read_bytes() + b"\0")
    entry = {"id": f"{repo}:{rel_dir}", "source": source, "repo": repo, "dir": rel_dir,
             "files": sorted(paths), "digest": "sha256:" + digest.hexdigest(), "status": "applied"}

    marker = validate.load_yaml(qf / "project.yaml")
    if not isinstance(marker, dict) or marker.get("version") != 1 or not marker.get("project_id"):
        raise ValueError(f"{where}/project.yaml: a repo config layer needs project.yaml with version: 1 "
                         f"and the project_id it configures" + (f" ({marker})" if isinstance(marker, Exception) else ""))
    if policy["project_id"] and marker["project_id"] != policy["project_id"]:
        entry.update(status="skipped_mismatch", warnings=[
            f"declares project_id {marker['project_id']!r}, not {policy['project_id']!r}: ignored"])
        return entry, {}, {}

    sensitive = rules["sensitive_files"]
    allowed = rules["allowed_files"] + [f for f in sensitive if f in policy["allow_sensitive"]]
    docs, files, warnings = {}, {}, []
    for rel, p in paths.items():
        if not any(_match(rel, pat) for pat in allowed):
            errors.append(f"{where}/{rel}: not allowed in a repo config layer" + (
                " unless the central repositories.yaml lists it in config_sources.allow_sensitive"
                if rel in sensitive else ""))
        elif rel == "README.md":
            continue
        elif any(pat.endswith("/**") and _match(rel, pat) for pat in allowed):
            files[rel] = p
        else:
            data = validate.load_yaml(p)
            if not isinstance(data, dict):
                errors.append(f"{where}/{rel}: " + (f"YAML error: {data}" if isinstance(data, Exception)
                                                     else "must be a mapping"))
                continue
            known = _known_keys(rel, schema, policy["dir"])
            errors += [f"{where}/{rel}: key {k!r} is not allowed here (allowed: {', '.join(sorted(known))})"
                       + ("; where tests land, the STP repo, repo_files and config_sources stay in the central "
                          "repositories.yaml" if rel == "repositories.yaml" else "")
                       for k in data if k not in known]
            if rel == "repositories.yaml" and "additional_repos" in data:
                errors += _layer_repo_errors(f"{where}/{rel}", data, rules, policy)
            docs[rel] = data

    project = docs["project.yaml"]
    del project["version"], project["project_id"]  # identity assertion only, never merged
    toggles = project.get("feature_toggles")
    if toggles is not None and not isinstance(toggles, dict):
        errors.append(f"{where}/project.yaml: feature_toggles must be a mapping")
        toggles = {}
    for k in list(toggles or {}):
        if k not in policy["toggles"]:
            errors.append(f"{where}/project.yaml: unknown feature toggle {k!r}")
        elif k in rules.get("central_toggles", []):
            errors.append(f"{where}/project.yaml: feature toggle {k!r} can only be set in the central project.yaml")
        elif k in rules["ratchet_toggles"] and toggles[k] is not True and policy["toggles"].get(k) is True:
            warnings.append(f"feature_toggles.{k}: {toggles.pop(k)!r} ignored, a repo layer may turn it on, never off")
    if errors:
        raise ValueError("\n".join(errors))
    if warnings:
        entry["warnings"] = warnings
    return entry, docs, files


def resolve(project_id, project_dir, repositories, schema, defaults, targets, env, out_dir):
    """Merge the repo layers over project_dir into out_dir (its name must be project_id).

    None when no checkout has a .qualityflow/. Otherwise a dict with
    config_layers, and when a layer applied also config_dir, config_provenance,
    config_hash and files (what the hash covers). Raises ValueError.
    """
    found = discover(repositories, targets, env, schema["config_layers"]["default_order"])
    if not found:
        return None
    policy = central(project_dir, project_id, defaults, repositories)
    loaded, errors = [], []
    for f in found:
        try:
            loaded.append(load_layer(f, schema, policy))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))
    result = {"config_layers": [e for e, _, _ in loaded] + [
        {"id": "central", "source": "central", "repo": None, "dir": f"config/projects/{project_id}", "status": "applied"}]}
    merged, copies, provenance, repo_owner = {}, {}, {}, {}
    for entry, docs, files in reversed(loaded):  # lowest precedence first
        for rel, doc in docs.items():
            base = merged.get(rel)
            if base is None:
                base = validate.load_yaml(project_dir / rel)
            try:
                if rel == "repositories.yaml":  # append-only, never the generic merge
                    merged[rel], added = _append_repos(base, doc, entry["id"], repo_owner)
                    provenance.update({f"{rel}:additional_repos.{n}": entry["id"] for n in added})
                    continue
                merged[rel] = merge(base if isinstance(base, dict) else {}, doc)
            except ValueError as exc:
                raise ValueError(f"{entry['id']}/{LAYER_DIR}/{rel}: {exc}") from None
            for path in leaves(doc):
                key = f"{rel}:{path}"
                for stale in [k for k in provenance if k.startswith(key + ".")]:
                    del provenance[stale]
                provenance[key] = entry["id"]
        for rel, p in files.items():
            copies[rel] = p
            provenance[rel] = entry["id"]
    if not any(e["status"] == "applied" for e, _, _ in loaded):
        return result

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(project_dir, out_dir)
    for rel, doc in merged.items():
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / rel).write_text(yaml.safe_dump(doc, sort_keys=False))
    for rel, p in copies.items():
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, out_dir / rel)
    errs = validate.validate_project(out_dir, schema, defaults)
    if errs:
        raise ValueError("the merged config is invalid:\n" + "\n".join(errs))
    # The hash covers every effective file: merged ones by content, the rest by digest.
    files = {}
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(out_dir).as_posix()
            files[rel] = merged[rel] if rel in merged else "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    canonical = yaml.safe_dump(files, sort_keys=True, default_flow_style=False)
    result.update(config_dir=out_dir, config_provenance=provenance,
                  config_hash="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(), files=files)
    return result


# Auto-discovery (no routed project) starts from these security toggles
# (skills/project-resolver/SKILL.md "Auto-Discovery Fallback"); a layer may only raise them.
AUTO_TOGGLES = {"pii_sanitization": False, "repo_files_fetch": False, "stp_review": True, "std_review": True}


def resolve_auto(schema, defaults, targets, env):
    """Auto-discovery mode: the .qualityflow/ layers in SOURCE_REPO_PATH, merged
    together with no central dir under them. The shallowest layer (the repo
    root's, when it has one) names the project; one declaring another is skipped. Only project.yaml
    applies: auto mode has no config_dir for the other files to land in.
    None when there is no layer. Raises ValueError.
    """
    repositories = {"primary_repo": {"name": "source", "local_path_env": "SOURCE_REPO_PATH"}}
    found = discover(repositories, targets, env, ["primary_repo"])
    if not found:
        return None
    marker = validate.load_yaml(found[-1][3] / LAYER_DIR / "project.yaml")
    policy = {"dir": None, "project_id": marker.get("project_id") if isinstance(marker, dict) else None,
              "toggles": {**defaults.get("feature_toggles", {}), **AUTO_TOGGLES}, "allow_sensitive": []}
    loaded, errors = [], []
    for f in found:
        try:
            loaded.append(load_layer(f, schema, policy))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("\n".join(errors))
    project, provenance = {}, {}
    for entry, docs, files in reversed(loaded):  # lowest precedence first
        try:
            project = merge(project, docs.get("project.yaml", {}))
        except ValueError as exc:
            raise ValueError(f"{entry['id']}/{LAYER_DIR}/project.yaml: {exc}") from None
        provenance.update({f"project.yaml:{p}": entry["id"] for p in leaves(docs.get("project.yaml", {}))})
        unused = sorted(set(docs) - {"project.yaml"} | set(files))
        if unused:
            entry.setdefault("warnings", []).append(
                "auto-discovery applies project.yaml only, not " + ", ".join(unused))
    return {"project_id": policy["project_id"], "config_layers": [e for e, _, _ in loaded],
            "config_provenance": provenance, "project": project}
