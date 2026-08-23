"""QualityFlow Dashboard — FastAPI backend serving the pipeline UI.

Launch:
    uv run ui.py              # starts on http://localhost:8420
    uv run ui.py --port 9000  # custom port
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115",
#     "uvicorn>=0.34",
#     "pyyaml>=6.0",
#     "markdown>=3.7",
#     "gitpython>=3.1",
# ]
# ///

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import markdown
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger("qualityflow.dashboard")

ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
RESOURCES = ROOT
CONFIG = ROOT / "config"

# ---------------------------------------------------------------------------
# Claude / Vertex AI client
# ---------------------------------------------------------------------------

_VERTEX_PROJECT = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
_VERTEX_REGION = os.environ.get("CLOUD_ML_REGION", "us-east5")
_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4@20250514")

def _get_claude_client():
    """Return an Anthropic client (Vertex or direct API)."""
    if _VERTEX_PROJECT:
        from anthropic import AnthropicVertex
        return AnthropicVertex(project_id=_VERTEX_PROJECT, region=_VERTEX_REGION)
    elif _ANTHROPIC_API_KEY:
        from anthropic import Anthropic
        return Anthropic(api_key=_ANTHROPIC_API_KEY)
    return None

def _claude_available() -> bool:
    return bool(_VERTEX_PROJECT or _ANTHROPIC_API_KEY)

from contextlib import asynccontextmanager


def _get_git_short_hash() -> str:
    """Return short git commit hash, or 'unknown'."""
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Startup: initial git sync, background loop, and banner."""
    _git_sync()
    _start_git_sync_loop()
    commit = _get_git_short_hash()
    n_pipelines = len(list((OUTPUTS / "state").glob("*/pipeline_state.yaml"))) if (OUTPUTS / "state").is_dir() else 0
    logger.info(
        "QualityFlow Dashboard ready  |  commit=%s  |  pipelines=%d  |  outputs=%s  |  claude=%s",
        commit, n_pipelines, str(OUTPUTS), "yes" if _claude_available() else "no",
    )
    yield
    logger.info("QualityFlow Dashboard shutting down gracefully")


app = FastAPI(title="QualityFlow Dashboard", version="0.1.0", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Middleware — security headers
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response as StarletteResponse


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request for log correlation."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = req_id
        response: StarletteResponse = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self'"
        )
        # Cache: HTML pages = no-cache, API = short-lived
        path = request.url.path
        if path == "/" or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        elif path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "private, max-age=5")
        return response


app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)

# ---------------------------------------------------------------------------
# Middleware — CORS for cross-cluster dashboard access
# ---------------------------------------------------------------------------

_CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else []


class CORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        allowed = origin and (_is_trusted_origin(origin) or origin in _CORS_ORIGINS)

        # Handle CORS preflight (OPTIONS) — must return 204 before call_next
        if request.method == "OPTIONS" and allowed:
            response = StarletteResponse(status_code=204)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            response.headers["Access-Control-Max-Age"] = "3600"
            response.headers["Vary"] = "Origin"
            return response

        response: StarletteResponse = await call_next(request)
        # Allow same-origin always; allow configured origins
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            response.headers["Access-Control-Max-Age"] = "3600"
            response.headers["Vary"] = "Origin"
        return response


def _is_trusted_origin(origin: str) -> bool:
    """Check if origin is a QualityFlow dashboard instance."""
    from urllib.parse import urlparse
    host = urlparse(origin).hostname or ""
    return host in ("localhost", "127.0.0.1") or "qualityflow" in host


# Always enable CORS — the middleware checks trusted origins + configured origins
app.add_middleware(CORSMiddleware)

# ---------------------------------------------------------------------------
# Auth — API key for write operations
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("QUALITYFLOW_API_KEY", "")
_BASE_URL = os.environ.get("QUALITYFLOW_BASE_URL", "")  # e.g. https://qualityflow.apps.mycluster.com

# Simple in-memory rate limiter for write endpoints (per-IP, sliding window)
_rate_limits: dict[str, list[float]] = {}
_rate_limits_lock = threading.Lock()
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 30  # max write requests per window per IP


def _check_rate_limit(request: Request):
    """Rate limit write endpoints. Raises 429 if exceeded."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _rate_limits_lock:
        window = _rate_limits.setdefault(client_ip, [])
        # Prune old entries
        _rate_limits[client_ip] = [t for t in window if now - t < _RATE_LIMIT_WINDOW]
        if len(_rate_limits[client_ip]) >= _RATE_LIMIT_MAX:
            raise HTTPException(429, "Rate limit exceeded. Try again later.")
        _rate_limits[client_ip].append(now)
        # Prune stale IPs periodically (keep dict bounded)
        if len(_rate_limits) > 1000:
            cutoff = now - _RATE_LIMIT_WINDOW * 2
            stale_ips = [ip for ip, ts in _rate_limits.items() if not ts or ts[-1] < cutoff]
            for ip in stale_ips:
                _rate_limits.pop(ip, None)


def _require_api_key(x_api_key: str = Header(default="")):
    """Verify the API key for write endpoints. No-op in local mode (no key set)."""
    if not _API_KEY:
        return  # Local development — no auth required
    if not x_api_key or not hmac.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(403, "Invalid or missing API key")


def _check_api_key_or_origin(request: Request, x_api_key: str):
    """Allow request if API key matches OR if it originates from the dashboard UI."""
    if not _API_KEY:
        return
    # Check referer for same-origin dashboard requests
    referer = request.headers.get("referer", "")
    if referer:
        from urllib.parse import urlparse
        ref_host = urlparse(referer).hostname or ""
        if ref_host in ("localhost", "127.0.0.1") or "qualityflow" in ref_host:
            return
    if not x_api_key or not hmac.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(403, "Invalid or missing API key")


# ---------------------------------------------------------------------------
# Git Sync — pulls outputs from GitLab in production
# ---------------------------------------------------------------------------

_git_sync_lock = threading.Lock()
_last_sync: str | None = None


def _git_sync() -> dict:
    """Pull latest changes from the configured Git remote."""
    global _last_sync
    repo_url = os.environ.get("GIT_REPO_URL", "")
    branch = os.environ.get("GIT_BRANCH", "main")

    if not repo_url:
        return {"status": "skipped", "reason": "GIT_REPO_URL not set (local mode)"}

    with _git_sync_lock:
        try:
            import shutil

            import git  # type: ignore[import-untyped]

            # Clone/pull into a scratch directory, then copy data into the app
            repo_path = Path("/tmp/qualityflow-repo")
            if (repo_path / ".git").exists():
                repo = git.Repo(repo_path)
                origin = repo.remotes.origin
                origin.fetch()
                origin.pull(branch, ff_only=True)
            else:
                repo_path.mkdir(parents=True, exist_ok=True)
                git.Repo.clone_from(repo_url, repo_path, branch=branch, depth=1)

            # Sync outputs/ into the app directory (config/ and resources/ are baked in)
            src = repo_path / "outputs"
            dst = ROOT / "outputs"
            if src.is_dir():
                for item in src.rglob("*"):
                    rel = item.relative_to(src)
                    target = dst / rel
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(item, target)

            _last_sync = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return {"status": "ok", "synced_at": _last_sync, "branch": branch}
        except Exception as e:
            logger.warning("Git sync failed: %s", e)
            return {"status": "error", "error": str(e)}


def _start_git_sync_loop() -> None:
    """Background thread that periodically syncs from Git."""
    interval = int(os.environ.get("GIT_SYNC_INTERVAL", "300"))
    repo_url = os.environ.get("GIT_REPO_URL", "")
    if not repo_url:
        logger.info("GIT_REPO_URL not set — git sync disabled (local mode)")
        return

    logger.info("Starting git sync loop (interval=%ds, branch=%s)",
                interval, os.environ.get("GIT_BRANCH", "main"))

    def loop():
        import time
        while True:
            time.sleep(interval)
            result = _git_sync()
            logger.info("Git sync: %s", result.get("status"))

    t = threading.Thread(target=loop, daemon=True)
    t.start()


@app.get("/api/sync")
def trigger_sync():
    """Manually trigger a git pull to refresh outputs."""
    result = _git_sync()
    return result


@app.get("/api/status")
def dashboard_status():
    """Dashboard health and sync status."""
    has_api_key = bool(_API_KEY)
    return {
        "version": app.version,
        "mode": "production" if os.environ.get("GIT_REPO_URL") or has_api_key else "local",
        "auth_enabled": has_api_key,
        "git_repo": os.environ.get("GIT_REPO_URL", ""),
        "git_branch": os.environ.get("GIT_BRANCH", "main"),
        "last_sync": _last_sync,
        "root": str(ROOT),
        "manager_mode": bool(_get_peers()),
    }


@app.post("/api/post-check")
async def post_check(request: Request):
    """POST reachability test — verifies POST requests reach the backend."""
    return {"ok": True, "method": "POST", "source": "qualityflow-backend"}


@app.get("/healthz")
def healthz():
    """Liveness probe for Kubernetes."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness probe — checks outputs directory is readable and writable."""
    try:
        if not OUTPUTS.is_dir():
            OUTPUTS.mkdir(parents=True, exist_ok=True)
        # Verify read access by listing contents
        list(OUTPUTS.iterdir())
        # Verify write access by touching a probe file
        probe = OUTPUTS / ".readyz_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return {"status": "ready", "outputs_accessible": True, "outputs_writable": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Not ready: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict:
    """Read a YAML file, return empty dict on failure."""
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def _read_md_frontmatter(path: Path) -> dict[str, str]:
    """Extract YAML front-matter from a markdown file."""
    try:
        text = path.read_text()
    except Exception:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}


def _file_modified(path: Path) -> str | None:
    """Return ISO-formatted mtime (UTC) or None."""
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


_jira_ids_cache: tuple[float, list[str]] = (0.0, [])
_JIRA_IDS_CACHE_TTL = 3  # seconds — brief cache to avoid redundant scans within a refresh cycle


def _scan_jira_ids() -> list[str]:
    """Discover all Jira IDs with any output artifacts (cached briefly)."""
    global _jira_ids_cache
    now = time.time()
    if now - _jira_ids_cache[0] < _JIRA_IDS_CACHE_TTL:
        return _jira_ids_cache[1]
    ids: set[str] = set()
    for sub in ("stp", "std", "reviews", "state", "go-tests", "python-tests"):
        d = OUTPUTS / sub
        if d.is_dir():
            for child in d.iterdir():
                if child.is_dir() and re.match(r"^[A-Z]+-\d+$", child.name):
                    ids.add(child.name)
    result = sorted(ids)
    _jira_ids_cache = (now, result)
    return result


# ---------------------------------------------------------------------------
# API: Pipelines
# ---------------------------------------------------------------------------

from starlette.responses import JSONResponse  # noqa: E402 — used for ETag responses


@app.get("/api/pipelines")
def list_pipelines(request: Request):
    """List all Jira IDs and their pipeline state summary."""
    results = []
    for jira_id in _scan_jira_ids():
        state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
        if state_file.exists():
            state = _read_yaml(state_file)
        else:
            state = _infer_state(jira_id)
        pr_info = _read_pr_info(jira_id)
        pr_summary = None
        if pr_info:
            pr_summary = {
                "url": pr_info.get("url", ""),
                "state": pr_info.get("state", "unknown"),
                "number": pr_info.get("number"),
            }
            if pr_info.get("tier2_pr"):
                pr_summary["tier2_url"] = pr_info["tier2_pr"].get("url", "")
        results.append({
            "jira_id": jira_id,
            "project_id": state.get("project_id", _infer_project(jira_id)),
            "has_state_file": state_file.exists(),
            "phases": _summarize_phases(state, jira_id),
            "updated": state.get("updated", _file_modified(state_file) if state_file.exists() else None),
            "pr": pr_summary,
        })
    # ETag: hash the response to enable 304 Not Modified for auto-refresh
    body = json.dumps(results, default=str)
    etag = '"' + hashlib.md5(body.encode()).hexdigest()[:16] + '"'
    if_none_match = request.headers.get("if-none-match", "")
    if if_none_match == etag:
        return StarletteResponse(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=results, headers={"ETag": etag})


@app.get("/api/pipelines/matrix")
def pipeline_matrix():
    """All pipelines as a flat table for the comparison view."""
    rows = []
    phase_names = ["stp", "std", "codegen"]

    for jira_id in _scan_jira_ids():
        state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
        state = _read_yaml(state_file) if state_file.exists() else _infer_state(jira_id)
        phases = state.get("phases", {})
        pr_info = _read_pr_info(jira_id)

        completed = sum(1 for p in phase_names if phases.get(p, {}).get("status") == "completed")
        total = len(phase_names)

        if completed == total:
            overall = "complete"
        elif completed == 0:
            overall = "not_started"
        else:
            overall = "in_progress"

        current_phase = None
        for p in phase_names:
            if phases.get(p, {}).get("status") != "completed":
                current_phase = p
                break

        row: dict = {
            "jira_id": jira_id,
            "project_id": state.get("project_id", _infer_project(jira_id)),
            "overall": overall,
            "progress": f"{completed}/{total}",
            "current_phase": current_phase,
        }
        for p in phase_names:
            phase_data = phases.get(p, {})
            row[p] = {
                "status": phase_data.get("status", "pending"),
                "verdict": phase_data.get("verdict"),
            }

        if pr_info:
            row["pr"] = {
                "url": pr_info.get("url", ""),
                "state": pr_info.get("state", "unknown"),
            }
        else:
            row["pr"] = None

        rows.append(row)

    return rows


@app.get("/api/pipelines/{jira_id}")
def get_pipeline(jira_id: str):
    """Get full pipeline state for a Jira ID."""
    state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
    if state_file.exists():
        state = _read_yaml(state_file)
    else:
        state = _infer_state(jira_id)
    state["_artifacts"] = _list_artifacts(jira_id)
    # Include feature toggles so frontend can show skipped phases
    project_id = state.get("project_id") or state.get("project") or _infer_project(jira_id)
    toggles = _load_project_toggles(project_id)
    state["feature_toggles"] = toggles
    # PR info — refresh state from GitHub if token available
    pr_info = _read_pr_info(jira_id)
    if pr_info and pr_info.get("url"):
        token = _GITHUB_TOKEN if pr_info.get("platform", "github") == "github" else _GITLAB_TOKEN
        if token:
            try:
                repo = pr_info.get("target_repo", "")
                nr = pr_info.get("number")
                if repo and nr:
                    data = _github_api("GET", f"https://api.github.com/repos/{repo}/pulls/{nr}", token)
                    new_state = "merged" if data.get("merged") else data.get("state", pr_info.get("state"))
                    if new_state != pr_info.get("state"):
                        pr_info["state"] = new_state
                        _write_pr_info(jira_id, pr_info)
            except Exception:
                pass
        state["pr"] = pr_info

    return state


_routing_cache: tuple[float, dict] = (0.0, {})
_ROUTING_CACHE_TTL = 30  # seconds — routing.yaml rarely changes


def _infer_project(jira_id: str) -> str:
    """Infer project from Jira prefix (cached routing)."""
    global _routing_cache
    now = time.time()
    if now - _routing_cache[0] > _ROUTING_CACHE_TTL:
        _routing_cache = (now, _read_yaml(CONFIG / "routing.yaml"))
    routing = _routing_cache[1]
    prefix = jira_id.split("-")[0].upper()
    for route in routing.get("routes", []):
        # v2 format: jira_prefixes list
        for p in route.get("jira_prefixes", []):
            if p.upper() == prefix:
                return route.get("project", prefix.lower())
    return prefix.lower()


def _load_project_toggles(project_id: str) -> dict:
    """Load merged feature toggles for a project (defaults + project overrides)."""
    defaults = _read_yaml(CONFIG / "_defaults.yaml")
    default_toggles = defaults.get("feature_toggles", {}) if defaults else {}
    proj_yaml = CONFIG / "projects" / project_id / "project.yaml"
    proj_cfg = _read_yaml(proj_yaml) if proj_yaml.exists() else {}
    return {**default_toggles, **proj_cfg.get("feature_toggles", {})}


def _extract_verdict_from_md(path: Path) -> str | None:
    """Extract verdict (PASS/WARN/FAIL/APPROVED/etc.) from a markdown file."""
    try:
        text = path.read_text()[:2000]
        for pattern in (r"Verdict:\s*(PASS|WARN|FAIL)",
                        r"Verdict:\s*(APPROVED_WITH_FINDINGS|APPROVED|NEEDS_REVISION)"):
            m = re.search(pattern, text)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _find_test_files(jira_id: str, lang: str) -> list[Path]:
    """Generated test files for a ticket, across the layouts QF has shipped.

    Tests have lived in three places over time: top-level type-first
    (outputs/go-tests/{id}/), JIRA-first (outputs/{id}/go-tests/), and nested
    under the STD dir (outputs/std/{id}/go-tests/). Check all three.
    """
    pattern = "*_test.go" if lang == "go" else "test_*.py"
    dirs = [
        OUTPUTS / f"{lang}-tests" / jira_id,
        OUTPUTS / jira_id / f"{lang}-tests",
        OUTPUTS / "std" / jira_id / f"{lang}-tests",
    ]
    files: list[Path] = []
    for d in dirs:
        if d.is_dir():
            files.extend(d.glob(pattern))
    return files


def _infer_state(jira_id: str) -> dict:
    """Build a synthetic state from file existence when no state YAML exists."""
    phases = {}
    # STP (includes internal review + refine)
    stp = OUTPUTS / "stp" / jira_id / f"{jira_id}_test_plan.md"
    stp_rev = OUTPUTS / "reviews" / jira_id / f"{jira_id}_stp_review.md"
    stp_data: dict = {"status": "completed" if stp.exists() else "pending",
                      "output": str(stp.relative_to(ROOT)) if stp.exists() else None}
    if stp_rev.exists():
        stp_data["verdict"] = _extract_verdict_from_md(stp_rev)
    phases["stp"] = stp_data
    # STD (includes internal review + refine)
    std = OUTPUTS / "std" / jira_id / f"{jira_id}_test_description.yaml"
    std_rev = OUTPUTS / "reviews" / jira_id / f"{jira_id}_std_review.md"
    std_data: dict = {"status": "completed" if std.exists() else "pending",
                      "output": str(std.relative_to(ROOT)) if std.exists() else None}
    if std_rev.exists():
        std_data["verdict"] = _extract_verdict_from_md(std_rev)
    phases["std"] = std_data
    # Test generation (any language)
    has_go = bool(_find_test_files(jira_id, "go"))
    has_py = bool(_find_test_files(jira_id, "python"))
    phases["codegen"] = {"status": "completed" if has_go or has_py else "pending"}

    # Apply approval gates
    project_id = _infer_project(jira_id)
    gates = _get_approval_gates(project_id)
    approvals = _read_approvals(jira_id)
    for gate_phase in gates:
        phase_data = phases.get(gate_phase, {})
        if phase_data.get("status") == "completed":
            approval = approvals.get(gate_phase)
            if approval:
                phase_data["approval"] = approval
            else:
                phase_data["status"] = "awaiting_approval"

    # PR info — refresh state from GitHub/GitLab if token available
    pr_info = _read_pr_info(jira_id)
    if pr_info and pr_info.get("url"):
        token = _GITHUB_TOKEN if pr_info.get("platform", "github") == "github" else _GITLAB_TOKEN
        if token:
            try:
                repo = pr_info.get("target_repo", "")
                nr = pr_info.get("number")
                if repo and nr:
                    data = _github_api("GET", f"https://api.github.com/repos/{repo}/pulls/{nr}", token)
                    new_state = data.get("state", pr_info.get("state"))
                    if data.get("merged"):
                        new_state = "merged"
                    if new_state != pr_info.get("state"):
                        pr_info["state"] = new_state
                        _write_pr_info(jira_id, pr_info)
            except Exception:
                pass  # non-critical — use cached state

    result: dict = {
        "ticket_id": jira_id,
        "project_id": _infer_project(jira_id),
        "phases": phases,
        "gates": gates,
        "_inferred": True,
    }
    if pr_info:
        result["pr"] = pr_info
    return result


def _summarize_phases(state: dict, _jira_id: str) -> dict:
    """Return a compact phase → status map."""
    phases = state.get("phases", {})
    summary = {}
    for phase_name in ("stp", "std", "codegen"):
        phase = phases.get(phase_name, {})
        summary[phase_name] = {
            "status": phase.get("status", "pending"),
            "verdict": phase.get("verdict"),
        }
    return summary


# ---------------------------------------------------------------------------
# API: Activity Feed
# ---------------------------------------------------------------------------

_ARTIFACT_EVENT_MAP: list[tuple[str, str, str]] = [
    # (output_subdir, filename_pattern, event_label)
    ("stp", "{id}_ticket_assessment.md", "Ticket assessed"),
    ("stp", "{id}_test_plan.md", "STP generated"),
    ("reviews", "{id}_stp_review.md", "STP reviewed"),
    ("std", "{id}_test_description.yaml", "STD generated"),
    ("reviews", "{id}_std_review.md", "STD reviewed"),
]


_activity_cache: tuple[float, list[dict]] = (0.0, [])
_ACTIVITY_CACHE_TTL = 5  # seconds — activity feed is expensive, cache briefly


@app.get("/api/activity")
def activity_feed(limit: int = 30):
    """Recent activity across all pipelines, reverse chronological (cached)."""
    global _activity_cache
    now = time.time()
    if now - _activity_cache[0] < _ACTIVITY_CACHE_TTL:
        return _activity_cache[1][:limit]
    events: list[dict] = []
    for jira_id in _scan_jira_ids():
        project_id = _infer_project(jira_id)

        # Artifact-based events
        for subdir, pattern, label in _ARTIFACT_EVENT_MAP:
            path = OUTPUTS / subdir / jira_id / pattern.format(id=jira_id)
            if path.exists():
                verdict = _extract_verdict_from_md(path) if path.suffix == ".md" else None
                events.append({
                    "jira_id": jira_id,
                    "project_id": project_id,
                    "event": label,
                    "verdict": verdict,
                    "timestamp": _file_modified(path),
                })

        # Go tests
        go_files = _find_test_files(jira_id, "go")
        if go_files:
            latest = max(f.stat().st_mtime for f in go_files)
            events.append({
                "jira_id": jira_id, "project_id": project_id,
                "event": f"Go tests generated ({len(go_files)} files)",
                "timestamp": datetime.fromtimestamp(latest, tz=timezone.utc).isoformat(timespec="seconds"),
            })

        # Python tests
        py_files = _find_test_files(jira_id, "python")
        if py_files:
            latest = max(f.stat().st_mtime for f in py_files)
            events.append({
                "jira_id": jira_id, "project_id": project_id,
                "event": f"Python tests generated ({len(py_files)} files)",
                "timestamp": datetime.fromtimestamp(latest, tz=timezone.utc).isoformat(timespec="seconds"),
            })

        # PR events
        pr_info = _read_pr_info(jira_id)
        if pr_info and pr_info.get("created"):
            events.append({
                "jira_id": jira_id, "project_id": project_id,
                "event": "PR pushed",
                "url": pr_info.get("url", ""),
                "timestamp": pr_info["created"],
            })
            # PR state change (close/reopen)
            if pr_info.get("state_changed"):
                state_label = pr_info.get("state", "unknown")
                events.append({
                    "jira_id": jira_id, "project_id": project_id,
                    "event": f"PR {state_label}",
                    "url": pr_info.get("url", ""),
                    "timestamp": pr_info["state_changed"],
                })

        # Approval events
        approvals = _read_approvals(jira_id)
        for phase, approval in approvals.items():
            if approval.get("timestamp"):
                events.append({
                    "jira_id": jira_id, "project_id": project_id,
                    "event": f"{phase.replace('_', ' ').title()} {approval.get('action', 'reviewed')}",
                    "timestamp": approval["timestamp"],
                })

    # Sort by timestamp descending, cache full result
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    _activity_cache = (time.time(), events)
    return events[:limit]


# ---------------------------------------------------------------------------
# API: Metrics
# ---------------------------------------------------------------------------

_metrics_cache: dict[str, tuple[float, dict]] = {}
_METRICS_CACHE_TTL = 10


def _compute_value_metrics(project_id: str, states: list[dict]) -> dict:
    """Derive value-demonstration metrics from existing pipeline data."""
    # states carry "ticket_id" (pipeline_state.yaml + _infer_state); "jira_id" fallback for safety
    jira_ids = [str(jid) for s in states
                if (jid := s.get("ticket_id") or s.get("jira_id"))]

    # --- tests_generated ---
    go_files = 0
    py_files = 0
    total_bytes = 0
    for jid in jira_ids:
        for f in _find_test_files(jid, "go"):
            go_files += 1
            total_bytes += f.stat().st_size
        for f in _find_test_files(jid, "python"):
            py_files += 1
            total_bytes += f.stat().st_size
    # ponytail: ~50 bytes/line estimate, good enough
    estimated_lines = total_bytes // 50 if total_bytes else 0

    # --- artifacts_produced ---
    stps = stds = reviews = 0
    for jid in jira_ids:
        if (OUTPUTS / "stp" / jid / f"{jid}_test_plan.md").exists():
            stps += 1
        if (OUTPUTS / "std" / jid / f"{jid}_test_description.yaml").exists():
            stds += 1
        if (OUTPUTS / "reviews" / jid / f"{jid}_stp_review.md").exists():
            reviews += 1
        if (OUTPUTS / "reviews" / jid / f"{jid}_std_review.md").exists():
            reviews += 1

    # --- phase_durations (from file mtimes) ---
    stp_durations: list[float] = []
    std_durations: list[float] = []
    codegen_durations: list[float] = []
    for s in states:
        jid = s.get("ticket_id") or s.get("jira_id") or ""
        if not jid:
            continue
        created_str = s.get("created", "")
        if not created_str:
            continue
        try:
            created_ts = datetime.fromisoformat(created_str).timestamp()
        except Exception:
            continue
        stp_path = OUTPUTS / "stp" / jid / f"{jid}_test_plan.md"
        std_path = OUTPUTS / "std" / jid / f"{jid}_test_description.yaml"
        if stp_path.exists():
            stp_mt = stp_path.stat().st_mtime
            stp_durations.append((stp_mt - created_ts) / 3600)
            if std_path.exists():
                std_mt = std_path.stat().st_mtime
                std_durations.append((std_mt - stp_mt) / 3600)
                # codegen = latest test file mtime - std mtime
                latest_test = 0.0
                for tf in _find_test_files(jid, "go") + _find_test_files(jid, "python"):
                    latest_test = max(latest_test, tf.stat().st_mtime)
                if latest_test > std_mt:
                    codegen_durations.append((latest_test - std_mt) / 3600)

    def _avg(lst: list[float]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    # --- pr_stats ---
    total_prs = 0
    merged_prs = 0
    merge_hours: list[float] = []
    for jid in jira_ids:
        pr_path = OUTPUTS / "state" / jid / "pr_info.yaml"
        if not pr_path.exists():
            continue
        try:
            pr = yaml.safe_load(pr_path.read_text()) or {}
        except Exception:
            continue
        total_prs += 1
        if pr.get("state") == "merged":
            merged_prs += 1
            pr_created = pr.get("created")
            pr_merged = pr.get("state_changed") or pr.get("merged_at")
            if pr_created and pr_merged:
                try:
                    c = datetime.fromisoformat(pr_created).timestamp()
                    m = datetime.fromisoformat(pr_merged).timestamp()
                    merge_hours.append((m - c) / 3600)
                except Exception:
                    pass

    # --- coverage ---
    cov_repos = _get_coverage_repos_config()
    project_repos = [r for r in cov_repos if r.get("project_id") == project_id]
    current_pct = None
    delta = None
    patch_coverage_pct = None
    uploads = 0
    cov_trend: list[dict] = []
    for repo_cfg in project_repos:
        org, repo = repo_cfg.get("org", ""), repo_cfg.get("repo", "")
        if not org or not repo:
            continue
        latest = _load_latest_coverage(org, repo)
        if latest:
            uploads += 1
            totals = latest.get("totals", {})
            current_pct = totals.get("coverage_pct") or totals.get("line_rate")
            if isinstance(current_pct, (int, float)):
                current_pct = round(current_pct, 1)
        history = _load_coverage_history(org, repo)
        if history:
            uploads = max(uploads, len(history))
            for entry in history[-30:]:
                t = entry.get("totals", {})
                pct = t.get("coverage_pct") or t.get("line_rate")
                if pct is not None:
                    cov_trend.append({"date": entry.get("timestamp", "")[:10], "coverage": round(pct, 1)})
            if len(history) >= 2:
                old_t = history[0].get("totals", {})
                old_pct = old_t.get("coverage_pct") or old_t.get("line_rate")
                if old_pct is not None and current_pct is not None:
                    delta = round(current_pct - old_pct, 1)

    # --- review_quality ---
    total_verdicts = 0
    approved = 0
    findings = 0
    needs_rev = 0
    for jid in jira_ids:
        for review_name in (f"{jid}_stp_review.md", f"{jid}_std_review.md"):
            rp = OUTPUTS / "reviews" / jid / review_name
            if not rp.exists():
                continue
            try:
                content = rp.read_text()[:2000]
            except Exception:
                continue
            total_verdicts += 1
            cl = content.lower()
            if "needs_revision" in cl or "needs revision" in cl:
                needs_rev += 1
            elif "approved_with_findings" in cl or "approved with findings" in cl:
                findings += 1
            elif "approved" in cl:
                approved += 1

    return {
        "tests_generated": {
            "total_files": go_files + py_files,
            "go_files": go_files,
            "python_files": py_files,
            "estimated_lines": estimated_lines,
        },
        "artifacts_produced": {
            "stps": stps,
            "stds": stds,
            "reviews": reviews,
            "total": stps + stds + reviews,
        },
        "phase_durations": {
            "stp_avg_hours": _avg(stp_durations),
            "std_avg_hours": _avg(std_durations),
            "codegen_avg_hours": _avg(codegen_durations),
            "total_avg_hours": _avg([sum(x) for x in zip(stp_durations, std_durations, codegen_durations)]) if stp_durations and std_durations and codegen_durations else None,
        },
        "pr_stats": {
            "total_prs": total_prs,
            "merged": merged_prs,
            "merge_rate_pct": round(merged_prs / total_prs * 100) if total_prs else 0,
            "avg_merge_hours": round(sum(merge_hours) / len(merge_hours), 1) if merge_hours else None,
        },
        "coverage": {
            "current_pct": current_pct,
            "delta": delta,
            "patch_coverage_pct": patch_coverage_pct,
            "uploads": uploads,
            "trend": cov_trend,
        },
        "review_quality": {
            "total": total_verdicts,
            "approved_pct": round(approved / total_verdicts * 100) if total_verdicts else 0,
            "needs_revision_pct": round(needs_rev / total_verdicts * 100) if total_verdicts else 0,
            "findings_pct": round(findings / total_verdicts * 100) if total_verdicts else 0,
        },
    }


@app.get("/api/metrics/{project_id}")
def get_metrics(project_id: str):
    """Aggregated pipeline metrics for a project (or _all for cross-project)."""
    global _metrics_cache
    now = time.time()
    cached = _metrics_cache.get(project_id)
    if cached and now - cached[0] < _METRICS_CACHE_TTL:
        return cached[1]

    all_ids = list(_scan_jira_ids())
    is_all = project_id == "_all"

    # Filter by project
    project_pipelines: dict[str, list[dict]] = {}
    for jira_id in all_ids:
        pid = _infer_project(jira_id)
        if not is_all and pid != project_id:
            continue
        state_path = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
        if state_path.exists():
            state = _read_yaml(state_path)
        else:
            state = _infer_state(jira_id)
        if state:
            project_pipelines.setdefault(pid or "unknown", []).append(state)

    if is_all:
        # Cross-project comparison
        projects_summary = []
        for pid, states in sorted(project_pipelines.items()):
            total = len(states)
            completed = sum(1 for s in states if all(
                (s.get("phases", {}).get(p, {}).get("status") or "pending") in ("completed", "skipped")
                for p in ("stp", "std", "codegen")
            ))
            failed = sum(1 for s in states if any(
                (s.get("phases", {}).get(p, {}).get("status")) == "failed"
                for p in ("stp", "std", "codegen")
            ))
            projects_summary.append({
                "project_id": pid,
                "total": total,
                "completed": completed,
                "failed": failed,
                "completion_pct": round(completed / total * 100) if total else 0,
            })
        result = {"projects": projects_summary}
        _metrics_cache[project_id] = (now, result)
        return result

    # Single-project metrics
    states = []
    for group in project_pipelines.values():
        states.extend(group)

    phase_names = ["stp", "std", "codegen"]
    phase_completion: dict[str, dict] = {}
    verdict_distribution: dict[str, dict] = {}
    timeline_buckets: dict[str, dict] = {}
    total = len(states)
    completed = 0
    failed = 0
    in_progress = 0

    for phase in phase_names:
        phase_completion[phase] = {"completed": 0, "total": 0}
        verdict_distribution[phase] = {}

    for state in states:
        phases = state.get("phases", {})
        all_done = True
        any_failed = False
        any_active = False
        for phase in phase_names:
            ph = phases.get(phase, {})
            status = ph.get("status", "pending")
            phase_completion[phase]["total"] += 1
            if status == "completed":
                phase_completion[phase]["completed"] += 1
            elif status == "failed":
                any_failed = True
            elif status in ("in_progress", "awaiting_approval"):
                any_active = True
            if status != "completed" and status != "skipped":
                all_done = False
            verdict = ph.get("verdict")
            if verdict:
                verdict_distribution[phase][verdict] = verdict_distribution[phase].get(verdict, 0) + 1
        if all_done and phases:
            completed += 1
        if any_failed:
            failed += 1
        if any_active:
            in_progress += 1

        # Timeline from timestamps
        ts = state.get("created") or state.get("updated") or ""
        day = ts[:10] if len(ts) >= 10 else ""
        if day:
            bucket = timeline_buckets.setdefault(day, {"date": day, "created": 0, "completed": 0})
            bucket["created"] += 1
            if all_done:
                bucket["completed"] += 1

    timeline = sorted(timeline_buckets.values(), key=lambda b: b["date"])

    result = {
        "totals": {
            "pipelines": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "completion_pct": round(completed / total * 100) if total else 0,
        },
        "phase_completion": phase_completion,
        "verdict_distribution": verdict_distribution,
        "timeline": timeline,
        "value": _compute_value_metrics(project_id, states),
    }
    _metrics_cache[project_id] = (now, result)
    return result


# ---------------------------------------------------------------------------
# API: Org roll-up (manager view across self-hosted team instances)
# ---------------------------------------------------------------------------
#
# Each team runs its own dashboard against its own cluster's config + outputs.
# A manager instance lists those team instances as "peers" and polls their
# /api/rollup?local=true, so no shared datastore is needed — the team APIs
# that already exist are the source of truth. Standalone (no peers) is the
# default: /api/rollup then just returns this instance's own projects.

def _get_peers() -> list[dict]:
    """Peer team instances to roll up. Empty => standalone (team) mode.

    Source (first that exists wins):
      1. config/peers.yaml  ->  {peers: [{label, url, token?}]}  (or a bare list)
      2. env QF_PEERS       ->  "cnv=https://cnv.example,mtv=https://mtv.example"
    """
    path = Path(os.environ["QF_PEERS_FILE"]) if os.environ.get("QF_PEERS_FILE") else CONFIG / "peers.yaml"
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text()) or {}
            peers = data.get("peers", []) if isinstance(data, dict) else data
            return [p for p in peers if p.get("url")]
        except Exception:
            return []
    peers = []
    for chunk in os.environ.get("QF_PEERS", "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        label, _, url = chunk.partition("=")
        url = url or label
        peers.append({"label": label.strip(), "url": url.strip()})
    return peers


def _local_rollup() -> dict:
    """This instance's per-project summary + value metrics, for one cluster."""
    cluster = os.environ.get("QF_CLUSTER_LABEL", "") or "local"
    projects = []
    for p in get_metrics("_all").get("projects", []):
        pid = p["project_id"]
        proj_yaml = CONFIG / "projects" / pid / "project.yaml"
        display = _read_yaml(proj_yaml).get("display_name", pid.upper()) if proj_yaml.exists() else pid.upper()
        projects.append({**p, "display_name": display, "cluster": cluster,
                         "value": get_metrics(pid).get("value", {})})
    return {"cluster": cluster, "projects": projects}


def _fetch_peer_rollup(peer: dict) -> dict:
    """Fetch a peer's own (local) rollup. Never asks the peer to expand further."""
    base = peer["url"].rstrip("/")
    req = urllib.request.Request(f"{base}/api/rollup?local=true")
    token = peer.get("token") or ""
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=8) as resp:  # ponytail: 8s/peer, make async if fleet grows
        data = json.loads(resp.read().decode())
    # stamp the configured label so the manager view is consistent even if the peer defaults to "local"
    data["cluster"] = peer.get("label") or data.get("cluster") or base
    for pr in data.get("projects", []):
        pr["cluster"] = data["cluster"]
    return data


