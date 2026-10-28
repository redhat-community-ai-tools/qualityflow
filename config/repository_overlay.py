"""Ticket-local repository selection; shared config is never modified."""
import copy
import re
from pathlib import Path

import yaml


def entries(repositories):
    for key, value in repositories.items():
        if key.endswith('_repo') and isinstance(value, dict):
            yield key.removesuffix('_repo'), value
        elif key == 'additional_repos':
            for repo in value:
                yield 'additional', repo


def apply_overlay(repositories, overlay_path):
    """Filter configured repos, append additions, then override local paths."""
    path = Path(overlay_path)
    if not path.exists():
        return repositories
    overlay = yaml.safe_load(path.read_text())
    if not isinstance(overlay, dict) or set(overlay) - {'only', 'add', 'paths'}:
        raise ValueError(f'{path}: expected only, add, paths mapping')
    only = overlay.get('only')
    additions = overlay.get('add', [])
    paths = overlay.get('paths', {})
    if (only is not None and (not isinstance(only, list) or not all(isinstance(x, str) for x in only))
            or not isinstance(additions, list) or not all(isinstance(x, dict) and x.get('name') for x in additions)
            or not isinstance(paths, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in paths.items())):
        raise ValueError(f'{path}: only must be a string list, add an entry list, paths a name-to-path mapping')
    result = copy.deepcopy(repositories)
    for key in list(result):
        if key.endswith('_repo') and isinstance(result[key], dict):
            repo = result[key]
            if only is not None and not {key, key.removesuffix('_repo'), repo.get('name')}.intersection(only):
                del result[key]
        elif key == 'additional_repos' and only is not None:
            result[key] = [r for r in result[key] if {'additional', 'additional_repos', r.get('name')}.intersection(only)]
    if additions:
        result.setdefault('additional_repos', []).extend(copy.deepcopy(additions))
    for _, repo in entries(result):
        if repo['name'] in paths:
            repo['local_path'] = str(Path(paths[repo['name']]).expanduser().resolve())
        if not repo.get('local_path_env') and repo.get('local_path'):
            repo['local_path_env'] = re.sub(r'[^A-Z0-9]', '_', repo['name'].upper()) + '_REPO_PATH'
    # A removed repository must not be fetched indirectly through repo_files.
    if 'repo_files' in result:
        result['repo_files'] = {k: v for k, v in result['repo_files'].items() if v['repo'] in result}
    return result


def scoped_environment(repositories, env):
    """Return a child-only environment with checkout variables restricted."""
    selected = {r['local_path_env']: r.get('local_path', env.get(r['local_path_env'], ''))
                for _, r in entries(repositories) if r.get('local_path_env')}
    return {**{k: v for k, v in env.items() if not k.endswith('_REPO_PATH')}, **selected}


def for_ticket(root, jira_id):
    """Runner lookup; canonical GitHub IDs use owner-repo-number."""
    root = Path(root)
    overlay = root / 'outputs' / jira_id / 'repositories.overlay.yaml'
    if not overlay.exists():
        return None
    routing = yaml.safe_load((root / 'config/routing.yaml').read_text())
    project = routing.get('default_project')
    for route in routing.get('routes', []):
        if (jira_id.split('-')[0] in route.get('jira_prefixes', []) or any(
                jira_id.startswith(repo.replace('/', '-') + '-') for repo in route.get('github_repos', []))):
            project = route['project']
            break
    if not project:
        raise ValueError(f'Cannot resolve repository overlay for {jira_id}: no project route')
    repos = yaml.safe_load((root / 'config/projects' / project / 'repositories.yaml').read_text())
    return apply_overlay(repos, overlay)
