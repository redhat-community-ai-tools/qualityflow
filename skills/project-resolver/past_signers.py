#!/usr/bin/env python3
"""Who signs the team's STPs: the people named on the filled-in `*Sign-off:*`
and `*PM/Lead Agreement:*` lines of the design-docs repo's merged STPs.

An STP leaves those lines as placeholders for its author to fill. This tells
the author whom to ask: per person, how many lines they signed, in which
folders (a design-docs repo keeps one folder per group), and when the newest
STP they signed last changed.

  past_signers.py --repo ORG/NAME [--ref BRANCH] [--exclude PATH]...

Prints YAML, most recent first. Reads the repo through `gh` (one tarball, plus
one commit lookup per STP that has a filled line). Exit 1 when `gh` fails.
"""

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile

import yaml

LINE = re.compile(r"\*(Sign-off|PM/Lead Agreement):\*+\s*(.+)")
LINK = re.compile(r"^\[([^\]]+)\]\(@?([\w.-]+)\)")    # [Name](@handle)
HANDLE = re.compile(r"\(@([\w.-]+)\)")                # Name (@handle)


def parse_signer(text):
    """(name, github handle or None) from a filled line's value, or None for a
    placeholder ("[Name/Date]") or a value with no name."""
    text = text.strip().lstrip("*").strip()
    m = LINK.match(text)
    if m:
        name, handle = m.group(1), m.group(2)
    else:
        handle = (HANDLE.search(text) or [None, None])[1]
        name = text.strip("[]")
    name = re.split(r"\s*[(/,—]|\s+\d", name, maxsplit=1)[0].strip(" []*")
    if not name or "Name" in name.split() or not re.search(r"[A-Za-z]{2}", name):
        return None
    return name, handle


def signers(files, dates):
    """files: {path: text}; dates: {path: ISO date}. Returns the per-person list."""
    people = {}
    for path, text in files.items():
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        for kind, value in LINE.findall(text):
            parsed = parse_signer(value)
            if not parsed:
                continue
            name, handle = parsed
            p = people.setdefault(name.lower(), {"name": name, "github": None, "sign_offs": 0,
                                                 "agreements": 0, "folders": set(), "last": "",
                                                 "example": path})
            p["github"] = p["github"] or handle
            p["sign_offs" if kind == "Sign-off" else "agreements"] += 1
            p["folders"].add(folder)
            if dates.get(path, "") > p["last"]:
                p["last"], p["example"] = dates[path], path
    out = sorted(people.values(), key=lambda p: (p["last"], p["sign_offs"] + p["agreements"]),
                 reverse=True)
    for p in out:
        p["folders"] = sorted(p["folders"])
    return out


def gh(*args):
    r = subprocess.run(["gh", "api", *args], capture_output=True)
    if r.returncode:
        sys.exit("gh api %s failed: %s" % (args[0], r.stderr.decode(errors="replace").strip()))
    return r.stdout


def fetch(repo, ref, exclude):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(gh("repos/%s/tarball/%s" % (repo, ref))), mode="r:gz") as tar:
        for m in tar.getmembers():
            path = m.name.split("/", 1)[-1]  # drop the tarball's top-level dir
            if m.isfile() and path.endswith(".md") and path not in exclude:
                text = tar.extractfile(m).read().decode(errors="replace")  # type: ignore[union-attr]  # a file member
                if LINE.search(text):
                    files[path] = text
    # ponytail: the date is the STP's last commit, not the line's own date,
    # which teams write in a dozen formats. Parse those if it ever misleads.
    dates = {}
    for path in files:
        commits = json.loads(gh("repos/%s/commits?sha=%s&path=%s&per_page=1" % (repo, ref, path)))
        dates[path] = commits[0]["commit"]["committer"]["date"][:10] if commits else ""
    return files, dates


def self_test():
    cases = {
        "Martin Smith (@msmith) / 2026-04-15": ("Martin Smith", "msmith"),
        "[Ana Lee](@alee)/30-07-2026": ("Ana Lee", "alee"),
        "Ron Cohen, 04/2026": ("Ron Cohen", None),
        "Kate Moss/2026-05-05": ("Kate Moss", None),
        "Jose Manuel Ortiz, Apr 22, 2026": ("Jose Manuel Ortiz", None),
        "[Dan Holm / 1.5.2026]": ("Dan Holm", None),
        "Ron Cohen (ron@example.com) / 01-06-2026": ("Ron Cohen", None),
        "* Den Shaw / 2026-06-30": ("Den Shaw", None),
        "Mike Hen (@mhen)": ("Mike Hen", "mhen"),
        "[Name/Date]": None,
        "[Name/Date — confirms awareness and acceptance of this risk]": None,
    }
    for text, want in cases.items():
        assert parse_signer(text) == want, (text, parse_signer(text), want)
    files = {
        "stps/a/x.md": "- *Sign-off:* Ron Cohen / 2026-01-01\n- *PM/Lead Agreement:* [Ana Lee](@alee)/1-1-2026\n"
                       "- *Sign-off:* [Name/Date]\n",
        "stps/b/y.md": "- *Sign-off:* ron cohen, 05/2026\n",
    }
    out = signers(files, {"stps/a/x.md": "2026-01-02", "stps/b/y.md": "2026-05-03"})
    assert [p["name"] for p in out] == ["Ron Cohen", "Ana Lee"], out
    assert out[0]["sign_offs"] == 2 and out[0]["folders"] == ["stps/a", "stps/b"]
    assert out[0]["last"] == "2026-05-03" and out[0]["example"] == "stps/b/y.md"
    assert out[1]["agreements"] == 1 and out[1]["github"] == "alee"
    print("self-test: OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo")
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--exclude", action="append", default=[], help="a path to skip (the STP template)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.repo:
        ap.error("--repo is required")
    yaml.safe_dump(signers(*fetch(a.repo, a.ref, set(a.exclude))), sys.stdout,
                   sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    main()