@app.get("/api/rollup")
def rollup(local: bool = False):
    """Org roll-up. On a team instance (or ?local=true) returns just this
    cluster; on a manager instance (peers configured) merges all peers."""
    mine = _local_rollup()
    if local:
        return mine
    clusters = [mine]
    for peer in _get_peers():
        try:
            clusters.append(_fetch_peer_rollup(peer))
        except Exception as e:
            clusters.append({"cluster": peer.get("label") or peer.get("url"),
                             "error": str(e), "projects": []})
    return {"clusters": clusters,
            "projects": [pr for c in clusters for pr in c.get("projects", [])]}


# ---------------------------------------------------------------------------
# API: Artifacts
# ---------------------------------------------------------------------------

@app.get("/api/artifacts/{jira_id}")
def list_artifacts(jira_id: str):
    """List all artifacts for a Jira ID."""
    return _list_artifacts(jira_id)


def _list_artifacts(jira_id: str) -> list[dict]:
    """Scan outputs for artifacts belonging to a Jira ID."""
    artifacts = []
    artifact_map = [
        ("stp", f"stp/{jira_id}/{jira_id}_test_plan.md", "STP"),
        ("stp_review", f"reviews/{jira_id}/{jira_id}_stp_review.md", "STP Review"),
        ("std", f"std/{jira_id}/{jira_id}_test_description.yaml", "STD"),
        ("std_review", f"reviews/{jira_id}/{jira_id}_std_review.md", "STD Review"),
    ]
    for artifact_type, rel_path, label in artifact_map:
        full = OUTPUTS / rel_path
        if full.exists():
            artifacts.append({
                "type": artifact_type,
                "label": label,
                "path": f"outputs/{rel_path}",
                "modified": _file_modified(full),
                "size": full.stat().st_size,
            })
    # Go test files
    go_dir = OUTPUTS / "go-tests" / jira_id
    if go_dir.is_dir():
        for f in sorted(go_dir.glob("*_test.go")):
            artifacts.append({
                "type": "go_test",
                "label": f"Go: {f.name}",
                "path": str(f.relative_to(ROOT)),
                "modified": _file_modified(f),
                "size": f.stat().st_size,
            })
    # Python test files
    py_dir = OUTPUTS / "python-tests" / jira_id
    if py_dir.is_dir():
        for f in sorted(py_dir.glob("test_*.py")):
            artifacts.append({
                "type": "python_test",
                "label": f"Python: {f.name}",
                "path": str(f.relative_to(ROOT)),
                "modified": _file_modified(f),
                "size": f.stat().st_size,
            })
    return artifacts


@app.get("/api/artifacts/{jira_id}/{artifact_type}")
def get_artifact(jira_id: str, artifact_type: str):
    """Read and return a specific artifact with rendered HTML for markdown."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")
    path_map = {
        "stp": OUTPUTS / "stp" / jira_id / f"{jira_id}_test_plan.md",
        "stp_review": OUTPUTS / "reviews" / jira_id / f"{jira_id}_stp_review.md",
        "std": OUTPUTS / "std" / jira_id / f"{jira_id}_test_description.yaml",
        "std_review": OUTPUTS / "reviews" / jira_id / f"{jira_id}_std_review.md",
    }
    path = path_map.get(artifact_type)

    # Support viewing individual Go/Python test files by path
    if not path or not path.exists():
        # Check if it's a go_test or python_test with a filename suffix
        # e.g., go_test:nad_live_update_test.go
        if ":" in artifact_type:
            kind, filename = artifact_type.split(":", 1)
            # Prevent path traversal — filename must be a bare name
            if "/" in filename or "\\" in filename or ".." in filename:
                raise HTTPException(400, f"Invalid filename: {filename}")
            if kind == "go_test":
                path = OUTPUTS / "go-tests" / jira_id / filename
            elif kind == "python_test":
                path = OUTPUTS / "python-tests" / jira_id / filename

    if not path or not path.exists():
        raise HTTPException(404, f"Artifact '{artifact_type}' not found for {jira_id}")

    # Final safety check: resolved path must be within OUTPUTS
    try:
        path.resolve().relative_to(OUTPUTS.resolve())
    except ValueError:
        raise HTTPException(400, "Path escapes outputs directory")

    raw = path.read_text()
    is_md = path.suffix == ".md"
    fmt_map = {".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".go": "go", ".py": "python"}
    return {
        "type": artifact_type,
        "path": str(path.relative_to(ROOT)),
        "raw": raw,
        "html": markdown.markdown(raw, extensions=["tables", "fenced_code"]) if is_md else None,
        "format": fmt_map.get(path.suffix, "text"),
    }


# ---------------------------------------------------------------------------
# API: Skills & Commands
# ---------------------------------------------------------------------------

@app.get("/api/skills")
def list_skills():
    """List all registered skills with metadata."""
    skills_dir = RESOURCES / "skills"
    skills = []
    categories = {
        "project-resolver": "Config", "pipeline-state": "Config",
        "ticket-validator": "Validation", "ticket-assessor": "Validation",
        "lsp-tracer": "Analysis", "feature-finder": "Analysis",
        "pr-analyzer": "Analysis", "pattern-detector": "Analysis",
        "requirement-mapper": "Mapping", "scenario-builder": "Mapping",
        "tier-classifier": "Mapping",
        "template-engine": "Generation", "std-generator": "Generation",
        "go-test-generator": "Generation", "python-test-generator": "Generation",
        "std-orchestrator": "Generation",
        "go-stub-generator": "Stubs", "python-stub-generator": "Stubs",
        "stp-reviewer": "Review", "std-reviewer": "Review",
        "review-rules-extractor": "Review",
        "jira-parser": "Utility", "link-resolver": "Utility",
        "pii-sanitizer": "Utility", "output-validator": "Utility",
        "table-generator": "Utility", "doc-to-stp": "Utility",
    }
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = _read_md_frontmatter(skill_md)
        name = fm.get("name", skill_dir.name)
        skills.append({
            "name": name,
            "description": fm.get("description", ""),
            "category": categories.get(name, "Other"),
            "path": str(skill_md.relative_to(ROOT)),
        })
    return skills


@app.get("/api/commands")
def list_commands():
    """List all registered commands."""
    cmds_dir = RESOURCES / "commands"
    commands = []
    if cmds_dir.is_dir():
        for cmd_file in sorted(cmds_dir.glob("*.md")):
            fm = _read_md_frontmatter(cmd_file)
            commands.append({
                "name": fm.get("name", cmd_file.stem),
                "description": fm.get("description", ""),
                "path": str(cmd_file.relative_to(ROOT)),
            })
    return commands


def _parse_skill_sections(text: str) -> dict:
    """Parse a SKILL.md or command .md into structured sections.

    Extracts key sections like Purpose, When to Use, Tools Required,
    Input, Output, and Workflow by splitting on ## headings.
    """
    # Strip frontmatter
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)

    sections: dict[str, str] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+)", line)
        if m:
            if current_heading:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(current_lines).strip()

    # Extract title from first # heading
    title_match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
    if title_match:
        sections["_title"] = title_match.group(1).strip()

    # Extract inline metadata like **Phase:** and **User-Invocable:**
    for key in ("Phase", "User-Invocable"):
        m = re.search(rf"\*\*{key}:\*\*\s*(.+)", body)
        if m:
            sections["_" + key.lower().replace("-", "_")] = m.group(1).strip()

    return sections


@app.get("/api/skills/{skill_name}")
def get_skill_detail(skill_name: str):
    """Get full detail for a single skill including parsed sections."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", skill_name)
    skill_md = RESOURCES / "skills" / safe / "SKILL.md"
    if not skill_md.exists():
        raise HTTPException(404, f"Skill not found: {skill_name}")

    fm = _read_md_frontmatter(skill_md)
    text = skill_md.read_text()
    sections = _parse_skill_sections(text)

    return {
        "name": fm.get("name", safe),
        "description": fm.get("description", ""),
        "model": fm.get("model", ""),
        "path": str(skill_md.relative_to(ROOT)),
        "phase": sections.get("_phase", ""),
        "user_invocable": sections.get("_user_invocable", ""),
        "purpose": sections.get("Purpose", ""),
        "when_to_use": sections.get("When to Use", sections.get("When To Use", "")),
        "tools": sections.get("Tools Required", sections.get("Tools", "")),
        "input": sections.get("Input", ""),
        "output": sections.get("Output", sections.get("Output Format", "")),
        "sections": {k: v for k, v in sections.items() if not k.startswith("_")},
    }


@app.get("/api/commands/{cmd_name}")
def get_command_detail(cmd_name: str):
    """Get full detail for a single command including parsed sections."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", cmd_name)
    cmd_file = RESOURCES / "commands" / f"{safe}.md"
    if not cmd_file.exists():
        raise HTTPException(404, f"Command not found: {cmd_name}")

    fm = _read_md_frontmatter(cmd_file)
    text = cmd_file.read_text()
    sections = _parse_skill_sections(text)

    return {
        "name": fm.get("name", safe),
        "description": fm.get("description", ""),
        "argument_hint": fm.get("argument-hint", ""),
        "allowed_tools": fm.get("allowed-tools", ""),
        "path": str(cmd_file.relative_to(ROOT)),
        "purpose": sections.get("Purpose", ""),
        "workflow": sections.get("Workflow", ""),
        "input": sections.get("Input", ""),
        "output": sections.get("Output", sections.get("Output Format", "")),
        "sections": {k: v for k, v in sections.items() if not k.startswith("_")},
    }


# ---------------------------------------------------------------------------
# API: Project Config
# ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    """List configured projects."""
    projects_dir = CONFIG / "projects"
    routing = _read_yaml(CONFIG / "routing.yaml")
    prefix_map = {}
    for route in (routing.get("routes", []) if routing else []):
        proj = route.get("project", "")
        prefixes = route.get("jira_prefixes", [])
        if proj and prefixes:
            prefix_map[proj] = prefixes
    projects = []
    if projects_dir.is_dir():
        for proj_dir in sorted(projects_dir.iterdir()):
            proj_yaml = proj_dir / "project.yaml"
            if proj_yaml.exists():
                cfg = _read_yaml(proj_yaml)
                prefixes = prefix_map.get(proj_dir.name, [proj_dir.name.upper()])
                projects.append({
                    "id": proj_dir.name,
                    "display_name": cfg.get("display_name", proj_dir.name.upper()),
                    "jira_prefix": prefixes[0] if prefixes else proj_dir.name.upper(),
                    "jira_prefixes": prefixes,
                    "feature_toggles": cfg.get("feature_toggles", {}),
                })
    return projects


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    """Get full project configuration."""
    proj_dir = CONFIG / "projects" / project_id
    if not proj_dir.is_dir():
        raise HTTPException(404, f"Project '{project_id}' not found")

    # Load defaults + project config and merge toggles
    defaults = _read_yaml(CONFIG / "_defaults.yaml")
    default_toggles = defaults.get("feature_toggles", {})
    proj_cfg = _read_yaml(proj_dir / "project.yaml")
    merged_toggles = {**default_toggles, **proj_cfg.get("feature_toggles", {})}

    # Load related config files
    components = _read_yaml(proj_dir / "components.yaml")
    repos = _read_yaml(proj_dir / "repositories.yaml")
    env = _read_yaml(proj_dir / "environment.yaml")
    jira_cfg = _read_yaml(proj_dir / "jira.yaml")

    # Routing info
    routing = _read_yaml(CONFIG / "routing.yaml")
    prefixes = []
    for r in routing.get("routes", []):
        if r.get("project") == project_id:
            prefixes.extend(r.get("jira_prefixes", []))

    # Config files list
    config_files = []
    if proj_dir.is_dir():
        for f in sorted(proj_dir.iterdir()):
            if f.is_file() and f.suffix in (".yaml", ".yml"):
                config_files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": _file_modified(f),
                })

    return {
        "id": project_id,
        "display_name": proj_cfg.get("display_name", project_id.upper()),
        "description": proj_cfg.get("description", ""),
        "jira_prefixes": prefixes,
        "feature_toggles": merged_toggles,
        "versioning": proj_cfg.get("versioning", {}),
        "scope_boundaries": proj_cfg.get("scope_boundaries", {}),
        "repositories": {
            "primary": repos.get("primary_repo", {}),
            "tier2": repos.get("tier2_repo", {}),
            "additional": repos.get("additional_repos", []),
        },
        "components": list(components.get("component_package_map", {}).keys()),
        "environment": env,
        "jira": {
            "project_key": jira_cfg.get("project_key", ""),
            "custom_fields": list(jira_cfg.get("custom_fields", {}).keys()),
        },
        "config_files": config_files,
        "stp_document": proj_cfg.get("stp_document", {}),
    }


@app.put("/api/projects/{project_id}/toggles")
async def update_toggles(project_id: str, request: Request, x_api_key: str = Header(default="")):
    """Update feature toggles for a project."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)
    proj_dir = CONFIG / "projects" / project_id
    proj_yaml = proj_dir / "project.yaml"
    if not proj_yaml.exists():
        raise HTTPException(404, f"Project '{project_id}' not found")

    body = await request.json()
    toggles = body.get("feature_toggles") or body

    # Read current config, update toggles, write back (atomic)
    def _update_toggles(cfg):
        if "feature_toggles" not in cfg:
            cfg["feature_toggles"] = {}
        cfg["feature_toggles"].update(toggles)
        return cfg

    cfg = _atomic_yaml_update(proj_yaml, _update_toggles)

    return {"status": "ok", "feature_toggles": cfg["feature_toggles"]}


@app.post("/api/projects")
async def create_project(request: Request, x_api_key: str = Header(default="")):
    """Create a new project from the onboarding wizard."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)
    body = await request.json()

    # Validate required fields
    project_id = body.get("project_id", "").strip().lower()
    if not project_id or not re.match(r"^[a-z][a-z0-9_-]*$", project_id):
        raise HTTPException(400, "Invalid project_id: must be lowercase alphanumeric (a-z, 0-9, -, _)")
    proj_dir = CONFIG / "projects" / project_id
    if proj_dir.exists():
        raise HTTPException(409, f"Project '{project_id}' already exists")

    display_name = body.get("display_name", project_id.upper())
    description = body.get("description", "")
    jira_prefixes = body.get("jira_prefixes", [])
    jira_url = body.get("jira_url", "https://your-org.atlassian.net")
    primary_repo = body.get("primary_repo", "")
    primary_language = body.get("primary_language", "go")
    primary_build = body.get("primary_build", "")
    tier2_repo = body.get("tier2_repo", "")
    tier2_language = body.get("tier2_language", "python")
    components = body.get("components", [])
    feature_toggles = body.get("feature_toggles", {})
    versioning = body.get("versioning", {})

    # Create directory structure
    proj_dir.mkdir(parents=True)
    (proj_dir / "patterns").mkdir()
    (proj_dir / "reference").mkdir()
    (proj_dir / "templates" / "stp").mkdir(parents=True)

    # project.yaml
    proj_cfg = {
        "project_id": project_id,
        "display_name": display_name,
        "description": description,
        "feature_toggles": feature_toggles or {},
        "versioning": versioning or {"product_name": display_name, "platform_name": "Kubernetes", "current_version": "1.0"},
        "stp_document": {"header": f"{display_name} Test plan"},
        "sig_mappings": {},
        "decorator_mappings": {},
        "scope_boundaries": {
            "validation_gate": f"Would removing {display_name} make this test meaningless?",
            "in_scope_resources": [],
            "out_of_scope_if_only": ["Pod", "Deployment", "StatefulSet", "ConfigMap", "Secret",
                                     "Service", "Namespace", "PersistentVolumeClaim", "Node"],
            "cli_tools": ["kubectl"],
            "domain_vocabulary": [],
        },
    }
    _write_yaml(proj_dir / "project.yaml", proj_cfg)

    # jira.yaml
    jira_cfg = {
        "instance": {"url": jira_url, "browse_pattern": f"{jira_url}/browse/{{key}}"},
        "prefixes": jira_prefixes,
        "custom_fields": {},
        "pr_url_scan_pattern": "https://github.com/.*/pull/\\d+",
    }
    _write_yaml(proj_dir / "jira.yaml", jira_cfg)

    # repositories.yaml
    repos_cfg: dict = {}
    if primary_repo:
        repos_cfg["primary_repo"] = {
            "full_name": primary_repo,
            "language": primary_language,
            "build_system": primary_build or ("bazel" if primary_language == "go" else ""),
        }
    if tier2_repo:
        repos_cfg["tier2_repo"] = {"full_name": tier2_repo, "language": tier2_language}
    repos_cfg["additional_repos"] = []
    _write_yaml(proj_dir / "repositories.yaml", repos_cfg)

    # components.yaml
    comp_map = {c: {"packages": []} for c in components} if components else {}
    _write_yaml(proj_dir / "components.yaml", {"component_package_map": comp_map})

    # environment.yaml
    env_cfg = {
        "platform": {"name": "Kubernetes", "short_name": "K8s",
                      "cli_tools": ["kubectl"]},
        "cluster_requirements": {"topology": "Single-node", "min_worker_nodes": 1},
        "version_constraints": {},
    }
    _write_yaml(proj_dir / "environment.yaml", env_cfg)

    # pii_exceptions.yaml
    _write_yaml(proj_dir / "pii_exceptions.yaml", {"exceptions": []})

    # tier files based on toggles
    if feature_toggles.get("tier1_tests", True):
        _write_yaml(proj_dir / "tier1.yaml", {
            "enabled": True, "language": "go", "framework": "ginkgo-v2",
            "import_base": "", "imports": {"dot_imports": [], "standard": ["context", "time"]},
        })
    if feature_toggles.get("tier2_tests", True):
        _write_yaml(proj_dir / "tier2.yaml", {
            "enabled": True, "language": "python", "framework": "pytest",
            "python_packages": {}, "import_patterns": {"standard": ["import logging", "import pytest"]},
        })

    # STP template placeholder
    tmpl = proj_dir / "templates" / "stp" / "stp-template.md"
    tmpl.write_text(f"# {display_name} — Test Plan Template\n\nCustomize this template for your project.\n")

    # Add routes to routing.yaml (string insertion to preserve comments)
    routing_path = CONFIG / "routing.yaml"
    content = routing_path.read_text() if routing_path.exists() else ""
    clean_prefixes = [p.strip().upper() for p in jira_prefixes if p.strip()]
    if f'project: "{project_id}"' not in content and f"project: {project_id}" not in content:
        prefixes_yaml = "\n".join(f'      - "{p}"' for p in clean_prefixes)
        block = f'\n  - project: "{project_id}"\n    jira_prefixes:\n{prefixes_yaml}\n'
        if "default_project:" in content:
            content = content.replace("default_project:", block + "\ndefault_project:", 1)
        else:
            content += block
        routing_path.write_text(content)

    # Invalidate routing cache so new prefix is immediately resolvable
    global _routing_cache
    _routing_cache = (0.0, {})

    return {"status": "created", "project_id": project_id, "config_dir": str(proj_dir.relative_to(ROOT))}


@app.post("/api/projects/{project_id}/import-repos")
async def import_repos(project_id: str, request: Request, x_api_key: str = Header(default="")):
    """Import multiple repositories into a project from a YAML/JSON list.

    JSON body:
        repos: list of {url, type?, language?}
            url: "https://github.com/org/repo" or "org/repo"
            type: "primary" | "tier2" | "additional" (default: "additional")
            language: "go" | "python" | "java" | "rust" (auto-detected if omitted)
    """
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)

    proj_dir = CONFIG / "projects" / project_id
    if not proj_dir.is_dir():
        raise HTTPException(404, f"Project '{project_id}' not found")

    body = await request.json()
    repos_input = body.get("repos", [])
    if not repos_input or not isinstance(repos_input, list):
        raise HTTPException(400, "Required: repos (list of {url, type?, language?})")

    # Parse and validate each repo
    results = []
    parsed_repos = []
    for entry in repos_input:
        if isinstance(entry, str):
            entry = {"url": entry}
        url = entry.get("url", "").strip()
        # Parse org/repo from URL
        url_clean = re.sub(r"^https?://", "", url).rstrip("/")
        url_clean = re.sub(r"^github\.com/", "", url_clean)
        parts = url_clean.split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            results.append({"url": url, "status": "error", "error": "Invalid format. Use org/repo or https://github.com/org/repo"})
            continue
        org, repo_name = parts[0], parts[1]
        full_name = f"{org}/{repo_name}"
        repo_type = entry.get("type", "additional").strip().lower()
        language = entry.get("language", "").strip().lower()
        parsed_repos.append({"full_name": full_name, "org": org, "repo": repo_name,
                             "type": repo_type, "language": language})
        results.append({"url": url, "full_name": full_name, "type": repo_type, "status": "ok"})

    if not parsed_repos:
        raise HTTPException(400, "No valid repos found in input")

    # Update repositories.yaml
    repos_path = proj_dir / "repositories.yaml"
    repos_cfg = _read_yaml(repos_path) if repos_path.exists() else {}
    for pr in parsed_repos:
        repo_entry = {"full_name": pr["full_name"]}
        if pr["language"]:
            repo_entry["language"] = pr["language"]
        if pr["type"] == "primary":
            repo_entry["build_system"] = ""
            repos_cfg["primary_repo"] = repo_entry
        elif pr["type"] == "tier2":
            repos_cfg["tier2_repo"] = repo_entry
        else:
            additional = repos_cfg.get("additional_repos", [])
            if not any(r.get("full_name") == pr["full_name"] for r in additional):
                additional.append(repo_entry)
            repos_cfg["additional_repos"] = additional
    _write_yaml(repos_path, repos_cfg)

    # Update coverage.yaml — add repos for coverage tracking
    cov_path = proj_dir / "coverage.yaml"
    cov_cfg = _read_yaml(cov_path) if cov_path.exists() else {}
    cov_repos = cov_cfg.get("repos", [])
    for pr in parsed_repos:
        if not any(r.get("org") == pr["org"] and r.get("repo") == pr["repo"] for r in cov_repos):
            cov_repos.append({
                "service": "github", "org": pr["org"], "repo": pr["repo"],
                "label": pr["full_name"], "type": pr["type"],
                "language": pr["language"] or "go",
                "flags": ["unit-tests"],
            })
    cov_cfg["repos"] = cov_repos
    _write_yaml(cov_path, cov_cfg)

    return {"status": "imported", "project_id": project_id, "repos": results,
            "total": len(parsed_repos), "errors": sum(1 for r in results if r["status"] == "error")}


@app.post("/api/projects/{project_id}/bulk-onboard")
async def bulk_onboard(project_id: str, request: Request, x_api_key: str = Header(default="")):
    """Run coverage onboarding for all repos in a project's coverage.yaml.

    JSON body (optional):
        github_token: User's GitHub PAT
        repos: list of "org/repo" to onboard (default: all from coverage.yaml)
    """
    _check_rate_limit(request)

    proj_dir = CONFIG / "projects" / project_id
    if not proj_dir.is_dir():
        raise HTTPException(404, f"Project '{project_id}' not found")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    user_gh_token = body.get("github_token", "").strip()
    if not user_gh_token:
        _check_api_key_or_origin(request, x_api_key)
    token = user_gh_token or _GITHUB_TOKEN
    if not token:
        raise HTTPException(503, "No GitHub token available")

    # Load repos from coverage.yaml
    cov_path = proj_dir / "coverage.yaml"
    cov_cfg = _read_yaml(cov_path) if cov_path.exists() else {}
    all_repos = cov_cfg.get("repos", [])
    if not all_repos:
        raise HTTPException(400, "No repos in coverage.yaml. Import repos first.")

    # Optional filter
    filter_repos = body.get("repos", None)

    # Dashboard URL: prefer env var, fall back to auto-detect from request
    dashboard_url = _BASE_URL
    if not dashboard_url:
        scheme = request.headers.get("x-forwarded-proto", "http")
        host = request.headers.get("host", "localhost:8420")
        dashboard_url = f"{scheme}://{host}"

    # Fetch GitHub username once (for DCO signoff if needed)
    gh_user_resp = _github_api("GET", "https://api.github.com/user", token)
    gh_user = gh_user_resp.get("login", "qualityflow")

    results = []
    for repo_entry in all_repos:
        org = repo_entry.get("org", "")
        repo_name = repo_entry.get("repo", "")
        full_name = f"{org}/{repo_name}"
        if filter_repos and full_name not in filter_repos:
            continue
        try:
            # Skip if already onboarded
            existing = _load_onboarding_state(org, repo_name)
            if existing and existing.get("status") == "pr_created":
                results.append({"repo": full_name, "status": "already_onboarded",
                                "pr_url": existing.get("pr", {}).get("url", "")})
                continue

            language = _github_detect_language(org, repo_name, token)
            if language not in ("go", "python"):
                results.append({"repo": full_name, "status": "skipped", "reason": f"Unsupported language: {language}"})
                continue

            # Generate instrumentation files
            if language == "go":
                gen_files = _generate_go_instrumentation(org, repo_name, token, dashboard_url)
            else:
                gen_files = _generate_python_instrumentation(org, repo_name, token, dashboard_url)
            if not gen_files:
                results.append({"repo": full_name, "status": "error", "error": "No instrumentation files generated"})
                continue

            # Extract repo context from generated files (appended by generators)
            repo_ctx = {}
            actual_files = []
            for f in gen_files:
                if "_ctx" in f:
                    repo_ctx = f["_ctx"]
                else:
                    actual_files.append(f)
            gen_files = actual_files

            # Resolve fork, create branch, tree, commit, PR
            default_branch = _github_get_default_branch(org, repo_name, token)
            push_repo = _github_resolve_fork(f"{org}/{repo_name}", token)
            pr_branch = "qualityflow/coverage-onboarding"

            base_ref = _github_api("GET",
                f"https://api.github.com/repos/{push_repo}/git/ref/heads/{default_branch}", token)
            base_sha = base_ref["object"]["sha"]
            base_commit = _github_api("GET",
                f"https://api.github.com/repos/{push_repo}/git/commits/{base_sha}", token)
            base_tree_sha = base_commit["tree"]["sha"]

            _github_create_branch(push_repo, pr_branch, base_sha, token)
            tree_sha = _github_create_tree(push_repo, base_tree_sha, gen_files, token)

            # Build commit message with DCO signoff if needed
            file_list = "\n".join(f"- {f['path']}" for f in gen_files)
            commit_msg = (
                f"Add CoverPort coverage instrumentation ({language})\n\n"
                f"Auto-generated by QualityFlow coverage onboarding.\n\n"
                f"Files added/modified:\n{file_list}\n"
            )
            if repo_ctx.get("needs_dco"):
                commit_msg += f"\nSigned-off-by: {gh_user} <{gh_user}@users.noreply.github.com>\n"

            commit_sha = _github_create_commit(push_repo, commit_msg, tree_sha, base_sha, token)
            _github_update_ref(push_repo, pr_branch, commit_sha, token)

            head_ref = pr_branch
            if push_repo != f"{org}/{repo_name}":
                head_ref = f"{push_repo.split('/')[0]}:{pr_branch}"

            # Build PR body — fill repo's PR template if one exists
            pr_template = repo_ctx.get("pr_template")
            if pr_template:
                pr_body = _fill_pr_template(pr_template, org, repo_name, language, gen_files, dashboard_url)
            else:
                pr_body = _build_default_pr_body(org, repo_name, language, gen_files, dashboard_url)

            pr_title = f"Add CoverPort coverage instrumentation ({language})"
            pr = _github_create_pr(f"{org}/{repo_name}", head_ref, default_branch,
                pr_title, pr_body, token)

            _save_onboarding_state(org, repo_name, {
                "status": "pr_created", "language": language,
                "pr": {"url": pr.get("url", ""), "number": pr.get("number", 0)},
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            results.append({"repo": full_name, "status": "pr_created", "pr_url": pr.get("url", "")})
        except Exception as e:
            logger.error("Bulk onboard failed for %s: %s", full_name, e)
            results.append({"repo": full_name, "status": "error", "error": str(e)})
        time.sleep(3)  # Avoid GitHub rate limits between repos

    return {"status": "completed", "project_id": project_id, "results": results,
            "created": sum(1 for r in results if r["status"] == "pr_created"),
            "errors": sum(1 for r in results if r["status"] == "error"),
            "skipped": sum(1 for r in results if r["status"] == "skipped")}


@app.get("/api/github/org-repos")
def list_org_repos(org: str, token: str = ""):
    """List repositories in a GitHub org/user with language info.

    Query params:
        org: GitHub org or username
        token: optional GitHub PAT (uses server token if not provided)
    """
    # Extract org name from full GitHub URLs
    url_match = re.search(r"github\.com/(?:orgs/)?([a-zA-Z0-9_.-]+)", org)
    if url_match:
        org = url_match.group(1)
    if not re.match(r"^[a-zA-Z0-9_.-]+$", org):
        raise HTTPException(400, "Invalid org name")

    gh_token = token.strip() or _GITHUB_TOKEN
    if not gh_token:
        raise HTTPException(503, "No GitHub token available")

    # Try as org first, fall back to user
    repos = []
    for endpoint in [f"https://api.github.com/orgs/{org}/repos", f"https://api.github.com/users/{org}/repos"]:
        try:
            page = 1
            while True:
                data = _github_api("GET", f"{endpoint}?per_page=100&page={page}&sort=updated&type=sources", gh_token)
                if not data:
                    break
                for r in data:
                    if r.get("fork") or r.get("archived"):
                        continue
                    repos.append({
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "language": (r.get("language") or "").lower(),
                        "description": r.get("description") or "",
                        "stars": r.get("stargazers_count", 0),
                        "updated": r.get("updated_at", ""),
                        "default_branch": r.get("default_branch", "main"),
                    })
                if len(data) < 100:
                    break
                page += 1
            break  # org endpoint worked, don't try user endpoint
        except RuntimeError as e:
            if "404" in str(e) and endpoint.startswith("https://api.github.com/orgs/"):
                continue  # Try as user
            raise HTTPException(502, f"GitHub API error: {e}")

    if not repos:
        raise HTTPException(404, f"No repos found for '{org}' (or org/user does not exist)")

    # Sort: supported languages first, then by stars
    supported = {"go", "python", "java", "rust", "javascript", "typescript"}
    repos.sort(key=lambda r: (0 if r["language"] in supported else 1, -r["stars"]))

    return {"org": org, "repos": repos, "total": len(repos)}


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict to a YAML file."""
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _atomic_yaml_update(path: Path, updater) -> dict:
    """Read-modify-write a YAML file with file-level locking.

    Args:
        path: YAML file path (created if missing).
        updater: callable(data: dict) -> dict — receives current data, returns updated data.

    Returns the updated data dict.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use a .lock sidecar to avoid truncation issues with flock on the data file
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = _read_yaml(path) if path.exists() else {}
            data = updater(data)
            # Write to temp file then rename for atomicity
            tmp = path.with_suffix(".tmp")
            tmp.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
            tmp.rename(path)
            return data
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# API: Ticket Routing & Validation
# ---------------------------------------------------------------------------

@app.get("/api/resolve/{jira_id}")
def resolve_ticket(jira_id: str):
    """Validate a Jira ID and resolve it to a project + suggested commands."""
    jira_id = jira_id.strip().upper()
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: '{jira_id}'. Expected FORMAT: ABC-12345")

    prefix = jira_id.split("-")[0]
    routing = _read_yaml(CONFIG / "routing.yaml")
    project_id = _infer_project(jira_id)
    proj_dir = CONFIG / "projects" / project_id
    if not proj_dir.is_dir():
        default = routing.get("default_project")
        if default:
            project_id = default
        else:
            known = []
            for r in routing.get("routes", []):
                known.extend(r.get("jira_prefixes", []))
            return {
                "jira_id": jira_id,
                "resolved": False,
                "error": f"No project configured for prefix '{prefix}'. "
                         f"Known prefixes: {', '.join(known)}",
            }

    # Load project config
    proj_yaml = CONFIG / "projects" / project_id / "project.yaml"
    proj_cfg = _read_yaml(proj_yaml) if proj_yaml.exists() else {}
    display_name = proj_cfg.get("display_name", project_id.upper())
    toggles = proj_cfg.get("feature_toggles", {})

    # Check if artifacts already exist
    has_stp = (OUTPUTS / "stp" / jira_id / f"{jira_id}_test_plan.md").exists()
    has_std = (OUTPUTS / "std" / jira_id / f"{jira_id}_test_description.yaml").exists()
    go_dir = OUTPUTS / "go-tests" / jira_id
    has_go = go_dir.is_dir() and any(go_dir.glob("*_test.go"))
    py_dir = OUTPUTS / "python-tests" / jira_id
    has_py = py_dir.is_dir() and any(py_dir.glob("test_*.py"))
    existing = has_stp or has_std

    # Build command suggestions based on state — suggest the next incomplete step
    suggestions = []
    if not has_stp and toggles.get("stp_generation", True):
        suggestions.append({"command": f"/stp-builder {jira_id}", "label": "Generate STP", "phase": "stp"})
    elif has_stp and not has_std and toggles.get("std_generation", True):
        suggestions.append({"command": f"/std-builder {jira_id}", "label": "Generate STD", "phase": "std"})
    elif has_std and not (has_go or has_py):
        suggestions.append({"command": f"/generate-tests {jira_id}", "label": "Generate Tests", "phase": "codegen"})

    # If everything is done, indicate completion
    if not suggestions:
        if has_stp:
            suggestions.append({"command": f"/pipeline-status {jira_id}", "label": "Pipeline Complete — View Status", "phase": "done"})
        else:
            suggestions.append({"command": f"/stp-builder {jira_id}", "label": "Generate STP", "phase": "stp"})

    return {
        "jira_id": jira_id,
        "resolved": True,
        "project_id": project_id,
        "display_name": display_name,
        "feature_toggles": toggles,
        "existing_artifacts": existing,
        "has_stp": has_stp,
        "has_std": has_std,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Pipeline Init API — create a new pipeline entry from the dashboard
# ---------------------------------------------------------------------------

@app.post("/api/pipelines/init")
async def init_pipeline(request: Request):
    """Create a new pipeline entry for a Jira ticket.

    This creates the state directory so the pipeline appears in the sidebar.
    Called when a user clicks 'Start Pipeline' from the search bar.
    """
    _check_rate_limit(request)
    _check_api_key_or_origin(request, "")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body required")

    jira_id = body.get("jira_id", "").strip().upper()
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    # Check if pipeline already exists
    existing_ids = _scan_jira_ids()
    if jira_id in existing_ids:
        return {"status": "existing", "jira_id": jira_id, "message": "Pipeline already exists"}

    # Create state directory — this makes the pipeline appear in the sidebar
    state_dir = OUTPUTS / "state" / jira_id
    state_dir.mkdir(parents=True, exist_ok=True)

    # Write initial pipeline_state.yaml
    project_id = _infer_project(jira_id)
    state_file = state_dir / "pipeline_state.yaml"

    def _init(_data):
        return {
            "jira_id": jira_id,
            "project": project_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
            "phases": {
                "stp": {"status": "not_started"},
                "std": {"status": "not_started"},
                "codegen": {"status": "not_started"},
            },
        }

    _atomic_yaml_update(state_file, _init)

    _slack_pipeline_event(jira_id, "Pipeline initialized", f"Project: {project_id}")

    return {"status": "created", "jira_id": jira_id, "project_id": project_id}


# ---------------------------------------------------------------------------
# Pipeline Run API — execute a phase via Claude AI
# ---------------------------------------------------------------------------

_VALID_PHASES = ["stp", "std", "codegen"]

# ---------------------------------------------------------------------------
# Background phase execution — avoids HTTP gateway timeouts
# ---------------------------------------------------------------------------
_running_tasks: dict[str, dict] = {}  # key: "jira_id/phase" → {status, result, error, started}
_tasks_lock = threading.Lock()
_TASK_RESULT_TTL = 600  # seconds — auto-clean completed/failed results after 10 min


def _run_phase_background(jira_id: str, phase: str):
    """Execute a pipeline phase in a background thread."""
    key = f"{jira_id}/{phase}"
    try:
        from pipeline_runner import run_phase as _run_real_phase  # type: ignore[import-not-found]
        client = _get_claude_client()
        if not client:
            raise RuntimeError("Claude client initialization failed")

        result = _run_real_phase(client, _CLAUDE_MODEL, jira_id, phase)

        # Update pipeline state file (atomic)
        state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"

        def _mark_completed(state):
            if not state:
                state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
            phase_data = {"status": "completed", "output": result.get("output", "")}
            if result.get("verdict"):
                phase_data["verdict"] = result["verdict"]
            state.setdefault("phases", {})[phase] = phase_data
            state["updated"] = datetime.now(timezone.utc).isoformat()
            return state

        _atomic_yaml_update(state_file, _mark_completed)

        _slack_pipeline_event(jira_id, f"{phase.replace('_', ' ').title()} completed",
                              f"Verdict: {result.get('verdict', 'N/A')}")

        with _tasks_lock:
            _running_tasks[key] = {
                "status": "completed",
                "_finished": time.time(),
                "result": {
                    "phase": phase,
                    "jira_id": jira_id,
                    "output": result.get("output", ""),
                    "verdict": result.get("verdict"),
                    "progress": result.get("progress", []),
                },
            }
        logger.info(f"Phase {phase} for {jira_id} completed successfully")

    except Exception as e:
        logger.error(f"Pipeline error for {jira_id}/{phase}: {e}")
        # Write error to state file so UI can show it (atomic)
        state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
        error_msg = str(e)[:500]

        def _mark_failed(state):
            if not state:
                state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
            state.setdefault("phases", {})[phase] = {"status": "failed", "error": error_msg}
            state["updated"] = datetime.now(timezone.utc).isoformat()
            return state

        _atomic_yaml_update(state_file, _mark_failed)

        with _tasks_lock:
            _running_tasks[key] = {"status": "failed", "_finished": time.time(), "error": error_msg}


@app.post("/api/pipelines/{jira_id}/run/{phase}")
async def run_pipeline_phase(jira_id: str, phase: str, request: Request):
    """Start a pipeline phase in the background. Returns immediately."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, "")

    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID: {jira_id}")
    if phase not in _VALID_PHASES:
        raise HTTPException(400, f"Unknown phase: {phase}. Valid: {_VALID_PHASES}")
    if not _claude_available():
        raise HTTPException(503, "Claude AI not configured. Set ANTHROPIC_VERTEX_PROJECT_ID or ANTHROPIC_API_KEY.")

    # Check feature toggles — block disabled phases
    project_id = _infer_project(jira_id)
    toggles = _load_project_toggles(project_id)
    toggle_map = {"stp": "stp_generation", "std": "std_generation"}
    toggle_key = toggle_map.get(phase)
    if toggle_key and not toggles.get(toggle_key, True):
        raise HTTPException(400, f"Phase '{phase}' is disabled for project '{project_id}' (toggle: {toggle_key}=false)")

    key = f"{jira_id}/{phase}"
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("status") == "running":
            return {"status": "already_running", "phase": phase, "jira_id": jira_id}

    # Mark as in_progress in state file immediately (atomic)
    state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"

    def _mark_in_progress(state):
        if not state:
            state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
        state.setdefault("phases", {})[phase] = {"status": "in_progress"}
        state["updated"] = datetime.now(timezone.utc).isoformat()
        return state

    _atomic_yaml_update(state_file, _mark_in_progress)

    with _tasks_lock:
        _running_tasks[key] = {"status": "running", "started": datetime.now(timezone.utc).isoformat()}

    thread = threading.Thread(target=_run_phase_background, args=(jira_id, phase), daemon=True)
    thread.start()

    logger.info(f"Started phase {phase} for {jira_id} in background")
    return {"status": "started", "phase": phase, "jira_id": jira_id}


