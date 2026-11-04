#!/usr/bin/env python3
"""Put Jira's own text into a jira_data.yaml snapshot.

The collector writes {JIRA_ID}_jira_data.yaml itself, and a model may shorten
it: descriptions cut to one line, comments dropped, and with them the names a
plan needs (endpoints, metric names). This re-reads each issue in the snapshot
from Jira's REST API and overwrites summary, description and comments with
what Jira returns, word for word. Every other field stays as written.

    python3 skills/jira-parser/stamp.py outputs/PROJ-123/stp/PROJ-123_jira_data.yaml

Credentials: JIRA_URL plus JIRA_USERNAME + JIRA_API_TOKEN (basic auth), or
JIRA_API_TOKEN alone (a bearer personal access token). Read-only.
"""
import base64
import json
import os
import re
import sys
import urllib.request

import yaml

PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def fetch(key):
    base = os.environ["JIRA_URL"].rstrip("/")
    token, user = os.environ["JIRA_API_TOKEN"], os.environ.get("JIRA_USERNAME")
    auth = ("Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()) if user else "Bearer " + token
    req = urllib.request.Request(f"{base}/rest/api/2/issue/{key}?fields=summary,description,comment",
                                 headers={"Authorization": auth, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["fields"]


def stamp(issue, fields, comments=True):
    issue["summary"] = fields.get("summary") or issue.get("summary")
    issue["description"] = fields.get("description") or ""
    if comments:
        issue["comments"] = [{"author": (c.get("author") or {}).get("displayName"),
                              "created": c.get("created"), "body": c.get("body") or "",
                              "pr_urls_found": sorted(set(PR_URL.findall(c.get("body") or "")))}
                             for c in (fields.get("comment") or {}).get("comments", [])]


def main(path):
    data = yaml.safe_load(open(path)) or {}
    main_issue = data.get("main_issue") or {}
    issues = [(main_issue, True)] + [(i, False) for k in ("linked_issues", "subtasks")
                                     for i in data.get(k) or [] if isinstance(i, dict)]
    done = 0
    for issue, with_comments in issues:
        if not issue.get("key"):
            continue
        try:
            stamp(issue, fetch(issue["key"]), with_comments)
            done += 1
        except Exception as exc:  # a linked issue we may not read: keep what was written
            print(f"{issue['key']}: not stamped ({exc})", file=sys.stderr)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=1000)
    print(f"stamped {done} of {len(issues)} issues with Jira's own text: {path}")
    return 0 if main_issue.get("key") and done else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
