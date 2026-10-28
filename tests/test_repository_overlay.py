"""Ticket scope is shared by project resolution and runner checkout/LSP setup."""
import sys
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.repository_overlay import apply_overlay, entries, for_ticket, scoped_environment
import pipeline_runner


def test_ticket_overlay_filters_adds_overrides_and_scopes_bridges(tmp_path, monkeypatch):
    repos = {
        'primary_repo': {'name': 'my-repo', 'local_path_env': 'SOURCE_REPO_PATH'},
        'tier2_repo': {'name': 'tests', 'local_path_env': 'TESTS_REPO_PATH'},
        'repo_files': {'rules': {'repo': 'tier2_repo', 'path': 'AGENTS.md'}},
    }
    overlay = tmp_path / 'outputs/PROJ-12345/repositories.overlay.yaml'
    assert apply_overlay(repos, overlay) is repos
    assert for_ticket(tmp_path, 'PROJ-12345') is None
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / 'go.mod').write_text('module example\n')
    overlay.parent.mkdir(parents=True)
    overlay.write_text(yaml.safe_dump({
        'only': ['primary'],
        'add': [{'name': 'my-fork', 'org': 'my-org'}],
        'paths': {'my-repo': str(checkout), 'my-fork': str(checkout)},
    }))
    config = tmp_path / 'config/projects/example'
    config.mkdir(parents=True)
    (config / 'repositories.yaml').write_text(yaml.safe_dump(repos))
    (tmp_path / 'config/routing.yaml').write_text(
        'routes:\n  - project: example\n    jira_prefixes: [PROJ]\n')
    resolved = for_ticket(tmp_path, 'PROJ-12345')
    assert 'tier2_repo' not in resolved
    assert resolved['repo_files'] == {}
    assert resolved['additional_repos'][0]['name'] == 'my-fork'
    original_env = {'SOURCE_REPO_PATH': '/old', 'TESTS_REPO_PATH': '/excluded', 'OTHER': 'keep'}
    env = scoped_environment(resolved, original_env)
    assert env == {'SOURCE_REPO_PATH': str(checkout), 'MY_FORK_REPO_PATH': str(checkout), 'OTHER': 'keep'}
    assert original_env['SOURCE_REPO_PATH'] == '/old'
    assert 'local_path' not in repos['primary_repo']
    monkeypatch.setattr(pipeline_runner.shutil, 'which', lambda _: '/bin/example')
    bridges = pipeline_runner._lsp_bridge_servers(env)
    assert set(bridges) == {'lsp_source', 'lsp_my_fork'}
    assert all(cmd[1] == str(checkout) for cmd in bridges.values())
    overlay.write_text('only: []\n')
    assert not list(entries(apply_overlay(repos, overlay)))
    overlay.write_text('only: primary\n')
    with pytest.raises(ValueError, match='only must be'):
        apply_overlay(repos, overlay)

    # Exercise the actual resolver contract, including the YAML file consumed
    # by downstream tools, and prove removing the overlay restores the output.
    source = Path(__file__).resolve().parents[1]
    integration = tmp_path / 'integration'
    shutil.copytree(source / 'config', integration / 'config')
    resolver = integration / 'skills/project-resolver/resolve.py'
    resolver.parent.mkdir(parents=True)
    shutil.copy(source / 'skills/project-resolver/resolve.py', resolver)
    routing = integration / 'config/routing.yaml'
    routing.write_text('routes:\n  - project: example\n    jira_prefixes: [PROJ]\n')
    def context():
        result = subprocess.run([sys.executable, str(resolver), 'PROJ-12345'],
                                cwd=integration, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return yaml.safe_load(result.stdout)['project_context']
    baseline = context()
    ticket_overlay = integration / 'outputs/PROJ-12345/repositories.overlay.yaml'
    ticket_overlay.parent.mkdir(parents=True)
    ticket_overlay.write_text('only: []\n')
    ctx = context()
    assert not list(entries(ctx['repositories']))
    assert yaml.safe_load(Path(ctx['repositories_file']).read_text()) == ctx['repositories']
    ticket_overlay.unlink()
    assert context() == baseline