@app.get("/api/pipelines/{jira_id}/run/{phase}/status")
async def get_phase_run_status(jira_id: str, phase: str):
    """Poll for background phase execution status."""
    key = f"{jira_id}/{phase}"
    with _tasks_lock:
        task = _running_tasks.get(key)
        # Prune stale completed/failed results while holding the lock
        now = time.time()
        stale = [k for k, v in _running_tasks.items()
                 if v.get("status") in ("completed", "failed")
                 and now - v.get("_finished", now) > _TASK_RESULT_TTL]
        for k in stale:
            _running_tasks.pop(k, None)
    if not task:
        return {"status": "idle", "phase": phase, "jira_id": jira_id}
    if task["status"] == "completed":
        with _tasks_lock:
            _running_tasks.pop(key, None)
        return {"status": "completed", **task.get("result", {})}
    if task["status"] == "failed":
        with _tasks_lock:
            _running_tasks.pop(key, None)
        return {"status": "failed", "phase": phase, "jira_id": jira_id, "error": task.get("error", "Unknown error")}
    return {"status": "running", "phase": phase, "jira_id": jira_id}


@app.get("/api/claude/status")
def claude_status():
    """Check if Claude AI is available for running phases."""
    return {
        "available": _claude_available(),
        "backend": "vertex" if _VERTEX_PROJECT else "api" if _ANTHROPIC_API_KEY else "none",
        "model": _CLAUDE_MODEL if _claude_available() else None,
        "project": _VERTEX_PROJECT or None,
        "region": _VERTEX_REGION if _VERTEX_PROJECT else None,
    }


# ---------------------------------------------------------------------------
# Output Upload API — pipeline pushes artifacts here
# ---------------------------------------------------------------------------

@app.post("/api/outputs/{jira_id}")
async def upload_outputs(jira_id: str, request: Request, x_api_key: str = Header(default="")):
    """Upload pipeline outputs for a Jira ticket.

    Accepts a tar.gz archive containing the outputs directory structure.
    The archive should contain paths like:
        stp/{JIRA_ID}/{JIRA_ID}_test_plan.md
        std/{JIRA_ID}/{JIRA_ID}_test_description.yaml
        reviews/{JIRA_ID}/{JIRA_ID}_stp_review.md
        go-tests/{JIRA_ID}/*_test.go
        python-tests/{JIRA_ID}/test_*.py
        state/{JIRA_ID}/pipeline_state.yaml
    """
    _require_api_key(x_api_key)

    # Validate Jira ID format
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    content_type = request.headers.get("content-type", "")

    # Enforce max upload size (50 MB) to prevent memory exhaustion
    content_length = request.headers.get("content-length", "")
    if content_length and int(content_length) > 50 * 1024 * 1024:
        raise HTTPException(413, "Upload too large. Maximum 50 MB.")

    body = await request.body()

    if not body:
        raise HTTPException(400, "Empty request body")
    if len(body) > 50 * 1024 * 1024:
        raise HTTPException(413, "Upload too large. Maximum 50 MB.")

    # Accept tar.gz uploads
    if "application/gzip" in content_type or "application/x-tar" in content_type or "application/octet-stream" in content_type:
        try:
            with tarfile.open(fileobj=BytesIO(body), mode="r:gz") as tar:
                # Security: validate all paths are safe before extracting
                allowed_prefixes = ("stp/", "std/", "reviews/", "go-tests/", "python-tests/", "state/")
                safe_members = []
                for member in tar.getmembers():
                    # Normalize: strip leading ./
                    name = member.name.lstrip("./") if member.name.startswith("./") else member.name
                    # Block absolute paths and path traversal
                    if name.startswith("/") or ".." in name:
                        raise HTTPException(400, f"Unsafe path in archive: {name}")
                    # Skip macOS metadata, hidden files
                    basename = name.split("/")[-1]
                    if basename.startswith("._") or basename == ".DS_Store" or not name:
                        continue
                    # Only allow known output subdirectories
                    if not any(name.startswith(p) for p in allowed_prefixes):
                        continue
                    safe_members.append(member)

                # Extract safe members into outputs directory
                with tempfile.TemporaryDirectory() as tmpdir:
                    tar.extractall(tmpdir, members=safe_members, filter="data")
                    # Copy extracted files into outputs
                    import shutil
                    tmp_path = Path(tmpdir)
                    for item in tmp_path.rglob("*"):
                        if item.is_file():
                            rel = item.relative_to(tmp_path)
                            dest = OUTPUTS / rel
                            # Archive existing file to .previous/ for diff
                            if dest.exists():
                                prev_dir = dest.parent / ".previous"
                                prev_dir.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(dest, prev_dir / dest.name)
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest)

            _slack_pipeline_event(jira_id, "Pipeline outputs uploaded",
                                  f"{len(safe_members)} files")
            return {"status": "ok", "jira_id": jira_id, "message": "Outputs uploaded successfully"}
        except tarfile.TarError as e:
            raise HTTPException(400, f"Invalid tar.gz archive: {e}")

    # Accept JSON upload for single files
    elif "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        file_path = data.get("path", "")
        content = data.get("content", "")
        if not file_path or not content:
            raise HTTPException(400, "JSON upload requires 'path' and 'content' fields")

        # Validate path safety
        if file_path.startswith("/") or ".." in file_path:
            raise HTTPException(400, f"Unsafe path: {file_path}")
        allowed_prefixes = ("stp/", "std/", "reviews/", "go-tests/", "python-tests/", "state/")
        if not any(file_path.startswith(p) for p in allowed_prefixes):
            raise HTTPException(400, f"Path not in allowed output directories: {file_path}")

        dest = OUTPUTS / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        return {"status": "ok", "jira_id": jira_id, "path": file_path}

    else:
        raise HTTPException(415, "Unsupported content type. Use application/gzip (tar.gz) or application/json")


@app.delete("/api/outputs/{jira_id}")
async def delete_outputs(jira_id: str, x_api_key: str = Header(default="")):
    """Delete all outputs for a Jira ticket. Requires API key."""
    _require_api_key(x_api_key)

    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    import shutil
    deleted = []
    for subdir in ("stp", "std", "reviews", "go-tests", "python-tests", "state"):
        target = OUTPUTS / subdir / jira_id
        if target.is_dir():
            shutil.rmtree(target)
            deleted.append(subdir)

    if not deleted:
        raise HTTPException(404, f"No outputs found for {jira_id}")

    return {"status": "ok", "jira_id": jira_id, "deleted": deleted}


# ---------------------------------------------------------------------------
# PR Push — push test files to the team's repo (GitHub) via API, open PR
# ---------------------------------------------------------------------------

_GITHUB_TOKEN = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "") or os.environ.get("QUALITYFLOW_GIT_TOKEN", "")
_GITLAB_TOKEN = os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN", "") or os.environ.get("QUALITYFLOW_GIT_TOKEN", "")


def _read_pr_info(jira_id: str) -> dict | None:
    """Read PR info from state file."""
    pr_file = OUTPUTS / "state" / jira_id / "pr_info.yaml"
    if pr_file.exists():
        return _read_yaml(pr_file)
    return None


def _write_pr_info(jira_id: str, info: dict) -> None:
    """Write PR info to state file."""
    state_dir = OUTPUTS / "state" / jira_id
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(state_dir / "pr_info.yaml", info)


def _get_target_repo(project_id: str, tier: str = "primary") -> dict:
    """Get the target repository from project config.

    Args:
        project_id: Project ID (e.g., 'cnv')
        tier: 'primary' for Go/tier1 repo, 'tier2' for Python repo

    Returns dict with keys: full_name, default_branch, platform, url
    """
    repos_file = CONFIG / "projects" / project_id / "repositories.yaml"
    if not repos_file.exists():
        return {}
    repos = _read_yaml(repos_file)
    repo_key = "tier2_repo" if tier == "tier2" else "primary_repo"
    repo = repos.get(repo_key, {})
    if not repo:
        return {}

    url = repo.get("url", "")
    platform = "gitlab" if "gitlab" in url else "github"
    return {
        "full_name": repo.get("full_name", ""),
        "default_branch": repo.get("default_branch", "main"),
        "platform": platform,
        "url": url,
        "name": repo.get("name", ""),
        "org": repo.get("org", ""),
    }


def _github_api(method: str, url: str, token: str, data: dict | None = None) -> dict:
    """Make a GitHub API request."""
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"GitHub API error ({e.code}): {error_body}")


def _github_get_user(token: str) -> str:
    """Get the authenticated GitHub username."""
    result = _github_api("GET", "https://api.github.com/user", token)
    return result["login"]


def _github_resolve_fork(upstream_repo: str, token: str) -> str:
    """Find the authenticated user's fork of the upstream repo.

    Returns 'user/repo' if a fork exists, otherwise creates one.
    Falls back to upstream_repo if user has direct push access.
    """
    username = _github_get_user(token)
    repo_name = upstream_repo.split("/")[1]
    fork_full = f"{username}/{repo_name}"

    # Check if user has push access to upstream (org member, maintainer, etc.)
    try:
        upstream_info = _github_api("GET", f"https://api.github.com/repos/{upstream_repo}", token)
        if upstream_info.get("permissions", {}).get("push"):
            return upstream_repo  # Direct push — no fork needed
    except RuntimeError:
        pass

    # Check if fork exists
    try:
        fork_info = _github_api("GET", f"https://api.github.com/repos/{fork_full}", token)
        if fork_info.get("fork"):
            return fork_full
    except RuntimeError:
        pass

    # Create fork — GitHub needs time to set it up
    _github_api("POST", f"https://api.github.com/repos/{upstream_repo}/forks", token, {"default_branch_only": True})

    # Wait for fork to become available (GitHub forks are async)
    for attempt in range(12):
        time.sleep(5)
        try:
            fork_info = _github_api("GET", f"https://api.github.com/repos/{fork_full}", token)
            if fork_info.get("fork"):
                logger.info("Fork %s ready after %d seconds", fork_full, (attempt + 1) * 5)
                return fork_full
        except RuntimeError:
            pass
    logger.warning("Fork %s may not be ready yet, proceeding anyway", fork_full)
    return fork_full


def _github_create_branch(owner_repo: str, branch: str, base_sha: str, token: str) -> None:
    """Create a branch on GitHub via refs API."""
    url = f"https://api.github.com/repos/{owner_repo}/git/refs"
    try:
        _github_api("POST", url, token, {"ref": f"refs/heads/{branch}", "sha": base_sha})
    except RuntimeError as e:
        if "422" in str(e) and "Reference already exists" in str(e):
            # Branch exists — update it to the base SHA
            update_url = f"https://api.github.com/repos/{owner_repo}/git/refs/heads/{urllib.parse.quote(branch, safe='')}"
            _github_api("PATCH", update_url, token, {"sha": base_sha, "force": True})
        else:
            raise


def _github_create_tree(owner_repo: str, base_tree_sha: str, files: list[dict], token: str) -> str:
    """Create a git tree on GitHub with the given files.

    files: list of {"path": "relative/path", "content": "file content string"}
    Returns the tree SHA.
    """
    tree_items = []
    for f in files:
        tree_items.append({
            "path": f["path"],
            "mode": "100644",
            "type": "blob",
            "content": f["content"],
        })
    url = f"https://api.github.com/repos/{owner_repo}/git/trees"
    result = _github_api("POST", url, token, {"base_tree": base_tree_sha, "tree": tree_items})
    return result["sha"]


def _github_create_commit(owner_repo: str, message: str, tree_sha: str, parent_sha: str, token: str) -> str:
    """Create a commit on GitHub. Returns commit SHA."""
    url = f"https://api.github.com/repos/{owner_repo}/git/commits"
    result = _github_api("POST", url, token, {
        "message": message, "tree": tree_sha, "parents": [parent_sha],
    })
    return result["sha"]


def _github_update_ref(owner_repo: str, branch: str, sha: str, token: str) -> None:
    """Update a branch ref to point to a commit."""
    url = f"https://api.github.com/repos/{owner_repo}/git/refs/heads/{urllib.parse.quote(branch, safe='')}"
    _github_api("PATCH", url, token, {"sha": sha, "force": True})


def _github_create_pr(upstream_repo: str, head: str, base: str, title: str, body: str, token: str) -> dict:
    """Create a GitHub Pull Request. Supports cross-repo (fork) PRs.

    Args:
        upstream_repo: Target repo for the PR (e.g., 'my-org/my-repo')
        head: Branch ref — 'branch' for same-repo, 'user:branch' for fork PRs
        base: Target branch (e.g., 'main')
    """
    url = f"https://api.github.com/repos/{upstream_repo}/pulls"
    try:
        result = _github_api("POST", url, token, {
            "title": title, "body": body, "head": head, "base": base,
        })
        return {"url": result["html_url"], "number": result["number"], "state": result["state"]}
    except RuntimeError as e:
        if "422" in str(e) and "already exists" in str(e).lower():
            return _github_find_pr(upstream_repo, head, token)
        raise


def _github_find_pr(upstream_repo: str, head: str, token: str) -> dict:
    """Find an existing PR for the given head ref.

    head can be 'branch' or 'user:branch' for cross-repo PRs.
    """
    url = f"https://api.github.com/repos/{upstream_repo}/pulls?head={urllib.parse.quote(head, safe=':')}&state=open"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req) as resp:
        prs = json.loads(resp.read())
        if prs:
            return {"url": prs[0]["html_url"], "number": prs[0]["number"], "state": prs[0]["state"]}
    return {"url": "", "number": 0, "state": "unknown", "error": "PR exists but could not be found"}



def _collect_pr_files(jira_id: str) -> dict[str, list[dict]]:
    """Collect output files grouped by target repo tier.

    Returns {"primary": [...], "tier2": [...], "docs": [...]}
    Each item: {"path": "relative/path/in/target/repo", "content": "...", "source": "local/path"}
    """
    groups: dict[str, list[dict]] = {"primary": [], "tier2": [], "docs": []}

    # Go test files → primary repo
    go_dir = OUTPUTS / "go-tests" / jira_id
    if go_dir.is_dir():
        for f in go_dir.rglob("*"):
            if f.is_file() and f.suffix == ".go":
                groups["primary"].append({
                    "path": f"tests/qualityflow/{jira_id}/{f.name}",
                    "content": f.read_text(errors="replace"),
                    "source": str(f),
                })

    # Python test files → tier2 repo
    py_dir = OUTPUTS / "python-tests" / jira_id
    if py_dir.is_dir():
        for f in py_dir.rglob("*"):
            if f.is_file() and f.suffix == ".py":
                groups["tier2"].append({
                    "path": f"tests/qualityflow/{jira_id}/{f.name}",
                    "content": f.read_text(errors="replace"),
                    "source": str(f),
                })

    # STP, STD, reviews → docs (pushed to primary repo under docs/)
    for subdir, label in [("stp", "stp"), ("std", "std"), ("reviews", "reviews")]:
        sub = OUTPUTS / subdir / jira_id
        if sub.is_dir():
            for f in sub.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    groups["docs"].append({
                        "path": f"docs/qualityflow/{jira_id}/{label}/{f.relative_to(sub)}",
                        "content": f.read_text(errors="replace"),
                        "source": str(f),
                    })

    return groups


@app.post("/api/pipelines/{jira_id}/push-pr")
async def push_to_pr(jira_id: str, request: Request, x_api_key: str = Header(default="")):
    """Push pipeline outputs to the team's GitHub repo and open a PR.

    Reads target repo from project config (repositories.yaml).
    Uses GitHub API directly — no local git clone needed.
    Go tests → primary_repo, Python tests → tier2_repo, docs → primary_repo.
    """
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)

    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    # Check for existing PR
    existing = _read_pr_info(jira_id)
    if existing and existing.get("url"):
        return {"status": "existing", "pr": existing, "message": "PR already exists for this ticket"}

    # Parse optional body
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_id = _infer_project(jira_id)
    target = _get_target_repo(project_id, "primary")
    if not target.get("full_name"):
        raise HTTPException(400, f"No target repository configured for project '{project_id}'. Check repositories.yaml")

    owner_repo = target["full_name"]
    base_branch = body.get("base_branch", target.get("default_branch", "main"))
    platform = target.get("platform", "github")
    branch_name = f"qualityflow/{jira_id.lower()}"

    # Resolve token: prefer user-provided token from request body, fall back to server-side
    user_token = body.get("github_token", "").strip() if platform == "github" else body.get("gitlab_token", "").strip()
    token = user_token or (_GITHUB_TOKEN if platform == "github" else _GITLAB_TOKEN)
    if not token:
        raise HTTPException(400, f"No {'GitHub' if platform == 'github' else 'GitLab'} token provided. Please configure your personal token in Settings.")

    # Collect files grouped by tier
    file_groups = _collect_pr_files(jira_id)
    all_files = file_groups["primary"] + file_groups["docs"]

    # If there are tier2 files and a separate tier2 repo, we'll push those separately
    tier2_target = _get_target_repo(project_id, "tier2")
    tier2_pr_info = None

    if not all_files and not file_groups["tier2"]:
        raise HTTPException(404, f"No output files found for {jira_id}")

    try:
        pr_result: dict = {}

        def _push_and_pr(upstream_repo: str, base_branch: str, files: list[dict], pr_title: str, pr_body: str) -> dict:
            """Push files to fork (or upstream if allowed) and create a PR."""
            # Resolve where to push — fork or upstream
            push_repo = _github_resolve_fork(upstream_repo, token)
            is_fork = push_repo != upstream_repo

            # Get base branch SHA from upstream
            base_info = _github_api("GET", f"https://api.github.com/repos/{upstream_repo}/git/ref/heads/{base_branch}", token)
            base_sha = base_info["object"]["sha"]
            commit_info = _github_api("GET", f"https://api.github.com/repos/{upstream_repo}/git/commits/{base_sha}", token)
            base_tree_sha = commit_info["tree"]["sha"]

            # Create tree + commit on push_repo (fork or upstream)
            tree_sha = _github_create_tree(push_repo, base_tree_sha, files, token)
            file_list = "\n".join(f"  - {f['path']}" for f in files)
            commit_msg = f"QualityFlow: test artifacts for {jira_id}\n\nAuto-generated files:\n{file_list}\n\nGenerated by QualityFlow pipeline."
            commit_sha = _github_create_commit(push_repo, commit_msg, tree_sha, base_sha, token)

            # Create/update branch on push_repo
            _github_create_branch(push_repo, branch_name, commit_sha, token)
            _github_update_ref(push_repo, branch_name, commit_sha, token)

            # Create PR on upstream — head is 'user:branch' for forks, 'branch' for same-repo
            push_user = push_repo.split("/")[0]
            head_ref = f"{push_user}:{branch_name}" if is_fork else branch_name
            return _github_create_pr(upstream_repo, head_ref, base_branch, pr_title, pr_body, token)

        # --- Push to primary repo (Go tests + docs) ---
        if all_files and platform == "github":
            title = f"[QualityFlow] Test artifacts for {jira_id}"
            pr_body = (
                f"## QualityFlow Pipeline Outputs\n\n"
                f"**Ticket:** [{jira_id}](https://your-org.atlassian.net/browse/{jira_id})\n"
                f"**Project:** {project_id}\n"
                f"**Files:** {len(all_files)}\n\n"
                f"### Test Files\n"
                + "\n".join(f"- `{f['path']}`" for f in all_files)
                + "\n\n---\n*Auto-generated by QualityFlow*"
            )
            pr_result = _push_and_pr(owner_repo, base_branch, all_files, title, pr_body)

        # --- Push tier2 files to tier2 repo (if separate) ---
        if file_groups["tier2"] and tier2_target.get("full_name") and tier2_target["full_name"] != owner_repo:
            tier2_repo = tier2_target["full_name"]
            tier2_base = tier2_target.get("default_branch", "main")

            title = f"[QualityFlow] Tier 2 tests for {jira_id}"
            pr_body = (
                f"## QualityFlow Tier 2 Tests\n\n"
                f"**Ticket:** [{jira_id}](https://your-org.atlassian.net/browse/{jira_id})\n"
                f"**Files:** {len(file_groups['tier2'])}\n\n"
                + "\n".join(f"- `{f['path']}`" for f in file_groups["tier2"])
                + "\n\n---\n*Auto-generated by QualityFlow*"
            )
            tier2_pr_info = _push_and_pr(tier2_repo, tier2_base, file_groups["tier2"], title, pr_body)

        # Save PR info
        pr_info = {
            "jira_id": jira_id,
            "project_id": project_id,
            "branch": branch_name,
            "base_branch": base_branch,
            "target_repo": owner_repo,
            "platform": platform,
            "url": pr_result.get("url", ""),
            "number": pr_result.get("number"),
            "state": pr_result.get("state", "open"),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": [f["path"] for f in all_files],
        }
        if tier2_pr_info:
            pr_info["tier2_pr"] = {
                "target_repo": tier2_target["full_name"],
                "url": tier2_pr_info.get("url", ""),
                "number": tier2_pr_info.get("number"),
            }
        _write_pr_info(jira_id, pr_info)

        # Slack notification
        _slack_pipeline_event(jira_id, "PR pushed",
                              f"{len(all_files)} files to {owner_repo}",
                              pr_info.get("url", ""))

        return {"status": "created", "pr": pr_info}

    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.exception("Push to PR failed for %s", jira_id)
        raise HTTPException(500, f"Failed to push PR: {e}")


# ---------------------------------------------------------------------------
# Approval Gates — human-in-the-loop review
# ---------------------------------------------------------------------------

_DEFAULT_GATES = ["stp", "std"]  # Phases requiring manual approval before proceeding


def _get_approval_gates(project_id: str) -> list[str]:
    """Get the list of phases requiring manual approval for a project."""
    proj_yaml = CONFIG / "projects" / project_id / "project.yaml"
    if proj_yaml.exists():
        cfg = _read_yaml(proj_yaml)
        gates = cfg.get("approval_gates")
        if gates is not None:
            return gates
    return _DEFAULT_GATES


