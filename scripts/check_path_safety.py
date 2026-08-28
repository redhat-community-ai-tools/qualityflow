#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115",
#     "uvicorn>=0.34",
#     "pyyaml>=6.0",
#     "markdown>=3.7",
#     "bleach>=6.1",
#     "gitpython>=3.1",
#     "authlib>=1.3",
#     "httpx>=0.27",
#     "itsdangerous>=2.2",
# ]
# ///
"""Regression check for the path-traversal fixes.

An unauthenticated GET used to read an arbitrary .yaml file off the filesystem:

    /api/coverage/test/{project}/raw?commit=../../../../../config/routing

`commit` was interpolated straight into a path with no validation, and `/raw`
streamed the result back. The upload side had always required a strict SHA;
only the read side was missing it.

What this pins:
  1. Every untrusted value reduced by _safe_path_segment stays a *child* of the
     directory it is joined to. The predecessor sanitizer mapped separators to
     '_' but passed a bare '..' through unchanged, so a single '..' segment
     still traversed one level.
  2. The commit-SHA regex the read endpoints now share with the writer rejects
     traversal payloads and accepts real SHAs.
  3. The directory helpers that build storage paths from request input contain
     their result.

Run: uv run scripts/check_path_safety.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Payloads that must never escape. The first is the one that actually worked.
TRAVERSALS = [
    "../../../../../config/routing",
    "..",
    ".",
    "../etc/passwd",
    "..%2f..%2fetc",
    "a/../../b",
    "/etc/passwd",
    "....//....//etc",
    "",
    "\x00etc",
]


def main() -> int:
    os.environ["QF_DEV"] = "1"  # ui.py refuses to import without a key otherwise
    tmp = Path(tempfile.mkdtemp(prefix="qf-path-check-"))
    os.environ["QF_OUTPUTS_DIR"] = str(tmp / "outputs")
    os.environ["QF_CONFIG_DIR"] = str(tmp / "config")
    sys.path.insert(0, str(ROOT))
    import ui  # noqa: E402 — env must be set before import

    base = Path("/base/dir")
    for payload in TRAVERSALS:
        seg = ui._safe_path_segment(payload)
        assert "/" not in seg and "\\" not in seg, f"{payload!r} -> {seg!r} kept a separator"
        assert seg not in (".", "..", ""), f"{payload!r} -> {seg!r} is a relative segment"
        resolved = (base / seg).resolve()
        assert resolved.parent == base, f"{payload!r} -> {seg!r} escaped to {resolved}"

    # Ordinary values must survive intact — a sanitizer that mangles real input
    # is its own outage.
    for ok in ("my-org", "my_project.v2", "CNV-80969", "abc1234def"):
        assert ui._safe_path_segment(ok) == ok, f"mangled a legitimate value: {ok!r}"

    # The commit SHA gate the read endpoints share with the upload path.
    for payload in TRAVERSALS:
        assert not ui._COMMIT_SHA_RE.match(payload), f"commit regex accepted {payload!r}"
    for sha in ("abc1234", "a" * 40, "ABC1234def5678"):
        assert ui._COMMIT_SHA_RE.match(sha), f"commit regex rejected a real SHA: {sha!r}"
    for bad in ("abc123", "g" * 8, "a" * 41):  # too short / non-hex / too long
        assert not ui._COMMIT_SHA_RE.match(bad), f"commit regex accepted {bad!r}"

    # The directory helpers that take request input must contain their result.
    for helper, args, root in (
        (ui._coverage_repo_dir, ("..", ".."), ui.COVERAGE_DIR),
        (ui._test_cov_project_dir, ("../../etc",), ui._TEST_COVERAGE_DIR),
        (ui._product_coverage_dir, ("..",), ui.COVERAGE_DIR / "_product"),
    ):
        got = helper(*args).resolve()
        assert got.is_relative_to(root.resolve()), f"{helper.__name__}{args} escaped to {got}"

    print(f"path-safety self-check passed ({len(TRAVERSALS)} traversal payloads contained, "
          "commit gate + 3 dir helpers verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
