"""Shared test guards.

ui.py's lifespan starts background pollers. Tests that enter the lifespan
already stub the git-sync loop one by one; the review-cycle poller is stubbed
here, once, for every test. Without this, a local run picks up the real GitHub
token from the repo's .env, the lifespan starts a real poll against the real
project config, and that thread holds the review-cycle lock while the poll
tests run — five of them then fail with {"status": "busy"} (CI never saw it:
no .env there). Real API calls from a test run are the actual hazard.
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _no_review_cycle_poller(monkeypatch):
    ui = sys.modules.get("ui")  # only patch once a test module has imported ui
    if ui is not None:
        monkeypatch.setattr(ui, "_start_review_cycle_loop", lambda: None)
        # Every run/approve/push body may carry Jira creds, and .env may set
        # JIRA_URL: never let attribution call the real Jira /myself.
        # tests/test_member_identity.py restores the real helper over a mocked urlopen.
        monkeypatch.setattr(ui, "_jira_identity", lambda *a, **k: (None, None))