def _read_approvals(jira_id: str) -> dict:
    """Read approval state from state file."""
    approvals_file = OUTPUTS / "state" / jira_id / "approvals.yaml"
    if approvals_file.exists():
        return _read_yaml(approvals_file)
    return {}


def _write_approvals(jira_id: str, approvals: dict) -> None:
    """Write approval state to state file."""
    state_dir = OUTPUTS / "state" / jira_id
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(state_dir / "approvals.yaml", approvals)


@app.get("/api/pipelines/{jira_id}/approvals")
def get_approvals(jira_id: str):
    """Get approval status for all gated phases."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    project_id = _infer_project(jira_id)
    gates = _get_approval_gates(project_id)
    approvals = _read_approvals(jira_id)

    return {
        "jira_id": jira_id,
        "gates": gates,
        "approvals": approvals,
    }


@app.post("/api/pipelines/{jira_id}/approve/{phase}")
async def approve_phase(jira_id: str, phase: str, request: Request, x_api_key: str = Header(default="")):
    """Approve or reject a gated phase."""
    _check_api_key_or_origin(request, x_api_key)

    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    project_id = _infer_project(jira_id)
    gates = _get_approval_gates(project_id)
    if phase not in gates:
        raise HTTPException(400, f"Phase '{phase}' is not a gated phase. Gates: {gates}")

    try:
        body = await request.json()
    except Exception:
        body = {}

    action = body.get("action", "approve")  # "approve" or "reject"
    reviewer = body.get("reviewer", "dashboard-user")
    comment = body.get("comment", "")

    if action not in ("approve", "reject"):
        raise HTTPException(400, f"Invalid action: {action}. Must be 'approve' or 'reject'")

    approvals = _read_approvals(jira_id)
    approvals[phase] = {
        "status": "approved" if action == "approve" else "rejected",
        "reviewer": reviewer,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_approvals(jira_id, approvals)

    # Slack notification
    _slack_pipeline_event(jira_id, f"{phase.replace('_', ' ').title()} {action}ed",
                          f"Reviewer: {reviewer}" + (f" — {comment}" if comment else ""))

    return {"status": "ok", "phase": phase, "approval": approvals[phase]}


@app.get("/api/git/status")
def git_integration_status():
    """Check Git integration status — which tokens are configured."""
    return {
        "github": {"configured": bool(_GITHUB_TOKEN), "token_prefix": _GITHUB_TOKEN[:4] + "..." if _GITHUB_TOKEN else None},
        "gitlab": {"configured": bool(_GITLAB_TOKEN), "token_prefix": _GITLAB_TOKEN[:4] + "..." if _GITLAB_TOKEN else None},
    }


@app.get("/api/pipelines/{jira_id}/pr-status")
def get_pr_status(jira_id: str):
    """Get PR/MR status for a Jira ticket."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    pr_info = _read_pr_info(jira_id)
    if not pr_info:
        return {"status": "none", "jira_id": jira_id}
    return {"status": "exists", "pr": pr_info}


@app.post("/api/pipelines/{jira_id}/refresh-pr")
def refresh_pr_status(jira_id: str, request: Request, x_api_key: str = Header(default="")):
    """Poll GitHub/GitLab for current PR state and update pr_info.yaml."""
    _check_api_key_or_origin(request, x_api_key)
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    pr_info = _read_pr_info(jira_id)
    if not pr_info or not pr_info.get("url"):
        raise HTTPException(404, "No PR info found for this ticket")

    token = _GITHUB_TOKEN if pr_info.get("platform", "github") == "github" else _GITLAB_TOKEN
    if not token:
        raise HTTPException(400, "No token configured for PR platform")

    updated = False
    try:
        # Refresh primary PR
        if pr_info.get("number") and pr_info.get("target_repo"):
            repo = pr_info["target_repo"]
            data = _github_api("GET", f"https://api.github.com/repos/{repo}/pulls/{pr_info['number']}", token)
            new_state = "merged" if data.get("merged") else data.get("state", "unknown")
            if new_state != pr_info.get("state"):
                pr_info["state"] = new_state
                updated = True

        # Refresh tier2 PR
        t2 = pr_info.get("tier2_pr", {})
        if t2.get("number") and t2.get("target_repo"):
            data = _github_api("GET", f"https://api.github.com/repos/{t2['target_repo']}/pulls/{t2['number']}", token)
            new_state = "merged" if data.get("merged") else data.get("state", "unknown")
            t2["state"] = new_state
            updated = True

        if updated:
            _write_pr_info(jira_id, pr_info)

    except RuntimeError as e:
        raise HTTPException(502, f"GitHub API error: {e}")

    return {"status": "refreshed", "pr": pr_info, "changed": updated}


@app.post("/api/pipelines/{jira_id}/close-pr")
async def close_or_reopen_pr(jira_id: str, request: Request, x_api_key: str = Header(default="")):
    """Close or reopen the PR(s) for a pipeline."""
    _check_api_key_or_origin(request, x_api_key)
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    pr_info = _read_pr_info(jira_id)
    if not pr_info or not pr_info.get("url"):
        raise HTTPException(404, "No PR info found for this ticket")

    try:
        body = await request.json()
    except Exception:
        body = {}

    action = body.get("action", "close")  # "close" or "reopen"
    new_state = "closed" if action == "close" else "open"

    # Resolve token: user-provided or server-side
    user_token = body.get("github_token", "").strip()
    token = user_token or _GITHUB_TOKEN
    if not token:
        raise HTTPException(400, "No GitHub token available. Configure in Settings.")

    try:
        # Update primary PR
        if pr_info.get("number") and pr_info.get("target_repo"):
            repo = pr_info["target_repo"]
            _github_api("PATCH", f"https://api.github.com/repos/{repo}/pulls/{pr_info['number']}",
                        token, {"state": new_state})
            pr_info["state"] = new_state

        # Update tier2 PR
        t2 = pr_info.get("tier2_pr", {})
        if t2.get("number") and t2.get("target_repo"):
            _github_api("PATCH", f"https://api.github.com/repos/{t2['target_repo']}/pulls/{t2['number']}",
                        token, {"state": new_state})
            t2["state"] = new_state

        pr_info["state_changed"] = datetime.now().isoformat(timespec="seconds")
        _write_pr_info(jira_id, pr_info)

    except RuntimeError as e:
        raise HTTPException(502, f"GitHub API error: {e}")

    return {"status": new_state, "pr": pr_info}


# ---------------------------------------------------------------------------
# Jira Integration — live ticket status
# ---------------------------------------------------------------------------

_JIRA_URL = os.environ.get("JIRA_URL", "")
_JIRA_USERNAME = os.environ.get("JIRA_USERNAME", "")
_JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")

# In-memory cache: jira_id → (data, timestamp) — bounded LRU
_jira_cache: dict[str, tuple[dict, float]] = {}
_JIRA_CACHE_TTL = 300  # 5 minutes
_JIRA_CACHE_MAX = 200  # max entries before eviction


def _jira_configured() -> bool:
    return bool(_JIRA_URL and _JIRA_USERNAME and _JIRA_API_TOKEN)


def _jira_fetch(jira_id: str) -> dict:
    """Fetch ticket data from Jira REST API with caching."""
    now = time.time()
    cached = _jira_cache.get(jira_id)
    if cached and (now - cached[1]) < _JIRA_CACHE_TTL:
        return cached[0]

    # Build Basic auth header
    creds = base64.b64encode(f"{_JIRA_USERNAME}:{_JIRA_API_TOKEN}".encode()).decode()
    fields = "summary,status,assignee,priority,issuetype,labels,components,created,updated,resolution"
    url = f"{_JIRA_URL.rstrip('/')}/rest/api/2/issue/{jira_id}?fields={fields}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {creds}",
        "Accept": "application/json",
    })

    # Allow self-signed certs for internal instances
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"Ticket {jira_id} not found", "status_code": 404}
        return {"error": f"Jira API error: {e.code}", "status_code": e.code}
    except Exception as e:
        return {"error": f"Failed to connect to Jira: {e}"}

    f = raw.get("fields", {})
    result = {
        "key": raw.get("key", jira_id),
        "summary": f.get("summary", ""),
        "status": f.get("status", {}).get("name", ""),
        "status_category": f.get("status", {}).get("statusCategory", {}).get("key", ""),
        "assignee": f.get("assignee", {}).get("displayName", "Unassigned") if f.get("assignee") else "Unassigned",
        "assignee_avatar": f.get("assignee", {}).get("avatarUrls", {}).get("24x24", "") if f.get("assignee") else "",
        "priority": f.get("priority", {}).get("name", "") if f.get("priority") else "",
        "priority_icon": f.get("priority", {}).get("iconUrl", "") if f.get("priority") else "",
        "issue_type": f.get("issuetype", {}).get("name", "") if f.get("issuetype") else "",
        "issue_type_icon": f.get("issuetype", {}).get("iconUrl", "") if f.get("issuetype") else "",
        "labels": f.get("labels", []),
        "components": [c.get("name", "") for c in f.get("components", [])],
        "resolution": f.get("resolution", {}).get("name", "") if f.get("resolution") else None,
        "created": f.get("created", ""),
        "updated": f.get("updated", ""),
        "url": f"{_JIRA_URL.rstrip('/')}/browse/{jira_id}",
    }

    # Evict oldest entries if cache exceeds max size
    if len(_jira_cache) >= _JIRA_CACHE_MAX:
        oldest = sorted(_jira_cache, key=lambda k: _jira_cache[k][1])
        for k in oldest[:len(_jira_cache) - _JIRA_CACHE_MAX + 1]:
            del _jira_cache[k]
    _jira_cache[jira_id] = (result, now)
    return result


@app.get("/api/jira/status")
def jira_status():
    """Check Jira integration status."""
    return {
        "configured": _jira_configured(),
        "url": _JIRA_URL if _jira_configured() else None,
        "username": _JIRA_USERNAME if _jira_configured() else None,
        "cache_size": len(_jira_cache),
        "cache_ttl": _JIRA_CACHE_TTL,
    }


@app.get("/api/jira/batch")
def get_jira_batch(ids: str = ""):
    """Fetch multiple Jira tickets at once. ids=PROJ-12345,PROJ-12346"""
    if not _jira_configured():
        return {"configured": False, "tickets": {}}

    jira_ids = [j.strip().upper() for j in ids.split(",") if j.strip()]
    if not jira_ids:
        return {"configured": True, "tickets": {}}

    tickets = {}
    for jid in jira_ids[:20]:  # Cap at 20 to avoid abuse
        if re.match(r"^[A-Z]+-\d+$", jid):
            tickets[jid] = _jira_fetch(jid)

    return {"configured": True, "tickets": tickets}


@app.get("/api/jira/{jira_id}")
def get_jira_ticket(jira_id: str):
    """Get live Jira ticket status."""
    jira_id = jira_id.strip().upper()
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID: {jira_id}")

    if not _jira_configured():
        return {
            "configured": False,
            "message": "Jira integration not configured. Set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN env vars.",
        }

    data = _jira_fetch(jira_id)
    if "error" in data:
        raise HTTPException(data.get("status_code", 502), data["error"])

    return {"configured": True, **data}


# ---------------------------------------------------------------------------
# Pipeline Reset — re-run from a specific phase
# ---------------------------------------------------------------------------

_PHASE_ORDER = ["stp", "std", "codegen"]

# Map phases to the output directories/files they produce
_PHASE_OUTPUTS: dict[str, list[str]] = {
    "stp": ["stp/{id}/{id}_test_plan.md", "reviews/{id}/{id}_stp_review.md"],
    "std": ["std/{id}/", "reviews/{id}/{id}_std_review.md"],
    "codegen": ["go-tests/{id}/", "python-tests/{id}/"],
}


@app.post("/api/pipelines/{jira_id}/reset/{from_phase}")
def reset_pipeline(jira_id: str, from_phase: str, request: Request, x_api_key: str = Header(default="")):
    """Reset a pipeline from a given phase — clears that phase and all downstream outputs."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")
    if from_phase not in _PHASE_ORDER:
        raise HTTPException(400, f"Unknown phase: {from_phase}. Valid: {', '.join(_PHASE_ORDER)}")

    start_idx = _PHASE_ORDER.index(from_phase)
    phases_to_clear = _PHASE_ORDER[start_idx:]
    cleared: list[str] = []

    for phase in phases_to_clear:
        for pattern in _PHASE_OUTPUTS.get(phase, []):
            path_str = pattern.format(id=jira_id)
            target = OUTPUTS / path_str
            if target.exists():
                if target.is_dir():
                    # Archive to .previous before deleting
                    prev = target.parent / ".previous" / target.name
                    prev.parent.mkdir(parents=True, exist_ok=True)
                    if prev.exists():
                        import shutil
                        shutil.rmtree(prev)
                    target.rename(prev)
                else:
                    # Archive file to .previous
                    prev_dir = target.parent / ".previous"
                    prev_dir.mkdir(parents=True, exist_ok=True)
                    prev_file = prev_dir / target.name
                    if prev_file.exists():
                        prev_file.unlink()
                    import shutil
                    shutil.copy2(target, prev_file)
                    target.unlink()
                cleared.append(path_str)

        # Clear approvals for this phase
        approvals = _read_approvals(jira_id)
        if phase in approvals:
            del approvals[phase]
            _write_approvals(jira_id, approvals)

    # Clear PR info if resetting from stp or earlier (full re-run)
    if start_idx <= 1:
        pr_file = OUTPUTS / "state" / jira_id / "pr_info.yaml"
        if pr_file.exists():
            pr_file.unlink()
            cleared.append(f"state/{jira_id}/pr_info.yaml")

    return {
        "status": "reset",
        "jira_id": jira_id,
        "from_phase": from_phase,
        "phases_cleared": phases_to_clear,
        "files_cleared": cleared,
    }


# ---------------------------------------------------------------------------
# Delete Pipeline — remove all outputs for a Jira ID
# ---------------------------------------------------------------------------

@app.delete("/api/pipelines/{jira_id}")
def delete_pipeline(jira_id: str, request: Request, x_api_key: str = Header(default="")):
    """Delete all outputs for a pipeline. Allowed from dashboard UI or with API key."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    import shutil

    deleted_dirs: list[str] = []
    for subdir in ("stp", "std", "reviews", "go-tests", "python-tests", "state"):
        target = OUTPUTS / subdir / jira_id
        if target.is_dir():
            shutil.rmtree(target)
            deleted_dirs.append(f"{subdir}/{jira_id}")

    if not deleted_dirs:
        raise HTTPException(404, f"No outputs found for {jira_id}")

    logger.info("Deleted pipeline %s: %s", jira_id, deleted_dirs)
    return {
        "status": "deleted",
        "jira_id": jira_id,
        "deleted": deleted_dirs,
    }


# ---------------------------------------------------------------------------
# Artifact Diff — compare current vs previous version
# ---------------------------------------------------------------------------

@app.get("/api/artifacts/{jira_id}/{artifact_type}/diff")
def artifact_diff(jira_id: str, artifact_type: str):
    """Return diff between current and previous version of an artifact."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    # Map artifact_type to file path
    type_to_path = {
        "stp": f"stp/{jira_id}/{jira_id}_test_plan.md",
        "stp_review": f"reviews/{jira_id}/{jira_id}_stp_review.md",
        "std": f"std/{jira_id}/{jira_id}_test_description.yaml",
        "std_review": f"reviews/{jira_id}/{jira_id}_std_review.md",
    }
    rel_path = type_to_path.get(artifact_type)
    if not rel_path:
        raise HTTPException(400, f"Diff not supported for artifact type: {artifact_type}")

    current_file = OUTPUTS / rel_path
    prev_file = current_file.parent / ".previous" / current_file.name

    if not current_file.exists():
        raise HTTPException(404, "Current artifact not found")
    if not prev_file.exists():
        return {"has_diff": False, "message": "No previous version available"}

    current_text = current_file.read_text(errors="replace")
    prev_text = prev_file.read_text(errors="replace")

    if current_text == prev_text:
        return {"has_diff": False, "message": "No changes between versions"}

    # Generate unified diff
    import difflib
    diff_lines = list(difflib.unified_diff(
        prev_text.splitlines(keepends=True),
        current_text.splitlines(keepends=True),
        fromfile=f"previous/{current_file.name}",
        tofile=f"current/{current_file.name}",
        n=3,
    ))
    additions = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    return {
        "has_diff": True,
        "diff": "".join(diff_lines),
        "stats": {"additions": additions, "deletions": deletions},
    }


# ---------------------------------------------------------------------------
# Pipeline Summary Export
# ---------------------------------------------------------------------------

@app.get("/api/pipelines/{jira_id}/summary")
def pipeline_summary(jira_id: str):
    """Generate a markdown summary of a pipeline for sharing."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    state_file = OUTPUTS / "state" / jira_id / "pipeline_state.yaml"
    state = _read_yaml(state_file) if state_file.exists() else _infer_state(jira_id)
    phases = state.get("phases", {})
    project_id = state.get("project_id", _infer_project(jira_id))
    pr_info = _read_pr_info(jira_id)

    phase_labels = {
        "stp": "STP", "std": "STD", "codegen": "Test Generation",
    }
    status_emoji = {
        "completed": "done", "in_progress": "in progress",
        "awaiting_approval": "awaiting approval", "pending": "pending", "failed": "failed",
    }

    lines = [
        f"## QualityFlow Pipeline: {jira_id}",
        f"**Project:** {project_id.upper()}  ",
        f"**Jira:** {jira_id}  ",
        "",
        "| Phase | Status | Verdict |",
        "|-------|--------|---------|",
    ]
    for p_name in _PHASE_ORDER:
        phase = phases.get(p_name, {})
        st = status_emoji.get(phase.get("status", "pending"), phase.get("status", "pending"))
        verdict = phase.get("verdict", "-")
        label = phase_labels.get(p_name, p_name)
        lines.append(f"| {label} | {st} | {verdict} |")

    if pr_info and pr_info.get("url"):
        lines.extend([
            "",
            f"**PR:** [{pr_info.get('target_repo', '')}#{pr_info.get('number', '')}]({pr_info['url']}) ({pr_info.get('state', 'unknown')})",
        ])
        if pr_info.get("tier2_pr", {}).get("url"):
            t2 = pr_info["tier2_pr"]
            lines.append(f"**Tier 2 PR:** [{t2.get('target_repo', '')}#{t2.get('number', '')}]({t2['url']})")

    lines.extend(["", f"*Generated by QualityFlow dashboard — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*"])

    return {"markdown": "\n".join(lines), "jira_id": jira_id}


# ---------------------------------------------------------------------------
# Slack Notifications
# ---------------------------------------------------------------------------

_SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")


def _slack_notify(text: str, blocks: list[dict] | None = None) -> None:
    """Post a notification to Slack via webhook. Fire-and-forget."""
    if not _SLACK_WEBHOOK:
        return
    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(_SLACK_WEBHOOK, data=data, method="POST", headers={
            "Content-Type": "application/json",
        })
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)


def _slack_pipeline_event(jira_id: str, event: str, detail: str = "", url: str = "") -> None:
    """Send a formatted pipeline event to Slack."""
    project_id = _infer_project(jira_id)
    jira_url = f"https://your-org.atlassian.net/browse/{jira_id}"
    text = f"*{event}* | <{jira_url}|{jira_id}> ({project_id.upper()})"
    if detail:
        text += f"\n{detail}"
    if url:
        text += f"\n<{url}|View PR>"
    _slack_notify(text)


# ---------------------------------------------------------------------------
# Direct Coverage Ingestion — parse raw coverage files uploaded via API
# ---------------------------------------------------------------------------

COVERAGE_DIR = OUTPUTS / "coverage"



def _parse_go_coverage(content: str) -> dict:
    """Parse Go coverage.out into normalized coverage data with line-level detail.

    Format: mode: {atomic|set|count}
            file:startLine.startCol,endLine.endCol numStatements hitCount

    Each entry maps to a range of lines. We expand these into per-line hit data
    so GitHub Check annotations can point to specific uncovered lines.
    """
    files: dict[str, dict] = {}
    file_line_hits: dict[str, dict[int, int]] = {}  # file -> {line -> max_hits}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("mode:"):
            continue
        # e.g. github.com/my-org/my-repo/pkg/handler/service.go:42.58,45.2 3 1
        colon_idx = line.rfind(":")
        if colon_idx == -1:
            continue
        filepath = line[:colon_idx]
        rest = line[colon_idx + 1:]
        parts = rest.split()
        if len(parts) < 2:
            continue
        try:
            stmts = int(parts[-2])
            hits = int(parts[-1])
        except ValueError:
            continue
        if filepath not in files:
            files[filepath] = {"statements": 0, "hits": 0, "misses": 0}
            file_line_hits[filepath] = {}
        files[filepath]["statements"] += stmts
        if hits > 0:
            files[filepath]["hits"] += stmts
        else:
            files[filepath]["misses"] += stmts

        # Extract line range: "startLine.startCol,endLine.endCol"
        range_part = parts[0] if parts else ""
        range_match = re.match(r"(\d+)\.\d+,(\d+)\.\d+", range_part)
        if range_match:
            start_line = int(range_match.group(1))
            end_line = int(range_match.group(2))
            for ln in range(start_line, end_line + 1):
                # Keep the max hit count if multiple ranges overlap a line
                file_line_hits[filepath][ln] = max(file_line_hits[filepath].get(ln, 0), hits)

    # Build normalized result
    file_reports = []
    total_stmts = 0
    total_hits = 0
    total_misses = 0
    for fpath, data in sorted(files.items()):
        pct = (data["hits"] / data["statements"] * 100) if data["statements"] > 0 else 0
        # Build line_details from expanded line ranges
        line_details = []
        for ln in sorted(file_line_hits.get(fpath, {}).keys()):
            line_details.append({"line": ln, "hits": file_line_hits[fpath][ln]})
        file_reports.append({
            "name": fpath,
            "coverage": round(pct, 2),
            "lines": data["statements"],
            "hits": data["hits"],
            "misses": data["misses"],
            "line_details": line_details,
        })
        total_stmts += data["statements"]
        total_hits += data["hits"]
        total_misses += data["misses"]

    overall = (total_hits / total_stmts * 100) if total_stmts > 0 else 0
    return {
        "totals": {
            "coverage": round(overall, 2),
            "files": len(files),
            "lines": total_stmts,
            "hits": total_hits,
            "misses": total_misses,
        },
        "files": file_reports,
    }


def _parse_lcov(content: str) -> dict:
    """Parse LCOV format into normalized coverage data with line-level detail.

    LCOV records:
      SF:<filepath>
      DA:<linenum>,<hitcount>
      LF:<lines_found>
      LH:<lines_hit>
      end_of_record
    """
    files: dict[str, dict] = {}
    file_line_details: dict[str, list] = {}
    current_file = None
    cur_hits = 0
    cur_lines = 0
    cur_line_details: list[dict] = []

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SF:"):
            current_file = line[3:]
            cur_hits = 0
            cur_lines = 0
            cur_line_details = []
        elif line.startswith("DA:"):
            parts = line[3:].split(",")
            if len(parts) >= 2:
                cur_lines += 1
                try:
                    ln = int(parts[0])
                    h = int(parts[1])
                    cur_line_details.append({"line": ln, "hits": h})
                    if h > 0:
                        cur_hits += 1
                except ValueError:
                    pass
        elif line.startswith("LF:"):
            try:
                cur_lines = int(line[3:])
            except ValueError:
                pass
        elif line.startswith("LH:"):
            try:
                cur_hits = int(line[3:])
            except ValueError:
                pass
        elif line == "end_of_record" and current_file:
            files[current_file] = {
                "lines": cur_lines,
                "hits": cur_hits,
                "misses": cur_lines - cur_hits,
            }
            file_line_details[current_file] = cur_line_details
            current_file = None

    file_reports = []
    total_lines = 0
    total_hits = 0
    total_misses = 0
    for fpath, data in sorted(files.items()):
        pct = (data["hits"] / data["lines"] * 100) if data["lines"] > 0 else 0
        file_reports.append({
            "name": fpath,
            "coverage": round(pct, 2),
            "lines": data["lines"],
            "hits": data["hits"],
            "misses": data["misses"],
            "line_details": file_line_details.get(fpath, []),
        })
        total_lines += data["lines"]
        total_hits += data["hits"]
        total_misses += data["misses"]

    overall = (total_hits / total_lines * 100) if total_lines > 0 else 0
    return {
        "totals": {
            "coverage": round(overall, 2),
            "files": len(files),
            "lines": total_lines,
            "hits": total_hits,
            "misses": total_misses,
        },
        "files": file_reports,
    }


def _parse_cobertura_xml(content: str) -> dict:
    """Parse Cobertura XML into normalized coverage data with line-level detail.

    Works with Python pytest-cov, Java JaCoCo, and other Cobertura-format outputs.
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return {"totals": {"coverage": 0, "files": 0, "lines": 0, "hits": 0, "misses": 0}, "files": []}

    file_reports = []
    total_lines = 0
    total_hits = 0

    for pkg in root.iter("package"):
        for cls in pkg.iter("class"):
            fname = cls.get("filename", "")
            lines_el = cls.findall(".//line")
            flines = len(lines_el)
            fhits = sum(1 for el in lines_el if int(el.get("hits", "0")) > 0)
            pct = (fhits / flines * 100) if flines > 0 else 0
            line_details = []
            for el in lines_el:
                try:
                    line_details.append({
                        "line": int(el.get("number", "0")),
                        "hits": int(el.get("hits", "0")),
                    })
                except ValueError:
                    pass
            file_reports.append({
                "name": fname,
                "coverage": round(pct, 2),
                "lines": flines,
                "hits": fhits,
                "misses": flines - fhits,
                "line_details": line_details,
            })
            total_lines += flines
            total_hits += fhits

    overall = (total_hits / total_lines * 100) if total_lines > 0 else 0
    total_misses = total_lines - total_hits
    return {
        "totals": {
            "coverage": round(overall, 2),
            "files": len(file_reports),
            "lines": total_lines,
            "hits": total_hits,
            "misses": total_misses,
        },
        "files": file_reports,
    }


def _detect_and_parse_coverage(content: str) -> dict:
    """Auto-detect coverage format and parse it."""
    stripped = content.strip()
    if stripped.startswith("mode:"):
        return _parse_go_coverage(content)
    if stripped.startswith("<?xml") or stripped.startswith("<coverage"):
        return _parse_cobertura_xml(content)
    if "SF:" in content and "end_of_record" in content:
        return _parse_lcov(content)
    raise ValueError("Unrecognized coverage format. Supported: Go coverage.out, LCOV, Cobertura XML")


def _coverage_repo_dir(org: str, repo: str) -> Path:
    """Return the storage directory for a repo's coverage data."""
    # Sanitize org/repo to prevent path traversal
    safe_org = re.sub(r"[^a-zA-Z0-9_.-]", "_", org)
    safe_repo = re.sub(r"[^a-zA-Z0-9_.-]", "_", repo)
    return COVERAGE_DIR / safe_org / safe_repo


def _store_coverage(org: str, repo: str, commit: str, branch: str, data: dict) -> Path:
    """Store parsed coverage data as YAML."""
    repo_dir = _coverage_repo_dir(org, repo)
    repo_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "org": org,
        "repo": repo,
        "commit": commit,
        "branch": branch,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": data["totals"],
        "files": data["files"],
    }

    # Store by commit
    commit_file = repo_dir / f"{commit}.yaml"
    commit_file.write_text(yaml.dump(record, default_flow_style=False, sort_keys=False))

    # Update latest pointer
    latest_file = repo_dir / "latest.yaml"
    latest_file.write_text(yaml.dump(record, default_flow_style=False, sort_keys=False))

    # Append to history (keep last 50 commits)
    history_file = repo_dir / "history.yaml"
    history: list[dict] = []
    if history_file.exists():
        try:
            history = yaml.safe_load(history_file.read_text()) or []
        except Exception:
            history = []
    # Add summary entry (no per-file data to keep history lean)
    history.insert(0, {
        "commit": commit,
        "branch": branch,
        "timestamp": record["timestamp"],
        "totals": data["totals"],
    })
    history = history[:50]
    history_file.write_text(yaml.dump(history, default_flow_style=False, sort_keys=False))

    return commit_file


def _load_latest_coverage(org: str, repo: str) -> dict | None:
    """Load the latest coverage data for a repo."""
    latest = _coverage_repo_dir(org, repo) / "latest.yaml"
    if not latest.exists():
        return None
    try:
        return yaml.safe_load(latest.read_text())
    except Exception:
        return None


def _load_coverage_history(org: str, repo: str) -> list[dict]:
    """Load coverage history for a repo."""
    hist = _coverage_repo_dir(org, repo) / "history.yaml"
    if not hist.exists():
        return []
    try:
        return yaml.safe_load(hist.read_text()) or []
    except Exception:
        return []


def _build_coverage_tree(files: list[dict]) -> list[dict]:
    """Build a hierarchical tree from flat file coverage data."""
    tree: dict = {}
    for f in files:
        parts = f["name"].split("/")
        node = tree
        for i, part in enumerate(parts):
            if part not in node:
                node[part] = {"_children": {}, "_data": None}
            if i == len(parts) - 1:
                node[part]["_data"] = f
            node = node[part]["_children"]

    def _to_list(node: dict) -> list[dict]:
        result = []
        for name, val in sorted(node.items()):
            children = _to_list(val["_children"])
            if val["_data"]:
                # Leaf file
                entry = {
                    "name": name,
                    "coverage": val["_data"]["coverage"],
                    "lines": val["_data"]["lines"],
                    "hits": val["_data"]["hits"],
                    "misses": val["_data"]["misses"],
                    "type": "file",
                }
            else:
                # Directory — aggregate children
                total_lines = sum(c.get("lines", 0) for c in children)
                total_hits = sum(c.get("hits", 0) for c in children)
                pct = (total_hits / total_lines * 100) if total_lines > 0 else 0
                entry = {
                    "name": name,
                    "coverage": round(pct, 2),
                    "lines": total_lines,
                    "hits": total_hits,
                    "misses": total_lines - total_hits,
                    "type": "directory",
                    "children": children,
                }
            result.append(entry)
        return result

    return _to_list(tree)




@app.post("/api/coverage/upload")
async def upload_coverage(request: Request, x_api_key: str = Header(default="")):
    """Upload raw coverage data (Go coverage.out, LCOV, or Cobertura XML).

    Query params:
        org: GitHub/GitLab org (required)
        repo: Repository name (required)
        commit: Git commit SHA (required)
        branch: Git branch (default: main)
    """
    _require_api_key(x_api_key)
    _check_rate_limit(request)

    org = request.query_params.get("org", "").strip()
    repo_name = request.query_params.get("repo", "").strip()
    commit = request.query_params.get("commit", "").strip()
    branch = request.query_params.get("branch", "main").strip()

    if not org or not repo_name or not commit:
        raise HTTPException(400, "Required query params: org, repo, commit")
    if not re.match(r"^[a-fA-F0-9]{7,40}$", commit):
        raise HTTPException(400, f"Invalid commit SHA: {commit}")
    # Sanitize inputs
    if not re.match(r"^[a-zA-Z0-9_.-]+$", org):
        raise HTTPException(400, f"Invalid org name: {org}")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", repo_name):
        raise HTTPException(400, f"Invalid repo name: {repo_name}")

    # Read body — enforce 10 MB limit for coverage files
    content_length = request.headers.get("content-length", "")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        raise HTTPException(413, "Coverage file too large. Maximum 10 MB.")

    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty request body")
    if len(body) > 10 * 1024 * 1024:
        raise HTTPException(413, "Coverage file too large. Maximum 10 MB.")

    content = body.decode("utf-8", errors="replace")

    try:
        parsed = _detect_and_parse_coverage(content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    stored = _store_coverage(org, repo_name, commit, branch, parsed)
    logger.info("Coverage uploaded: %s/%s@%s — %.1f%% (%d files)",
                org, repo_name, commit[:7], parsed["totals"]["coverage"], parsed["totals"]["files"])

    return {
        "status": "ok",
        "org": org,
        "repo": repo_name,
        "commit": commit,
        "branch": branch,
        "totals": parsed["totals"],
        "source": "direct",
        "stored_at": str(stored),
    }



# ---------------------------------------------------------------------------
# One-Click Coverage Collection — run tests, parse results, store
# ---------------------------------------------------------------------------

_collection_tasks: dict[str, dict] = {}


def _find_repo_config(org: str, repo: str) -> dict | None:
    """Find coverage config entry for a given org/repo."""
    for r in _get_coverage_repos_config():
        if r.get("org") == org and r.get("repo") == repo:
            return r
    return None


# ---------------------------------------------------------------------------
# K8s Job-based Coverage — for e2e repos that need cluster access
# ---------------------------------------------------------------------------

_K8S_API = "https://kubernetes.default.svc"
_K8S_CA = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
_K8S_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_K8S_NS_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


def _k8s_namespace() -> str:
    return _K8S_NS_PATH.read_text().strip() if _K8S_NS_PATH.exists() else "qualityflow"


def _k8s_token() -> str:
    return _K8S_TOKEN_PATH.read_text().strip() if _K8S_TOKEN_PATH.exists() else ""


def _k8s_request(method: str, path: str, body: dict | None = None,
                 timeout: int = 30) -> tuple[int, dict | str]:
    """HTTP request to the in-cluster K8s API."""
    import urllib.request
    import urllib.error
    import ssl

    url = f"{_K8S_API}{path}"
    ctx = ssl.create_default_context(cafile=str(_K8S_CA)) if _K8S_CA.exists() else ssl._create_unverified_context()
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {_k8s_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        raw = resp.read().decode()
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def _k8s_get_pod_logs(pod_name: str, tail: int | None = None) -> str:
    """Read pod logs via K8s API (returns plain text, not JSON)."""
    import urllib.request
    import ssl

    ns = _k8s_namespace()
    path = f"/api/v1/namespaces/{ns}/pods/{pod_name}/log"
    if tail:
        path += f"?tailLines={tail}"
    url = f"{_K8S_API}{path}"
    ctx = ssl.create_default_context(cafile=str(_K8S_CA)) if _K8S_CA.exists() else ssl._create_unverified_context()
    headers = {"Authorization": f"Bearer {_k8s_token()}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60, context=ctx)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[log read error: {e}]"


# The Python script that runs INSIDE the K8s Job pod.
# It clones the repo, installs deps, runs pytest --cov, and outputs
# Cobertura XML between markers so the dashboard can extract it.
_E2E_COVERAGE_SCRIPT = r'''
import subprocess, sys, os, json
from pathlib import Path

ORG = os.environ["COV_ORG"]
REPO = os.environ["COV_REPO"]
TEST_PATHS = [p for p in os.environ.get("COV_TEST_PATHS", ".").split(",") if p]
TIMEOUT = int(os.environ.get("COV_TIMEOUT", "7200"))

print(f"=== QualityFlow E2E Coverage Job ===")
print(f"Repo: {ORG}/{REPO}")
print(f"Test paths: {TEST_PATHS}")

# Clone
print(">>> Cloning repository...")
subprocess.run(["git", "clone", "--depth=1",
                f"https://github.com/{ORG}/{REPO}.git", "/tmp/repo"], check=True)
os.chdir("/tmp/repo")
sha = subprocess.run(["git", "rev-parse", "HEAD"],
                     capture_output=True, text=True).stdout.strip()
print(f">>>SHA:{sha}")

# Install test tools
print(">>> Installing test tools...")
subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                "pytest", "pytest-cov", "coverage"], capture_output=True)

# Install repo dependencies
print(">>> Installing dependencies...")

def pip_install(*args):
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", *args],
        capture_output=True, text=True, timeout=300
    ).returncode == 0

# Strategy 1: requirements files
for rf in ["requirements.txt", "test-requirements.txt",
           "requirements/base.txt", "requirements/test.txt"]:
    if Path(rf).exists():
        print(f"  Installing from {rf}...")
        pip_install("-r", rf)

# Strategy 2: editable install
for sf in ["pyproject.toml", "setup.py"]:
    if Path(sf).exists():
        print(f"  Trying editable install from {sf}...")
        if pip_install("-e", "."):
            print("  Editable install OK")
            break
        # Strategy 3: parse pyproject.toml
        if sf == "pyproject.toml":
            print("  Editable install failed, parsing pyproject.toml...")
            try:
                import tomllib
                with open("pyproject.toml", "rb") as f:
                    data = tomllib.load(f)
                deps = list(data.get("project", {}).get("dependencies", []))
                for g in ["test", "tests", "dev", "utilities-test"]:
                    deps.extend(data.get("project", {}).get("optional-dependencies", {}).get(g, []))
                dep_groups = data.get("dependency-groups", {})
                for g in ["test", "tests", "dev"]:
                    deps.extend(dep_groups.get(g, []))
                ok = 0
                for d in deps:
                    if isinstance(d, str) and not d.startswith("{"):
                        if pip_install(d):
                            ok += 1
                print(f"  Installed {ok}/{len(deps)} deps")
            except Exception as e:
                print(f"  Parse error: {e}")
        break

# Generate kubeconfig from SA token (so kubernetes Python client works)
sa_dir = Path("/var/run/secrets/kubernetes.io/serviceaccount")
if sa_dir.exists():
    kube_dir = Path(os.environ.get("HOME", "/tmp")) / ".kube"
    kube_dir.mkdir(parents=True, exist_ok=True)
    ns = (sa_dir / "namespace").read_text().strip()
    kube_cfg = f"""apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority: {sa_dir}/ca.crt
    server: https://kubernetes.default.svc
  name: in-cluster
contexts:
- context:
    cluster: in-cluster
    namespace: {ns}
    user: sa
  name: default
current-context: default
users:
- name: sa
  user:
    tokenFile: {sa_dir}/token
"""
    (kube_dir / "config").write_text(kube_cfg)
    print(f">>> Generated kubeconfig for namespace '{ns}'")

# Run pre-test commands (patches, config, etc.)
PRE_CMDS = os.environ.get("COV_PRE_TEST_COMMANDS", "")
if PRE_CMDS:
    for cmd_line in PRE_CMDS.split(";;"):
        cmd_line = cmd_line.strip()
        if cmd_line:
            print(f">>> Pre-test: {cmd_line}")
            subprocess.run(cmd_line, shell=True)

# Run tests with coverage
EXTRA_ARGS = [a for a in os.environ.get("COV_PYTEST_ARGS", "").split(";;") if a.strip()]
print(">>> Running tests with coverage...")
base_args = ["--cov=.", "--cov-report=xml:/tmp/coverage.xml",
             "--override-ini=addopts=", "--tb=short"]
# Only fail-fast if no extra args override behavior
if not EXTRA_ARGS:
    base_args.append("-x")
cmd = [sys.executable, "-m", "pytest"] + TEST_PATHS + base_args + EXTRA_ARGS
try:
    r = subprocess.run(cmd, timeout=TIMEOUT)
    print(f">>> pytest exit code: {r.returncode}")
except subprocess.TimeoutExpired:
    print(f">>> pytest timed out after {TIMEOUT}s")
except Exception as e:
    print(f">>> pytest error: {e}")

# Output coverage with markers
if Path("/tmp/coverage.xml").exists():
    print("===COVERAGE_XML_START===")
    print(Path("/tmp/coverage.xml").read_text())
    print("===COVERAGE_XML_END===")
else:
    print("===NO_COVERAGE_DATA===")

print(">>> Finished")
'''


def _create_coverage_job(org: str, repo: str, config: dict) -> str:
    """Create a K8s Job for e2e coverage collection. Returns job name."""
    ns = _k8s_namespace()
    ts = int(time.time())
    safe_repo = re.sub(r"[^a-z0-9-]", "-", repo.lower())[:30]
    job_name = f"cov-{safe_repo}-{ts}"

    test_paths = ",".join(config.get("test_paths", ["."]))
    timeout_val = str(config.get("timeout", 7200))
    image = config.get("image", f"{ns}/qualityflow-dashboard:latest")

    job_body = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": ns,
            "labels": {"app": "qualityflow-coverage", "repo": safe_repo},
        },
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": int(timeout_val) + 600,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": {"app": "qualityflow-coverage", "job-name": job_name}},
                "spec": {
                    "serviceAccountName": "external-user",
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "runner",
                        "image": image,
                        "command": ["python3", "-c", _E2E_COVERAGE_SCRIPT],
                        "env": [
                            {"name": "COV_ORG", "value": org},
                            {"name": "COV_REPO", "value": repo},
                            {"name": "COV_TEST_PATHS", "value": test_paths},
                            {"name": "COV_TIMEOUT", "value": timeout_val},
                            {"name": "COV_PRE_TEST_COMMANDS",
                             "value": ";;".join(config.get("pre_test_commands", []))},
                            {"name": "COV_PYTEST_ARGS",
                             "value": ";;".join(config.get("pytest_args", []))},
                            {"name": "HOME", "value": "/tmp"},
                        ] + [{"name": k, "value": v}
                             for k, v in config.get("test_env", {}).items()],
                        "resources": {
                            "requests": {"memory": "2Gi", "cpu": "1"},
                            "limits": {"memory": "8Gi", "cpu": "4"},
                        },
                    }],
                },
            },
        },
    }

    status, resp = _k8s_request("POST", f"/apis/batch/v1/namespaces/{ns}/jobs", job_body)
    if status not in (200, 201):
        detail = resp["message"] if isinstance(resp, dict) and "message" in resp else str(resp)
        raise RuntimeError(f"K8s API {status}: {detail}")
    logger.info("Created coverage Job %s for %s/%s", job_name, org, repo)
    return job_name


def _get_job_status(job_name: str) -> dict:
    """Get Job completion status."""
    ns = _k8s_namespace()
    status, resp = _k8s_request("GET", f"/apis/batch/v1/namespaces/{ns}/jobs/{job_name}")
    if status != 200 or not isinstance(resp, dict):
        return {"error": True, "message": str(resp)}
    js = resp.get("status", {})
    return {
        "active": bool(js.get("active", 0)),
        "succeeded": bool(js.get("succeeded", 0)),
        "failed": bool(js.get("failed", 0)),
    }


def _get_job_pod_name(job_name: str) -> str | None:
    """Find the pod created by a Job."""
    ns = _k8s_namespace()
    status, resp = _k8s_request(
        "GET", f"/api/v1/namespaces/{ns}/pods?labelSelector=job-name={job_name}")
    if status != 200 or not isinstance(resp, dict):
        return None
    items = resp.get("items", [])
    return items[0]["metadata"]["name"] if items else None


def _delete_job(job_name: str):
    """Delete a completed Job and its pods."""
    ns = _k8s_namespace()
    _k8s_request("DELETE", f"/apis/batch/v1/namespaces/{ns}/jobs/{job_name}",
                 {"propagationPolicy": "Background"})
    logger.info("Deleted coverage Job %s", job_name)


def _collect_e2e_coverage(task_id: str, org: str, repo: str, config: dict):
    """Collect coverage for e2e repos by spawning a K8s Job on the cluster."""
    task = _collection_tasks[task_id]

    # --- Create Job ---
    task["step"] = "creating_job"
    task["message"] = "Creating test runner Job on cluster..."
    try:
        job_name = _create_coverage_job(org, repo, config)
    except Exception as e:
        task["status"] = "failed"
        task["message"] = f"Failed to create Job: {e}"
        return
    task["job_name"] = job_name
    task["message"] = f"Job '{job_name}' created, waiting for pod..."

    # --- Poll Job until completion ---
    task["step"] = "running_job"
    max_wait = config.get("timeout", 7200) + 900
    start = time.time()
    pod_name = None

    while time.time() - start < max_wait:
        js = _get_job_status(job_name)

        if js.get("error"):
            task["status"] = "failed"
            task["message"] = f"Job status error: {js.get('message', 'unknown')}"
            return

        if js["succeeded"]:
            task["message"] = "Tests completed, reading results..."
            break

        if js["failed"]:
            if not pod_name:
                pod_name = _get_job_pod_name(job_name)
            if pod_name:
                logs = _k8s_get_pod_logs(pod_name, tail=30)
                task["message"] = f"Tests failed:\n{logs[-500:]}"
            else:
                task["message"] = "Job failed (no logs available)"
            task["status"] = "failed"
            _delete_job(job_name)
            return

        # Still running — show progress from pod logs
        if not pod_name:
            pod_name = _get_job_pod_name(job_name)
        if pod_name:
            logs = _k8s_get_pod_logs(pod_name, tail=3)
            last_lines = [ln for ln in logs.strip().splitlines() if ln.strip()]
            if last_lines:
                task["message"] = last_lines[-1][:120]
        else:
            task["message"] = "Waiting for pod to start..."

        time.sleep(15)
    else:
        task["status"] = "failed"
        task["message"] = f"Job timed out after {max_wait}s"
        _delete_job(job_name)
        return

    # --- Extract coverage from pod logs ---
    task["step"] = "parsing"
    task["message"] = "Parsing coverage results..."
    if not pod_name:
        pod_name = _get_job_pod_name(job_name)
    if not pod_name:
        task["status"] = "failed"
        task["message"] = "Job completed but pod not found"
        _delete_job(job_name)
        return

    logs = _k8s_get_pod_logs(pod_name)

    # Extract commit SHA
    sha_match = re.search(r">>>SHA:([a-f0-9]+)", logs)
    sha = sha_match.group(1) if sha_match else "unknown"
    task["commit"] = sha[:12]

    # Extract Cobertura XML between markers
    marker_start = "===COVERAGE_XML_START==="
    marker_end = "===COVERAGE_XML_END==="

    if marker_start in logs and marker_end in logs:
        xml_content = logs.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
        try:
            parsed = _detect_and_parse_coverage(xml_content)
            _store_coverage(org, repo, sha, "main", parsed)
            task["status"] = "completed"
            pct = parsed["totals"]["coverage"]
            nf = parsed["totals"]["files"]
            task["message"] = f"Coverage collected — {pct:.1f}% across {nf} files"
            task["totals"] = parsed["totals"]
        except Exception as e:
            task["status"] = "failed"
            task["message"] = f"Failed to parse coverage XML: {e}"
    elif "===NO_COVERAGE_DATA===" in logs:
        # Tests ran but produced no coverage — show last log lines as context
        tail = [ln for ln in logs.splitlines() if ln.strip() and "===" not in ln][-10:]
        task["status"] = "failed"
        task["message"] = "Tests ran but no coverage data generated.\n" + "\n".join(tail)
    else:
        task["status"] = "failed"
        task["message"] = "Job completed but no coverage markers found in output"

    _delete_job(job_name)


def _collection_worker(task_id: str, org: str, repo: str, repo_config: dict):
    """Background worker: run tests with coverage profiling, parse, store."""
    task = _collection_tasks[task_id]
    repo_path = repo_config.get("local_path", "")
    language = repo_config.get("language", "go")

    try:
        task["status"] = "running"

        # --- E2e Python repos: delegate to K8s Job (needs cluster access) ---
        is_e2e = "e2e-tests" in repo_config.get("flags", [])
        on_cluster = _K8S_TOKEN_PATH.exists()
        if language == "python" and is_e2e and on_cluster:
            _collect_e2e_coverage(task_id, org, repo, repo_config)
            return

        # --- Resolve repo path ---
        task["step"] = "resolving"
        task["message"] = "Locating repository..."

        if repo_path and Path(repo_path).is_dir():
            work_dir = Path(repo_path)
            cloned = False
        else:
            # Shallow clone for public repos
            task["message"] = f"Cloning {org}/{repo} (shallow)..."
            clone_dir = Path(tempfile.mkdtemp(prefix="qf-cov-"))
            try:
                subprocess.run(
                    ["git", "clone", "--depth=1", f"https://github.com/{org}/{repo}.git", str(clone_dir)],
                    check=True, capture_output=True, timeout=300,
                )
            except subprocess.TimeoutExpired:
                task["status"] = "failed"
                task["message"] = "Clone timed out (5min limit)"
                shutil.rmtree(clone_dir, ignore_errors=True)
                return
            except Exception as exc:
                task["status"] = "failed"
                task["message"] = f"Clone failed: {exc}"
                shutil.rmtree(clone_dir, ignore_errors=True)
                return
            work_dir = clone_dir
            cloned = True

        # --- Get commit SHA ---
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(work_dir),
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception:
            sha = "unknown"
        task["commit"] = sha[:12]

        # --- Auto-detect language if not configured ---
        if not language or language == "unknown":
            if (work_dir / "go.mod").exists():
                language = "go"
            elif (work_dir / "pyproject.toml").exists() or (work_dir / "setup.py").exists():
                language = "python"
            else:
                # Check file extensions
                go_files = list(work_dir.glob("**/*_test.go"))
                py_files = list(work_dir.glob("**/test_*.py"))
                language = "go" if len(go_files) > len(py_files) else "python"

        # --- Run tests ---
        if language == "go":
            _collect_go_coverage(task_id, work_dir, org, repo, sha, repo_config)
        elif language == "python":
            _collect_python_coverage(task_id, work_dir, org, repo, sha, repo_config)
        else:
            task["status"] = "failed"
            task["message"] = f"Unsupported language: {language}"
            return

        # --- Cleanup clone if needed ---
        if cloned:
            shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as exc:
        task["status"] = "failed"
        task["message"] = f"Unexpected error: {exc}"


def _collect_go_coverage(task_id: str, work_dir: Path, org: str, repo: str, sha: str, config: dict):
    """Run Go tests with coverage profiling, merge profiles, store."""
    task = _collection_tasks[task_id]

    # Check Go is available
    go_check = subprocess.run(["go", "version"], capture_output=True, text=True, timeout=5)
    if go_check.returncode != 0:
        task["status"] = "failed"
        task["message"] = "Go is not installed"
        return

    # Low-memory Go environment: aggressive GC, single-threaded compilation
    go_env = {**os.environ, "GOGC": "50", "GOFLAGS": "-p=1"}

    # Download dependencies if go.mod exists (needed for cloned repos)
    if (work_dir / "go.mod").exists():
        task["step"] = "dependencies"
        task["message"] = "Downloading Go dependencies..."
        mod_result = subprocess.run(
            ["go", "mod", "download"], cwd=str(work_dir),
            capture_output=True, text=True, timeout=600, env=go_env,
        )
        if mod_result.returncode != 0:
            logger.warning("go mod download warnings: %s", mod_result.stderr[:500])

    # Determine packages to test
    test_packages = config.get("test_packages")
    if not test_packages:
        # Auto-discover packages with test files
        task["step"] = "discovering"
        task["message"] = "Discovering testable packages..."
        try:
            disc = subprocess.run(
                ["go", "list", "-f", "{{if .TestGoFiles}}{{.ImportPath}}{{end}}", "./..."],
                cwd=str(work_dir), capture_output=True, text=True, timeout=300, env=go_env,
            )
            if disc.returncode == 0 and disc.stdout.strip():
                test_packages = [p for p in disc.stdout.strip().splitlines() if p]
                if len(test_packages) > 30:
                    test_packages = test_packages[:30]
            else:
                test_packages = ["./..."]
        except subprocess.TimeoutExpired:
            test_packages = ["./..."]

    # Pre-compile to warm the build cache (avoids per-package compile timeouts)
    # Uses -p=1 via GOFLAGS to limit parallelism and reduce peak memory
    task["step"] = "compiling"
    task["message"] = "Compiling packages (build cache warmup, low-memory mode)..."
    try:
        subprocess.run(
            ["go", "build", "-o", "/dev/null", "./..."],
            cwd=str(work_dir), capture_output=True, text=True, timeout=900, env=go_env,
        )
    except subprocess.TimeoutExpired:
        task["message"] = "Build warmup timed out, continuing with tests..."

    task["step"] = "testing"
    task["message"] = f"Testing {len(test_packages)} package groups..."
    task["total_packages"] = len(test_packages)
    task["completed_packages"] = 0
    task["package_results"] = []

    _fd, _tmp = tempfile.mkstemp(suffix=".out", prefix="qf-cov-merged-")
    os.close(_fd)
    merged_profile = Path(_tmp)
    partial_profiles: list[Path] = []

    try:
        for i, pkg in enumerate(test_packages):
            task["step"] = "testing"
            pkg_short = pkg.split("/")[-1] if "/" in pkg else pkg.replace("./", "").rstrip("/.")
            task["message"] = f"Testing {pkg_short} ({i+1}/{len(test_packages)})..."
            task["completed_packages"] = i

            _fd, _tmp = tempfile.mkstemp(suffix=".out", prefix=f"qf-cov-{i}-")
            os.close(_fd)
            profile_path = Path(_tmp)
            try:
                result = subprocess.run(
                    ["go", "test", "-coverprofile", str(profile_path), "-covermode=atomic", "-timeout=180s", pkg],
                    cwd=str(work_dir), capture_output=True, text=True, timeout=300, env=go_env,
                )
            except subprocess.TimeoutExpired:
                task["package_results"].append({"pkg": pkg_short, "status": "fail", "error": "timeout"})
                if profile_path.exists():
                    profile_path.unlink(missing_ok=True)
                continue

            if profile_path.exists() and profile_path.stat().st_size > 20:
                partial_profiles.append(profile_path)
                # Extract coverage % from output
                cov_pct = ""
                for line in result.stdout.splitlines():
                    if "coverage:" in line:
                        cov_pct = line.split("coverage:")[1].strip().split()[0]
                        break
                task["package_results"].append({"pkg": pkg_short, "status": "ok", "coverage": cov_pct})
            else:
                err_msg = result.stderr[:200] if result.stderr else "no output"
                task["package_results"].append({"pkg": pkg_short, "status": "fail", "error": err_msg})
                if profile_path.exists():
                    profile_path.unlink(missing_ok=True)

        task["completed_packages"] = len(test_packages)

        if not partial_profiles:
            task["status"] = "failed"
            task["message"] = "No packages produced coverage data"
            return

        # --- Merge profiles ---
        task["step"] = "merging"
        task["message"] = f"Merging {len(partial_profiles)} coverage profiles..."

        with open(merged_profile, "w") as out:
            out.write("mode: atomic\n")
            for pf in partial_profiles:
                with open(pf) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("mode:"):
                            out.write(line + "\n")

        # --- Parse and store ---
        task["step"] = "storing"
        task["message"] = "Parsing and storing coverage data..."

        raw = merged_profile.read_text()
        parsed = _detect_and_parse_coverage(raw)
        if not parsed:
            task["status"] = "failed"
            task["message"] = "Failed to parse merged coverage"
            return

        _store_coverage(org, repo, sha, "main", parsed)

        task["status"] = "completed"
        task["message"] = "Coverage collected successfully"
        task["totals"] = parsed["totals"]

    finally:
        # Cleanup temp files
        for pf in partial_profiles:
            if pf.exists():
                pf.unlink(missing_ok=True)
        if merged_profile.exists():
            merged_profile.unlink(missing_ok=True)


def _extract_pyproject_deps(pyproject_path: Path) -> list[str]:
    """Parse pyproject.toml and extract the dependencies list directly.

    This bypasses requires-python checks that cause pip install -e . to fail
    when the container Python version doesn't match the project's requirement.
    """
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return []
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        deps = list(data.get("project", {}).get("dependencies", []))
        # Also grab optional test/dev dependency groups
        opt = data.get("project", {}).get("optional-dependencies", {})
        for group_name in ("test", "tests", "dev", "utilities-test"):
            deps.extend(opt.get(group_name, []))
        # Also check PEP 735 dependency-groups
        dep_groups = data.get("dependency-groups", {})
        for group_name in ("test", "tests", "dev"):
            deps.extend(dep_groups.get(group_name, []))
        # Filter out self-references like "myproject[extra]" and include-group dicts
        return [d for d in deps if isinstance(d, str)]
    except Exception:
        return []


def _collect_python_coverage(task_id: str, work_dir: Path, org: str, repo: str, sha: str, config: dict):
    """Run Python tests with coverage, parse, store."""
    task = _collection_tasks[task_id]

    # --- Install project dependencies ---
    task["step"] = "dependencies"
    task["message"] = "Installing Python dependencies..."
    deps_ok = False

    # Strategy 1: Try requirements files first (most reliable)
    for req_file in ["requirements.txt", "requirements/base.txt", "requirements/test.txt",
                     "test-requirements.txt", "requirements-dev.txt"]:
        req_path = work_dir / req_file
        if req_path.exists():
            task["message"] = f"Installing from {req_file}..."
            r = subprocess.run(
                ["pip", "install", "--no-cache-dir", "-r", str(req_path)],
                cwd=str(work_dir), capture_output=True, text=True, timeout=600,
            )
            if r.returncode == 0:
                deps_ok = True

    # Strategy 2: Try editable install from pyproject.toml / setup.py
    if not deps_ok:
        for setup_file in ["pyproject.toml", "setup.py", "setup.cfg"]:
            if (work_dir / setup_file).exists():
                task["message"] = f"Installing project from {setup_file}..."
                r = subprocess.run(
                    ["pip", "install", "--no-cache-dir", "-e", "."],
                    cwd=str(work_dir), capture_output=True, text=True, timeout=600,
                )
                if r.returncode == 0:
                    deps_ok = True
                break

    # Strategy 3: If editable install failed (e.g. Python version mismatch),
    # parse pyproject.toml directly and install deps individually
    if not deps_ok and (work_dir / "pyproject.toml").exists():
        task["message"] = "Editable install failed, extracting deps from pyproject.toml..."
        logger.info("pip install -e . failed, falling back to direct dep extraction")
        raw_deps = _extract_pyproject_deps(work_dir / "pyproject.toml")
        if raw_deps:
            # Install in batches to handle individual failures gracefully
            task["message"] = f"Installing {len(raw_deps)} dependencies directly..."
            # Split into chunks of 10 to avoid command-line length issues
            for i in range(0, len(raw_deps), 10):
                chunk = raw_deps[i:i + 10]
                r = subprocess.run(
                    ["pip", "install", "--no-cache-dir"] + chunk,
                    cwd=str(work_dir), capture_output=True, text=True, timeout=300,
                )
                if r.returncode != 0:
                    # Try one by one for the failed chunk
                    for dep in chunk:
                        subprocess.run(
                            ["pip", "install", "--no-cache-dir", dep],
                            cwd=str(work_dir), capture_output=True, text=True, timeout=120,
                        )
            deps_ok = True

    # Always ensure pytest-cov is available
    subprocess.run(
        ["pip", "install", "--no-cache-dir", "pytest-cov"],
        capture_output=True, text=True, timeout=60,
    )

    # --- Run pytest collection with coverage ---
    task["step"] = "testing"
    task["message"] = "Running pytest with coverage (collect-only)..."

    _fd, _tmp = tempfile.mkstemp(suffix=".xml", prefix="qf-pycov-")
    os.close(_fd)
    xml_path = Path(_tmp)
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--co", "-q",
             f"--cov={work_dir}", f"--cov-report=xml:{xml_path}",
             "--override-ini=addopts=", "--override-ini=testpaths=."],
            cwd=str(work_dir), capture_output=True, text=True, timeout=600,
        )

        if xml_path.exists() and xml_path.stat().st_size > 50:
            raw = xml_path.read_text()
            parsed = _detect_and_parse_coverage(raw)
            if parsed:
                _store_coverage(org, repo, sha, "main", parsed)
                task["status"] = "completed"
                task["message"] = "Coverage collected successfully"
                task["totals"] = parsed["totals"]
                return

        # --- Fallback: source-line scan for e2e repos where pytest can't collect ---
        task["message"] = "Tests need a live cluster — scanning source lines instead..."
        logger.info("pytest collection failed for %s/%s, falling back to source scan", org, repo)
        total_files = 0
        total_lines = 0
        file_data: list[dict] = []
        for py_file in sorted(work_dir.rglob("*.py")):
            rel = py_file.relative_to(work_dir)
            # Skip hidden dirs, venvs, build artifacts
            parts = rel.parts
            if any(p.startswith(".") or p in ("venv", ".venv", "__pycache__", "build", "dist", ".tox") for p in parts):
                continue
            try:
                lines = sum(1 for line in py_file.read_text(errors="ignore").splitlines()
                            if line.strip() and not line.strip().startswith("#"))
            except Exception:
                continue
            total_files += 1
            total_lines += lines
            file_data.append({"filename": str(rel), "lines": lines, "hits": 0, "misses": lines})

        if total_files == 0:
            task["status"] = "failed"
            task["message"] = "No Python source files found"
            return

        parsed = {
            "totals": {"coverage": 0.0, "files": total_files, "lines": total_lines, "hits": 0, "misses": total_lines},
            "files": file_data,
        }
        _store_coverage(org, repo, sha, "main", parsed)
        task["status"] = "completed"
        task["message"] = f"Source scan complete — {total_files} files, {total_lines} lines (0% covered, needs cluster execution)"
        task["totals"] = parsed["totals"]
    finally:
        if xml_path.exists():
            xml_path.unlink(missing_ok=True)


@app.post("/api/coverage/collect")
async def start_coverage_collection(request: Request, x_api_key: str = Header(default="")):
    """Start one-click coverage collection for a repo.

    Query params:
        org: GitHub org (required)
        repo: Repository name (required)
    """
    _check_api_key_or_origin(request, x_api_key)
    org = request.query_params.get("org", "").strip()
    repo_name = request.query_params.get("repo", "").strip()
    if not org or not repo_name:
        raise HTTPException(400, "org and repo query params are required")

    # Find repo config
    repo_config = _find_repo_config(org, repo_name)
    if not repo_config:
        raise HTTPException(404, f"No coverage config for {org}/{repo_name}")

    # Check if already collecting
    for t in _collection_tasks.values():
        if t.get("org") == org and t.get("repo") == repo_name and t["status"] in ("pending", "running"):
            return {"task_id": t["task_id"], "status": t["status"], "message": "Collection already in progress"}

    # Create task
    task_id = str(uuid.uuid4())[:8]
    task = {
        "task_id": task_id,
        "org": org,
        "repo": repo_name,
        "status": "pending",
        "step": "queued",
        "message": "Starting collection...",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "commit": "",
        "total_packages": 0,
        "completed_packages": 0,
        "package_results": [],
        "totals": None,
    }
    _collection_tasks[task_id] = task

    # Start background thread
    thread = threading.Thread(target=_collection_worker, args=(task_id, org, repo_name, repo_config), daemon=True)
    thread.start()

    return {"task_id": task_id, "status": "pending", "message": "Collection started"}


@app.get("/api/coverage/collect/{task_id}")
def get_collection_status(task_id: str):
    """Get status of a coverage collection task."""
    task = _collection_tasks.get(task_id)
    if not task:
        raise HTTPException(404, f"No collection task: {task_id}")
    return task


def _get_coverage_repos_config() -> list[dict]:
    """Load coverage repo mappings from project configs."""
    repos = []
    projects_dir = CONFIG / "projects"
    if not projects_dir.is_dir():
        return repos
    for proj_dir in sorted(projects_dir.iterdir()):
        cov_file = proj_dir / "coverage.yaml"
        if cov_file.exists():
            try:
                cov = yaml.safe_load(cov_file.read_text()) or {}
                for repo_entry in cov.get("repos", []):
                    repo_entry["project_id"] = proj_dir.name
                    repos.append(repo_entry)
            except Exception:
                pass
        else:
            # Auto-derive from repositories.yaml
            repo_file = proj_dir / "repositories.yaml"
            if repo_file.exists():
                try:
                    repo_cfg = yaml.safe_load(repo_file.read_text()) or {}
                    primary = repo_cfg.get("primary_repo", {})
                    if primary.get("org") and primary.get("name"):
                        repos.append({
                            "project_id": proj_dir.name,
                            "service": "github",
                            "org": primary["org"],
                            "repo": primary["name"],
                            "label": primary.get("full_name", f"{primary['org']}/{primary['name']}"),
                            "type": "primary",
                        })
                    tier2 = repo_cfg.get("tier2_repo", {})
                    if tier2.get("org") and tier2.get("name"):
                        repos.append({
                            "project_id": proj_dir.name,
                            "service": "github",
                            "org": tier2["org"],
                            "repo": tier2["name"],
                            "label": tier2.get("full_name", f"{tier2['org']}/{tier2['name']}"),
                            "type": "tier2",
                        })
                except Exception:
                    pass
    return repos


# ---------------------------------------------------------------------------
# Product Coverage — collect from live instrumented pods via CoverPort
# ---------------------------------------------------------------------------

_product_coverage_tasks: dict[str, dict] = {}


def _get_product_coverage_config(project_id: str = "") -> dict | None:
    """Load product_coverage config from coverage.yaml files."""
    projects_dir = CONFIG / "projects"
    if not projects_dir.is_dir():
        return None
    for proj_dir in sorted(projects_dir.iterdir()):
        if project_id and proj_dir.name != project_id:
            continue
        cov_file = proj_dir / "coverage.yaml"
        if cov_file.exists():
            try:
                cov = yaml.safe_load(cov_file.read_text()) or {}
                pc = cov.get("product_coverage")
                if pc:
                    pc["project_id"] = proj_dir.name
                    return pc
            except Exception:
                pass
    return None


def _k8s_list_pods(namespace: str, label_selector: str) -> list[dict]:
    """List pods matching a label selector in a namespace."""
    path = f"/api/v1/namespaces/{namespace}/pods?labelSelector={urllib.parse.quote(label_selector)}"
    status, resp = _k8s_request("GET", path)
    if status != 200 or not isinstance(resp, dict):
        return []
    return [
        {
            "name": p["metadata"]["name"],
            "status": p["status"].get("phase", "Unknown"),
            "ip": p["status"].get("podIP", ""),
            "node": p["spec"].get("nodeName", ""),
        }
        for p in resp.get("items", [])
        if p["status"].get("phase") == "Running"
    ]


def _k8s_portforward_get(namespace: str, pod_name: str, port: int,
                         path: str, timeout: int = 30) -> tuple[int, str]:
    """HTTP GET via K8s API pod proxy (acts like port-forward).

    Uses the K8s API server's pod proxy subresource to reach a pod's HTTP
    endpoint without needing a real port-forward tunnel.
    """
    api_path = f"/api/v1/namespaces/{namespace}/pods/{pod_name}:{port}/proxy{path}"
    status, resp = _k8s_request("GET", api_path, timeout=timeout)
    if isinstance(resp, dict):
        return status, json.dumps(resp)
    return status, resp


def _parse_coverport_go_response(data: str) -> dict | None:
    """Parse CoverPort Go coverage response (base64-encoded JSON).

    Returns parsed coverage with totals and file breakdown, or None.
    """
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None
    # CoverPort Go response fields: meta_data, counters_data (base64-encoded)
    meta_b64 = payload.get("meta_data", "") or payload.get("metadata", "")
    counters_b64 = payload.get("counters_data", "") or payload.get("counters", "")
    if not meta_b64 or not counters_b64:
        return None
    # Go binary coverage needs go tool covdata to process.
    # For now, store raw data and provide a summary.
    return {
        "format": "go-binary",
        "raw_metadata": meta_b64,
        "raw_counters": counters_b64,
        "raw_data_size": len(meta_b64) + len(counters_b64),
        "timestamp": payload.get("timestamp"),
    }


def _parse_coverport_python_response(data: str) -> dict | None:
    """Parse CoverPort Python coverage response (base64-encoded JSON or XML)."""
    try:
        payload = json.loads(data)
        cov_b64 = payload.get("coverage_data", "")
        if cov_b64:
            xml_data = base64.b64decode(cov_b64).decode("utf-8", errors="replace")
            return _parse_cobertura_xml(xml_data)
    except Exception:
        pass
    # Try as direct Cobertura XML
    if data.strip().startswith("<?xml") or "<coverage" in data[:200]:
        return _parse_cobertura_xml(data)
    return None


def _collect_product_coverage_worker(task_id: str, project_id: str):
    """Background worker: collect product coverage from all instrumented pods."""
    task = _product_coverage_tasks[task_id]
    task["status"] = "running"
    config = _get_product_coverage_config(project_id)
    if not config:
        task["status"] = "failed"
        task["message"] = f"No product_coverage config for project '{project_id}'"
        return

    namespace = config.get("namespace", "default")
    port = config.get("port", 53700)
    components = config.get("components", [])
    results = []

    for i, comp in enumerate(components):
        name = comp.get("name", f"component-{i}")
        label_sel = comp.get("label_selector", "")
        lang = comp.get("language", "go")

        task["message"] = f"Discovering {name} pods ({label_sel})..."
        task["current_component"] = name
        task["progress"] = f"{i}/{len(components)}"

        if not label_sel:
            results.append({"component": name, "status": "skipped", "reason": "no label_selector"})
            continue

        # Discover pods (per-component namespace overrides top-level)
        comp_ns = comp.get("namespace", namespace)
        pods = _k8s_list_pods(comp_ns, label_sel)
        if not pods:
            results.append({"component": name, "status": "no_pods", "pods_found": 0})
            continue

        comp_result = {"component": name, "pods_found": len(pods), "pods": []}

        for pod in pods:
            pod_name = pod["name"]
            task["message"] = f"Collecting coverage from {name}/{pod_name}..."

            # Health check first
            h_status, _ = _k8s_portforward_get(comp_ns, pod_name, port, "/health", timeout=10)
            if h_status != 200:
                comp_result["pods"].append({
                    "pod": pod_name, "status": "no_coverport",
                    "message": f"Health check failed (status {h_status}). Pod may not have CoverPort instrumentation.",
                })
                continue

            # Collect coverage
            c_status, c_data = _k8s_portforward_get(comp_ns, pod_name, port, "/coverage", timeout=60)
            if c_status != 200:
                comp_result["pods"].append({
                    "pod": pod_name, "status": "collection_failed",
                    "message": f"Coverage endpoint returned {c_status}",
                })
                continue

            # Parse based on language
            if lang == "python":
                parsed = _parse_coverport_python_response(c_data)
            else:
                parsed = _parse_coverport_go_response(c_data)

            if parsed:
                comp_result["pods"].append({
                    "pod": pod_name, "status": "collected",
                    "format": parsed.get("format", lang),
                    "has_data": True,
                })
                # Store the raw coverage data for this component
                _store_product_coverage(project_id, name, pod_name, parsed)
                # Also store raw response JSON for drill-down decoding
                safe_comp = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
                raw_path = OUTPUTS / "coverage" / "_product" / project_id / safe_comp / "raw_response.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(c_data if isinstance(c_data, str) else c_data.decode("utf-8", errors="replace"))
            else:
                comp_result["pods"].append({
                    "pod": pod_name, "status": "collected",
                    "format": "raw",
                    "has_data": True,
                    "raw_size": len(c_data),
                })
                _store_product_coverage(project_id, name, pod_name, {"format": "raw", "data": c_data[:10000]})

        results.append(comp_result)

    task["status"] = "completed"
    task["message"] = f"Collected from {len(components)} components"
    task["results"] = results
    task["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_product_coverage(project_id: str, component: str, pod: str, data: dict):
    """Store product coverage data for a component."""
    safe_comp = re.sub(r"[^a-zA-Z0-9_.-]", "_", component)
    safe_pod = re.sub(r"[^a-zA-Z0-9_.-]", "_", pod)
    out_dir = OUTPUTS / "coverage" / "_product" / project_id / safe_comp
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "component": component,
        "pod": pod,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **data,
    }
    (out_dir / f"{safe_pod}.yaml").write_text(
        yaml.dump(record, default_flow_style=False, sort_keys=False)
    )
    # Also update latest
    (out_dir / "latest.yaml").write_text(
        yaml.dump(record, default_flow_style=False, sort_keys=False)
    )


@app.post("/api/coverage/collect-product")
async def start_product_coverage_collection(
    request: Request, x_api_key: str = Header(default="")
):
    """One-click product coverage collection from instrumented pods.

    Discovers pods with CoverPort instrumentation via label selectors,
    port-forwards to their coverage HTTP server (port 53700), and retrieves
    coverage data. Requires dashboard running on-cluster.

    Query params:
        project: project ID (e.g. 'cnv') — uses product_coverage config
    """
    _check_api_key_or_origin(request, x_api_key)

    if not _K8S_TOKEN_PATH.exists():
        raise HTTPException(
            503,
            "Product coverage collection requires on-cluster deployment. "
            "Dashboard must run inside K8s with service account access.",
        )

    project_id = request.query_params.get("project", "").strip()
    if not project_id:
        raise HTTPException(400, "project query param is required (e.g. project=cnv)")

    config = _get_product_coverage_config(project_id)
    if not config:
        raise HTTPException(404, f"No product_coverage config for project '{project_id}'")

    # Check if already collecting
    for t in _product_coverage_tasks.values():
        if t.get("project") == project_id and t["status"] in ("pending", "running"):
            return {"task_id": t["task_id"], "status": t["status"], "message": "Collection in progress"}

    task_id = str(uuid.uuid4())[:8]
    task = {
        "task_id": task_id,
        "project": project_id,
        "status": "pending",
        "message": "Starting product coverage collection...",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current_component": "",
        "progress": "0/0",
        "results": [],
    }
    _product_coverage_tasks[task_id] = task

    thread = threading.Thread(
        target=_collect_product_coverage_worker,
        args=(task_id, project_id),
        daemon=True,
    )
    thread.start()

    return {"task_id": task_id, "status": "pending", "message": "Collection started",
            "components": [c["name"] for c in config.get("components", [])]}


@app.get("/api/coverage/collect-product/{task_id}")
def get_product_collection_status(task_id: str):
    """Get status of a product coverage collection task."""
    task = _product_coverage_tasks.get(task_id)
    if not task:
        raise HTTPException(404, f"No product collection task: {task_id}")
    return task


@app.post("/api/coverage/product/upload")
async def upload_product_coverage(request: Request, x_api_key: str = Header(default="")):
    """Upload product coverage from an external agent (e.g. Tekton Task on team cluster).

    This is Approach C — teams run a collection agent on their own cluster,
    which discovers CoverPort-instrumented pods, collects coverage via HTTP,
    and POSTs results here. The dashboard doesn't need cluster access.

    JSON body:
        project: project ID (e.g. 'cnv') (required)
        component: component name (e.g. 'virt-handler') (required)
        pod: pod name that was collected from (required)
        language: 'go' or 'python' (default: 'go')
        format: coverage format — 'go-binary', 'cobertura', 'coverage-py', 'raw' (default: 'raw')
        data: coverage data (base64-encoded binary or raw text) (required)
        metadata: optional dict with extra info (namespace, labels, node, etc.)
    """
    _require_api_key(x_api_key)
    _check_rate_limit(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    project_id = body.get("project", "").strip()
    component = body.get("component", "").strip()
    pod = body.get("pod", "").strip()
    if not project_id or not component or not pod:
        raise HTTPException(400, "Required fields: project, component, pod")

    # Sanitize
    if not re.match(r"^[a-zA-Z0-9_.-]+$", project_id):
        raise HTTPException(400, f"Invalid project ID: {project_id}")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", component):
        raise HTTPException(400, f"Invalid component name: {component}")

    cov_data = body.get("data", "")
    if not cov_data:
        raise HTTPException(400, "Missing 'data' field with coverage content")
    if len(str(cov_data)) > 10 * 1024 * 1024:
        raise HTTPException(413, "Coverage data too large. Maximum 10 MB.")

    lang = body.get("language", "go")
    fmt = body.get("format", "raw")
    extra_meta = body.get("metadata", {})

    # Parse if possible
    parsed = None
    if fmt == "cobertura" and isinstance(cov_data, str):
        raw_xml = cov_data
        if not raw_xml.strip().startswith("<?xml") and not "<coverage" in raw_xml[:200]:
            try:
                raw_xml = base64.b64decode(cov_data).decode("utf-8", errors="replace")
            except Exception:
                pass
        parsed = _parse_cobertura_xml(raw_xml)

    record = {
        "component": component,
        "pod": pod,
        "language": lang,
        "format": fmt,
        "source": "external",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if parsed:
        record["totals"] = parsed.get("totals", {})
        record["files"] = parsed.get("files", [])
    else:
        record["raw_data_size"] = len(str(cov_data))

    if extra_meta and isinstance(extra_meta, dict):
        record["metadata"] = extra_meta

    _store_product_coverage(project_id, component, pod, record)

    # Store raw coverage response for drill-down decoding (package names, etc.)
    if fmt in ("go-binary",) and isinstance(cov_data, str):
        safe_comp = re.sub(r"[^a-zA-Z0-9_.-]", "_", component)
        raw_path = OUTPUTS / "coverage" / "_product" / project_id / safe_comp / "raw_response.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(cov_data)

    logger.info("Product coverage uploaded: %s/%s/%s (source=external, format=%s)",
                project_id, component, pod, fmt)

    return {
        "status": "ok",
        "project": project_id,
        "component": component,
        "pod": pod,
        "format": fmt,
        "source": "external",
        "totals": record.get("totals"),
    }


# Route order matters: literal paths before parameterized ones.
# /config/{id} must precede /{id} and /{id}/{component}.

@app.get("/api/coverage/product/config/{project_id}")
def get_product_coverage_config_api(project_id: str):
    """Get product coverage configuration for a project."""
    config = _get_product_coverage_config(project_id)
    if not config:
        raise HTTPException(404, f"No product_coverage config for project '{project_id}'")
    return config


@app.get("/api/coverage/product/{project_id}")
def get_product_coverage_summary(project_id: str):
    """Get product coverage results for a project."""
    prod_dir = OUTPUTS / "coverage" / "_product" / project_id
    if not prod_dir.is_dir():
        raise HTTPException(404, f"No product coverage data for project '{project_id}'")
    components = []
    for comp_dir in sorted(prod_dir.iterdir()):
        if not comp_dir.is_dir():
            continue
        latest_file = comp_dir / "latest.yaml"
        if latest_file.exists():
            try:
                data = yaml.safe_load(latest_file.read_text()) or {}
                components.append({
                    "component": data.get("component", comp_dir.name),
                    "pod": data.get("pod"),
                    "timestamp": data.get("timestamp"),
                    "format": data.get("format"),
                    "source": data.get("source", "on-cluster"),
                    "totals": data.get("totals"),
                    "has_data": True,
                })
            except Exception:
                pass
    return {"project": project_id, "components": components}


def _extract_go_coverage_packages(meta_bytes: bytes) -> list[dict]:
    """Extract package and file names from Go binary coverage metadata."""
    packages = []
    # Extract printable strings of length >= 4 from the binary
    strings_found = []
    current = []
    for b in meta_bytes:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= 4:
                strings_found.append("".join(current))
            current = []
    if len(current) >= 4:
        strings_found.append("".join(current))

    def _clean_go_path(s: str) -> str:
        """Strip leading binary noise from a Go import path."""
        for marker in ("github.com/", "gitlab.com/", "golang.org/", "google.golang.org/"):
            idx = s.find(marker)
            if idx >= 0:
                return s[idx:]
        return s

    seen_pkgs: set[str] = set()
    for s in strings_found:
        cleaned = _clean_go_path(s)
        if "/" in cleaned and "." in cleaned and not cleaned.startswith("http"):
            if cleaned.endswith(".go"):
                pkg = cleaned.rsplit("/", 1)[0] if "/" in cleaned else cleaned
                if pkg not in seen_pkgs:
                    packages.append({"package": pkg, "files": [cleaned]})
                    seen_pkgs.add(pkg)
                else:
                    for p in packages:
                        if p["package"] == pkg:
                            p["files"].append(cleaned)
                            break
            elif cleaned.count("/") >= 2:
                if cleaned not in seen_pkgs:
                    packages.append({"package": cleaned, "files": []})
                    seen_pkgs.add(cleaned)

    return packages


@app.get("/api/coverage/product/{project_id}/{component}")
def get_product_coverage_detail(project_id: str, component: str):
    """Get detailed product coverage data for a specific component."""
    safe_comp = re.sub(r"[^a-zA-Z0-9_.-]", "_", component)
    comp_dir = OUTPUTS / "coverage" / "_product" / project_id / safe_comp
    if not comp_dir.is_dir():
        raise HTTPException(404, f"No data for component '{component}'")

    latest_file = comp_dir / "latest.yaml"
    if not latest_file.exists():
        raise HTTPException(404, f"No latest data for component '{component}'")

    data = yaml.safe_load(latest_file.read_text()) or {}

    # Try to decode Go coverage metadata to extract package/file info
    packages = []

    # Check if we have the raw coverage JSON stored
    raw_file = comp_dir / "raw_response.json"
    if raw_file.exists():
        try:
            raw_resp = json.loads(raw_file.read_text())
            meta_b64 = raw_resp.get("meta_data", "")
            if meta_b64:
                meta_bytes = base64.b64decode(meta_b64)
                packages = _extract_go_coverage_packages(meta_bytes)
        except Exception:
            pass

    # Build collection history from all YAML files in the directory
    history = []
    for f in sorted(comp_dir.iterdir(), reverse=True):
        if f.suffix == ".yaml" and f.name != "latest.yaml":
            try:
                entry = yaml.safe_load(f.read_text()) or {}
                history.append({
                    "pod": entry.get("pod"),
                    "timestamp": entry.get("timestamp"),
                    "source": entry.get("source", "on-cluster"),
                    "format": entry.get("format"),
                })
            except Exception:
                pass
    # Include latest in history
    history.insert(0, {
        "pod": data.get("pod"),
        "timestamp": data.get("timestamp"),
        "source": data.get("source", "on-cluster"),
        "format": data.get("format"),
        "current": True,
    })

    return {
        "component": data.get("component", component),
        "pod": data.get("pod"),
        "timestamp": data.get("timestamp"),
        "format": data.get("format"),
        "source": data.get("source", "on-cluster"),
        "language": data.get("language", "go"),
        "metadata": data.get("metadata", {}),
        "totals": data.get("totals"),
        "packages": packages,
        "history": history[:20],
    }


# ---------------------------------------------------------------------------
# Test Coverage (CI-based) — cross-repo coverage tracking
# ---------------------------------------------------------------------------
# Solves the "test repo ≠ product repo" problem: when tests in repo B
# run against code in repo A, this tracks which test PRs improve coverage
# of the source repo — without needing Codecov.
#
# Storage layout:
#   outputs/coverage/_tests/{project}/
#     latest.yaml          — current baseline coverage
#     history.yaml         — chronological list of uploads (last 100)
#     uploads/
#       {timestamp}_{commit_short}.yaml  — individual upload records
#     prs/
#       {test_repo}_{pr_number}.yaml     — per-PR contribution records

_TEST_COVERAGE_DIR = OUTPUTS / "coverage" / "_tests"


def _test_cov_project_dir(project_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", project_id)
    return _TEST_COVERAGE_DIR / safe


# --- GitHub API helpers for merge-base and patch coverage ---

def _github_api_get(url: str, token: str = "") -> dict | None:
    """GET a GitHub API URL. Returns parsed JSON or None on failure."""
    if not token:
        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.debug("GitHub API GET %s failed: %s", url, exc)
        return None


def _find_merge_base(source_repo: str, source_commit: str, base_branch: str = "main") -> str | None:
    """Find the merge-base commit between source_commit and base_branch.

    Uses GitHub's compare API: GET /repos/{owner}/{repo}/compare/{base}...{head}
    The response includes 'merge_base_commit.sha'.
    """
    url = f"https://api.github.com/repos/{source_repo}/compare/{base_branch}...{source_commit}"
    data = _github_api_get(url)
    if data and "merge_base_commit" in data:
        return data["merge_base_commit"]["sha"]
    return None


def _get_commit_diff_files(source_repo: str, base_sha: str, head_sha: str) -> list[dict]:
    """Get the files changed between base and head commits.

    Returns list of {filename, status, additions, deletions, patch} dicts.
    The 'patch' field contains the unified diff with line numbers.
    """
    url = f"https://api.github.com/repos/{source_repo}/compare/{base_sha}...{head_sha}"
    data = _github_api_get(url)
    if not data or "files" not in data:
        return []
    files = []
    for f in data["files"]:
        files.append({
            "filename": f.get("filename", ""),
            "status": f.get("status", ""),  # added, modified, removed, renamed
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "patch": f.get("patch", ""),
        })
    return files


def _parse_diff_line_numbers(patch: str) -> list[int]:
    """Extract added line numbers from a unified diff patch string.

    Parses @@ -a,b +c,d @@ hunk headers and counts '+' lines
    to determine which line numbers in the new file were added/changed.
    """
    if not patch:
        return []
    added_lines = []
    current_line = 0
    for line in patch.split("\n"):
        if line.startswith("@@"):
            # Parse +c,d from @@ -a,b +c,d @@
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(current_line)
            current_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # deleted line — don't advance new-file counter
        else:
            current_line += 1
    return added_lines


def _match_cov_file(fname: str, cov_map: dict) -> tuple[str | None, dict | None]:
    """Match a diff filename to coverage data. Returns (cov_key, cov_entry) or (None, None)."""
    for cov_file, cov_data in cov_map.items():
        if cov_file.endswith(fname) or fname.endswith(cov_file):
            return cov_file, cov_data
        cov_base = cov_file.rsplit("/", 1)[-1] if "/" in cov_file else cov_file
        diff_base = fname.rsplit("/", 1)[-1] if "/" in fname else fname
        if cov_base == diff_base:
            return cov_file, cov_data
    return None, None


def _compute_patch_coverage(
    parsed_files: list[dict],
    diff_files: list[dict],
) -> dict:
    """Compute patch coverage using per-line data when available.

    Uses line_details from parsers for precise line-level matching:
    each changed line in the diff is checked against the coverage data
    to determine if it was hit. Falls back to file-level approximation
    when line_details are not available.

    Returns {patch_coverage, covered_lines, total_lines,
             files: [{file, covered, total, coverage, uncovered_lines}]}
    """
    # Build coverage map: filename -> {coverage%, hits, lines, misses, line_hits}
    # line_hits is a dict of {line_number: hit_count} for precise matching
    cov_map: dict[str, dict] = {}
    for f in parsed_files:
        fname = f.get("name", "") or f.get("file", "")
        if not fname:
            continue
        line_hits: dict[int, int] = {}
        for ld in f.get("line_details", []):
            line_hits[ld["line"]] = ld["hits"]
        cov_map[fname] = {
            "coverage": f.get("coverage", 0),
            "hits": f.get("hits", 0),
            "lines": f.get("lines", 0) if isinstance(f.get("lines"), int) else len(f.get("lines", [])),
            "misses": f.get("misses", 0),
            "line_hits": line_hits,
        }

    total_changed = 0
    total_covered = 0
    file_details = []

    for df in diff_files:
        fname = df["filename"]
        if not any(fname.endswith(ext) for ext in (".go", ".py", ".java", ".js", ".ts", ".rs", ".c", ".cpp", ".h")):
            continue
        if df["status"] == "removed":
            continue

        added_lines = _parse_diff_line_numbers(df.get("patch", ""))
        if not added_lines:
            added_count = df.get("additions", 0)
            if added_count == 0:
                continue
        else:
            added_count = len(added_lines)

        _, matched = _match_cov_file(fname, cov_map)

        if matched and matched["line_hits"] and added_lines:
            # Precise mode: check each changed line against coverage data
            line_hits = matched["line_hits"]
            covered = sum(1 for ln in added_lines if line_hits.get(ln, 0) > 0)
            uncovered = [ln for ln in added_lines if line_hits.get(ln, 0) == 0]
            total_changed += added_count
            total_covered += covered
            file_details.append({
                "file": fname,
                "covered": covered,
                "total": added_count,
                "coverage": round(covered / added_count * 100, 1) if added_count else 0,
                "uncovered_lines": uncovered[:50],
            })
        elif matched:
            # Approximate mode: use file-level coverage
            file_cov = matched["coverage"]
            approx_covered = round(added_count * file_cov / 100)
            total_changed += added_count
            total_covered += approx_covered
            file_details.append({
                "file": fname,
                "covered": approx_covered,
                "total": added_count,
                "coverage": round(file_cov, 1),
            })
        else:
            total_changed += added_count
            file_details.append({
                "file": fname,
                "covered": 0,
                "total": added_count,
                "coverage": 0,
                "uncovered_lines": added_lines[:50] if added_lines else [],
            })

    patch_pct = round(total_covered / total_changed * 100, 1) if total_changed > 0 else 0
    return {
        "patch_coverage": patch_pct,
        "covered_lines": total_covered,
        "total_lines": total_changed,
        "files": file_details,
    }


# --- GitHub Checks API — line-level annotations on PRs ---

def _github_api_post(url: str, payload: dict, token: str = "") -> dict | None:
    """POST to a GitHub API URL. Returns parsed JSON or None on failure."""
    if not token:
        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        logger.warning("No GitHub token — cannot POST to %s", url)
        return None
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.warning("GitHub API POST %s failed: %s", url, exc)
        return None


def _github_api_patch(url: str, payload: dict, token: str = "") -> dict | None:
    """PATCH a GitHub API URL. Returns parsed JSON or None on failure."""
    if not token:
        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        return None
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PATCH", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.warning("GitHub API PATCH %s failed: %s", url, exc)
        return None


def _build_check_annotations(patch_result: dict) -> list[dict]:
    """Build GitHub Check Run annotations from patch coverage results.

    Creates annotations for uncovered lines in changed files.
    GitHub limits: 50 annotations per API call, up to 50 calls per check run.
    We prioritize files with lowest coverage first.
    """
    annotations = []
    # Sort files by coverage ascending (worst first)
    files = sorted(patch_result.get("files", []), key=lambda f: f.get("coverage", 0))

    for pf in files:
        filepath = pf["file"]
        uncovered = pf.get("uncovered_lines", [])
        file_cov = pf.get("coverage", 0)

        if not uncovered:
            # No line-level data — add a file-level annotation if coverage is low
            if file_cov < 50 and pf.get("total", 0) > 0:
                annotations.append({
                    "path": filepath,
                    "start_line": 1,
                    "end_line": 1,
                    "annotation_level": "warning",
                    "message": f"This file has {file_cov:.0f}% coverage ({pf['covered']}/{pf['total']} changed lines covered)",
                })
            continue

        # Group consecutive uncovered lines into ranges for cleaner annotations
        ranges = []
        start = uncovered[0]
        end = uncovered[0]
        for ln in uncovered[1:]:
            if ln == end + 1:
                end = ln
            else:
                ranges.append((start, end))
                start = ln
                end = ln
        ranges.append((start, end))

        for rng_start, rng_end in ranges:
            if len(annotations) >= 50:
                break
            line_count = rng_end - rng_start + 1
            if line_count == 1:
                msg = f"Line {rng_start} is not covered by tests"
            else:
                msg = f"Lines {rng_start}-{rng_end} ({line_count} lines) are not covered by tests"
            annotations.append({
                "path": filepath,
                "start_line": rng_start,
                "end_line": rng_end,
                "annotation_level": "warning",
                "message": msg,
            })

        if len(annotations) >= 50:
            break

    return annotations


def _create_github_check_run(
    source_repo: str,
    source_commit: str,
    totals: dict,
    delta_info: dict,
    patch_result: dict | None,
    project_id: str,
) -> dict | None:
    """Create a GitHub Check Run with coverage annotations on the source commit.

    This makes coverage results visible directly in the PR diff view —
    uncovered lines get yellow warning annotations, and the check run
    summary shows overall and patch coverage.
    """
    token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        logger.warning("No GitHub token — skipping check run creation")
        return None

    cov_pct = totals.get("coverage", 0)
    delta = delta_info.get("delta", 0)
    delta_str = f"+{delta:.2f}%" if delta > 0 else f"{delta:.2f}%"

    # Determine conclusion based on patch coverage
    conclusion = "success"
    if patch_result:
        patch_pct = patch_result.get("patch_coverage", 100)
        if patch_pct < 50:
            conclusion = "failure"
        elif patch_pct < 80:
            conclusion = "neutral"

    # Build summary markdown
    summary_lines = [
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **Overall Coverage** | **{cov_pct:.1f}%** |",
        f"| **Delta** | {delta_str} |",
    ]

    merge_base = delta_info.get("merge_base_sha")
    if merge_base:
        base_label = "merge-base" if not delta_info.get("fallback_used") else "latest upload"
        summary_lines.append(f"| **Base ({base_label})** | {delta_info.get('base_coverage', 0):.1f}% (`{merge_base[:7]}`) |")

    if patch_result and patch_result.get("total_lines", 0) > 0:
        patch_pct = patch_result["patch_coverage"]
        summary_lines.extend([
            f"| **Patch Coverage** | **{patch_pct:.1f}%** ({patch_result['covered_lines']}/{patch_result['total_lines']} lines) |",
        ])

    summary_lines.append(f"| **Files** | {totals.get('files', 0)} |")
    summary_lines.append(f"| **Lines** | {totals.get('lines', 0)} |")

    summary = "\n".join(summary_lines)

    # File breakdown
    if patch_result and patch_result.get("files"):
        summary += "\n\n### Changed Files\n\n| File | Coverage | Lines |\n|------|----------|-------|\n"
        for pf in patch_result["files"][:20]:
            fname = pf["file"].rsplit("/", 1)[-1] if "/" in pf["file"] else pf["file"]
            fc = pf.get("coverage", 0)
            icon = ":green_circle:" if fc >= 80 else (":yellow_circle:" if fc >= 50 else ":red_circle:")
            summary += f"| {icon} `{fname}` | {fc:.0f}% | {pf['covered']}/{pf['total']} |\n"

    # Build annotations from patch coverage
    annotations = []
    if patch_result:
        annotations = _build_check_annotations(patch_result)

    # Create the check run
    url = f"https://api.github.com/repos/{source_repo}/check-runs"
    payload: dict = {
        "name": "QualityFlow Coverage",
        "head_sha": source_commit,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": f"Coverage: {cov_pct:.1f}% ({delta_str})",
            "summary": summary,
            "annotations": annotations[:50],
        },
    }

    result = _github_api_post(url, payload, token)
    if result and result.get("id"):
        check_run_id = result["id"]
        logger.info("Created check run %s on %s@%s (%d annotations)",
                     check_run_id, source_repo, source_commit[:7], len(annotations))

        # If more than 50 annotations, send additional batches via PATCH
        remaining = annotations[50:]
        batch_num = 0
        while remaining and batch_num < 49:  # max 50 API calls total
            batch = remaining[:50]
            remaining = remaining[50:]
            batch_num += 1
            patch_url = f"https://api.github.com/repos/{source_repo}/check-runs/{check_run_id}"
            _github_api_patch(patch_url, {
                "output": {
                    "title": f"Coverage: {cov_pct:.1f}% ({delta_str})",
                    "summary": summary,
                    "annotations": batch,
                },
            }, token)

        return {"check_run_id": check_run_id, "annotations_count": len(annotations), "conclusion": conclusion}

    return None


def _lookup_commit_coverage(project_id: str, commit_sha: str) -> dict | None:
    """Look up stored coverage data for a specific source commit.

    First checks by_commit/ for exact match, then tries prefix match, then
    searches uploads/ by short SHA.
    """
    proj_dir = _test_cov_project_dir(project_id)
    by_commit_dir = proj_dir / "by_commit"
    # Exact match
    exact = by_commit_dir / f"{commit_sha}.yaml"
    if exact.exists():
        try:
            return yaml.safe_load(exact.read_text())
        except Exception:
            pass
    # Prefix match in by_commit/ (handles short SHA from merge-base)
    if by_commit_dir.is_dir():
        for f in by_commit_dir.iterdir():
            if f.suffix == ".yaml" and (f.stem.startswith(commit_sha[:12]) or commit_sha.startswith(f.stem[:12])):
                try:
                    return yaml.safe_load(f.read_text())
                except Exception:
                    pass
    # Fallback: scan uploads/
    uploads_dir = proj_dir / "uploads"
    if uploads_dir.is_dir():
        short = commit_sha[:7]
        for f in uploads_dir.iterdir():
            if f.suffix == ".yaml" and short in f.name:
                try:
                    return yaml.safe_load(f.read_text())
                except Exception:
                    pass
    return None


def _store_test_coverage(
    project_id: str,
    source_repo: str,
    source_commit: str,
    test_repo: str,
    test_pr: int | None,
    parsed: dict,
    branch: str = "main",
    metadata: dict | None = None,
) -> dict:
    """Store a test coverage upload and compute delta against merge-base.

    Uses GitHub API to find the merge-base commit and computes delta against
    that (like Codecov), falling back to the last upload if merge-base lookup
    fails. Also computes patch coverage if diff data is available.

    Returns a dict with delta info, merge-base info, and patch coverage.
    """
    proj_dir = _test_cov_project_dir(project_id)
    uploads_dir = proj_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    totals = parsed.get("totals", {})
    new_pct = totals.get("coverage", 0.0)

    # --- Merge-base comparison (Codecov-style) ---
    merge_base_sha = None
    base_coverage = None
    base_pct = 0.0
    merge_base_found = False

    # Try to find merge-base via GitHub API
    merge_base_sha = _find_merge_base(source_repo, source_commit, branch)
    if merge_base_sha:
        merge_base_found = True
        # Look up coverage stored for the merge-base commit
        base_data = _lookup_commit_coverage(project_id, merge_base_sha)
        if base_data:
            base_pct = base_data.get("totals", {}).get("coverage", 0.0)
            base_coverage = base_data
            logger.info("Merge-base found: %s (%.1f%% coverage)", merge_base_sha[:7], base_pct)
        else:
            logger.info("Merge-base %s found but no coverage data stored for it", merge_base_sha[:7])

    # Fallback: if no merge-base coverage, use latest upload
    fallback_used = False
    if base_coverage is None:
        latest_file = proj_dir / "latest.yaml"
        if latest_file.exists():
            try:
                prev = yaml.safe_load(latest_file.read_text()) or {}
                base_pct = prev.get("totals", {}).get("coverage", 0.0)
                fallback_used = True
            except Exception:
                pass

    delta = round(new_pct - base_pct, 2)

    # --- Patch coverage (file-level diff analysis) ---
    patch_cov = None
    if merge_base_sha:
        diff_files = _get_commit_diff_files(source_repo, merge_base_sha, source_commit)
        if diff_files and parsed.get("files"):
            patch_cov = _compute_patch_coverage(parsed["files"], diff_files)
            logger.info("Patch coverage: %.1f%% (%d/%d changed lines covered)",
                        patch_cov["patch_coverage"],
                        patch_cov["covered_lines"],
                        patch_cov["total_lines"])

    record = {
        "project": project_id,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "source_branch": branch,
        "test_repo": test_repo,
        "test_pr": test_pr,
        "timestamp": ts,
        "totals": totals,
        "delta": delta,
        "base_coverage": base_pct,
        "merge_base": {
            "sha": merge_base_sha,
            "found": merge_base_found,
            "has_coverage": base_coverage is not None,
            "fallback_used": fallback_used,
        },
        "files": parsed.get("files", []),
    }
    if patch_cov:
        record["patch"] = patch_cov
    if metadata:
        record["metadata"] = metadata

    # Store individual upload (indexed by commit for future lookup)
    commit_short = source_commit[:7] if source_commit else "unknown"
    ts_safe = ts.replace(":", "-")
    upload_file = uploads_dir / f"{ts_safe}_{commit_short}.yaml"
    upload_file.write_text(yaml.dump(record, default_flow_style=False, sort_keys=False))

    # Also store by commit SHA for merge-base lookups
    by_commit_dir = proj_dir / "by_commit"
    by_commit_dir.mkdir(parents=True, exist_ok=True)
    commit_file = by_commit_dir / f"{source_commit}.yaml"
    commit_file.write_text(yaml.dump(record, default_flow_style=False, sort_keys=False))

    # Update latest baseline
    latest_file = proj_dir / "latest.yaml"
    latest_file.write_text(yaml.dump(record, default_flow_style=False, sort_keys=False))

    # Append to history (keep last 100)
    history_file = proj_dir / "history.yaml"
    history: list[dict] = []
    if history_file.exists():
        try:
            history = yaml.safe_load(history_file.read_text()) or []
        except Exception:
            history = []
    history_entry = {
        "source_commit": source_commit,
        "source_branch": branch,
        "source_repo": source_repo,
        "test_repo": test_repo,
        "test_pr": test_pr,
        "timestamp": ts,
        "totals": totals,
        "delta": delta,
        "merge_base_sha": merge_base_sha,
        "merge_base_found": merge_base_found,
    }
    if patch_cov:
        history_entry["patch_coverage"] = patch_cov["patch_coverage"]
    history.insert(0, history_entry)
    history = history[:100]
    history_file.write_text(yaml.dump(history, default_flow_style=False, sort_keys=False))

    # Store per-PR record if a test PR was provided
    if test_pr is not None:
        prs_dir = proj_dir / "prs"
        prs_dir.mkdir(parents=True, exist_ok=True)
        safe_test_repo = re.sub(r"[^a-zA-Z0-9_.-]", "_", test_repo)
        pr_file = prs_dir / f"{safe_test_repo}_{test_pr}.yaml"
        pr_record = {
            "test_repo": test_repo,
            "test_pr": test_pr,
            "source_repo": source_repo,
            "source_commit": source_commit,
            "source_branch": branch,
            "timestamp": ts,
            "totals": totals,
            "delta": delta,
            "base_coverage": base_pct,
            "merge_base_sha": merge_base_sha,
        }
        if patch_cov:
            pr_record["patch_coverage"] = patch_cov["patch_coverage"]
            pr_record["patch_lines_covered"] = patch_cov["covered_lines"]
            pr_record["patch_lines_total"] = patch_cov["total_lines"]
        pr_file.write_text(yaml.dump(pr_record, default_flow_style=False, sort_keys=False))

    return {
        "base_coverage": base_pct,
        "new_coverage": new_pct,
        "delta": delta,
        "merge_base_sha": merge_base_sha,
        "merge_base_found": merge_base_found,
        "fallback_used": fallback_used,
        "patch": patch_cov,
        "upload_file": str(upload_file),
    }


@app.post("/api/coverage/test/upload")
async def upload_test_coverage(request: Request, x_api_key: str = Header(default="")):
    """Upload test coverage from a CI run, tagged with source repo info.

    Accepts coverage data (Go coverage.out, LCOV, Cobertura XML) from a CI
    pipeline running tests in a test repo against a source/product repo.
    Computes and returns the delta against the previous baseline.

    JSON body:
        project: QualityFlow project ID (e.g. 'example') (required)
        source_repo: full repo path (e.g. 'my-org/my-repo') (required)
        source_commit: commit SHA in source repo that tests ran against (required)
        source_branch: branch in source repo (default: 'main')
        test_repo: full repo path of test repo (e.g. 'my-org/my-tests') (required)
        test_pr: PR number in test repo (optional — enables per-PR tracking)
        format: 'go', 'lcov', 'cobertura', or 'auto' (default: 'auto')
        data: coverage content as text, OR base64-encoded (required)
        metadata: optional dict with extra info (ci_job, runner, duration, etc.)
        post_pr_comment: if true and test_pr is set, post a coverage summary comment on the PR (default: false)
        create_check_run: if true, create a GitHub Check Run on source_commit with line-level annotations (default: false)
    """
    _require_api_key(x_api_key)
    _check_rate_limit(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    project_id = body.get("project", "").strip()
    source_repo = body.get("source_repo", "").strip()
    source_commit = body.get("source_commit", "").strip()
    source_branch = body.get("source_branch", "main").strip()
    test_repo = body.get("test_repo", "").strip()
    test_pr = body.get("test_pr")
    fmt = body.get("format", "auto").strip()
    cov_data = body.get("data", "")
    extra_meta = body.get("metadata", {})
    post_comment = body.get("post_pr_comment", False)
    create_checks = body.get("create_check_run", False)

    # Validate required fields
    if not project_id or not source_repo or not source_commit or not test_repo:
        raise HTTPException(400, "Required fields: project, source_repo, source_commit, test_repo")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", project_id):
        raise HTTPException(400, f"Invalid project ID: {project_id}")
    if not re.match(r"^[a-fA-F0-9]{7,40}$", source_commit):
        raise HTTPException(400, f"Invalid commit SHA: {source_commit}")
    if "/" not in source_repo or "/" not in test_repo:
        raise HTTPException(400, "source_repo and test_repo must be in 'org/repo' format")
    if test_pr is not None:
        try:
            test_pr = int(test_pr)
        except (ValueError, TypeError):
            raise HTTPException(400, "test_pr must be an integer")

    if not cov_data:
        raise HTTPException(400, "Missing 'data' field with coverage content")
    if len(str(cov_data)) > 10 * 1024 * 1024:
        raise HTTPException(413, "Coverage data too large. Maximum 10 MB.")

    # Decode base64 if needed
    content = cov_data
    if not isinstance(content, str):
        content = str(content)
    # Try base64 decode if it doesn't look like raw coverage text
    if not content.strip().startswith(("mode:", "<?xml", "<coverage", "TN:", "SF:")):
        try:
            content = base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            pass  # keep as-is

    # Parse coverage
    try:
        if fmt == "go" or (fmt == "auto" and content.strip().startswith("mode:")):
            parsed = _parse_go_coverage(content)
        elif fmt == "cobertura" or (fmt == "auto" and (content.strip().startswith("<?xml") or "<coverage" in content[:200])):
            parsed = _parse_cobertura_xml(content)
        elif fmt == "lcov" or (fmt == "auto" and "SF:" in content and "end_of_record" in content):
            parsed = _parse_lcov(content)
        elif fmt == "auto":
            parsed = _detect_and_parse_coverage(content)
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    except ValueError as e:
        raise HTTPException(400, f"Failed to parse coverage data: {e}")

    # Store and compute delta
    delta_info = _store_test_coverage(
        project_id=project_id,
        source_repo=source_repo,
        source_commit=source_commit,
        test_repo=test_repo,
        test_pr=test_pr,
        parsed=parsed,
        branch=source_branch,
        metadata=extra_meta if isinstance(extra_meta, dict) else None,
    )

    logger.info("Test coverage uploaded: %s — %s → %s (%.1f%%, delta=%+.2f%%)",
                project_id, test_repo, source_repo,
                parsed["totals"]["coverage"], delta_info["delta"])

    # Post PR comment if requested
    pr_comment_posted = False
    if post_comment and test_pr is not None:
        try:
            pr_comment_posted = _post_coverage_pr_comment(
                test_repo=test_repo,
                test_pr=test_pr,
                project_id=project_id,
                source_repo=source_repo,
                source_commit=source_commit,
                delta_info=delta_info,
                totals=parsed["totals"],
            )
        except Exception as exc:
            logger.warning("Failed to post PR comment: %s", exc)

    # Create GitHub Check Run with line annotations if requested
    check_run_result = None
    if create_checks:
        try:
            check_run_result = _create_github_check_run(
                source_repo=source_repo,
                source_commit=source_commit,
                totals=parsed["totals"],
                delta_info=delta_info,
                patch_result=delta_info.get("patch"),
                project_id=project_id,
            )
        except Exception as exc:
            logger.warning("Failed to create check run: %s", exc)

    result = {
        "status": "ok",
        "project": project_id,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "test_repo": test_repo,
        "test_pr": test_pr,
        "totals": parsed["totals"],
        "delta": delta_info["delta"],
        "base_coverage": delta_info["base_coverage"],
        "new_coverage": delta_info["new_coverage"],
        "merge_base": {
            "sha": delta_info.get("merge_base_sha"),
            "found": delta_info.get("merge_base_found", False),
            "fallback_used": delta_info.get("fallback_used", False),
        },
        "pr_comment_posted": pr_comment_posted,
    }
    if delta_info.get("patch"):
        result["patch"] = delta_info["patch"]
    if check_run_result:
        result["check_run"] = check_run_result
    return result


def _post_coverage_pr_comment(
    test_repo: str,
    test_pr: int,
    project_id: str,
    source_repo: str,
    source_commit: str,
    delta_info: dict,
    totals: dict,
) -> bool:
    """Post a coverage summary comment on a GitHub PR.

    Includes merge-base comparison and patch coverage when available.
    """
    token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        logger.warning("No GITHUB_TOKEN set — skipping PR comment")
        return False

    delta = delta_info["delta"]
    arrow = "+" if delta > 0 else ""
    indicator = ":arrow_up:" if delta > 0 else (":arrow_down:" if delta < 0 else ":left_right_arrow:")

    # Merge-base info
    merge_base_sha = delta_info.get("merge_base_sha")
    base_label = "Base (merge-base)" if merge_base_sha and not delta_info.get("fallback_used") else "Base (latest)"
    base_sha_display = f"`{merge_base_sha[:7]}`" if merge_base_sha else "—"

    comment_body = (
        f"## {indicator} Coverage Report — QualityFlow\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| **Coverage** | **{totals.get('coverage', 0):.1f}%** |\n"
        f"| **Delta vs {base_label}** | **{arrow}{delta:.2f}%** |\n"
        f"| **{base_label}** | {delta_info['base_coverage']:.1f}% ({base_sha_display}) |\n"
        f"| **Source Repo** | `{source_repo}` |\n"
        f"| **Source Commit** | `{source_commit[:7]}` |\n"
        f"| **Files** | {totals.get('files', 0)} |\n"
        f"| **Lines** | {totals.get('lines', 0)} |\n"
        f"| **Hits** | {totals.get('hits', 0)} |\n"
    )

    # Add patch coverage section if available
    patch = delta_info.get("patch")
    if patch and patch.get("total_lines", 0) > 0:
        patch_pct = patch["patch_coverage"]
        patch_indicator = ":white_check_mark:" if patch_pct >= 80 else (":warning:" if patch_pct >= 50 else ":x:")
        comment_body += (
            f"\n### {patch_indicator} Patch Coverage\n\n"
            f"**{patch_pct:.1f}%** of changed lines are covered "
            f"({patch['covered_lines']}/{patch['total_lines']} lines)\n\n"
        )
        # File-level breakdown (top 10)
        if patch.get("files"):
            comment_body += "| File | Coverage | Lines |\n|------|----------|-------|\n"
            for pf in patch["files"][:10]:
                fname = pf["file"].rsplit("/", 1)[-1] if "/" in pf["file"] else pf["file"]
                file_pct = pf.get("coverage", 0)
                file_icon = ":green_circle:" if file_pct >= 80 else (":yellow_circle:" if file_pct >= 50 else ":red_circle:")
                comment_body += f"| {file_icon} `{fname}` | {file_pct:.0f}% | {pf['covered']}/{pf['total']} |\n"
            comment_body += "\n"

    comment_body += (
        f"\n*Reported by [QualityFlow](https://github.com/your-org/qualityflow) "
        f"for project `{project_id}`*"
    )

    # Parse org/repo from test_repo
    parts = test_repo.split("/", 1)
    if len(parts) != 2:
        return False
    org, repo_name = parts

    url = f"https://api.github.com/repos/{org}/{repo_name}/issues/{test_pr}/comments"
    payload = json.dumps({"body": comment_body}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            if resp.status in (200, 201):
                logger.info("Posted coverage comment on %s#%d", test_repo, test_pr)
                return True
    except Exception as exc:
        logger.warning("PR comment failed: %s", exc)
    return False


# --- Test coverage query endpoints ---
# Route order: literal paths (/test/...) before parameterized ones.

@app.get("/api/coverage/test/{project_id}/history")
def get_test_coverage_history(project_id: str):
    """Get test coverage upload history for a project."""
    proj_dir = _test_cov_project_dir(project_id)
    history_file = proj_dir / "history.yaml"
    if not history_file.exists():
        return {"project": project_id, "history": []}
    try:
        history = yaml.safe_load(history_file.read_text()) or []
    except Exception:
        history = []
    return {"project": project_id, "history": history}


@app.get("/api/coverage/test/{project_id}/prs")
def get_test_coverage_prs(project_id: str):
    """Get per-PR coverage contributions for a project."""
    proj_dir = _test_cov_project_dir(project_id)
    prs_dir = proj_dir / "prs"
    if not prs_dir.is_dir():
        return {"project": project_id, "prs": []}
    prs = []
    for f in sorted(prs_dir.iterdir(), reverse=True):
        if f.suffix == ".yaml":
            try:
                data = yaml.safe_load(f.read_text()) or {}
                prs.append(data)
            except Exception:
                pass
    # Sort by timestamp descending
    prs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"project": project_id, "prs": prs[:50]}


@app.delete("/api/coverage/test/{project_id}/reset")
def reset_test_coverage(project_id: str, x_api_key: str = Header(default="")):
    """Reset all test coverage data for a project. Requires API key."""
    _require_api_key(x_api_key)
    proj_dir = _test_cov_project_dir(project_id)
    if not proj_dir.is_dir():
        raise HTTPException(404, f"No test coverage data for project '{project_id}'")
    import shutil
    removed = {"uploads": 0, "prs": 0, "history": False}
    prs_dir = proj_dir / "prs"
    if prs_dir.is_dir():
        removed["prs"] = len(list(prs_dir.glob("*.yaml")))
        shutil.rmtree(prs_dir)
    uploads_dir = proj_dir / "uploads"
    if uploads_dir.is_dir():
        removed["uploads"] = len(list(uploads_dir.glob("*.yaml")))
        shutil.rmtree(uploads_dir)
    for f in ["latest.yaml", "history.yaml"]:
        fp = proj_dir / f
        if fp.exists():
            fp.unlink()
            if f == "history.yaml":
                removed["history"] = True
    return {"status": "reset", "project": project_id, "removed": removed}


@app.get("/api/coverage/test/{project_id}")
def get_test_coverage_summary(project_id: str):
    """Get current test coverage summary with trend data for a project."""
    proj_dir = _test_cov_project_dir(project_id)
    latest_file = proj_dir / "latest.yaml"
    if not latest_file.exists():
        raise HTTPException(404, f"No test coverage data for project '{project_id}'")

    try:
        latest = yaml.safe_load(latest_file.read_text()) or {}
    except Exception:
        raise HTTPException(500, "Failed to read coverage data")

    # Load history for trend
    history_file = proj_dir / "history.yaml"
    history = []
    if history_file.exists():
        try:
            history = yaml.safe_load(history_file.read_text()) or []
        except Exception:
            pass

    # Compute trend: compare latest to 7-days-ago or earliest
    trend_points = []
    for h in history[:30]:
        trend_points.append({
            "timestamp": h.get("timestamp"),
            "coverage": h.get("totals", {}).get("coverage", 0),
            "test_pr": h.get("test_pr"),
            "test_repo": h.get("test_repo"),
            "delta": h.get("delta", 0),
        })

    # Count PRs that contributed
    prs_dir = proj_dir / "prs"
    pr_count = 0
    positive_prs = 0
    if prs_dir.is_dir():
        for f in prs_dir.iterdir():
            if f.suffix == ".yaml":
                pr_count += 1
                try:
                    d = yaml.safe_load(f.read_text()) or {}
                    if d.get("delta", 0) > 0:
                        positive_prs += 1
                except Exception:
                    pass

    result = {
        "project": project_id,
        "source_repo": latest.get("source_repo"),
        "test_repo": latest.get("test_repo"),
        "source_commit": latest.get("source_commit"),
        "source_branch": latest.get("source_branch"),
        "timestamp": latest.get("timestamp"),
        "totals": latest.get("totals", {}),
        "delta": latest.get("delta", 0),
        "base_coverage": latest.get("base_coverage", 0),
        "merge_base": latest.get("merge_base"),
        "total_uploads": len(history),
        "total_prs_tracked": pr_count,
        "positive_prs": positive_prs,
        "trend": trend_points,
    }
    # Include patch coverage from latest if available
    if latest.get("patch"):
        result["patch_coverage"] = latest["patch"].get("patch_coverage")
    # Include metadata (packages, collector, etc.)
    if latest.get("metadata"):
        result["metadata"] = latest["metadata"]
    return result


@app.get("/api/coverage/test/{project_id}/files")
def get_test_coverage_files(project_id: str, commit: str = ""):
    """Get per-file coverage breakdown for a project.

    Returns the file-level coverage data from the latest (or specified commit) upload,
    sorted by coverage ascending (worst-covered files first).
    """
    proj_dir = _test_cov_project_dir(project_id)

    # Load specific commit or latest
    if commit:
        data_file = proj_dir / "by_commit" / f"{commit}.yaml"
        if not data_file.exists():
            raise HTTPException(404, f"No coverage data for commit {commit[:7]}")
    else:
        data_file = proj_dir / "latest.yaml"
        if not data_file.exists():
            raise HTTPException(404, f"No test coverage data for project '{project_id}'")

    try:
        data = yaml.safe_load(data_file.read_text()) or {}
    except Exception:
        raise HTTPException(500, "Failed to read coverage data")

    files = data.get("files", [])

    # Sort by coverage ascending (worst-covered first for attention)
    files_summary = []
    for f in files:
        files_summary.append({
            "name": f.get("name", ""),
            "coverage": f.get("coverage", 0),
            "lines": f.get("lines", 0),
            "hits": f.get("hits", 0),
            "misses": f.get("misses", 0),
        })
    files_summary.sort(key=lambda x: x["coverage"])

    return {
        "project": project_id,
        "source_repo": data.get("source_repo"),
        "source_commit": data.get("source_commit"),
        "source_branch": data.get("source_branch"),
        "timestamp": data.get("timestamp"),
        "totals": data.get("totals", {}),
        "metadata": data.get("metadata", {}),
        "files": files_summary,
    }


@app.get("/api/coverage/test/{project_id}/raw")
def get_test_coverage_raw(project_id: str, commit: str = ""):
    """Download the raw coverage YAML data for a project."""
    proj_dir = _test_cov_project_dir(project_id)

    if commit:
        data_file = proj_dir / "by_commit" / f"{commit}.yaml"
    else:
        data_file = proj_dir / "latest.yaml"

    if not data_file.exists():
        raise HTTPException(404, "No coverage data found")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        data_file.read_text(),
        media_type="text/yaml",
        headers={"Content-Disposition": f"attachment; filename=coverage-{project_id}.yaml"},
    )


# ---------------------------------------------------------------------------
# Coverage Onboarding — one-button repo instrumentation
# ---------------------------------------------------------------------------

def _github_detect_language(org: str, repo: str, token: str = "") -> str:
    """Detect the primary language of a GitHub repo. Returns 'go', 'python', or 'unknown'.

    Works without a token for public repos (unauthenticated GitHub API).
    """
    url = f"https://api.github.com/repos/{org}/{repo}/languages"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if not data:
            return "unknown"
        primary = max(data, key=data.get)
        return primary.lower()
    except Exception:
        # Try without auth as fallback (public repos)
        if token:
            return _github_detect_language(org, repo, token="")
        return "unknown"


def _github_find_file(org: str, repo: str, filename: str, token: str) -> list[dict]:
    """Search for a file in a GitHub repo. Returns list of {path, sha}."""
    try:
        url = f"https://api.github.com/search/code?q=filename:{filename}+repo:{org}/{repo}"
        data = _github_api("GET", url, token)
        return [{"path": item["path"], "sha": item.get("sha", "")} for item in data.get("items", [])]
    except Exception:
        return []


def _github_get_file_content(org: str, repo: str, path: str, token: str) -> str | None:
    """Get file content from a GitHub repo."""
    try:
        data = _github_api("GET", f"https://api.github.com/repos/{org}/{repo}/contents/{path}", token)
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")
    except Exception:
        return None


def _github_get_default_branch(org: str, repo: str, token: str) -> str:
    """Get the default branch of a GitHub repo."""
    data = _github_api("GET", f"https://api.github.com/repos/{org}/{repo}", token)
    return data.get("default_branch", "main")


def _detect_repo_context(org: str, repo: str, token: str) -> dict:
    """Detect repo conventions: PR template, package manager, DCO, WORKDIR, etc."""
    ctx: dict = {"pr_template": None, "pkg_manager": "pip", "needs_dco": False, "workdir": "/app"}

    # Detect PR template
    for tmpl_path in (".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
                      "PULL_REQUEST_TEMPLATE.md", "docs/PULL_REQUEST_TEMPLATE.md"):
        tmpl = _github_get_file_content(org, repo, tmpl_path, token)
        if tmpl:
            ctx["pr_template"] = tmpl
            break

    # Detect Python package manager
    for indicator, mgr in [("uv.lock", "uv"), ("pyproject.toml", None), ("Pipfile", "pipenv"),
                           ("poetry.lock", "poetry"), ("requirements.txt", "pip")]:
        check = _github_get_file_content(org, repo, indicator, token)
        if check is not None:
            if mgr:
                ctx["pkg_manager"] = mgr
            elif indicator == "pyproject.toml":
                if "[tool.uv]" in check or "uv" in check.split("[build-system]")[0] if "[build-system]" in check else False:
                    ctx["pkg_manager"] = "uv"
                elif "[tool.poetry]" in check:
                    ctx["pkg_manager"] = "poetry"
                else:
                    ctx["pkg_manager"] = "pip"
            break

    # Detect DCO requirement (check CONTRIBUTING.md for sign-off mentions)
    contributing = _github_get_file_content(org, repo, "CONTRIBUTING.md", token)
    if contributing and ("sign-off" in contributing.lower() or "dco" in contributing.lower()
                         or "signed-off-by" in contributing.lower()):
        ctx["needs_dco"] = True

    # Detect WORKDIR from Dockerfile
    for df_name in ("Dockerfile", "Containerfile", "build/Dockerfile"):
        df = _github_get_file_content(org, repo, df_name, token)
        if df:
            # Find last WORKDIR in the final stage
            workdirs = re.findall(r'^\s*WORKDIR\s+(\S+)', df, re.MULTILINE)
            if workdirs:
                ctx["workdir"] = workdirs[-1]
            ctx["dockerfile_name"] = df_name
            ctx["dockerfile_content"] = df
            break

    return ctx


def _generate_go_instrumentation(org: str, repo: str, token: str, dashboard_url: str,
                                  components: list[str] | None = None) -> list[dict]:
    """Generate Go CoverPort instrumentation files.

    Returns list of {path, content} for the GitHub tree API.
    """
    files: list[dict] = []
    ctx = _detect_repo_context(org, repo, token)

    # 1. Find main.go files — be selective
    all_main_files = _github_find_file(org, repo, "main.go", token)

    target_files = []
    if components:
        for mf in all_main_files:
            for comp in components:
                if mf["path"].startswith(comp.rstrip("/") + "/"):
                    target_files.append(mf)
    else:
        skip_prefixes = ("tests/", "test/", "tools/", "hack/", "staging/",
                         "vendor/", "third_party/", "examples/", "cmd/example",
                         "cmd/test", "cmd/sidecars/", "cmd/fake-", "pkg/")
        service_patterns = ("api", "controller", "handler", "operator", "server",
                            "proxy", "manager", "scheduler", "webhook", "gateway")
        for mf in all_main_files:
            path = mf["path"]
            if any(path.startswith(p) for p in skip_prefixes):
                continue
            parts = path.split("/")
            if len(parts) == 3 and parts[0] == "cmd" and parts[2] == "main.go":
                comp_name = parts[1].lower()
                if any(kw in comp_name for kw in service_patterns):
                    target_files.append(mf)

    logger.info("Onboard %s/%s: found %d main.go, targeting %d components: %s",
                org, repo, len(all_main_files), len(target_files),
                [f["path"] for f in target_files])

    # Create a separate coverport.go file next to each main.go with a build tag.
    # This means `go build` (normal) ignores it entirely — the import only exists
    # when built with `go build -tags coverport`. No production binary is affected.
    for mf in target_files:
        main_dir = "/".join(mf["path"].split("/")[:-1])
        coverport_path = f"{main_dir}/coverport.go" if main_dir else "coverport.go"

        # Check if coverport.go already exists
        existing = _github_get_file_content(org, repo, coverport_path, token)
        if existing and "konflux-ci/coverport" in existing:
            continue

        # Detect package name from main.go
        content = _github_get_file_content(org, repo, mf["path"], token)
        if content is None:
            continue
        pkg_match = re.search(r'^package\s+(\w+)', content, re.MULTILINE)
        pkg_name = pkg_match.group(1) if pkg_match else "main"

        files.append({
            "path": coverport_path,
            "content": (
                "//go:build coverport\n\n"
                f"package {pkg_name}\n\n"
                "// CoverPort: blank import starts coverage HTTP server on :53700.\n"
                "// Only compiled when: go build -tags coverport\n"
                "// Alternative: use `coverport collect` CLI without this import.\n"
                'import _ "github.com/konflux-ci/coverport/instrumentation/go"\n'
            ),
        })

    # 2. go.mod dependency
    gomod = _github_get_file_content(org, repo, "go.mod", token)
    if gomod and "konflux-ci/coverport" not in gomod:
        if "require (" in gomod:
            gomod = gomod.replace(
                "require (",
                "require (\n\tgithub.com/konflux-ci/coverport v0.0.0-00010101000000-000000000000",
                1,
            )
        else:
            gomod += "\nrequire github.com/konflux-ci/coverport v0.0.0-00010101000000-000000000000\n"
        files.append({"path": "go.mod", "content": gomod})

    # 3. Dockerfile.coverport — separate file, does NOT modify the original Dockerfile.
    df_content = ctx.get("dockerfile_content")
    df_name = ctx.get("dockerfile_name", "Dockerfile")
    if df_content:
        files.append({
            "path": "Dockerfile.coverport",
            "content": _generate_coverport_dockerfile(df_content, "go", df_name),
        })

    # 4. Tekton Task for collection
    files.append({
        "path": ".tekton/coverport-collect.yaml",
        "content": _generate_tekton_coverport_task(org, repo, dashboard_url),
    })

    # 5. GitHub Actions workflow
    files.append({
        "path": ".github/workflows/coverage-upload.yml",
        "content": _generate_github_actions_coverage(org, repo, "go", dashboard_url),
    })

    # Store context for PR body generation
    files.append({"_ctx": ctx})

    return files


def _patch_go_dockerfile(content: str) -> str:
    """Patch a Go Dockerfile for CoverPort instrumentation.

    All coverage additions are conditional on ENABLE_COVERAGE=true so
    normal builds are completely unaffected.
    """
    lines = content.split("\n")
    result = []
    added_gocoverdir = False
    added_expose = False
    added_enable_coverage_arg = False

    for line in lines:
        stripped = line.strip()

        if "ENABLE_COVERAGE" in stripped:
            added_enable_coverage_arg = True

        # Wrap go build in ENABLE_COVERAGE conditional — adds -tags coverport
        # so the coverport.go build-tagged file is compiled, plus -cover flag
        if "go build" in stripped and "-cover" not in stripped and "ENABLE_COVERAGE" not in stripped:
            indent = line[:len(line) - len(line.lstrip())]
            original_cmd = stripped
            line = (
                f'{indent}RUN if [ "$ENABLE_COVERAGE" = "true" ]; then \\\n'
                f'{indent}  {original_cmd.replace("RUN ", "").replace("run ", "")} -tags coverport -cover -covermode=atomic; \\\n'
                f'{indent}else \\\n'
                f'{indent}  {original_cmd.replace("RUN ", "").replace("run ", "")}; \\\n'
                f'{indent}fi'
            )

        if stripped.startswith("ENV") and "GOCOVERDIR" in stripped:
            added_gocoverdir = True
        if stripped.startswith("EXPOSE") and "53700" in stripped:
            added_expose = True

        result.append(line)

    # Add ENABLE_COVERAGE build arg near top (after FROM)
    if not added_enable_coverage_arg:
        for i, line in enumerate(result):
            if line.strip().startswith("FROM"):
                result.insert(i + 1, 'ARG ENABLE_COVERAGE=false')
                break

    # GOCOVERDIR and EXPOSE only when ENABLE_COVERAGE=true (conditional)
    if not added_gocoverdir or not added_expose:
        for i in range(len(result) - 1, -1, -1):
            s = result[i].strip()
            if s.startswith("CMD") or s.startswith("ENTRYPOINT"):
                conditional_lines = [
                    '# CoverPort: coverage dir + port only when ENABLE_COVERAGE=true',
                    'RUN if [ "$ENABLE_COVERAGE" = "true" ]; then mkdir -p /tmp/covdata; fi',
                ]
                if not added_gocoverdir:
                    conditional_lines.append('ENV GOCOVERDIR=${ENABLE_COVERAGE:+/tmp/covdata}')
                if not added_expose:
                    conditional_lines.append('EXPOSE 53700')
                for j, cl in enumerate(conditional_lines):
                    result.insert(i + j, cl)
                break

    return "\n".join(result)


def _generate_coverport_dockerfile(original_content: str, language: str,
                                    original_name: str = "Dockerfile",
                                    workdir: str = "/app",
                                    pkg_mgr: str = "pip") -> str:
    """Generate Dockerfile.coverport from the original Dockerfile.

    Applies coverage instrumentation to a COPY of the original — the original
    Dockerfile is never modified. Teams build the instrumented image with:
        docker build -f Dockerfile.coverport -t myapp:coverport .
    """
    header = (
        f"# Dockerfile.coverport — CoverPort instrumented build\n"
        f"# Generated from {original_name} — DO NOT edit {original_name}, this is a separate file.\n"
        f"#\n"
        f"# Normal build:       docker build -f {original_name} -t myapp .\n"
        f"# Instrumented build: docker build -f Dockerfile.coverport -t myapp:coverport .\n"
        f"#\n"
    )
    if language == "go":
        patched = _patch_go_dockerfile(original_content)
    else:
        patched = _patch_python_dockerfile(original_content, workdir=workdir, pkg_mgr=pkg_mgr)
    return header + patched


def _generate_python_instrumentation(org: str, repo: str, token: str, dashboard_url: str) -> list[dict]:
    """Generate Python CoverPort instrumentation files."""
    files: list[dict] = []
    ctx = _detect_repo_context(org, repo, token)
    workdir = ctx["workdir"]
    pkg_mgr = ctx["pkg_manager"]

    # 1. Coverage server — clean, linted code
    files.append({
        "path": "coverport/coverage_server.py",
        "content": f'''"""CoverPort coverage server — exposes coverage data via HTTP."""
import http.server
import os
import tempfile
import threading

try:
    import coverage
except ImportError:
    coverage = None  # type: ignore[assignment]

COVERAGE_PORT = int(os.environ.get("COVERAGE_PORT", "53700"))


class CoverageHandler(http.server.BaseHTTPRequestHandler):
    """Serves coverage data collected by coverage.py."""

    def do_GET(self):
        """Handle GET requests for coverage data."""
        if self.path == "/coverage":
            self._serve_coverage()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"CoverPort coverage server ready")

    def _serve_coverage(self):
        """Export and serve current coverage data as LCOV."""
        if coverage is None:
            self._send_error(503, "coverage package not installed")
            return
        cov = coverage.Coverage.current()
        if cov is None:
            self._send_error(404, "No active coverage session")
            return
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".lcov")
            os.close(fd)
            cov.lcov_report(outfile=tmp_path)
            with open(tmp_path) as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(data.encode())
        except coverage.CoverageException as e:
            self._send_error(500, f"Coverage report failed: {{e}}")
        except OSError as e:
            self._send_error(500, f"File I/O error: {{e}}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _send_error(self, code, message):
        """Send an error response."""
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, fmt, *args):
        """Suppress request logs."""


def start():
    """Start coverage server in a background thread (only when ENABLE_COVERAGE=true)."""
    if os.environ.get("ENABLE_COVERAGE", "").lower() != "true":
        return
    server = http.server.HTTPServer(("0.0.0.0", COVERAGE_PORT), CoverageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


# Auto-start when imported — no-op unless ENABLE_COVERAGE=true
start()
''',
    })

    # 2. sitecustomize.py
    coveragerc_path = f"{workdir}/.coveragerc"
    files.append({
        "path": "coverport/sitecustomize.py",
        "content": f'''"""Auto-enable coverage measurement in every Python subprocess."""
import os

if os.environ.get("ENABLE_COVERAGE", "").lower() == "true":
    os.environ.setdefault("COVERAGE_PROCESS_START", "{coveragerc_path}")
    try:
        import coverage
        coverage.process_startup()
    except ImportError:
        pass
''',
    })

    # 3. .coveragerc
    files.append({
        "path": ".coveragerc",
        "content": f'''[run]
branch = True
source = .
parallel = True
omit =
    */test*
    */tests/*
    */conftest.py
    coverport/*

[report]
show_missing = True
precision = 2

[lcov]
output = coverage.lcov
''',
    })

    # 4. Dockerfile.coverport — separate file, does NOT modify original Dockerfile
    # or requirements.txt. The coverport Dockerfile handles pip install coverage.
    df_content = ctx.get("dockerfile_content")
    df_name = ctx.get("dockerfile_name", "Dockerfile")
    if df_content:
        files.append({
            "path": "Dockerfile.coverport",
            "content": _generate_coverport_dockerfile(df_content, "python", df_name, workdir, pkg_mgr),
        })

    # 6. GitHub Actions workflow
    files.append({
        "path": ".github/workflows/coverage-upload.yml",
        "content": _generate_github_actions_coverage(org, repo, "python", dashboard_url),
    })

    # Store context for PR body generation
    files.append({"_ctx": ctx})

    return files


def _patch_python_dockerfile(content: str, workdir: str = "/app", pkg_mgr: str = "pip") -> str:
    """Patch a Python Dockerfile for CoverPort instrumentation.

    All coverage additions are conditional on ENABLE_COVERAGE=true so
    normal builds are completely unaffected. Respects the repo's package
    manager (uv/pip/poetry) and WORKDIR.
    """
    lines = content.split("\n")
    result = []
    added_env = False
    added_copy = False
    added_expose = False
    added_enable_coverage_arg = False

    for line in lines:
        stripped = line.strip()
        if "COVERAGE_PROCESS_START" in stripped:
            added_env = True
        if "coverport/" in stripped and stripped.startswith("COPY"):
            added_copy = True
        if "53700" in stripped and stripped.startswith("EXPOSE"):
            added_expose = True
        if "ENABLE_COVERAGE" in stripped:
            added_enable_coverage_arg = True
        result.append(line)

    if added_env and added_copy:
        return content

    # Add ENABLE_COVERAGE build arg near top (after FROM)
    if not added_enable_coverage_arg:
        for i, line in enumerate(result):
            if line.strip().startswith("FROM"):
                result.insert(i + 1, 'ARG ENABLE_COVERAGE=false')
                break

    # Use the correct install command for the package manager
    install_cmds = {
        "uv": "uv pip install --no-cache coverage>=7.0",
        "pip": "pip install --no-cache-dir coverage>=7.0",
        "poetry": "poetry add --group dev coverage",
        "pipenv": "pipenv install coverage",
    }
    install_cmd = install_cmds.get(pkg_mgr, install_cmds["pip"])

    # All instrumentation lines are conditional on ENABLE_COVERAGE
    insert_lines = []
    insert_lines.append("# CoverPort: runtime coverage instrumentation (opt-in via ENABLE_COVERAGE=true)")
    if not added_copy:
        insert_lines.append(f"COPY coverport/ {workdir}/coverport/")
        insert_lines.append(f'RUN if [ "$ENABLE_COVERAGE" = "true" ]; then {install_cmd}; fi')
    if not added_env:
        insert_lines.append(f'ENV ENABLE_COVERAGE=${{ENABLE_COVERAGE}}')
        insert_lines.append(f'RUN if [ "$ENABLE_COVERAGE" = "true" ]; then \\')
        insert_lines.append(f'  echo "COVERAGE_PROCESS_START={workdir}/.coveragerc" >> /etc/environment; fi')
        insert_lines.append(f'ENV COVERAGE_PROCESS_START="${{ENABLE_COVERAGE:+{workdir}/.coveragerc}}"')
        insert_lines.append(f'ENV PYTHONPATH="${{ENABLE_COVERAGE:+{workdir}/coverport}}"')
        insert_lines.append(f'ENV COVERAGE_PORT="${{ENABLE_COVERAGE:+53700}}"')
    if not added_expose:
        insert_lines.append("EXPOSE 53700")

    if insert_lines:
        for i in range(len(result) - 1, -1, -1):
            s = result[i].strip()
            if s.startswith("CMD") or s.startswith("ENTRYPOINT"):
                for j, il in enumerate(insert_lines):
                    result.insert(i + j, il)
                break

    return "\n".join(result)


def _generate_tekton_coverport_task(org: str, repo: str, dashboard_url: str) -> str:
    """Generate a Tekton Task for collecting CoverPort runtime coverage.

    Uses the CoverPort CLI (coverport collect) for pod discovery and collection.
    """
    safe_dashboard = dashboard_url.rstrip("/")
    return f"""# CoverPort Coverage Collection — Tekton Task
# Run this task AFTER your e2e/integration tests as a `finally` step.
# Uses the CoverPort CLI for automated pod discovery and coverage collection.
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: coverport-collect-{repo}
  labels:
    app.kubernetes.io/part-of: qualityflow
spec:
  description: Collect CoverPort runtime coverage from {org}/{repo} pods
  params:
    - name: NAMESPACE
      description: Namespace where instrumented pods run
      type: string
      default: "{repo}"
    - name: LABEL_SELECTOR
      description: Label selector for target pods
      type: string
    - name: SNAPSHOT
      description: Konflux Snapshot JSON (alternative to LABEL_SELECTOR for Konflux CI)
      type: string
      default: ""
    - name: DASHBOARD_URL
      description: QualityFlow dashboard URL
      type: string
      default: "{safe_dashboard}"
    - name: QUALITYFLOW_API_KEY
      description: API key for QualityFlow dashboard
      type: string
      default: ""
  steps:
    - name: collect
      image: ghcr.io/konflux-ci/coverport/cli:latest
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        NAMESPACE="$(params.NAMESPACE)"
        SELECTOR="$(params.LABEL_SELECTOR)"
        SNAPSHOT="$(params.SNAPSHOT)"
        API_KEY="$(params.QUALITYFLOW_API_KEY)"
        DASHBOARD="$(params.DASHBOARD_URL)"
        OUTDIR="/tmp/coverport-output"

        if [ -n "$SNAPSHOT" ]; then
          echo "Collecting via Konflux Snapshot..."
          coverport collect --snapshot="$SNAPSHOT" --output="$OUTDIR"
        else
          echo "Collecting: namespace=$NAMESPACE selector=$SELECTOR"
          coverport collect -n "$NAMESPACE" --label-selector="$SELECTOR" --output="$OUTDIR"
        fi

        if [ -n "$API_KEY" ] && [ -n "$DASHBOARD" ]; then
          for f in "$OUTDIR"/*; do
            [ -f "$f" ] || continue
            echo "Uploading $(basename "$f")..."
            curl -s -X POST \\
              -H "Content-Type: application/octet-stream" \\
              -H "X-API-Key: $API_KEY" \\
              --data-binary @"$f" \\
              "$DASHBOARD/api/coverage/upload?org={org}&repo={repo}&commit=runtime-$(date +%s)&type=product"
          done
          echo "Uploaded to $DASHBOARD"
        else
          echo "Coverage saved to $OUTDIR (set QUALITYFLOW_API_KEY + DASHBOARD_URL to auto-upload)"
          ls -la "$OUTDIR"
        fi
"""


def _generate_github_actions_coverage(org: str, repo: str, language: str, dashboard_url: str) -> str:
    """Generate a GitHub Actions workflow for coverage collection.

    Uses proper ${{...}} escaping (double braces for Python f-string).
    No -k/--insecure flags — TLS verification is always enabled.
    Upload step only runs if coverage file exists.
    """
    safe_dashboard = dashboard_url.rstrip("/")

    if language == "go":
        # Go: unit test coverage + instrumented image build + CLI collection
        return (
            "# Auto-generated by QualityFlow Coverage Onboarding\n"
            "# Unit test coverage — go test -coverprofile (runs every push/PR)\n"
            "name: Coverage\n"
            "\n"
            "on:\n"
            "  push:\n"
            "    branches: [main, master]\n"
            "  pull_request:\n"
            "    branches: [main, master]\n"
            "  workflow_dispatch:\n"
            "    inputs:\n"
            "      label_selector:\n"
            "        description: 'Pod label selector for runtime coverage collection'\n"
            "        required: true\n"
            "        type: string\n"
            "      namespace:\n"
            "        description: 'Kubernetes namespace'\n"
            "        required: true\n"
            "        type: string\n"
            "\n"
            "jobs:\n"
            "  unit-test-coverage:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-go@v5\n"
            "        with:\n"
            '          go-version: "1.22"\n'
            "\n"
            "      - name: Run tests with coverage\n"
            "        run: go test -coverprofile=coverage.out -covermode=atomic ./...\n"
            "\n"
            "      - name: Upload coverage to QualityFlow\n"
            "        if: hashFiles('coverage.out') != ''\n"
            "        env:\n"
            "          QUALITYFLOW_API_KEY: ${{ secrets.QUALITYFLOW_API_KEY }}\n"
            "        run: |\n"
            "          curl -s -X POST \\\n"
            '            -H "Content-Type: text/plain" \\\n'
            '            -H "X-API-Key: $QUALITYFLOW_API_KEY" \\\n'
            "            --data-binary @coverage.out \\\n"
            f'            "{safe_dashboard}/api/coverage/upload?org={org}&repo={repo}'
            '&commit=${{ github.sha }}&branch=${{ github.ref_name }}"\n'
            "\n"
            "  coverport-build:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name == 'push'\n"
            "    permissions:\n"
            "      packages: write\n"
            "    env:\n"
            "      IMAGE_PREFIX: ghcr.io/${{ github.repository }}\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "\n"
            "      - name: Log in to container registry\n"
            "        uses: docker/login-action@v3\n"
            "        with:\n"
            "          registry: ghcr.io\n"
            "          username: ${{ github.actor }}\n"
            "          password: ${{ secrets.GITHUB_TOKEN }}\n"
            "\n"
            "      - name: Build instrumented image\n"
            "        run: |\n"
            "          docker build \\\n"
            "            -f Dockerfile.coverport \\\n"
            "            -t $IMAGE_PREFIX:coverport-${{ github.sha }} \\\n"
            "            -t $IMAGE_PREFIX:coverport-latest \\\n"
            "            .\n"
            "\n"
            "      - name: Push instrumented images\n"
            "        run: |\n"
            "          docker push $IMAGE_PREFIX:coverport-${{ github.sha }}\n"
            "          docker push $IMAGE_PREFIX:coverport-latest\n"
            "\n"
            "  coverport-collect:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name == 'workflow_dispatch'\n"
            "    steps:\n"
            "      - uses: actions/setup-go@v5\n"
            "        with:\n"
            '          go-version: "1.24"\n'
            "\n"
            "      - name: Install CoverPort CLI\n"
            "        run: go install github.com/konflux-ci/coverport/cli@latest\n"
            "\n"
            "      - name: Collect runtime coverage\n"
            "        run: |\n"
            '          coverport collect \\\n'
            '            -n "${{ inputs.namespace }}" \\\n'
            '            --label-selector="${{ inputs.label_selector }}" \\\n'
            '            --output=./coverage-output\n'
            "\n"
            "      - name: Upload to QualityFlow\n"
            "        env:\n"
            "          QUALITYFLOW_API_KEY: ${{ secrets.QUALITYFLOW_API_KEY }}\n"
            "        run: |\n"
            "          for f in ./coverage-output/*; do\n"
            '            [ -f "$f" ] || continue\n'
            '            curl -s -X POST \\\n'
            '              -H "Content-Type: application/octet-stream" \\\n'
            '              -H "X-API-Key: $QUALITYFLOW_API_KEY" \\\n'
            '              --data-binary @"$f" \\\n'
            f'              "{safe_dashboard}/api/coverage/upload?org={org}&repo={repo}'
            '&commit=runtime-${{ github.run_id }}&type=product"\n'
            "          done\n"
        )
    else:
        # Python: test coverage upload
        return (
            "# Auto-generated by QualityFlow Coverage Onboarding\n"
            "# Test coverage — pytest + coverage.py (runs every push/PR)\n"
            "name: Coverage\n"
            "\n"
            "on:\n"
            "  push:\n"
            "    branches: [main, master]\n"
            "  pull_request:\n"
            "    branches: [main, master]\n"
            "\n"
            "jobs:\n"
            "  test-coverage:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n"
            "        with:\n"
            '          python-version: "3.12"\n'
            "\n"
            "      - name: Install dependencies\n"
            "        run: |\n"
            "          pip install -r requirements.txt 2>/dev/null || pip install . 2>/dev/null || true\n"
            "          pip install coverage\n"
            "\n"
            "      - name: Run tests with coverage\n"
            "        run: |\n"
            "          coverage run -m pytest || true\n"
            "          coverage lcov -o coverage.lcov || true\n"
            "\n"
            "      - name: Upload coverage to QualityFlow\n"
            "        if: hashFiles('coverage.lcov') != ''\n"
            "        env:\n"
            "          QUALITYFLOW_API_KEY: ${{ secrets.QUALITYFLOW_API_KEY }}\n"
            "        run: |\n"
            "          curl -s -X POST \\\n"
            '            -H "Content-Type: text/plain" \\\n'
            '            -H "X-API-Key: $QUALITYFLOW_API_KEY" \\\n'
            "            --data-binary @coverage.lcov \\\n"
            f'            "{safe_dashboard}/api/coverage/upload?org={org}&repo={repo}'
            '&commit=${{ github.sha }}&branch=${{ github.ref_name }}"\n'
        )


def _fill_pr_template(template: str, org: str, repo: str, language: str,
                      gen_files: list[dict], dashboard_url: str) -> str:
    """Fill in a repo's PR template with coverage onboarding content."""
    body = template

    # Common replacements for standard PR template sections
    replacements = {
        # "What this PR does / why we need it" section
        "##### What this PR does / why we need it:": (
            "##### What this PR does / why we need it:\n\n"
            f"Adds CoverPort coverage instrumentation ({language}) to enable automated "
            f"code coverage collection and reporting via the QualityFlow dashboard.\n\n"
            "**Files added/modified:**\n" +
            "\n".join(f"- `{f['path']}`" for f in gen_files)
        ),
        # "Which issue(s) this PR fixes" section
        "##### Which issue(s) this PR fixes:": (
            "##### Which issue(s) this PR fixes:\n\n"
            "N/A — infrastructure/tooling change"
        ),
        # "Special notes for reviewer" section
        "##### Special notes for reviewer:": (
            "##### Special notes for reviewer:\n\n"
            "This is an automated PR from QualityFlow coverage onboarding. "
            "All coverage instrumentation is **opt-in** — your original Dockerfile is not modified. "
            "Build the instrumented image with: `docker build -f Dockerfile.coverport .`\n\n"
            f"Dashboard: {dashboard_url}"
        ),
        # Jira ticket section
        "##### jira-ticket:": "##### jira-ticket:\n",
    }

    for marker, replacement in replacements.items():
        if marker in body:
            # Replace the marker line and any placeholder text after it
            # Find the marker and the next section marker (next ##### line)
            idx = body.index(marker)
            next_section = body.find("\n##### ", idx + len(marker))
            if next_section == -1:
                body = body[:idx] + replacement
            else:
                body = body[:idx] + replacement + "\n\n" + body[next_section + 1:]

    # If template didn't have recognizable sections, append our content
    if all(marker not in template for marker in replacements):
        body += "\n\n" + _build_default_pr_body(org, repo, language, gen_files, dashboard_url)

    return body


def _build_default_pr_body(org: str, repo: str, language: str,
                           gen_files: list[dict], dashboard_url: str) -> str:
    """Build a default PR body when no PR template exists."""
    file_table = "| File | Purpose |\n|------|---------|"
    for f in gen_files:
        path = f["path"]
        if "coverage-upload" in path:
            desc = "GitHub Actions workflow — uploads test coverage"
        elif "coverport-collect" in path:
            desc = "Tekton Task — collects runtime coverage from pods after e2e tests"
        elif "main.go" in path or "go.mod" in path:
            desc = "CoverPort instrumentation — adds runtime coverage (opt-in via ENABLE_COVERAGE)"
        elif "coverage_server" in path:
            desc = "Coverage HTTP server — exposes coverage data on port 53700"
        elif "sitecustomize" in path:
            desc = "Auto-enables coverage.py in subprocesses"
        elif "coveragerc" in path:
            desc = "Coverage.py configuration (branch coverage, omit patterns)"
        elif "requirements" in path:
            desc = "Adds coverage.py dependency"
        elif path == "Dockerfile.coverport":
            desc = "Separate Dockerfile for instrumented builds (original Dockerfile untouched)"
        elif "Dockerfile" in path or "Containerfile" in path:
            desc = "Dockerfile patch — coverage build arg (opt-in, no effect on normal builds)"
        else:
            desc = "Instrumentation file"
        file_table += f"\n| `{path}` | {desc} |"

    return f"""## What this PR does / why we need it

Adds CoverPort coverage instrumentation ({language}) for automated code coverage
collection and reporting via the QualityFlow dashboard.

All coverage instrumentation is **opt-in** — your original Dockerfile is not modified.
A separate `Dockerfile.coverport` is provided for instrumented builds.

### Files

{file_table}

### Setup after merge

1. Add `QUALITYFLOW_API_KEY` to repository secrets (Settings > Secrets > Actions)
2. Unit test coverage uploads automatically on every push
3. For runtime/e2e coverage: build and deploy with coverage enabled (see options below)

### Coverage collection options

**Option A — CoverPort CLI (recommended)**

Install the CLI and collect from any environment with cluster access:
```bash
go install github.com/konflux-ci/coverport/cli@latest
coverport collect --label-selector=app=myservice --output=./coverage
```
For Konflux CI, use `coverport collect --snapshot="$SNAPSHOT"` in a Tekton `finally` task.

**Option B — Embedded server**

Build with `Dockerfile.coverport`, deploy to test cluster, then collect via the
Tekton task in `.tekton/coverport-collect.yaml` (add as a `finally` step in your pipeline).

### Dashboard

Coverage data appears at: [{dashboard_url}]({dashboard_url})

---
*Auto-generated by QualityFlow coverage onboarding*
"""


def _save_onboarding_state(org: str, repo: str, state: dict) -> None:
    """Save onboarding state for a repo."""
    repo_dir = _coverage_repo_dir(org, repo)
    repo_dir.mkdir(parents=True, exist_ok=True)
    state_file = repo_dir / "onboarding.yaml"
    state_file.write_text(yaml.dump(state, default_flow_style=False, sort_keys=False))


def _load_onboarding_state(org: str, repo: str) -> dict | None:
    """Load onboarding state for a repo."""
    state_file = _coverage_repo_dir(org, repo) / "onboarding.yaml"
    if not state_file.exists():
        return None
    try:
        return yaml.safe_load(state_file.read_text())
    except Exception:
        return None


@app.get("/api/coverage/detect-language")
def detect_language(org: str, repo: str):
    """Detect the primary language of a GitHub repo (works for public repos without token)."""
    if not re.match(r"^[a-zA-Z0-9_.-]+$", org) or not re.match(r"^[a-zA-Z0-9_.-]+$", repo):
        raise HTTPException(400, "Invalid org or repo name")
    try:
        lang = _github_detect_language(org, repo, _GITHUB_TOKEN)
        supported = lang in ("go", "python")
        desc = {
            "go": "Will add CoverPort Go instrumentation + GitHub Actions workflow",
            "python": "Will add coverage.py instrumentation + GitHub Actions workflow",
        }
        return {
            "language": lang,
            "supported": supported,
            "description": desc.get(lang, f"Language '{lang}' not supported for auto-onboarding (Go and Python only)"),
        }
    except Exception as e:
        raise HTTPException(502, f"Could not detect language: {e}")


@app.post("/api/coverage/onboard")
async def onboard_coverage(request: Request, x_api_key: str = Header(default="")):
    """One-button coverage onboarding: detect language, generate instrumentation, create PR.

    JSON body:
        org: GitHub org (required)
        repo: Repository name (required)
        github_token: User's GitHub PAT (optional, uses server token if not provided)
        dashboard_url: QualityFlow dashboard URL (optional, auto-detected from request)
    """
    _check_rate_limit(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    # Auth: accept either dashboard API key OR user-provided GitHub token
    user_gh_token = body.get("github_token", "").strip()
    if not user_gh_token:
        _require_api_key(x_api_key)

    # Use user's GitHub token if provided, otherwise fall back to server token
    token = user_gh_token or _GITHUB_TOKEN
    if not token:
        raise HTTPException(503, "No GitHub token available. Provide one in User Settings or configure GITHUB_PERSONAL_ACCESS_TOKEN on the server.")

    org = body.get("org", "").strip()
    repo_name = body.get("repo", "").strip()
    if not org or not repo_name:
        raise HTTPException(400, "Required fields: org, repo")

    # Auto-detect dashboard URL from the incoming request
    dashboard_url = body.get("dashboard_url", "").strip()
    if not dashboard_url:
        scheme = request.headers.get("x-forwarded-proto", "http")
        host = request.headers.get("host", "localhost:8420")
        dashboard_url = f"{scheme}://{host}"

    # Optional: specific components to instrument (e.g. ["cmd/virt-handler"])
    components = body.get("components", None)
    force = body.get("force", False)

    # Check if already onboarded (skip if force=true)
    existing = _load_onboarding_state(org, repo_name)
    if existing and existing.get("status") == "pr_created" and not force:
        return {
            "status": "already_onboarded",
            "pr": existing.get("pr"),
            "language": existing.get("language"),
            "message": f"Onboarding PR already exists: {existing.get('pr', {}).get('url', '')}",
        }

    # Step 1: Detect language
    language = _github_detect_language(org, repo_name, token)
    if language not in ("go", "python"):
        raise HTTPException(
            400,
            f"Unsupported language: {language}. Currently supports Go and Python.",
        )

    # Step 2: Generate instrumentation files
    if language == "go":
        gen_files = _generate_go_instrumentation(org, repo_name, token, dashboard_url, components=components)
    else:
        gen_files = _generate_python_instrumentation(org, repo_name, token, dashboard_url)

    if not gen_files:
        raise HTTPException(400, "Could not generate instrumentation files. Check repo structure.")

    # Step 3: Create PR via GitHub API
    default_branch = _github_get_default_branch(org, repo_name, token)
    pr_branch = "qualityflow/coverage-onboarding"

    # Resolve fork or direct push
    try:
        gh_user = _github_get_user(token)
        logger.info("Onboard: authenticated as GitHub user '%s'", gh_user)
    except Exception as e:
        logger.error("Onboard: failed to get GitHub user: %s", e)
        raise HTTPException(502, f"GitHub token is invalid or expired. Check your token in User Settings.")
    push_repo = _github_resolve_fork(f"{org}/{repo_name}", token)
    logger.info("Onboard: push_repo=%s, default_branch=%s, files=%d", push_repo, default_branch, len(gen_files))

    # Get base commit
    try:
        base_ref = _github_api(
            "GET",
            f"https://api.github.com/repos/{push_repo}/git/ref/heads/{default_branch}",
            token,
        )
    except RuntimeError as e:
        logger.error("Failed to get base ref from %s: %s", push_repo, e)
        raise HTTPException(502, f"Cannot access repository {push_repo}. Fork may still be initializing — try again in 30 seconds.")
    base_sha = base_ref["object"]["sha"]
    base_commit = _github_api(
        "GET",
        f"https://api.github.com/repos/{push_repo}/git/commits/{base_sha}",
        token,
    )
    base_tree_sha = base_commit["tree"]["sha"]

    # Create branch
    _github_create_branch(push_repo, pr_branch, base_sha, token)

    # Extract repo context from generated files (appended by generators)
    repo_ctx = {}
    actual_files = []
    for f in gen_files:
        if "_ctx" in f:
            repo_ctx = f["_ctx"]
        else:
            actual_files.append(f)
    gen_files = actual_files

    # Create tree + commit
    try:
        tree_sha = _github_create_tree(push_repo, base_tree_sha, gen_files, token)
    except RuntimeError as e:
        logger.error("Failed to create tree on %s: %s", push_repo, e)
        raise HTTPException(502, f"Cannot create files on {push_repo}. Check that your GitHub token has 'repo' scope and try again.")

    # Build commit message — include DCO signoff if repo requires it
    file_list = "\n".join(f"- {f['path']}" for f in gen_files)
    commit_msg = (
        f"Add CoverPort coverage instrumentation ({language})\n\n"
        f"Auto-generated by QualityFlow coverage onboarding.\n\n"
        f"Files added/modified:\n{file_list}\n"
    )
    if repo_ctx.get("needs_dco"):
        # Add DCO signoff line
        commit_msg += f"\nSigned-off-by: {gh_user} <{gh_user}@users.noreply.github.com>\n"

    commit_sha = _github_create_commit(push_repo, commit_msg, tree_sha, base_sha, token)
    _github_update_ref(push_repo, pr_branch, commit_sha, token)

    # Create PR
    head_ref = pr_branch
    if push_repo != f"{org}/{repo_name}":
        head_ref = f"{push_repo.split('/')[0]}:{pr_branch}"

    # Build PR body — fill repo's PR template if one exists
    pr_template = repo_ctx.get("pr_template")
    if pr_template:
        pr_body = _fill_pr_template(pr_template, org, repo_name, language, gen_files, dashboard_url)
    else:
        pr_body = _build_default_pr_body(org, repo_name, language, gen_files, dashboard_url)

    pr_title = f"Add CoverPort coverage instrumentation ({language})"

    pr_info = _github_create_pr(
        f"{org}/{repo_name}",
        head_ref,
        default_branch,
        pr_title,
        pr_body,
        token,
    )

    # Save onboarding state
    onboarding_state = {
        "org": org,
        "repo": repo_name,
        "language": language,
        "status": "pr_created",
        "pr": pr_info,
        "dashboard_url": dashboard_url,
        "files_generated": [f["path"] for f in gen_files],
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save_onboarding_state(org, repo_name, onboarding_state)

    logger.info("Coverage onboarding PR created: %s/%s (%s) — %s",
                org, repo_name, language, pr_info.get("url", ""))

    return {
        "status": "pr_created",
        "org": org,
        "repo": repo_name,
        "language": language,
        "pr": pr_info,
        "files": [f["path"] for f in gen_files],
        "dashboard_url": dashboard_url,
        "next_step": "Add QUALITYFLOW_API_KEY to repo secrets after PR is merged",
    }


@app.get("/api/coverage/onboarding")
def list_onboarding():
    """List all repos with onboarding state, including PR status refresh."""
    results = []
    if not COVERAGE_DIR.is_dir():
        return {"repos": results}

    for org_dir in sorted(COVERAGE_DIR.iterdir()):
        if not org_dir.is_dir():
            continue
        for repo_dir in sorted(org_dir.iterdir()):
            state_file = repo_dir / "onboarding.yaml"
            if not state_file.exists():
                continue
            try:
                state = yaml.safe_load(state_file.read_text()) or {}
            except Exception:
                continue

            # Refresh PR state from GitHub if token available
            pr = state.get("pr", {})
            if pr.get("url") and _GITHUB_TOKEN and pr.get("number"):
                try:
                    org = state.get("org", org_dir.name)
                    repo_name = state.get("repo", repo_dir.name)
                    gh_pr = _github_api(
                        "GET",
                        f"https://api.github.com/repos/{org}/{repo_name}/pulls/{pr['number']}",
                        _GITHUB_TOKEN,
                    )
                    new_state = "merged" if gh_pr.get("merged") else gh_pr.get("state", "open")
                    if new_state != pr.get("state"):
                        pr["state"] = new_state
                        state["pr"] = pr
                        if new_state == "merged":
                            state["status"] = "merged"
                        elif new_state == "closed":
                            state["status"] = "pr_closed"
                        state_file.write_text(yaml.dump(state, default_flow_style=False, sort_keys=False))
                except Exception:
                    pass

            # Check if repo has started sending coverage data
            has_data = (repo_dir / "latest.yaml").exists()
            state["receiving_data"] = has_data
            if has_data and state.get("status") == "merged":
                state["status"] = "active"

            results.append(state)

    return {"repos": results}


@app.get("/api/coverage/repos")
def get_coverage_repos():
    """List all repos configured for coverage tracking."""
    repos = _get_coverage_repos_config()
    for r in repos:
        local = _load_latest_coverage(r.get("org", ""), r.get("repo", ""))
        r["has_local_data"] = local is not None
        r["effective_source"] = "direct" if local else "none"
    return {"repos": repos}


@app.get("/api/coverage/{service}/{org}/{repo}")
def get_coverage_summary(service: str, org: str, repo: str):
    """Get coverage summary from direct upload data."""
    local = _load_latest_coverage(org, repo)
    if local:
        return {
            "totals": local["totals"],
            "commit": local.get("commit"),
            "branch": local.get("branch"),
            "timestamp": local.get("timestamp"),
            "_source": "direct",
        }
    raise HTTPException(404, f"No coverage data for {org}/{repo}. Upload via POST /api/coverage/upload")


@app.get("/api/coverage/{service}/{org}/{repo}/flags")
def get_coverage_flags(service: str, org: str, repo: str):
    """Get coverage breakdown by flag. Returns empty — flags are tracked per-upload."""
    return {"results": [], "_source": "direct"}


@app.get("/api/coverage/{service}/{org}/{repo}/trend")
def get_coverage_trend(service: str, org: str, repo: str, interval: str = "30d"):
    """Get coverage trend from upload history."""
    history = _load_coverage_history(org, repo)
    if history:
        return {
            "results": [
                {
                    "timestamp": h.get("timestamp"),
                    "coverage": h["totals"]["coverage"],
                    "commit": h.get("commit"),
                    "branch": h.get("branch"),
                }
                for h in history
            ],
            "_source": "direct",
        }
    return {"results": [], "_source": "direct"}


@app.get("/api/coverage/{service}/{org}/{repo}/tree")
def get_coverage_tree(service: str, org: str, repo: str, path: str = "", depth: int = 2):
    """Get file/directory coverage tree from direct upload data."""
    local = _load_latest_coverage(org, repo)
    if local and local.get("files"):
        tree = _build_coverage_tree(local["files"])
        if path:
            parts = path.strip("/").split("/")
            for part in parts:
                found = None
                for item in tree:
                    if item.get("name") == part and item.get("children"):
                        found = item["children"]
                        break
                if found is not None:
                    tree = found
                else:
                    tree = []
                    break
        return {"results": tree, "_source": "direct"}
    return {"results": [], "_source": "direct"}


@app.get("/api/coverage/{service}/{org}/{repo}/commits")
def get_coverage_commits(service: str, org: str, repo: str, branch: str = "", page_size: int = 5):
    """Get recent commits with coverage from upload history."""
    page_size = max(1, min(page_size, 25))
    history = _load_coverage_history(org, repo)
    if history:
        if branch:
            history = [h for h in history if h.get("branch") == branch]
        results = [
            {
                "commitid": h.get("commit"),
                "branch": h.get("branch"),
                "timestamp": h.get("timestamp"),
                "totals": h.get("totals"),
            }
            for h in history[:page_size]
        ]
        return {"results": results, "_source": "direct"}
    return {"results": [], "_source": "direct"}


@app.get("/api/coverage/status")
def get_coverage_status():
    """Check coverage integration status."""
    local_repos = 0
    if COVERAGE_DIR.is_dir():
        for org_dir in COVERAGE_DIR.iterdir():
            if org_dir.is_dir():
                for repo_dir in org_dir.iterdir():
                    if (repo_dir / "latest.yaml").exists():
                        local_repos += 1

    return {
        "configured": local_repos > 0,
        "repos_with_data": local_repos,
        "storage": str(COVERAGE_DIR),
        "upload_endpoint": "POST /api/coverage/upload",
    }


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------

_ui_html_cache: tuple[float, str] = (0.0, "")
_UI_CACHE_TTL = 60  # seconds — re-read HTML from disk every minute


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    """Serve the single-page dashboard (cached in memory)."""
    global _ui_html_cache
    html_path = ROOT / "ui" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI not found</h1><p>Missing ui/index.html</p>", 404)
    now = time.time()
    if now - _ui_html_cache[0] > _UI_CACHE_TTL:
        _ui_html_cache = (now, html_path.read_text())
    return HTMLResponse(_ui_html_cache[1])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="QualityFlow Dashboard")
    parser.add_argument("--port", type=int, default=8420, help="Port (default: 8420)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    if not args.no_browser:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
