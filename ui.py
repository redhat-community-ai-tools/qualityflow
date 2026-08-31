"""QualityFlow Dashboard — FastAPI backend serving the pipeline UI.

Launch:
    uv run ui.py              # starts on http://localhost:8420
    uv run ui.py --port 9000  # custom port

SSO/OIDC (optional, per-cluster — unset = anonymous reads + API-key writes as before):
    OIDC_CLIENT_ID, OIDC_CLIENT_SECRET   # from your IdP (Keycloak/Red Hat SSO/Google/...)
    OIDC_DISCOVERY_URL                    # .well-known/openid-configuration URL
        (or OIDC_ISSUER, from which the discovery URL is derived)
    SESSION_SECRET                        # required when OIDC is set; random 32+ char string
    OIDC_REDIRECT_URI                     # optional; set behind a TLS-terminating proxy
    OIDC_ALLOWED_DOMAINS / OIDC_ALLOWED_GROUPS  # optional CSV allowlists (email domain / claim)
    OIDC_PUBLIC_READ=true                 # optional; allow anonymous GETs, require login for writes
    Machines (CI upload, peer rollup) keep using QUALITYFLOW_API_KEY (X-API-Key or Bearer).
"""

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
#     "anthropic>=0.39",
# ]
# ///

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import contextvars
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
import sys
import tarfile
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import bleach
import markdown
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

logger = logging.getLogger("qualityflow.dashboard")

# ---------------------------------------------------------------------------
# Structured logging — JSON lines by default, correlated to the request-id
# that RequestIDMiddleware (below) stamps on every request. QF_LOG_FORMAT=text
# gives human-readable output for local dev; QF_LOG_LEVEL sets the level.
# ---------------------------------------------------------------------------

_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class _RequestIDLogFilter(logging.Filter):
    """Stamps the current request's id (set by RequestIDMiddleware) onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


class _JsonLogFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, request_id (when set)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        req_id = getattr(record, "request_id", None)
        if req_id:
            payload["request_id"] = req_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _setup_logging() -> None:
    """Configure the dashboard logger at import time (env QF_LOG_FORMAT=json|text,
    QF_LOG_LEVEL=DEBUG|INFO|WARNING|...). ponytail: only touches our own logger,
    not the root — uvicorn keeps configuring its own access/error loggers as before."""
    level = getattr(logging, os.environ.get("QF_LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIDLogFilter())
    if os.environ.get("QF_LOG_FORMAT", "json").strip().lower() == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    else:
        handler.setFormatter(_JsonLogFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # we now have our own handler — avoid double-emit via root


_setup_logging()

ROOT = Path(__file__).parent

# Load .env (gitignored) so `uv run ui.py` picks up tokens without a dotenv dep.
# .env overrides the inherited shell env on purpose: it's explicit local config
# (e.g. replacing a stale GITHUB_PERSONAL_ACCESS_TOKEN exported elsewhere).
# ponytail: naive KEY=VALUE parser, swap for python-dotenv if you need quoting/interpolation.
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

# Data dirs are env-overridable so they can live on separate writable PVCs
# while the code/resources stay on a read-only image layer.
OUTPUTS = Path(os.environ["QF_OUTPUTS_DIR"]).resolve() if os.environ.get("QF_OUTPUTS_DIR") else ROOT / "outputs"
RESOURCES = ROOT
CONFIG = Path(os.environ["QF_CONFIG_DIR"]).resolve() if os.environ.get("QF_CONFIG_DIR") else ROOT / "config"

# Allowlist for sanitizing rendered artifact markdown (STP/STD content is
# derived from Jira ticket text, which is attacker-influenceable — this is
# the trust boundary before the HTML is injected client-side via innerHTML).
_MD_ALLOWED_TAGS = [
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code", "em", "strong", "del",
    "a", "img", "table", "thead", "tbody", "tr", "th", "td", "span",
]
_MD_ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
    "th": ["align"],
    "td": ["align"],
}


def _md_to_html(raw: str) -> str:
    """Markdown -> sanitized HTML, same allowlist/trust-boundary as get_artifact."""
    return bleach.clean(
        markdown.markdown(raw, extensions=["tables", "fenced_code"]),
        tags=_MD_ALLOWED_TAGS,
        attributes=_MD_ALLOWED_ATTRS,
        strip=True,
    )


def _state_dir(jira_id: str) -> Path:
    """Per-ticket state dir. Canonical JIRA-first (outputs/{id}/state/) — the layout
    the pipeline-state skill writes — with a fallback to legacy type-first
    (outputs/state/{id}/) so pilot data from before the migration still resolves.
    New writes land in canonical when neither exists yet."""
    canonical = OUTPUTS / jira_id / "state"
    if canonical.is_dir():
        return canonical
    legacy = OUTPUTS / "state" / jira_id
    if legacy.is_dir():
        return legacy
    return canonical


_COMMIT_SHA_RE = re.compile(r"^[a-fA-F0-9]{7,40}$")


def _safe_path_segment(value: str, fallback: str = "_") -> str:
    """Reduce untrusted input to exactly one safe filesystem path segment.

    Mapping everything outside [A-Za-z0-9_.-] to '_' kills separators, but on
    its own it still passes '.' and '..' through unchanged — and a bare '..'
    segment traverses a level. Both are replaced, so the result provably names
    a child of whatever directory it is joined to.

    Use this for any untrusted value interpolated into a path. Where the value
    has a known shape (a commit SHA), prefer rejecting it outright with a 400
    over silently rewriting it into a path that won't be found.
    """
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", value or "")
    return fallback if safe in ("", ".", "..") else safe


def _iter_state_files():
    """Yield (jira_id, pipeline_state.yaml Path) across both layouts, canonical
    first, de-duped by ticket. Used for whole-instance sweeps (startup
    reconciliation, pipeline count)."""
    seen: set[str] = set()
    if OUTPUTS.is_dir():
        for p in OUTPUTS.glob("*/state/pipeline_state.yaml"):  # canonical
            jid = p.parent.parent.name
            if re.match(r"^[A-Z]+-\d+$", jid) and jid not in seen:
                seen.add(jid)
                yield jid, p
    legacy_root = OUTPUTS / "state"
    if legacy_root.is_dir():
        for p in legacy_root.glob("*/pipeline_state.yaml"):  # legacy type-first
            jid = p.parent.name
            if re.match(r"^[A-Z]+-\d+$", jid) and jid not in seen:
                seen.add(jid)
                yield jid, p

# ---------------------------------------------------------------------------
# Claude / Vertex AI client
# ---------------------------------------------------------------------------

_VERTEX_PROJECT = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
_VERTEX_REGION = os.environ.get("CLOUD_ML_REGION", "us-east5")
_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4@20250514")

# Model selection for the dashboard pipeline runner (UI picker + backend default).
# Empty default = inherit the `claude` CLI session model (safest — always valid).
# Configure via env:
#   QF_RUNNER_MODEL   default model id passed to the runner ("" = inherit session)
#   QF_RUNNER_MODELS  comma-separated model ids offered in the UI dropdown
_RUNNER_MODEL_DEFAULT = os.environ.get("QF_RUNNER_MODEL", "")
_RUNNER_MODELS = [m.strip() for m in os.environ.get("QF_RUNNER_MODELS", "").split(",") if m.strip()]

def _claude_available() -> bool:
    return bool(_VERTEX_PROJECT or _ANTHROPIC_API_KEY)

from contextlib import asynccontextmanager


def _get_git_short_hash() -> str:
    """Return short git commit hash, the baked-in QF_COMMIT, or 'unknown'.

    In a checkout git wins; in the container image there is no .git, so the
    build-arg-baked QF_COMMIT env (see Containerfile) is the fallback."""
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return os.environ.get("QF_COMMIT", "unknown")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Startup: initial git sync, background loop, and banner."""
    _git_sync()
    _start_git_sync_loop()
    commit = _get_git_short_hash()
    # ponytail: a phase can only be "in_progress" while a background thread is
    # running it, tracked in the in-memory _running_tasks dict — a restart
    # always wipes that. Any state file still marked in_progress belongs to a
    # thread that died with the old process, so it's stuck forever unless we
    # flip it here. Sweep both layouts via _iter_state_files.
    def _fail_stuck_phases(data: dict) -> dict:
        for phase in data.get("phases", {}).values():
            if isinstance(phase, dict) and phase.get("status") == "in_progress":
                phase["status"] = "failed"
                phase["error"] = "Interrupted by dashboard restart"
        return data

    _reconciled = 0
    n_pipelines = 0
    for _jid, _state_file in _iter_state_files():
        n_pipelines += 1
        try:
            _data = _read_yaml(_state_file)
            if any(isinstance(p, dict) and p.get("status") == "in_progress"
                   for p in _data.get("phases", {}).values()):
                _atomic_yaml_update(_state_file, _fail_stuck_phases)
                _reconciled += 1
        except Exception as e:
            logger.warning("Startup reconciliation skipped %s: %s", _state_file, e)
    if _reconciled:
        logger.info("Startup reconciliation: marked %d pipeline(s) failed (was in_progress at restart)", _reconciled)
    logger.info(
        "QualityFlow Dashboard ready  |  commit=%s  |  pipelines=%d  |  outputs=%s  |  claude=%s",
        commit, n_pipelines, str(OUTPUTS), "yes" if _claude_available() else "no",
    )
    yield
    # ponytail: shutdown-side complement to the startup reconciliation above —
    # startup fails stuck phases left by a *previous* process death; this drains
    # what's in-flight in *this* process so the next restart doesn't repeat the work.
    _shutdown_event.set()  # wakes the git-sync loop immediately instead of sleeping out its interval
    _drained = 0
    with _tasks_lock:
        _in_flight = [k for k, v in _running_tasks.items() if v.get("status") == "running"]
    for _key in _in_flight:
        try:
            _jid, _phase = _key.split("/", 1)
            state_file = _state_dir(_jid) / "pipeline_state.yaml"

            def _mark_interrupted(state, _phase=_phase):
                if not state:
                    return state
                phase_data = state.get("phases", {}).get(_phase)
                if isinstance(phase_data, dict) and phase_data.get("status") == "in_progress":
                    phase_data["status"] = "failed"
                    phase_data["error"] = "Interrupted by dashboard shutdown"
                return state

            _atomic_yaml_update(state_file, _mark_interrupted)
            _drained += 1
        except Exception as e:
            logger.warning("Shutdown drain skipped %s: %s", _key, e)
    if _drained:
        logger.info("Graceful shutdown: marked %d in-flight phase(s) failed", _drained)
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
        token = _request_id_ctx.set(req_id)
        try:
            response: StarletteResponse = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = req_id
        _record_http_metric(request.method, response.status_code)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: StarletteResponse = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # ponytail: assets are vendored and served locally from /vendor (air-gap friendly) —
        # no more external CDN/font hosts in the default policy.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
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


def _hostname_of(entry: str) -> str:
    """Extract a bare hostname from a CORS_ORIGINS entry (full origin URL or bare host)."""
    entry = entry.strip()
    return (urllib.parse.urlparse(entry).hostname if "://" in entry else entry) or ""


# ponytail: no substring matching — an entry must equal the request's host exactly.
_TRUSTED_HOSTS = {h for h in (_hostname_of(o) for o in _CORS_ORIGINS) if h}


def _is_trusted_origin(origin: str) -> bool:
    """Check if origin is a QualityFlow dashboard instance: localhost, or a host
    explicitly allow-listed via the CORS_ORIGINS env var. Exact match only."""
    host = urllib.parse.urlparse(origin).hostname or ""
    return host in ("localhost", "127.0.0.1") or host in _TRUSTED_HOSTS


# Always enable CORS — the middleware checks trusted origins + configured origins
app.add_middleware(CORSMiddleware)

# ---------------------------------------------------------------------------
# Auth — API key for write operations
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("QUALITYFLOW_API_KEY", "")
if not _API_KEY and os.environ.get("QF_DEV", "").lower() not in ("1", "true", "yes"):
    print(
        "FATAL: QUALITYFLOW_API_KEY is not set. Write endpoints would be "
        "unauthenticated. Set QUALITYFLOW_API_KEY to a strong secret, or set "
        "QF_DEV=1 to run locally with unauthenticated writes (dev only).",
        file=sys.stderr,
    )
    raise SystemExit(1)
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
    """Require a valid API key for write endpoints. No-op in dev mode (no key set).

    Note: `request` is unused now that the Referer-based bypass is gone (Referer
    is attacker-controlled and was a spoofable auth bypass). Kept in the
    signature so existing call sites don't need updating.
    """
    if not _API_KEY:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(403, "Invalid or missing API key")


# ---------------------------------------------------------------------------
# Auth — OIDC/SSO (optional, per-cluster). Unconfigured → behaves exactly as
# before: API-key for writes, anonymous reads. When configured, a logged-in
# session (or the shared API key, for CI/peer machines) is required.
# ---------------------------------------------------------------------------

_OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
_OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
_OIDC_DISCOVERY_URL = os.environ.get("OIDC_DISCOVERY_URL", "") or (
    os.environ["OIDC_ISSUER"].rstrip("/") + "/.well-known/openid-configuration"
    if os.environ.get("OIDC_ISSUER") else "")
_OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")  # override behind a TLS-terminating proxy
_OIDC_ALLOWED_DOMAINS = [d.strip().lower() for d in os.environ.get("OIDC_ALLOWED_DOMAINS", "").split(",") if d.strip()]
_OIDC_ALLOWED_GROUPS = [g.strip() for g in os.environ.get("OIDC_ALLOWED_GROUPS", "").split(",") if g.strip()]
_OIDC_PUBLIC_READ = os.environ.get("OIDC_PUBLIC_READ", "").lower() in ("1", "true", "yes")
_SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
_OIDC_ENABLED = bool(_OIDC_CLIENT_ID and _OIDC_CLIENT_SECRET and _OIDC_DISCOVERY_URL)

_oauth = None
_AUTH_EXEMPT_PREFIXES = ("/auth/", "/healthz", "/readyz", "/favicon", "/metrics")


def _machine_authorized(request: Request) -> bool:
    """True if the request carries the shared API key (CI upload, peer rollup).
    Accepts it as X-API-Key or Authorization: Bearer."""
    if not _API_KEY:
        return False
    key = request.headers.get("x-api-key", "")
    if not key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    return bool(key) and hmac.compare_digest(key, _API_KEY)


def _session_user(request: Request):
    """Logged-in user dict from the session, or None. Safe when SSO is off."""
    try:
        return request.session.get("user")
    except (AssertionError, AttributeError):
        return None  # SessionMiddleware not installed (SSO disabled)


def _authorized_user(email: str, groups) -> bool:
    """Enforce optional domain/group allowlists on an authenticated identity."""
    if _OIDC_ALLOWED_DOMAINS and email.rpartition("@")[2] not in _OIDC_ALLOWED_DOMAINS:
        return False
    if _OIDC_ALLOWED_GROUPS and not (set(groups or []) & set(_OIDC_ALLOWED_GROUPS)):
        return False
    return True


def _resolve_actor(request: Request, x_api_key: str = "") -> str:
    """Best-effort identity for audit logging: the SSO session user when OIDC is
    on, else the shared API key (machine caller), else anonymous."""
    user = _session_user(request)
    if user:
        return user.get("email") or user.get("name") or "sso-user"
    if x_api_key or _machine_authorized(request):
        return "api-key"
    return "anonymous"


class AuthMiddleware(BaseHTTPMiddleware):
    """Gate every request behind a session (or API key) when SSO is enabled.
    Browsers get redirected to login; API/XHR callers get 401."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (request.method == "OPTIONS"
                or path.startswith(_AUTH_EXEMPT_PREFIXES)
                or _session_user(request)
                or _machine_authorized(request)
                or (_OIDC_PUBLIC_READ and request.method in ("GET", "HEAD"))):
            return await call_next(request)
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            request.session["post_login"] = request.url.path
            return RedirectResponse("/auth/login")
        return JSONResponse({"detail": "Authentication required"}, status_code=401)


def _setup_oidc() -> None:
    """Register the OIDC client + session/auth middleware. No-op when unconfigured."""
    global _oauth
    if not _OIDC_ENABLED:
        return
    if not _SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be set when OIDC/SSO is configured")
    from authlib.integrations.starlette_client import OAuth
    from starlette.middleware.sessions import SessionMiddleware

    _oauth = OAuth()
    _oauth.register(
        name="oidc",
        server_metadata_url=_OIDC_DISCOVERY_URL,
        client_id=_OIDC_CLIENT_ID,
        client_secret=_OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )
    # SessionMiddleware must wrap AuthMiddleware so request.session is populated
    # first; last-added is outermost, so add Auth then Session.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=_SESSION_SECRET,
        same_site="lax",  # required so the cookie survives the IdP callback redirect
        https_only=_OIDC_REDIRECT_URI.startswith("https") or _BASE_URL.startswith("https"),
        max_age=8 * 3600,
    )
    logger.info("OIDC/SSO enabled (discovery=%s, public_read=%s)", _OIDC_DISCOVERY_URL, _OIDC_PUBLIC_READ)


@app.get("/auth/login")
async def auth_login(request: Request):
    if not _OIDC_ENABLED or _oauth is None:
        raise HTTPException(404, "SSO is not enabled")
    redirect_uri = _OIDC_REDIRECT_URI or str(request.url_for("auth_callback"))
    return await _oauth.oidc.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    if not _OIDC_ENABLED or _oauth is None:
        raise HTTPException(404, "SSO is not enabled")
    try:
        token = await _oauth.oidc.authorize_access_token(request)  # validates the id_token via JWKS
    except Exception as e:
        logger.warning("OIDC callback failed: %s", e)
        raise HTTPException(403, "Authentication failed")
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").lower()
    groups = info.get("groups") or info.get("roles") or []
    if not _authorized_user(email, groups):
        raise HTTPException(403, "Your account is not authorized for this dashboard")
    request.session["user"] = {"email": email,
                               "name": info.get("name") or info.get("preferred_username") or email}
    dest = request.session.pop("post_login", "/") or "/"
    return RedirectResponse(dest if dest.startswith("/") else "/")  # guard against open redirect


@app.get("/auth/logout")
async def auth_logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/")


_setup_oidc()


# ---------------------------------------------------------------------------
# Git Sync — pulls outputs from GitLab in production
# ---------------------------------------------------------------------------

_git_sync_lock = threading.Lock()
_last_sync: str | None = None
_shutdown_event = threading.Event()  # signals the git-sync loop to stop on shutdown


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

            # Sync into the mounted data dirs, NOT ROOT/*: in-cluster those are
            # separate PVCs (QF_OUTPUTS_DIR/QF_CONFIG_DIR) while ROOT is the
            # read-mostly image layer, so writing to ROOT/outputs succeeded and
            # was then never read by anything.
            # config/ is synced because GIT_REPO_URL is documented as "pull
            # pipeline config from git instead of the bundled default".
            # ponytail: git wins over dashboard-created projects on the next
            # sync. Fine while git is the declared source of truth; if teams
            # need to author projects in the UI *and* sync, merge per-project
            # instead of copying the tree.
            for sub, dst in (("outputs", OUTPUTS), ("config", CONFIG)):
                src = repo_path / sub
                if not src.is_dir():
                    continue
                for item in src.rglob("*"):
                    rel = item.relative_to(src)
                    target = dst / rel
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)  # copy2: preserve mtime (duration/timeline metrics read it)

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
        while not _shutdown_event.is_set():
            if _shutdown_event.wait(interval):
                break
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
def dashboard_status(request: Request):
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
        "sso_enabled": _OIDC_ENABLED,
        "user": _session_user(request),
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
# Prometheus metrics — hand-rolled text exposition (no client dependency).
# ---------------------------------------------------------------------------

_http_request_counts: dict[tuple[str, int], int] = {}
_http_request_counts_lock = threading.Lock()


def _record_http_metric(method: str, status: int) -> None:
    key = (method, status)
    with _http_request_counts_lock:
        _http_request_counts[key] = _http_request_counts.get(key, 0) + 1


def _prom_escape(value: str) -> str:
    """Minimal escaping for a Prometheus label value."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@app.get("/metrics")
def metrics():
    """Prometheus text exposition format. Auth-exempt — see _AUTH_EXEMPT_PREFIXES."""
    lines = [
        "# HELP qf_pipelines_total Number of pipelines with state on disk.",
        "# TYPE qf_pipelines_total gauge",
        f"qf_pipelines_total {sum(1 for _ in _iter_state_files())}",
        "# HELP qf_running_tasks In-memory background pipeline tasks currently running.",
        "# TYPE qf_running_tasks gauge",
        f"qf_running_tasks {len(_running_tasks)}",
        "# HELP qf_build_info Build info, value is always 1; commit label carries the version.",
        "# TYPE qf_build_info gauge",
        f'qf_build_info{{commit="{_prom_escape(_get_git_short_hash())}"}} 1',
        "# HELP qf_http_requests_total Total HTTP requests by method and status code.",
        "# TYPE qf_http_requests_total counter",
    ]
    with _http_request_counts_lock:
        counts = dict(_http_request_counts)
    for (method, status), count in sorted(counts.items()):
        lines.append(f'qf_http_requests_total{{method="{_prom_escape(method)}",status="{status}"}} {count}')

    # --- per-project value/business gauges (reuses the /api/metrics cache+TTL,
    # so a scrape only recomputes for projects whose cache has actually expired) ---
    projects_dir = CONFIG / "projects"
    project_ids = sorted(
        p.name for p in projects_dir.iterdir() if (p / "project.yaml").exists()
    ) if projects_dir.is_dir() else []
    per_project: dict[str, dict] = {}
    for pid in project_ids:
        try:
            per_project[pid] = get_metrics(pid)
        except Exception:
            pass  # ponytail: one broken project must never break the scrape

    def _project_gauge(name: str, help_text: str, getter) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for pid, m in per_project.items():
            try:
                v = getter(m)
            except Exception:
                continue
            if v is None:
                continue
            lines.append(f'{name}{{project="{_prom_escape(pid)}"}} {v}')

    _project_gauge("qf_project_pipelines_total", "Total pipelines for the project.",
                    lambda m: m["totals"]["pipelines"])
    _project_gauge("qf_project_pipelines_completed", "Completed pipelines for the project.",
                    lambda m: m["totals"]["completed"])
    _project_gauge("qf_project_tests_generated", "Total generated tests for the project.",
                    lambda m: m["value"]["tests_generated"]["total_tests"])
    _project_gauge("qf_project_time_saved_hours", "Estimated engineering hours saved for the project.",
                    lambda m: m["value"]["time_saved_hours"])
    _project_gauge("qf_project_coverage_pct", "Current code coverage percentage for the project.",
                    lambda m: m["value"]["coverage"]["current_pct"])
    _project_gauge("qf_project_reviews_auto_approved", "Auto-approved review count for the project.",
                    lambda m: m["value"]["review_quality"]["auto_approved"])
    _project_gauge("qf_project_reviews_human_approved", "Human-approved review count for the project.",
                    lambda m: m["value"]["review_quality"]["human_approved"])

    return StarletteResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict:
    """Read a YAML file, return empty dict on failure."""
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


_JIRA_URL_PLACEHOLDER = "https://your-org.atlassian.net"


def _jira_base_url(project_id: str | None = None) -> str:
    """Configured Jira base URL: env JIRA_URL, else the project's jira.yaml, else the placeholder."""
    env_url = os.environ.get("JIRA_URL", "")
    if env_url:
        return env_url.rstrip("/")
    if project_id:
        jira_cfg = _read_yaml(CONFIG / "projects" / project_id / "jira.yaml")
        url = (jira_cfg.get("instance", {}) or {}).get("url") or jira_cfg.get("jira_url") or jira_cfg.get("url")
        if url:
            return url.rstrip("/")
    return _JIRA_URL_PLACEHOLDER


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


def _canonical_or_legacy(jira_id: str, sub: str, fname: str) -> Path:
    """A single output file, canonical-first with a legacy-layout fallback.

    QF writes artifacts JIRA-first today: outputs/{id}/{sub}/{fname}. Older
    data (and some not-yet-migrated call sites) used type-first:
    outputs/{sub}/{id}/{fname}. Prefer canonical; fall back to legacy only if
    canonical doesn't exist, so old data still shows up. Returns the
    canonical path even when neither exists (keeps writes canonical).
    """
    canonical = OUTPUTS / jira_id / sub / fname
    if canonical.exists():
        return canonical
    legacy = OUTPUTS / sub / jira_id / fname
    return legacy if legacy.exists() else canonical


def _pick_dir(*candidates: Path) -> Path | None:
    """First candidate dir that exists — canonical jira-first layout first,
    type-first as legacy fallback. Shared by _collect_pr_files and the value
    metrics (tests_generated.total_tests)."""
    for d in candidates:
        if d.is_dir():
            return d
    return None


_SKILL_VERSION: str | None = None


def _compute_skill_version() -> str:
    """Short content hash of every skill/agent instruction file, computed once
    and cached. Stamped on each phase run (see _run_phase_background) so a
    pipeline_state entry says which skill/agent prompt version produced it —
    without this, a skill edit is invisible in the run history.

    sha256 over sorted "relpath + content" for every RESOURCES/skills/**/SKILL.md
    and ROOT/agents/*.md file, truncated to 12 hex chars. Falls back to
    "unknown" (never raises) if the dirs are missing or unreadable.
    """
    global _SKILL_VERSION
    if _SKILL_VERSION is not None:
        return _SKILL_VERSION
    try:
        files: list[Path] = []
        skills_dir = RESOURCES / "skills"
        if skills_dir.is_dir():
            files.extend(skills_dir.glob("**/SKILL.md"))
        agents_dir = ROOT / "agents"
        if agents_dir.is_dir():
            files.extend(agents_dir.glob("*.md"))
        if not files:
            _SKILL_VERSION = "unknown"
        else:
            h = hashlib.sha256()
            for f in sorted(files, key=lambda p: str(p.relative_to(ROOT))):
                h.update(str(f.relative_to(ROOT)).encode())
                h.update(f.read_bytes())
            _SKILL_VERSION = h.hexdigest()[:12]
    except Exception:
        _SKILL_VERSION = "unknown"
    return _SKILL_VERSION


_HISTORY_CAP = 10
_TERMINAL_PHASE_STATUSES = ("completed", "failed", "blocked", "skipped")
# Go test declarations: `func TestFoo(t *testing.T)`. Anchored to line start so a
# mention inside a comment or string doesn't inflate the count. Benchmarks and
# fuzz targets are deliberately excluded — they aren't tests for this purpose.
_GO_TEST_FUNC_RE = re.compile(r"(?m)^func\s+(Test[A-Z_]\w*)\s*\(")


def _record_phase_result(phases: dict, phase: str, phase_data: dict) -> None:
    """Write `phase_data` into phases[phase], carrying forward (and, if the
    outgoing entry reached a terminal status, extending) phases[phase]['history']
    — capped at 10 entries.

    Two call sites share this: the run endpoint's "in_progress" placeholder
    write (where a just-finished terminal result would otherwise be silently
    discarded the moment a re-run starts) and the background thread's
    completed/failed write (where the placeholder's already-archived history
    must not be dropped just because "in_progress" itself isn't terminal).
    The archived copy is intentionally compact (status/verdict/model/
    finished_ts only) so history doesn't balloon with every past run's full
    `output` text.
    """
    prev = phases.get(phase)
    history = list(prev.get("history", [])) if isinstance(prev, dict) else []
    if isinstance(prev, dict) and prev.get("status") in _TERMINAL_PHASE_STATUSES:
        history.append({k: prev[k] for k in ("status", "verdict", "model", "finished_ts") if k in prev})
    if history:
        phase_data["history"] = history[-_HISTORY_CAP:]
    # Carry started_ts across the in_progress -> completed/failed write. Both
    # writes go through here and the terminal one builds a fresh dict, so
    # without this the start time is lost and the duration is unrecoverable.
    if isinstance(prev, dict) and "started_ts" in prev and "started_ts" not in phase_data:
        if prev.get("status") not in _TERMINAL_PHASE_STATUSES:
            phase_data["started_ts"] = prev["started_ts"]
    phases[phase] = phase_data


_ARTIFACT_KINDS: dict[str, tuple[str, str]] = {
    "stp": ("stp", "{id}_test_plan.md"),
    "std": ("std", "{id}_test_description.yaml"),
    "stp_review": ("reviews", "{id}_stp_review.md"),
    "std_review": ("reviews", "{id}_std_review.md"),
}


def _artifact_path(jira_id: str, kind: str) -> Path:
    """Canonical-first artifact path with legacy fallback. kind: stp|std|stp_review|std_review."""
    sub, fname_pattern = _ARTIFACT_KINDS[kind]
    return _canonical_or_legacy(jira_id, sub, fname_pattern.format(id=jira_id))


def _phase_artifact_exists(jira_id: str, kind: str) -> bool:
    return _artifact_path(jira_id, kind).exists()


_jira_ids_cache: tuple[float, list[str]] = (0.0, [])
_JIRA_IDS_CACHE_TTL = 3  # seconds — brief cache to avoid redundant scans within a refresh cycle


def _scan_jira_ids() -> list[str]:
    """Discover all Jira IDs with any output artifacts (cached briefly)."""
    global _jira_ids_cache
    now = time.time()
    if now - _jira_ids_cache[0] < _JIRA_IDS_CACHE_TTL:
        return _jira_ids_cache[1]
    ids: set[str] = set()
    if OUTPUTS.is_dir():
        # Canonical JIRA-first: outputs/{JIRA-ID}/...
        for child in OUTPUTS.iterdir():
            if child.is_dir() and re.match(r"^[A-Z]+-\d+$", child.name):
                ids.add(child.name)
        # Legacy type-first: outputs/{type}/{JIRA-ID}/... (backward compat)
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
        state_file = _state_dir(jira_id) / "pipeline_state.yaml"
        if state_file.exists():
            state = _read_yaml(state_file)
            _apply_approval_gates(
                state.get("phases") or {}, jira_id,
                _get_approval_gates(state.get("project_id") or state.get("project")
                                    or _infer_project(jira_id)))
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
        approvals = _read_approvals(jira_id)
        auto_approved = [gate for gate, entry in approvals.items()
                          if isinstance(entry, dict) and entry.get("reviewer") == "dashboard (auto)"]
        results.append({
            "jira_id": jira_id,
            "project_id": state.get("project_id", _infer_project(jira_id)),
            "has_state_file": state_file.exists(),
            "phases": _summarize_phases(state, jira_id),
            "updated": state.get("updated", _file_modified(state_file) if state_file.exists() else None),
            "pr": pr_summary,
            "auto_approved": auto_approved,
            "caveats": _detect_caveats(state),
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
        state_file = _state_dir(jira_id) / "pipeline_state.yaml"
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
            # staleness column in the matrix view reads this
            "updated": state.get("updated") or state.get("created"),
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
    state_file = _state_dir(jira_id) / "pipeline_state.yaml"
    if state_file.exists():
        state = _read_yaml(state_file)
    else:
        state = _infer_state(jira_id)
    state["_artifacts"] = _list_artifacts(jira_id)
    # Include feature toggles so frontend can show skipped phases
    project_id = state.get("project_id") or state.get("project") or _infer_project(jira_id)
    toggles = _load_project_toggles(project_id)
    state["feature_toggles"] = toggles
    # Gate overlay + gates list for the Approve card — on BOTH state sources
    # (idempotent re-run on the inferred path).
    gates = _get_approval_gates(project_id)
    state["gates"] = gates
    _apply_approval_gates(state.get("phases") or {}, jira_id, gates)
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
            except Exception as e:
                logger.debug("PR state refresh failed for %s (%s): %s", jira_id, pr_info.get("url"), e)
        state["pr"] = pr_info

    # Same enrichments the list endpoint carries — the detail view renders
    # caveat/auto-approval chips and rich phase output from THIS payload.
    state["caveats"] = _detect_caveats(state)
    state["auto_approved"] = [
        g for g, e in _read_approvals(jira_id).items()
        if isinstance(e, dict) and e.get("reviewer") == "dashboard (auto)"
    ]
    for _ph in (state.get("phases") or {}).values():
        if isinstance(_ph, dict) and _ph.get("output"):
            _ph["output_html"] = _md_to_html(str(_ph["output"])[:20000])

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


_VERDICT_ALTS = (
    r"APPROVED_WITH_FINDINGS|APPROVED\s+WITH\s+FINDINGS|APPROVED|"
    r"NEEDS_REVISION|NEEDS\s+REVISION|PASS|WARN|FAIL"
)
# Anchor on an explicit "Verdict: X" line, or a "## Verdict" heading with the
# value on the next line — NOT a bare word anywhere in the doc. A preamble
# that happens to say "this looks approved so far" must not count.
_VERDICT_LINE_RE = re.compile(rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?verdict[ \t]*:?[ \t]*[-:]?[ \t]*({_VERDICT_ALTS})\b")
_VERDICT_HEADING_RE = re.compile(rf"(?im)^#{{1,6}}[ \t]*verdict[ \t]*\n+[ \t]*({_VERDICT_ALTS})\b")


def _extract_verdict_from_md(path: Path) -> str | None:
    """Extract verdict (PASS/WARN/FAIL/APPROVED/etc.) from a markdown file.

    Anchors on an explicit verdict line/heading (first match wins) rather than
    scanning the whole doc for bare words. Falls back to a plain substring scan
    (APPROVED family only, matching the mapping callers already use) only when
    no explicit verdict line/heading is present, for older docs.
    """
    try:
        text = path.read_text()
    except Exception as e:
        logger.debug("verdict extraction: cannot read %s: %s", path, e)
        return None
    head = text[:4000]
    for pattern in (_VERDICT_LINE_RE, _VERDICT_HEADING_RE):
        m = pattern.search(head)
        if m:
            return m.group(1).upper().replace(" ", "_")
    # ponytail: fallback substring scan for docs without an explicit verdict line/heading
    cl = head[:2000].lower()
    if "needs_revision" in cl or "needs revision" in cl:
        return "NEEDS_REVISION"
    if "approved_with_findings" in cl or "approved with findings" in cl:
        return "APPROVED_WITH_FINDINGS"
    if "approved" in cl:
        return "APPROVED"
    return None


def _find_test_files(jira_id: str, lang: str) -> list[Path]:
    """Generated test files for a ticket, across the layouts QF has shipped.

    Tests have lived in three places over time: top-level type-first
    (outputs/go-tests/{id}/), JIRA-first (outputs/{id}/go-tests/), and nested
    under the STD dir (outputs/std/{id}/go-tests/). Check all three.
    """
    # QF codegen writes the `qf_` prefix (qf_{feature}{ext}) — see CLAUDE.md — but
    # the Python generator's outputs-fallback also emits pytest-native test_*.py
    # (e.g. CNV-95235). Both are generated tests here; exclude *_stubs* so STD
    # stub files (test_*_stubs.py) never count as real tests.
    patterns = ("qf_*.go",) if lang == "go" else ("qf_*.py", "test_*.py")
    dirs = [
        OUTPUTS / f"{lang}-tests" / jira_id,
        OUTPUTS / jira_id / f"{lang}-tests",
        OUTPUTS / "std" / jira_id / f"{lang}-tests",
    ]
    files: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for pat in patterns:
            files.extend(p for p in d.glob(pat) if "_stubs" not in p.name)
    return files


def _phase_deliverable_exists(jira_id: str, phase: str) -> bool:
    """Did a *runnable phase* (stp|std|codegen) actually produce its deliverable?
    A command can exit 0 while declining to run (disabled toggle, unmet
    prerequisite, unsatisfied approval gate), so exit-0 alone must not mark a
    phase 'completed'. (Distinct from _phase_artifact_exists, which keys on
    artifact *kind* stp|std|stp_review|std_review for metric counting.)"""
    if phase == "codegen":
        return bool(_find_test_files(jira_id, "go") or _find_test_files(jira_id, "python"))
    if phase in ("stp", "std"):
        return _phase_artifact_exists(jira_id, phase)  # canonical-or-legacy
    return True  # unknown phase — don't second-guess


# TTL cache for the synchronous PR-state lookup in _infer_state: /api/pipelines
# calls _infer_state in a loop per refresh, and each miss is a blocking GitHub
# API call. Keyed by PR URL. The explicit /refresh-pr endpoint updates it.
_pr_state_cache: dict[str, tuple[str, float]] = {}  # url → (state, fetched_ts)
_PR_STATE_CACHE_TTL = 300  # seconds


# Dashboard gate phases ("stp"/"std") map to the CLI state machine's approval
# keys ("stp_review"/"std_review") — the keys /std-builder and /generate-tests
# actually read. Writing or reading any other key makes an approval invisible
# to the pipeline (found on CNV-50425: a dashboard approval landed under "stp"
# and the CLI gate stayed blocked).
_GATE_APPROVAL_KEY = {"stp": "stp_review", "std": "std_review"}


def _apply_approval_gates(phases: dict, jira_id: str, gates: list) -> None:
    """Overlay approval-gate status onto a phases dict, whatever wrote it.

    A completed gated phase with no recorded approval becomes awaiting_approval
    (which is what makes the dashboard's Approve card render); one with a
    decision carries it as phase["approval"]. Runs on inferred AND runner-written
    state — previously only the inferred path applied it, so pipelines with a
    real state file never showed an Approve control. Idempotent."""
    approvals = _read_approvals(jira_id)
    for gate_phase in gates:
        phase_data = phases.get(gate_phase)
        if not isinstance(phase_data, dict) or phase_data.get("status") != "completed":
            continue
        key = _GATE_APPROVAL_KEY.get(gate_phase, gate_phase)
        approval = approvals.get(key) or approvals.get(gate_phase)  # legacy key
        if approval:
            phase_data["approval"] = approval
        else:
            phase_data["status"] = "awaiting_approval"


def _infer_state(jira_id: str) -> dict:
    """Build a synthetic state from file existence when no state YAML exists."""
    phases = {}
    # STP (includes internal review + refine)
    stp = _artifact_path(jira_id, "stp")
    stp_rev = _artifact_path(jira_id, "stp_review")
    stp_data: dict = {"status": "completed" if stp.exists() else "pending",
                      "output": str(stp.relative_to(OUTPUTS)) if stp.exists() else None}
    if stp_rev.exists():
        stp_data["verdict"] = _extract_verdict_from_md(stp_rev)
    phases["stp"] = stp_data
    # STD (includes internal review + refine)
    std = _artifact_path(jira_id, "std")
    std_rev = _artifact_path(jira_id, "std_review")
    std_data: dict = {"status": "completed" if std.exists() else "pending",
                      "output": str(std.relative_to(OUTPUTS)) if std.exists() else None}
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
    _apply_approval_gates(phases, jira_id, gates)

    # PR info — refresh state from GitHub/GitLab if token available, through a
    # TTL cache so the list endpoint doesn't make one blocking API call per
    # state-file-less pipeline per refresh (PERF-03).
    pr_info = _read_pr_info(jira_id)
    if pr_info and pr_info.get("url"):
        token = _GITHUB_TOKEN if pr_info.get("platform", "github") == "github" else _GITLAB_TOKEN
        cached = _pr_state_cache.get(pr_info["url"])
        if cached and (time.time() - cached[1]) < _PR_STATE_CACHE_TTL:
            if cached[0] != pr_info.get("state"):
                pr_info["state"] = cached[0]
                _write_pr_info(jira_id, pr_info)
        elif token:
            try:
                repo = pr_info.get("target_repo", "")
                nr = pr_info.get("number")
                if repo and nr:
                    data = _github_api("GET", f"https://api.github.com/repos/{repo}/pulls/{nr}", token)
                    new_state = data.get("state", pr_info.get("state"))
                    if data.get("merged"):
                        new_state = "merged"
                    _pr_state_cache[pr_info["url"]] = (new_state, time.time())
                    if new_state != pr_info.get("state"):
                        pr_info["state"] = new_state
                        _write_pr_info(jira_id, pr_info)
            except Exception as e:
                # non-critical — use cached state, but negative-cache the failure
                # so a down GitHub doesn't stall every subsequent list refresh.
                logger.debug("PR state refresh failed for %s (%s): %s", jira_id, pr_info.get("url"), e)
                _pr_state_cache[pr_info["url"]] = (pr_info.get("state", "unknown"), time.time())

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


# The pipeline-state skill's canonical phase list (skills/pipeline-state/state.py).
# Keep in sync with PHASES there — the dashboard timeline renders this order.
_CANONICAL_PHASES = ("stp", "stp_review", "stp_refine", "std", "std_review",
                     "go_codegen", "python_codegen")
# "codegen" is the legacy single-phase alias the original 3-dot UI was built on.
# It stays in the summary so existing callers keep resolving it.
_SUMMARY_PHASES = _CANONICAL_PHASES + ("codegen",)

_PHASE_DISPLAY = {
    "stp": "STP Generation", "stp_review": "STP Review",
    "stp_refine": "STP Refinement", "std": "STD Generation",
    "std_review": "STD Review", "go_codegen": "Go Code Gen",
    "python_codegen": "Python Code Gen", "codegen": "Test Generation",
}


# The two pipeline writers name their phase timestamps differently: the
# pipeline-state skill (CLI slash commands) writes started/completed, the
# dashboard's own run endpoint writes started_ts/finished_ts. Read both, or
# every CLI-driven run reports no duration at all.
_PHASE_START_KEYS = ("started_ts", "started")
_PHASE_END_KEYS = ("finished_ts", "completed")


def _phase_timestamps(phase) -> tuple[str | None, str | None]:
    """(start, end) ISO strings for a phase, whichever writer recorded them."""
    if not isinstance(phase, dict):
        return None, None
    start = next((phase[k] for k in _PHASE_START_KEYS if phase.get(k)), None)
    end = next((phase[k] for k in _PHASE_END_KEYS if phase.get(k)), None)
    return start, end


def _phase_duration_seconds(phase) -> float | None:
    """Wall-clock seconds a phase took, from the timestamps the run recorded.

    Returns None unless both ends are present and the result is positive —
    mtime-derived clocks skew across a git sync or container rebuild, and a
    negative duration is worse than an absent one."""
    start_raw, end_raw = _phase_timestamps(phase)
    try:
        start = datetime.fromisoformat(start_raw).timestamp()  # type: ignore[arg-type]
        end = datetime.fromisoformat(end_raw).timestamp()  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(end - start, 1) if end > start else None


def _summarize_phases(state: dict, _jira_id: str) -> dict:
    """Return a compact phase → status map. Each phase's markdown `output` (the
    agent's narration of the run) is rendered to sanitized HTML too, capped at
    20000 chars input, so the dashboard can show it without a raw-artifact fetch.

    Emits every canonical phase, not just the three the legacy UI drew: the
    review and refine phases are where approvals and reruns actually happen, and
    collapsing them hid that state from every consumer of this endpoint."""
    phases = state.get("phases", {})
    # The dashboard's own runner only ever writes the combined "codegen" phase
    # (_VALID_PHASES), never the go/python split the CLI state machine declares.
    # Reporting those two as "pending" on a run that already generated its tests
    # leaves the run permanently incomplete — and eventually flags it as stale.
    # They didn't run and won't, which is what "skipped" means.
    legacy_codegen_done = (phases.get("codegen") or {}).get("status") == "completed"
    summary = {}
    for phase_name in _SUMMARY_PHASES:
        phase = phases.get(phase_name) or {}
        status = phase.get("status", "pending")
        superseded = (legacy_codegen_done
                      and phase_name in ("go_codegen", "python_codegen")
                      and status == "pending")
        entry = {
            "status": "skipped" if superseded else status,
            "verdict": phase.get("verdict"),
            "label": _PHASE_DISPLAY[phase_name],
        }
        if superseded:
            entry["note"] = "covered by the combined codegen phase"
        started, finished = _phase_timestamps(phase)
        if started:
            entry["started_ts"] = started
        if finished:
            entry["finished_ts"] = finished
        for key in ("model", "error"):
            if phase.get(key):
                entry[key] = phase[key]
        duration = _phase_duration_seconds(phase)
        if duration is not None:
            entry["duration_seconds"] = duration
        output = phase.get("output") or ""
        if output:
            entry["output_html"] = _md_to_html(output[:20000])
        summary[phase_name] = entry
    return summary


# Gate/phase output text is scanned for these substrings (case-insensitive) to
# surface degraded-run conditions the pipeline narrated but didn't fail on.
# ponytail: substring heuristics on free-text narration, not structured
# signals — good enough to flag "look closer", not meant to be exhaustive.
_CAVEAT_ORDER = ("stp", "stp_review", "std", "std_review", "codegen")


def _detect_caveats(state: dict) -> list[str]:
    """Short-label caveats detected in any phase's `output` text, deduped,
    in order of first appearance."""
    phases = state.get("phases") or {}
    ordered_names = list(_CAVEAT_ORDER) + [p for p in phases if p not in _CAVEAT_ORDER]
    caveats: list[str] = []

    def _add(label: str) -> None:
        if label not in caveats:
            caveats.append(label)

    for name in ordered_names:
        phase = phases.get(name)
        if not isinstance(phase, dict):
            continue
        text = (phase.get("output") or "")
        if not text:
            continue
        low = text.lower()
        if "mcp auth failed" in low:
            _add("GitHub data incomplete")
        if "lsp" in low and any(w in low for w in ("skipped", "not set", "unavailable")):
            _add("No LSP regression analysis")
        if "source_repo_path" in low and any(w in low for w in ("not set", "unset")):
            _add("No source checkout")
        if "reconstructed" in low:
            _add("Requirements reconstructed")
        if "best-effort" in low:
            _add("Best-effort test data")
    return caveats


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
            path = _canonical_or_legacy(jira_id, subdir, pattern.format(id=jira_id))
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
_TRENDS_DIR = OUTPUTS / "_trends"


def _append_trend_snapshot(project_id: str, value: dict, pipelines: int, completed: int) -> None:
    """Append today's value snapshot to the project's trend file (one row/day).

    ponytail: flat YAML list behind a lock, no database — same-day recompute
    replaces the last entry in place (idempotent with the /api/metrics cache),
    capped at 104 entries (~2 years of daily snapshots).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tests_meta = value.get("tests_generated") or {}
    coverage = value.get("coverage") or {}
    review_quality = value.get("review_quality") or {}
    record = {
        "date": today,
        "pipelines": pipelines,
        "completed": completed,
        "tests": tests_meta.get("total_tests") or tests_meta.get("total_files") or 0,
        "time_saved_hours": value.get("time_saved_hours"),
        "coverage_pct": coverage.get("current_pct"),
        "auto_approved": review_quality.get("auto_approved", 0),
        "human_approved": review_quality.get("human_approved", 0),
    }

    def _update(data: dict) -> dict:
        history = data.get("history") if isinstance(data, dict) else None
        if not isinstance(history, list):
            history = []
        if history and history[-1].get("date") == today:
            history[-1] = record
        else:
            history.append(record)
        return {"history": history[-104:]}

    _atomic_yaml_update(_TRENDS_DIR / f"{project_id}.yaml", _update)


@app.get("/api/trends/{project_id}")
def get_trends(project_id: str):
    """Daily value-metrics history for a project. Read-only — see _append_trend_snapshot.

    `all` merges every project's trend file by date: counts sum, coverage_pct
    averages over projects that reported one that day."""
    if project_id != "all":
        data = _read_yaml(_TRENDS_DIR / f"{project_id}.yaml")
        return {"history": data.get("history", [])}

    by_date: dict[str, dict] = {}
    cov_by_date: dict[str, list] = {}
    for path in sorted(_TRENDS_DIR.glob("*.yaml")) if _TRENDS_DIR.is_dir() else []:
        for row in (_read_yaml(path).get("history") or []):
            date = row.get("date")
            if not date:
                continue
            merged = by_date.setdefault(
                date,
                {"date": date, "pipelines": 0, "completed": 0, "tests": 0,
                 "time_saved_hours": 0.0, "coverage_pct": None,
                 "auto_approved": 0, "human_approved": 0},
            )
            for k in ("pipelines", "completed", "tests", "auto_approved", "human_approved"):
                merged[k] += row.get(k) or 0
            merged["time_saved_hours"] = round(
                merged["time_saved_hours"] + (row.get("time_saved_hours") or 0), 1
            )
            if isinstance(row.get("coverage_pct"), (int, float)):
                cov_by_date.setdefault(date, []).append(row["coverage_pct"])
    for date, covs in cov_by_date.items():
        by_date[date]["coverage_pct"] = round(sum(covs) / len(covs), 1)
    return {"history": [by_date[d] for d in sorted(by_date)]}


def _ticket_test_count(jira_id: str) -> int:
    """Generated-test count for one ticket, python + go combined.

    Extracted out of _compute_value_metrics so /api/metrics/roi can report a
    per-ticket test count without re-deriving it. Python prefers
    python-tests/summary.yaml's `test_count` (compat fallback:
    `generated_tests`, an older/wrong key some summaries still carry), else
    counts `def test_` in the qf_* files directly. Go has no summary.yaml
    equivalent, so its functions are always counted via regex.
    """
    count = 0
    py_dir = _pick_dir(OUTPUTS / jira_id / "python-tests", OUTPUTS / "python-tests" / jira_id)
    summary_path = py_dir / "summary.yaml" if py_dir else None
    counted = False
    if summary_path and summary_path.exists():
        try:
            summary = yaml.safe_load(summary_path.read_text()) or {}
            n = summary.get("test_count", summary.get("generated_tests"))
            if isinstance(n, (int, float)):
                count += int(n)
                counted = True
        except Exception:
            pass
    if not counted and py_dir:
        for f in py_dir.glob("qf_*.py"):
            try:
                count += f.read_text(errors="ignore").count("def test_")
            except Exception:
                pass  # best-effort — skip unreadable files
    for f in _find_test_files(jira_id, "go"):
        try:
            count += len(_GO_TEST_FUNC_RE.findall(f.read_text(errors="ignore")))
        except Exception:
            pass  # best-effort — skip unreadable files
    return count


def _compute_value_metrics(project_id: str, states: list[dict]) -> dict:
    """Derive value-demonstration metrics from existing pipeline data."""
    # states carry "ticket_id" (pipeline_state.yaml + _infer_state); "jira_id" fallback for safety
    jira_ids = [str(jid) for s in states
                if (jid := s.get("ticket_id") or s.get("jira_id"))]

    # ponytail: per-team calibration heuristic, not a measured number — tune
    # QF_HOURS_PER_STP / QF_HOURS_PER_SCENARIO / QF_HOURS_PER_STD / QF_MINUTES_PER_TEST
    # to your team's real authoring pace.
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return default

    # --- tests_generated ---
    go_files = 0
    py_files = 0
    total_lines = 0
    for jid in jira_ids:
        for f in _find_test_files(jid, "go"):
            go_files += 1
            try:
                total_lines += len(f.read_text(errors="ignore").splitlines())
            except Exception:
                pass  # best-effort — skip unreadable files
        for f in _find_test_files(jid, "python"):
            py_files += 1
            try:
                total_lines += len(f.read_text(errors="ignore").splitlines())
            except Exception:
                pass  # best-effort — skip unreadable files

    # total_tests: prefer python-tests/summary.yaml's `test_count` (what the
    # codegen skill actually writes — `generated_tests` kept as a compat
    # fallback for older summaries); else count `def test_` in the qf_* files
    # themselves. Go has no summary.yaml equivalent, so its functions are
    # always counted directly via regex.
    # scaffolded_files: qf_ test files that are `raise NotImplementedError`
    # stubs rather than runnable tests (checked across go + python).
    total_tests = 0
    scaffolded_files = 0
    for jid in jira_ids:
        total_tests += _ticket_test_count(jid)
        for f in _find_test_files(jid, "go") + _find_test_files(jid, "python"):
            try:
                if "raise NotImplementedError" in f.read_text(errors="ignore"):
                    scaffolded_files += 1
            except Exception:
                pass  # best-effort — skip unreadable files

    # --- scenarios --- (from each STD's document_metadata; tickets without an
    # STD artifact contribute nothing. Also feeds the STD share of time_saved.)
    scenario_totals = {k: 0 for k in
                        ("total", "p0", "p1", "p2", "e2e", "functional", "integration", "unit")}
    _SCENARIO_KEYS = {
        "total": "total_scenarios", "p0": "p0_count", "p1": "p1_count", "p2": "p2_count",
        "e2e": "e2e_count", "functional": "functional_count",
        "integration": "integration_count", "unit": "unit_count",
    }
    std_hours_total = 0.0
    hours_per_scenario = _env_float("QF_HOURS_PER_SCENARIO", 0.5)
    hours_per_std = _env_float("QF_HOURS_PER_STD", 1.5)  # old per-STD fallback, no document_metadata
    for jid in jira_ids:
        std_path = _artifact_path(jid, "std")
        if not std_path.exists():
            continue
        try:
            std_doc = yaml.safe_load(std_path.read_text()) or {}
        except Exception:
            std_doc = {}
        meta = std_doc.get("document_metadata")
        if meta:
            for out_key, yaml_key in _SCENARIO_KEYS.items():
                scenario_totals[out_key] += meta.get(yaml_key) or 0
            std_hours_total += (meta.get("total_scenarios") or 0) * hours_per_scenario
        else:
            std_hours_total += hours_per_std  # no document_metadata — old flat-per-STD credit

    # --- review_quality (auto vs. human decisions from approvals.yaml) ---
    rq_human_approved = rq_auto_approved = rq_human_rejected = 0
    for jid in jira_ids:
        for _gate, entry in _read_approvals(jid).items():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if status == "rejected":
                rq_human_rejected += 1
            elif status == "approved":
                if entry.get("reviewer") == "dashboard (auto)":
                    rq_auto_approved += 1
                else:
                    rq_human_approved += 1

    # --- artifacts_produced ---
    stps = stds = reviews = 0
    for jid in jira_ids:
        if _phase_artifact_exists(jid, "stp"):
            stps += 1
        if _phase_artifact_exists(jid, "std"):
            stds += 1
        if _phase_artifact_exists(jid, "stp_review"):
            reviews += 1
        if _phase_artifact_exists(jid, "std_review"):
            reviews += 1

    # --- phase_durations ---
    # Prefer the timestamps a run actually recorded (started_ts/finished_ts on
    # the phase entry). Fall back to file mtimes for tickets produced by the CLI
    # or before those were written — but mtimes don't survive a git sync, a
    # container rebuild or a volume restore, which is how this metric was
    # emitting NEGATIVE durations. Anything non-positive is dropped rather than
    # averaged in.
    def _ts(value) -> float | None:
        try:
            return datetime.fromisoformat(value).timestamp() if value else None
        except (TypeError, ValueError):
            return None

    def _recorded(state: dict, phase: str) -> float | None:
        entry = (state.get("phases") or {}).get(phase)
        if not isinstance(entry, dict):
            return None
        start, end = _ts(entry.get("started_ts")), _ts(entry.get("finished_ts"))
        return (end - start) / 3600 if start and end else None

    # Per-ticket so the totals below stay aligned. The old code zipped three
    # independently-filtered lists, which silently paired one ticket's STP with
    # another ticket's STD as soon as any ticket had an STP but no STD.
    per_ticket: list[dict[str, float]] = []
    for s in states:
        jid = s.get("ticket_id") or s.get("jira_id") or ""
        if not jid:
            continue
        d: dict[str, float] = {}
        stp_path, std_path = _artifact_path(jid, "stp"), _artifact_path(jid, "std")
        stp_mt = stp_path.stat().st_mtime if stp_path.exists() else None
        std_mt = std_path.stat().st_mtime if std_path.exists() else None

        stp = _recorded(s, "stp")
        if stp is None and stp_mt:
            created_ts = _ts(s.get("created"))
            stp = (stp_mt - created_ts) / 3600 if created_ts else None
        if stp is not None and stp > 0:
            d["stp"] = stp

        std = _recorded(s, "std")
        if std is None and std_mt and stp_mt:
            std = (std_mt - stp_mt) / 3600
        if std is not None and std > 0:
            d["std"] = std

        codegen = _recorded(s, "codegen")
        if codegen is None and std_mt:
            latest_test = 0.0
            for tf in _find_test_files(jid, "go") + _find_test_files(jid, "python"):
                latest_test = max(latest_test, tf.stat().st_mtime)
            if latest_test > std_mt:
                codegen = (latest_test - std_mt) / 3600
        if codegen is not None and codegen > 0:
            d["codegen"] = codegen

        if d:
            per_ticket.append(d)

    def _avg(lst: list[float]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    stp_durations = [d["stp"] for d in per_ticket if "stp" in d]
    std_durations = [d["std"] for d in per_ticket if "std" in d]
    codegen_durations = [d["codegen"] for d in per_ticket if "codegen" in d]
    # Only tickets that went all the way through contribute an end-to-end total.
    full_runs = [d for d in per_ticket if {"stp", "std", "codegen"} <= d.keys()]

    # --- pr_stats ---
    total_prs = 0
    merged_prs = 0
    merge_hours: list[float] = []
    for jid in jira_ids:
        pr_path = _state_dir(jid) / "pr_info.yaml"
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
    uploads = 0
    cov_trend: list[dict] = []

    def _pct_of(totals: dict):
        # "coverage" is the key every writer in this file emits (and what's on
        # disk); the other two are legacy spellings kept as fallback.
        return totals.get("coverage") or totals.get("coverage_pct") or totals.get("line_rate")

    # Aggregate across the project's repos by line count rather than letting the
    # last repo in the loop win. Falls back to a plain mean when a repo's totals
    # predate hits/lines being recorded.
    agg_hits = agg_lines = 0
    loose_pcts: list[float] = []
    # date -> [hits, lines] so multi-repo projects get one point per day, not one
    # per repo per day stacked on the same x position.
    trend_by_date: dict[str, list[float]] = {}
    prev_hits = prev_lines = 0
    prev_pcts: list[float] = []

    for repo_cfg in project_repos:
        org, repo = repo_cfg.get("org", ""), repo_cfg.get("repo", "")
        if not org or not repo:
            continue
        latest = _load_latest_coverage(org, repo)
        if latest:
            uploads += 1
            totals = latest.get("totals", {})
            pct = _pct_of(totals)
            hits, lines = totals.get("hits"), totals.get("lines")
            if isinstance(hits, (int, float)) and isinstance(lines, (int, float)) and lines:
                agg_hits += hits
                agg_lines += lines
            elif isinstance(pct, (int, float)):
                loose_pcts.append(float(pct))
        history = _load_coverage_history(org, repo)
        if history:
            uploads = max(uploads, len(history))
            # History is newest-first (_store_coverage does history.insert(0, …)),
            # so the newest 30 are history[:30] and chronological order is that
            # reversed. Reading history[-30:] took the OLDEST 30, backwards.
            for entry in reversed(history[:30]):
                t = entry.get("totals", {})
                pct = _pct_of(t)
                if pct is None:
                    continue
                day = (entry.get("timestamp") or "")[:10]
                h, ln = t.get("hits"), t.get("lines")
                if not (isinstance(h, (int, float)) and isinstance(ln, (int, float)) and ln):
                    h, ln = float(pct), 100.0  # weight a bare % as if out of 100 lines
                slot = trend_by_date.setdefault(day, [0.0, 0.0])
                slot[0] += float(h)
                slot[1] += float(ln)
            # Delta is vs. the PREVIOUS upload, which on a newest-first list is
            # index 1. Index 0 is the current one — subtracting it from itself is
            # why every delta on the dashboard read as 0.
            if len(history) >= 2:
                pt = history[1].get("totals", {})
                ppct = _pct_of(pt)
                ph, pln = pt.get("hits"), pt.get("lines")
                if isinstance(ph, (int, float)) and isinstance(pln, (int, float)) and pln:
                    prev_hits += ph
                    prev_lines += pln
                elif isinstance(ppct, (int, float)):
                    prev_pcts.append(float(ppct))

    def _blend(hits: float, lines: float, loose: list[float]):
        """Line-weighted where we have line counts, mean where we only have a %."""
        parts = ([hits / lines * 100] if lines else []) + ([sum(loose) / len(loose)] if loose else [])
        return round(sum(parts) / len(parts), 1) if parts else None

    current_pct = _blend(agg_hits, agg_lines, loose_pcts)
    prev_pct = _blend(prev_hits, prev_lines, prev_pcts)
    if current_pct is not None and prev_pct is not None:
        delta = round(current_pct - prev_pct, 1)
    cov_trend = [
        {"date": d, "coverage": round(hl[0] / hl[1] * 100, 1)}
        for d, hl in sorted(trend_by_date.items())
        if hl[1]
    ]

    # --- review_quality ---
    total_verdicts = 0
    approved = 0
    findings = 0
    needs_rev = 0
    for jid in jira_ids:
        for review_name in (f"{jid}_stp_review.md", f"{jid}_std_review.md"):
            rp = _canonical_or_legacy(jid, "reviews", review_name)
            if not rp.exists():
                continue
            verdict = _extract_verdict_from_md(rp)  # anchored on "Verdict:" line/heading, not a bare-word scan
            if verdict is None:
                continue
            total_verdicts += 1
            if verdict == "NEEDS_REVISION":
                needs_rev += 1
            elif verdict == "APPROVED_WITH_FINDINGS":
                findings += 1
            elif verdict == "APPROVED":
                approved += 1

    # --- time_saved (headline value claim) ---
    # STP credit stays per-artifact; STD credit is now per-scenario
    # (std_hours_total, computed above alongside `scenarios`) since a 40-scenario
    # STD and a 3-scenario STD don't take the same time to author by hand; test
    # credit is now per-test (total_tests), not per-file, for the same reason.
    hours_per_stp = _env_float("QF_HOURS_PER_STP", 2.0)
    minutes_per_test = _env_float("QF_MINUTES_PER_TEST", 20)
    time_saved_hours = round(
        stps * hours_per_stp + std_hours_total + total_tests * (minutes_per_test / 60), 1
    )
    time_saved_basis = (
        f"{hours_per_stp:g}h/STP + {hours_per_scenario:g}h/scenario "
        f"(or {hours_per_std:g}h/STD when a doc has no scenario metadata) + "
        f"{minutes_per_test:g}m/test (configurable, estimate)"
    )

    # --- coverage.configured: false when the project's coverage repos are
    # unfilled-in template placeholders (org == "my-org") or have no data on
    # disk yet — the frontend uses this to gray out the coverage card instead
    # of showing a misleading 0%.
    coverage_configured = bool(project_repos) and uploads > 0 and not all(
        r.get("org") == "my-org" for r in project_repos
    )

    return {
        "time_saved_hours": time_saved_hours,
        # index.html reads the bare number above directly (arithmetic, no
        # `.value`) — kept as-is. This flagged form is additive, for the new
        # confidence/ROI-aware frontend (also available structured the same
        # way from /api/metrics/roi).
        "time_saved_hours_flagged": {"value": time_saved_hours, "estimated": True},
        "time_saved_basis": time_saved_basis,
        "estimate": True,
        "tests_generated": {
            "total_files": go_files + py_files,
            "go_files": go_files,
            "python_files": py_files,
            "lines": total_lines,
            "estimated_lines": total_lines,  # alias — kept for frontends reading the old key
            "total_tests": total_tests,
            "scaffolded_files": scaffolded_files,
        },
        "scenarios": scenario_totals,
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
            "total_avg_hours": _avg([d["stp"] + d["std"] + d["codegen"] for d in full_runs]),
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
            # patch_coverage_pct removed: it was declared, never assigned and
            # never read (the UI's patch % comes from /api/coverage/test/{p}).
            # Patch coverage is PR-scoped; there's no project-wide value to put
            # here. Re-add only with a real source, not a None placeholder.
            "uploads": uploads,
            "trend": cov_trend,
            "configured": coverage_configured,
        },
        "review_quality": {
            "total": total_verdicts,
            "approved_pct": round(approved / total_verdicts * 100) if total_verdicts else 0,
            "needs_revision_pct": round(needs_rev / total_verdicts * 100) if total_verdicts else 0,
            "findings_pct": round(findings / total_verdicts * 100) if total_verdicts else 0,
            "human_approved": rq_human_approved,
            "auto_approved": rq_auto_approved,
            "human_rejected": rq_human_rejected,
        },
    }


# ---------------------------------------------------------------------------
# API: Confidence / ROI / Gaps / Quality-trend / Drift / Usage
#
# Six read endpoints + one write (beacon). Registered *before*
# /api/metrics/{project_id} below — that catch-all would otherwise swallow
# e.g. /api/metrics/confidence as project_id="confidence". All read from the
# same per-ticket pipeline_state.yaml + traceability data everything else on
# this page already reads; none re-parse or re-implement that. Every one
# degrades to available:false / empty lists on missing data — never a 500.
# ---------------------------------------------------------------------------

def _project_states(project_id: str) -> list[tuple[str, dict]]:
    """[(jira_id, state)] for every ticket in a project. Blank or "_all" ->
    every ticket with outputs. Same discovery + state-loading as get_metrics(),
    just keyed by jira_id instead of grouped."""
    out = []
    for jira_id in _scan_jira_ids():
        if project_id and project_id not in ("_all", "all") and _infer_project(jira_id) != project_id:
            continue
        state_file = _state_dir(jira_id) / "pipeline_state.yaml"
        state = _read_yaml(state_file) if state_file.exists() else _infer_state(jira_id)
        out.append((jira_id, state))
    return out


_REVIEW_VERDICT_SCORE = {"APPROVED": 1.0, "APPROVED_WITH_FINDINGS": 0.7, "NEEDS_REVISION": 0.2}
_CONFIDENCE_SIGNAL_KEYS = ("coverage", "link_quality", "review_health", "refinement",
                          "verification", "effectiveness", "freshness")


def _review_phase_score(phases: dict, base: str) -> float | None:
    """Score one doc's review (base='stp'|'std'). Checks the dedicated
    `{base}_review` phase first (CLI dialect — carries `findings`), falling
    back to the `{base}` phase's own `verdict` (dashboard dialect, which
    folds review into the generation phase). This order avoids double-counting
    the same review when a state file happens to carry both (real data does —
    the CLI writes the granular _review phase, the dashboard runner also
    stamps a verdict on the combined phase when the whole command finishes)."""
    for entry in (phases.get(f"{base}_review"), phases.get(base)):
        if not isinstance(entry, dict):
            continue
        # Prefer the reviewer's own holistic 0-100 weighted_score when present:
        # it's the QE verdict itself (from dimension_scores), whereas the
        # findings-count heuristic below clamps to 0 for many non-critical
        # findings — a 75/100 APPROVED_WITH_FINDINGS review shouldn't read as 0.
        ws = entry.get("weighted_score")
        if isinstance(ws, (int, float)) and not isinstance(ws, bool):
            return max(0.0, min(1.0, ws / 100.0))
        findings = entry.get("findings")
        if isinstance(findings, dict):
            crit = findings.get("critical") or 0
            major = findings.get("major") or 0
            minor = findings.get("minor") or 0
            return max(0.0, 1 - (crit * 1.0 + major * 0.2 + minor * 0.05))
        score = _REVIEW_VERDICT_SCORE.get(entry.get("verdict"))
        if score is not None:
            return score
    return None


def _freshness_signal(updated: str | None) -> float | None:
    """1.0 at <=7 days old, linear decay to 0.0 at 90 days, None if unknown."""
    if not updated:
        return None
    try:
        dt = datetime.fromisoformat(updated)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    if days <= 7:
        return 1.0
    if days >= 90:
        return 0.0
    return round(1 - (days - 7) / 83, 3)


def _confidence_signals(jira_id: str, state: dict) -> dict:
    """The 7 confidence signals for one ticket, each {"value", "available"}."""
    phases = state.get("phases") or {}
    signals: dict[str, dict] = {}

    try:
        trace = pipeline_traceability(jira_id)
    except Exception:
        trace = {"summary": {"requirements_total": 0, "requirements_with_tests": 0},
                 "requirements": [], "orphaned_scenarios": []}

    total_reqs = trace["summary"]["requirements_total"]
    signals["coverage"] = (
        {"value": round(trace["summary"]["requirements_with_tests"] / total_reqs, 3), "available": True}
        if total_reqs else {"value": None, "available": False}
    )

    # link quality: strong ("id") vs inferred STP<->STD links, deduped by
    # std_test_id (a scenario can appear under more than one requirement).
    links: dict[str, str] = {}
    for req in trace["requirements"]:
        for sc in req["scenarios"]:
            links[sc.get("std_test_id") or f"idx{len(links)}"] = sc["link"]
    for sc in trace["orphaned_scenarios"]:
        links[sc.get("std_test_id") or f"idx{len(links)}"] = sc["link"]
    if links:
        strong = sum(1 for v in links.values() if v == "id")
        signals["link_quality"] = {"value": round(strong / len(links), 3), "available": True}
    else:
        signals["link_quality"] = {"value": None, "available": False}

    rh_scores = [s for s in (_review_phase_score(phases, "stp"), _review_phase_score(phases, "std"))
                 if s is not None]
    signals["review_health"] = (
        {"value": round(sum(rh_scores) / len(rh_scores), 3), "available": True}
        if rh_scores else {"value": None, "available": False}
    )

    # Any *_refine phase key that actually ran (not just pre-seeded pending by
    # `state.py init`, which stamps every canonical phase up front).
    refine_ran = any(
        k.endswith("_refine") and isinstance(v, dict) and v.get("status") not in (None, "pending", "not_started")
        for k, v in phases.items()
    )
    signals["refinement"] = {"value": 0.5 if refine_ran else 1.0, "available": True}

    verifs = [v.get("verification") for k, v in phases.items()
              if "codegen" in k and isinstance(v, dict) and v.get("verification")]
    if "passed" in verifs:
        signals["verification"] = {"value": 1.0, "available": True}
    elif "failed" in verifs:
        signals["verification"] = {"value": 0.0, "available": True}
    else:
        signals["verification"] = {"value": None, "available": False}

    ci_data = _read_yaml(OUTPUTS / jira_id / "ci" / "test_runs.yaml")
    runs = ci_data.get("runs") if isinstance(ci_data, dict) else None
    if runs:
        latest = runs[-1] or {}
        total = latest.get("total") or 0
        signals["effectiveness"] = (
            {"value": round((latest.get("passed") or 0) / total, 3), "available": True}
            if total else {"value": None, "available": False}
        )
    else:
        signals["effectiveness"] = {"value": None, "available": False}

    fresh = _freshness_signal(state.get("updated"))
    signals["freshness"] = {"value": fresh, "available": fresh is not None}

    return signals


def _score_confidence(signals: dict) -> tuple[int | None, str, int, str | None]:
    """Score = mean(available signals) * 100. Fewer than 4 available signals
    -> never fake a green: band 'insufficient', score None."""
    available = {k: v["value"] for k, v in signals.items() if v["available"]}
    biggest_drag = min(available, key=available.get) if available else None
    if len(available) < 4:
        return None, "insufficient", len(available), biggest_drag
    score = round(sum(available.values()) / len(available) * 100)
    band = "trusted" if score >= 80 else "watch" if score >= 60 else "at_risk"
    return score, band, len(available), biggest_drag


@app.get("/api/metrics/confidence")
def get_metrics_confidence(project: str = ""):
    """Per-ticket + project rollup trust score across 7 pipeline-health signals."""
    tickets = []
    for jira_id, state in _project_states(project):
        try:
            signals = _confidence_signals(jira_id, state)
            score, band, n, biggest_drag = _score_confidence(signals)
        except Exception:
            logger.exception("confidence: skipped %s", jira_id)
            continue
        tickets.append({
            "jira_id": jira_id, "score": score, "band": band,
            "signals_present": n, "signals_total": len(_CONFIDENCE_SIGNAL_KEYS),
            "biggest_drag": biggest_drag, "signals": signals,
        })
    numeric = [t["score"] for t in tickets if t["score"] is not None]
    rollup_score = round(sum(numeric) / len(numeric)) if numeric else None
    rollup_band = ("insufficient" if rollup_score is None else
                   "trusted" if rollup_score >= 80 else "watch" if rollup_score >= 60 else "at_risk")
    return {
        "project": project or "_all",
        "rollup": {"score": rollup_score, "band": rollup_band, "tickets": len(tickets)},
        "tickets": tickets,
    }


@app.get("/api/metrics/roi")
def get_metrics_roi(project: str = ""):
    """Cost/usage totals summed across every phase of every ticket's
    pipeline_state.yaml — tolerates both writer dialects: whatever a phase is
    named (codegen/python_codegen/go_codegen/...), its `usage` sub-dict, if
    present, is summed the same way."""
    states = _project_states(project)
    totals = {"cost_usd": 0.0, "duration_ms": 0, "num_turns": 0, "input_tokens": 0, "output_tokens": 0}
    per_ticket = []
    for jira_id, state in states:
        phases = state.get("phases") or {}
        ticket_cost = 0.0
        phase_costs: dict[str, float] = {}
        for name, entry in phases.items():
            usage = entry.get("usage") if isinstance(entry, dict) else None
            if not isinstance(usage, dict):
                continue
            for key in totals:
                v = usage.get(key)
                if isinstance(v, (int, float)):
                    totals[key] += v
            cost = usage.get("cost_usd")
            if isinstance(cost, (int, float)):
                ticket_cost += cost
                bucket = "codegen" if "codegen" in name else name  # go_codegen/python_codegen -> codegen
                phase_costs[bucket] = round(phase_costs.get(bucket, 0.0) + cost, 4)
        if phase_costs:
            per_ticket.append({
                "jira_id": jira_id, "cost_usd": round(ticket_cost, 4),
                "tests": _ticket_test_count(jira_id), "phases": phase_costs,
            })

    tests_accepted = sum(_ticket_test_count(jid) for jid, _ in states)
    requirements_covered = 0
    for jid, _ in states:
        try:
            requirements_covered += pipeline_traceability(jid)["summary"]["requirements_with_tests"]
        except Exception:
            logger.exception("roi: traceability failed for %s", jid)

    # Reuse the existing value-metrics formula for time_saved_hours rather
    # than re-deriving it — states need a jira_id under the key it reads.
    value_states = [dict(s, ticket_id=s.get("ticket_id") or s.get("jira_id") or jid) for jid, s in states]
    value = _compute_value_metrics(project or "_all", value_states)

    return {
        "project": project or "_all",
        "totals": {**totals, "cost_usd": round(totals["cost_usd"], 4)},
        "tests_accepted": tests_accepted,
        "requirements_covered": requirements_covered,
        "cost_per_test": round(totals["cost_usd"] / tests_accepted, 2) if tests_accepted else None,
        "cost_per_requirement": round(totals["cost_usd"] / requirements_covered, 2) if requirements_covered else None,
        "time_saved_hours": {"value": value.get("time_saved_hours"), "estimated": True},
        "per_ticket": per_ticket,
    }


@app.get("/api/metrics/gaps")
def get_metrics_gaps(project: str = ""):
    """Requirements the traceability chain shows as uncovered or only
    weakly (inferred) linked, ranked by priority_score descending."""
    gaps = []
    for jira_id, _state in _project_states(project):
        try:
            trace = pipeline_traceability(jira_id)
        except Exception:
            logger.exception("gaps: traceability failed for %s", jira_id)
            continue
        for req in trace["requirements"]:
            scenarios = req["scenarios"]
            test_bearing = [s for s in scenarios if s["tests"]]
            if not test_bearing:
                status = "uncovered"
            elif any(s["link"] == "id" for s in test_bearing):
                continue  # a solid link with tests exists — fully covered, not a gap
            else:
                status = "inferred_only"
            strong = sum(1 for s in scenarios if s["link"] == "id")
            inferred = sum(1 for s in scenarios if s["link"] == "inferred")
            score = 5 if status == "uncovered" else 3
            # +3 bonus for P0/critical. The only "priority" data the
            # traceability chain actually carries is the STD scenario's own
            # priority field — no live Jira issue-priority is persisted to
            # outputs/ anywhere, so that half of the bonus is never available
            # here. We don't fake it; we just never add it.
            if any((s.get("priority") or "").upper() in ("P0", "CRITICAL") for s in scenarios):
                score += 3
            summary = next((s["title"] for s in scenarios if s.get("title")), "")
            gaps.append({
                "jira_id": req["id"], "epic": jira_id, "summary": summary,
                "status": status, "priority_score": score,
                "links": {"strong": strong, "inferred": inferred},
            })
    gaps.sort(key=lambda g: g["priority_score"], reverse=True)
    return {"project": project or "_all", "gaps": gaps}


@app.get("/api/metrics/quality-trend")
def get_metrics_quality_trend(project: str = ""):
    """Review-quality history: per-run verdicts/findings, first-time-approve
    rate (FTAR), and a findings-by-day trend."""
    runs = []
    for jira_id, state in _project_states(project):
        try:
            phases = state.get("phases") or {}
            stp_entry = phases.get("stp_review") or phases.get("stp")
            std_entry = phases.get("std_review") or phases.get("std")
            stp_verdict = stp_entry.get("verdict") if isinstance(stp_entry, dict) else None
            std_verdict = std_entry.get("verdict") if isinstance(std_entry, dict) else None
            verdicts = {k: v for k, v in (("stp", stp_verdict), ("std", std_verdict)) if v}
            if not verdicts:
                continue  # nothing reviewed yet — not a "run" for FTAR purposes
            findings = {"critical": 0, "major": 0, "minor": 0}
            for entry in (stp_entry, std_entry):
                f = entry.get("findings") if isinstance(entry, dict) else None
                if isinstance(f, dict):
                    for k in findings:
                        findings[k] += f.get(k) or 0
            refine_loops = sum(
                1 for k, v in phases.items()
                if k.endswith("_refine") and isinstance(v, dict)
                and v.get("status") not in (None, "pending", "not_started")
            )
            rejected = any(
                isinstance(e, dict) and e.get("status") == "rejected"
                for e in _read_approvals(jira_id).values()
            )
            first_time_approve = (
                all(v == "APPROVED" for v in verdicts.values())
                and refine_loops == 0 and not rejected
            )
            date = (state.get("updated") or state.get("created") or "")[:10]
            runs.append({
                "jira_id": jira_id, "date": date, "verdicts": verdicts,
                "findings": findings, "first_time_approve": first_time_approve,
                "refine_loops": refine_loops,
            })
        except Exception:
            logger.exception("quality-trend: skipped %s", jira_id)

    n = len(runs)
    ftar_value = round(sum(1 for r in runs if r["first_time_approve"]) / n, 2) if n else 0.0

    trend_by_date: dict[str, dict] = {}
    for r in runs:
        if not r["date"]:
            continue
        bucket = trend_by_date.setdefault(r["date"], {"date": r["date"], "critical": 0, "major": 0, "minor": 0})
        for k in ("critical", "major", "minor"):
            bucket[k] += r["findings"][k]

    return {
        "project": project or "_all",
        "runs": runs,
        "ftar": {"value": ftar_value, "n": n},
        "findings_trend": sorted(trend_by_date.values(), key=lambda b: b["date"]),
    }


@app.get("/api/metrics/drift")
def get_metrics_drift(project: str = ""):
    """Have the committed test files changed since codegen produced them?
    Recomputes the sha256 each generation_checksums entry recorded, against a
    local checkout of the target repo (SOURCE_REPO_PATH env), falling back to
    this repo's own root when unset. An unresolvable root -> available:false
    for that ticket rather than reporting everything as unchanged."""
    base = Path(os.environ.get("SOURCE_REPO_PATH") or ROOT)
    root_ok = base.is_dir()
    tickets = []
    for jira_id, state in _project_states(project):
        checksums = state.get("generation_checksums")
        if not isinstance(checksums, dict) or not checksums:
            continue
        if not root_ok:
            tickets.append({"jira_id": jira_id, "available": False, "files": [], "modified": 0, "missing": 0})
            continue
        files = []
        modified = missing = 0
        for path, expected in checksums.items():
            fp = base / path
            if not fp.is_file():
                status = "missing"
                missing += 1
            else:
                try:
                    # Same encoding the writer used (ui.py ~3388): read_text
                    # (not raw bytes) so universal-newline handling matches.
                    actual = hashlib.sha256(fp.read_text(errors="replace").encode()).hexdigest()[:16]
                except Exception:
                    actual = None
                status = "unchanged" if actual == expected else "modified"
                if status == "modified":
                    modified += 1
            files.append({"path": path, "status": status})
        tickets.append({"jira_id": jira_id, "available": True, "files": files, "modified": modified, "missing": missing})
    return {"project": project or "_all", "tickets": tickets}


_USAGE_LOG = OUTPUTS / "_usage" / "dashboard_usage.jsonl"


@app.post("/api/beacon")
async def post_beacon(request: Request):
    """Record one dashboard view hit, for /api/metrics/usage to aggregate
    later (panel-pruning data — see the usage endpoint below).
    navigator.sendBeacon can't attach a custom header, so — unlike every
    other write endpoint in this file — this one skips
    _check_api_key_or_origin; it only ever appends a view name + today's
    date, plain-append, nothing sensitive."""
    _check_rate_limit(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    view = str((body or {}).get("view") or "").strip()[:64]
    if not view:
        return {"status": "ignored"}
    _USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "view": view}
    try:
        with open(_USAGE_LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        logger.exception("beacon append failed")
    return {"status": "ok"}


@app.get("/api/metrics/usage")
def get_metrics_usage():
    """Per-view hit counts aggregated from the beacon log at read time
    (upsert-by-rewrite would work too; plain append is simpler and the log
    stays small — one line per page view)."""
    views: dict[str, dict] = {}
    if _USAGE_LOG.exists():
        try:
            lines = _USAGE_LOG.read_text().splitlines()
        except Exception:
            lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            view = row.get("view") if isinstance(row, dict) else None
            if not view:
                continue
            entry = views.setdefault(view, {"hits": 0, "days": set()})
            entry["hits"] += 1
            if row.get("date"):
                entry["days"].add(row["date"])
    return {"views": {v: {"hits": e["hits"], "active_days": len(e["days"])} for v, e in views.items()}}


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
        state_path = _state_dir(jira_id) / "pipeline_state.yaml"
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
    _append_trend_snapshot(project_id, result["value"], total, completed)
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
        projects.append({**p, "display_name": display, "cluster": cluster, "url": "",
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
        pr["url"] = base  # so the frontend can link back to the team dashboard that owns this project
    return data


@app.get("/api/rollup")
def rollup(local: bool = False):
    """Org roll-up. On a team instance (or ?local=true) returns just this
    cluster; on a manager instance (peers configured) merges all peers."""
    mine = _local_rollup()
    if local:
        return mine
    peers = _get_peers()
    clusters = [mine]
    if peers:
        # ponytail: peers are independent HTTP calls (8s timeout each) — fan out
        # instead of N sequential round-trips. Errors stay isolated per peer.
        def _fetch(peer):
            try:
                return _fetch_peer_rollup(peer)
            except Exception as e:
                return {"cluster": peer.get("label") or peer.get("url"),
                        "error": str(e), "projects": []}

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(peers))) as pool:
            peer_results = list(pool.map(_fetch, peers))
        clusters.extend(sorted(peer_results, key=lambda c: c.get("cluster") or ""))
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
    # Canonical JIRA-ID-first layout: outputs/{jira_id}/{stp,reviews,std}/...
    artifact_map = [
        ("stp", f"{jira_id}/stp/{jira_id}_test_plan.md", "STP"),
        ("stp_review", f"{jira_id}/reviews/{jira_id}_stp_review.md", "STP Review"),
        ("std", f"{jira_id}/std/{jira_id}_test_description.yaml", "STD"),
        ("std_review", f"{jira_id}/reviews/{jira_id}_std_review.md", "STD Review"),
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
    # STD stubs (human-review form) live under outputs/{jira_id}/std/{lang}-tests/.
    # These are the deliverable reviewers read; the YAML above feeds codegen.
    for lang, glob, kind in (("go", "*.go", "go_stub"), ("python", "*.py", "python_stub")):
        stubs_dir = OUTPUTS / jira_id / "std" / f"{lang}-tests"
        if stubs_dir.is_dir():
            for f in sorted(stubs_dir.glob(glob)):
                artifacts.append({
                    "type": kind,
                    "label": f"STD Stubs ({lang.capitalize()}): {f.name}",
                    "path": str(f.relative_to(OUTPUTS)),
                    "modified": _file_modified(f),
                    "size": f.stat().st_size,
                })
    # Generated test files live under outputs/{jira_id}/{language}-tests/
    for lang, glob, kind in (("go", "*_test.go", "go_test"), ("python", "*.py", "python_test")):
        tests_dir = OUTPUTS / jira_id / f"{lang}-tests"
        if tests_dir.is_dir():
            for f in sorted(tests_dir.glob(glob)):
                artifacts.append({
                    "type": kind,
                    "label": f"{lang.capitalize()}: {f.name}",
                    "path": str(f.relative_to(OUTPUTS)),
                    "modified": _file_modified(f),
                    "size": f.stat().st_size,
                })
    return artifacts


@app.get("/api/artifacts/{jira_id}/{artifact_type}")
def get_artifact(jira_id: str, artifact_type: str):
    """Read and return a specific artifact with rendered HTML for markdown."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")
    # Canonical-first with legacy fallback (same resolver the metrics use), so
    # the viewer opens pilot-era type-first artifacts too, not just canonical.
    path_map = {
        "stp": _artifact_path(jira_id, "stp"),
        "stp_review": _artifact_path(jira_id, "stp_review"),
        "std": _artifact_path(jira_id, "std"),
        "std_review": _artifact_path(jira_id, "std_review"),
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
                path = OUTPUTS / jira_id / "go-tests" / filename
            elif kind == "python_test":
                path = OUTPUTS / jira_id / "python-tests" / filename
            elif kind == "go_stub":
                path = OUTPUTS / jira_id / "std" / "go-tests" / filename
            elif kind == "python_stub":
                path = OUTPUTS / jira_id / "std" / "python-tests" / filename

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
        "path": str(path.relative_to(OUTPUTS)),
        "raw": raw,
        # ponytail: bleach.clean(strip=True) is the sanitizer here — the
        # allowlist above is the trust boundary between Jira-derived markdown
        # and the innerHTML sink in the browser. Do not widen it casually.
        "html": _md_to_html(raw) if is_md else None,
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
    jira_url = body.get("jira_url") or _jira_base_url()
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

    return {"status": "created", "project_id": project_id, "config_dir": str(proj_dir.relative_to(CONFIG))}


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


@app.post("/api/github/org-repos")
async def list_org_repos(request: Request):
    """List repositories in a GitHub org/user with language info.

    POST, not GET, and the token comes from the JSON body rather than a query
    parameter: a `repo`-scoped PAT in a URL is recorded by the uvicorn access
    log, the ingress/Route log and the browser's history, none of which are
    places a credential can be rotated out of. The other call sites that pass a
    user token (push-pr, close-pr, onboard, bulk-onboard) already POST it in
    the body; this endpoint was the one that didn't.

    Body: {"org": "<org or GitHub URL>", "token": "<optional GitHub PAT>"}
    """
    try:
        body = await request.json() if request.headers.get(
            "content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    org = (body.get("org") or "").strip()
    token = (body.get("token") or "").strip()
    if not org:
        raise HTTPException(400, "Required field: org")

    # Extract org name from full GitHub URLs
    url_match = re.search(r"github\.com/(?:orgs/)?([a-zA-Z0-9_.-]+)", org)
    if url_match:
        org = url_match.group(1)
    if not re.match(r"^[a-zA-Z0-9_.-]+$", org):
        raise HTTPException(400, "Invalid org name")

    gh_token = token or _GITHUB_TOKEN
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
    has_stp = _phase_artifact_exists(jira_id, "stp")
    has_std = _phase_artifact_exists(jira_id, "std")
    has_go = bool(_find_test_files(jira_id, "go"))
    has_py = bool(_find_test_files(jira_id, "python"))
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
async def init_pipeline(request: Request, x_api_key: str = Header(default="")):
    """Create a new pipeline entry for a Jira ticket.

    This creates the state directory so the pipeline appears in the sidebar.
    Called when a user clicks 'Start Pipeline' from the search bar.
    """
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)

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
    state_dir = _state_dir(jira_id)
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

_VALID_PHASES = ["stp", "stp_review", "std", "std_review", "codegen"]

# ---------------------------------------------------------------------------
# Background phase execution — avoids HTTP gateway timeouts
# ---------------------------------------------------------------------------
_running_tasks: dict[str, dict] = {}  # key: "jira_id/phase" → {status, result, error, started}
_tasks_lock = threading.Lock()
_TASK_RESULT_TTL = 600  # seconds — auto-clean completed/failed results after 10 min


def _run_phase_background(jira_id: str, phase: str, model: str = ""):
    """Execute a pipeline phase in a background thread."""
    key = f"{jira_id}/{phase}"
    try:
        from pipeline_runner import run_phase as _run_real_phase  # type: ignore[import-not-found]
        # The runner shells out to the `claude` CLI — no in-process Anthropic
        # client (and no `anthropic` dep) is ever used by it.
        result = _run_real_phase(model or _RUNNER_MODEL_DEFAULT, jira_id, phase)

        # Update pipeline state file (atomic)
        state_file = _state_dir(jira_id) / "pipeline_state.yaml"

        # A command can exit 0 while declining to run (gate/prereq/toggle). Only
        # call it 'completed' if the deliverable is actually on disk; otherwise
        # 'blocked' so the UI shows the reason instead of a misleading green ✓.
        produced = _phase_deliverable_exists(jira_id, phase)
        final_status = "completed" if produced else "blocked"

        def _mark_completed(state):
            if not state:
                state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
            phase_data = {"status": final_status, "output": result.get("output", "")}
            if result.get("verdict"):
                phase_data["verdict"] = result["verdict"]
            # Persist the run's cost/token/latency (from the CLI result event) so a
            # per-run cost record exists — nothing captured this before.
            usage = {k: v for k, v in (result.get("usage") or {}).items() if v is not None}
            if usage:
                phase_data["usage"] = usage
            if model:
                phase_data["model"] = model
            phase_data["skill_version"] = _compute_skill_version()
            phase_data["finished_ts"] = datetime.now(timezone.utc).isoformat()
            _record_phase_result(state.setdefault("phases", {}), phase, phase_data)

            # Generation checksums — sha256 (first 16 hex) of every test file this
            # completed codegen run produced, keyed by the same relpath the PR push
            # uses. Lets the dashboard prove which committed tests came from which
            # run, independent of git history.
            if phase == "codegen" and final_status == "completed":
                try:
                    file_groups = _collect_pr_files(jira_id)
                    checksums = {
                        item["path"]: hashlib.sha256(item["content"].encode()).hexdigest()[:16]
                        for item in file_groups.get("primary", []) + file_groups.get("tier2", [])
                    }
                    if checksums:
                        state["generation_checksums"] = checksums
                except Exception:
                    logger.exception("generation checksum computation failed for %s", jira_id)

            state["updated"] = datetime.now(timezone.utc).isoformat()
            return state

        _atomic_yaml_update(state_file, _mark_completed)

        _slack_pipeline_event(jira_id, f"{phase.replace('_', ' ').title()} {final_status}",
                              f"Verdict: {result.get('verdict', 'N/A')}")

        with _tasks_lock:
            _running_tasks[key] = {
                "status": final_status,
                "_finished": time.time(),
                "result": {
                    "phase": phase,
                    "jira_id": jira_id,
                    "output": result.get("output", ""),
                    "verdict": result.get("verdict"),
                    "progress": result.get("progress", []),
                },
            }
        logger.info(f"Phase {phase} for {jira_id} finished: {final_status}")

    except Exception as e:
        logger.error(f"Pipeline error for {jira_id}/{phase}: {e}")
        # Write error to state file so UI can show it (atomic)
        state_file = _state_dir(jira_id) / "pipeline_state.yaml"
        error_msg = str(e)[:500]

        def _mark_failed(state):
            if not state:
                state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
            phase_data = {"status": "failed", "error": error_msg}
            if model:
                phase_data["model"] = model
            phase_data["skill_version"] = _compute_skill_version()
            phase_data["finished_ts"] = datetime.now(timezone.utc).isoformat()
            _record_phase_result(state.setdefault("phases", {}), phase, phase_data)
            state["updated"] = datetime.now(timezone.utc).isoformat()
            return state

        _atomic_yaml_update(state_file, _mark_failed)

        with _tasks_lock:
            _running_tasks[key] = {"status": "failed", "_finished": time.time(), "error": error_msg}


@app.get("/api/models")
async def get_runner_models():
    """Models offered in the dashboard run picker. Empty value = inherit the
    `claude` session model (the safe default). Configure the list via
    QF_RUNNER_MODELS and the default via QF_RUNNER_MODEL."""
    return {"default": _RUNNER_MODEL_DEFAULT, "models": _RUNNER_MODELS}


@app.post("/api/pipelines/{jira_id}/run/{phase}")
async def run_pipeline_phase(jira_id: str, phase: str, request: Request, x_api_key: str = Header(default="")):
    """Start a pipeline phase in the background. Returns immediately."""
    _check_rate_limit(request)
    _check_api_key_or_origin(request, x_api_key)

    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID: {jira_id}")
    if phase not in _VALID_PHASES:
        raise HTTPException(400, f"Unknown phase: {phase}. Valid: {_VALID_PHASES}")
    if not _claude_available():
        raise HTTPException(503, "Claude AI not configured. Set ANTHROPIC_VERTEX_PROJECT_ID or ANTHROPIC_API_KEY.")

    # Optional model override from the UI picker ("" = backend default / inherit
    # session). When an allowlist is configured, reject anything not on it so a
    # bad id can't make the CLI exit 1.
    model = ""
    try:
        model = ((await request.json()) or {}).get("model", "") or ""
    except Exception:
        model = ""
    if model and _RUNNER_MODELS and model not in _RUNNER_MODELS:
        raise HTTPException(400, f"Model not allowed: {model!r}. Allowed: {_RUNNER_MODELS}")

    # Check feature toggles — block disabled phases
    project_id = _infer_project(jira_id)
    toggles = _load_project_toggles(project_id)
    toggle_map = {"stp": "stp_generation", "std": "std_generation"}
    toggle_key = toggle_map.get(phase)
    if toggle_key and not toggles.get(toggle_key, True):
        raise HTTPException(400, f"Phase '{phase}' is disabled for project '{project_id}' (toggle: {toggle_key}=false)")

    # This auto-approve existed because the dashboard flow once had no review
    # step, so a pending gate had no way to be unblocked from here. Both halves
    # of that premise are gone: the chained builders run real reviews
    # (/stp-builder and /std-builder auto-chain review + refine), and the
    # detail view renders an Approve/Reject card on awaiting_approval phases.
    # The human decision is therefore the DEFAULT now; set
    # QF_DASHBOARD_AUTOAPPROVE=on|true|1 to restore the old wave-through for
    # review-less demo flows. A spurious entry is ignored when the project
    # isn't gated. Approvals share the canonical path (_state_dir) the CLI
    # subprocess reads.
    _autoapprove_enabled = os.environ.get(
        "QF_DASHBOARD_AUTOAPPROVE", "").lower() in ("on", "true", "1")
    _autoapprove_gate = {"std": "stp_review", "codegen": "std_review"}.get(phase)
    if _autoapprove_gate and _autoapprove_enabled:
        _approvals = _read_approvals(jira_id)
        if _autoapprove_gate not in _approvals:
            _approvals[_autoapprove_gate] = {
                "status": "approved",
                "reviewer": "dashboard (auto)",
                "comment": "Auto-approved: dashboard run has no review step.",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            _write_approvals(jira_id, _approvals)

            # Keep pipeline_state consistent with the approval we just wrote —
            # previously the review phase stayed "pending" forever while
            # approvals.yaml said "approved", and the two files contradicted
            # each other about whether a review happened. "skipped" is the
            # honest status: the gate was waved through, no review ran.
            def _mark_gate_skipped(state):
                if not state:
                    state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
                gate_phase = state.setdefault("phases", {}).setdefault(_autoapprove_gate, {})
                # Never clobber a review that actually ran.
                if gate_phase.get("status") in (None, "", "pending"):
                    gate_phase["status"] = "skipped"
                    gate_phase["output"] = "Auto-approved by dashboard Run — no review was performed."
                state["updated"] = datetime.now(timezone.utc).isoformat()
                return state

            _atomic_yaml_update(_state_dir(jira_id) / "pipeline_state.yaml", _mark_gate_skipped)

    key = f"{jira_id}/{phase}"
    # Atomic check-and-set: check + registration in ONE lock acquisition, so two
    # concurrent clicks can't both pass the running-check and spawn two `claude`
    # subprocesses (the old code released the lock for a YAML write in between).
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("status") == "running":
            return {"status": "already_running", "phase": phase, "jira_id": jira_id}
        _running_tasks[key] = {"status": "running", "started": datetime.now(timezone.utc).isoformat()}

    # Mark as in_progress in state file immediately (atomic)
    state_file = _state_dir(jira_id) / "pipeline_state.yaml"

    def _mark_in_progress(state):
        if not state:
            state = {"jira_id": jira_id, "project": _infer_project(jira_id), "phases": {}}
        # Archive the outgoing terminal result (if any) here — this is the
        # moment it's about to be overwritten. Doing it in _mark_completed/
        # _mark_failed instead is too late: by the time the background thread
        # writes its result, THIS write has already replaced the prior
        # completed/failed entry with "in_progress", so it would never look
        # terminal to _record_phase_result.
        # started_ts pairs with the finished_ts written on completion, so
        # phase_durations can use a real measured elapsed time instead of
        # inferring one from artifact file mtimes.
        _record_phase_result(
            state.setdefault("phases", {}),
            phase,
            {"status": "in_progress", "started_ts": datetime.now(timezone.utc).isoformat()},
        )
        state["updated"] = datetime.now(timezone.utc).isoformat()
        return state

    try:
        _atomic_yaml_update(state_file, _mark_in_progress)
        thread = threading.Thread(target=_run_phase_background, args=(jira_id, phase, model), daemon=True)
        thread.start()
    except Exception:
        # Roll back the reservation so a transient failure here doesn't leave the
        # phase permanently "running" (which would block every future click).
        with _tasks_lock:
            _running_tasks.pop(key, None)
        raise

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
                 if v.get("status") in ("completed", "failed", "blocked")
                 and now - v.get("_finished", now) > _TASK_RESULT_TTL]
        for k in stale:
            _running_tasks.pop(k, None)
    if not task:
        return {"status": "idle", "phase": phase, "jira_id": jira_id}
    if task["status"] in ("completed", "blocked"):
        with _tasks_lock:
            _running_tasks.pop(key, None)
        return {"status": task["status"], **task.get("result", {})}
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

_LEGACY_ARTIFACT_SUBDIRS = ("stp", "std", "reviews", "go-tests", "python-tests")
# "state" is excluded — pipeline_state.yaml/pr_info.yaml are still read and
# written type-first (outputs/state/{id}/...) everywhere else in this file,
# so uploaded state files must land there too or nothing would ever read them.


def _canonicalize_upload_rel(rel: Path) -> Path:
    """Rewrite a legacy type-first relative path ({sub}/{id}/...) to canonical
    JIRA-first (outputs/{id}/{sub}/...) so uploaded artifacts land where every
    read path now looks."""
    parts = rel.parts
    if len(parts) >= 2 and parts[0] in _LEGACY_ARTIFACT_SUBDIRS:
        sub, jid, *rest = parts
        return Path(jid, sub, *rest)
    return rel


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
                            dest = OUTPUTS / _canonicalize_upload_rel(rel)
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

        dest = OUTPUTS / _canonicalize_upload_rel(Path(file_path))
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
    # Canonical JIRA-first layout — this ticket's artifacts may live here instead.
    canonical_dir = OUTPUTS / jira_id
    if canonical_dir.is_dir():
        shutil.rmtree(canonical_dir)
        deleted.append(jira_id)

    if not deleted:
        raise HTTPException(404, f"No outputs found for {jira_id}")

    return {"status": "ok", "jira_id": jira_id, "deleted": deleted}


# ---------------------------------------------------------------------------
# PR Push — push test files to the team's repo (GitHub) via API, open PR
# ---------------------------------------------------------------------------

# GITHUB_TOKEN is read last but must be read: it's the name the Helm chart's
# Secret writes, and the check-run/PR-comment helpers further down already
# accept it. Without it here, a chart-installed cluster reported "no token" for
# push-PR, close-PR, org scan and bulk onboard while other GitHub calls worked.
_GITHUB_TOKEN = (
    os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    or os.environ.get("QUALITYFLOW_GIT_TOKEN", "")
    or os.environ.get("GITHUB_TOKEN", "")
)
_GITLAB_TOKEN = os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN", "") or os.environ.get("QUALITYFLOW_GIT_TOKEN", "")


def _read_pr_info(jira_id: str) -> dict | None:
    """Read PR info from state file."""
    pr_file = _state_dir(jira_id) / "pr_info.yaml"
    if pr_file.exists():
        return _read_yaml(pr_file)
    return None


def _write_pr_info(jira_id: str, info: dict) -> None:
    """Write PR info to state file."""
    state_dir = _state_dir(jira_id)
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
        with urllib.request.urlopen(req, timeout=15) as resp:
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
    with urllib.request.urlopen(req, timeout=15) as resp:
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

    # Go test files → primary repo. Only the qf_ generated tests, skip caches.
    go_dir = _pick_dir(OUTPUTS / jira_id / "go-tests", OUTPUTS / "go-tests" / jira_id)
    if go_dir:
        for f in sorted(go_dir.glob("qf_*.go")):
            groups["primary"].append({
                "path": f"tests/qualityflow/{jira_id}/{f.name}",
                "content": f.read_text(errors="replace"),
                "source": str(f),
            })

    # Python test files → tier2 repo. Push qf_ tests + conftest.py (needed to run),
    # skip summary.yaml and __pycache__.
    py_dir = _pick_dir(OUTPUTS / jira_id / "python-tests", OUTPUTS / "python-tests" / jira_id)
    if py_dir:
        for f in sorted(py_dir.glob("*.py")):
            groups["tier2"].append({
                "path": f"tests/qualityflow/{jira_id}/{f.name}",
                "content": f.read_text(errors="replace"),
                "source": str(f),
            })

    # STP, STD, reviews → docs (pushed to primary repo under docs/)
    for subdir, label in [("stp", "stp"), ("std", "std"), ("reviews", "reviews")]:
        sub = _pick_dir(OUTPUTS / jira_id / subdir, OUTPUTS / subdir / jira_id)
        if sub:
            for f in sub.rglob("*"):
                if f.is_file() and not f.name.startswith(".") and "__pycache__" not in f.parts:
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

    # tier2 (Python) files go to a separate tier2 repo only when one is actually
    # configured and distinct from the primary. Otherwise fold them into the
    # primary push — previously they were silently DROPPED here for
    # Python-primary projects (no tier2_repo configured): collected, credited in
    # the metrics, and never committed anywhere.
    tier2_target = _get_target_repo(project_id, "tier2")
    tier2_pr_info = None
    tier2_separate = bool(
        file_groups["tier2"]
        and tier2_target.get("full_name")
        and tier2_target["full_name"] != owner_repo
    )
    if file_groups["tier2"] and not tier2_separate:
        logger.warning(
            "push_pr: no separate tier2 repo for project %s — folding %d tier2 file(s) into the primary push to %s",
            project_id, len(file_groups["tier2"]), owner_repo,
        )
        all_files = all_files + file_groups["tier2"]

    if not all_files and not file_groups["tier2"]:
        raise HTTPException(404, f"No output files found for {jira_id}")

    try:
        pr_result: dict = {}

        def _push_and_pr(upstream_repo: str, base_branch: str, files: list[dict], pr_title: str, pr_body: str) -> dict:
            """Push files to fork (or upstream if allowed) and create a PR."""
            # Resolve where to push — fork or upstream
            push_repo = _github_resolve_fork(upstream_repo, token)
            is_fork = push_repo != upstream_repo

            # Base off the repo we push to, so parent objects exist there.
            # A stale fork lacks upstream's latest objects, so create-ref would
            # 404 — sync it to upstream first (best-effort; no-op if current or
            # pushing straight to upstream).
            if is_fork:
                try:
                    _github_api("POST", f"https://api.github.com/repos/{push_repo}/merge-upstream", token, {"branch": base_branch})
                except RuntimeError:
                    pass
            base_info = _github_api("GET", f"https://api.github.com/repos/{push_repo}/git/ref/heads/{base_branch}", token)
            base_sha = base_info["object"]["sha"]
            commit_info = _github_api("GET", f"https://api.github.com/repos/{push_repo}/git/commits/{base_sha}", token)
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
                f"**Ticket:** [{jira_id}]({_jira_base_url(project_id)}/browse/{jira_id})\n"
                f"**Project:** {project_id}\n"
                f"**Files:** {len(all_files)}\n\n"
                f"### Test Files\n"
                + "\n".join(f"- `{f['path']}`" for f in all_files)
                + "\n\n---\n*Auto-generated by QualityFlow*"
            )
            pr_result = _push_and_pr(owner_repo, base_branch, all_files, title, pr_body)

        # --- Push tier2 files to tier2 repo (if separate) ---
        if tier2_separate:
            tier2_repo = tier2_target["full_name"]
            tier2_base = tier2_target.get("default_branch", "main")

            title = f"[QualityFlow] Tier 2 tests for {jira_id}"
            pr_body = (
                f"## QualityFlow Tier 2 Tests\n\n"
                f"**Ticket:** [{jira_id}]({_jira_base_url(project_id)}/browse/{jira_id})\n"
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

        actor = _resolve_actor(request, x_api_key)
        logger.info("audit action=push_pr jira_id=%s phase=- actor=%s result=created url=%s",
                    jira_id, actor, pr_info.get("url", ""))
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
    approvals_file = _state_dir(jira_id) / "approvals.yaml"
    if approvals_file.exists():
        return _read_yaml(approvals_file)
    return {}


def _write_approvals(jira_id: str, approvals: dict) -> None:
    """Write approval state to state file."""
    state_dir = _state_dir(jira_id)
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
    reviewer = body.get("reviewer") or _resolve_actor(request, x_api_key)
    comment = body.get("comment", "")

    if action not in ("approve", "reject"):
        raise HTTPException(400, f"Invalid action: {action}. Must be 'approve' or 'reject'")

    approvals = _read_approvals(jira_id)
    # Write under the CLI's canonical key (stp_review/std_review) — the one the
    # pipeline-state gate actually reads. Writing "stp"/"std" recorded a decision
    # the pipeline could not see.
    approval_key = _GATE_APPROVAL_KEY.get(phase, phase)
    approvals[approval_key] = {
        "status": "approved" if action == "approve" else "rejected",
        "reviewer": reviewer,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_approvals(jira_id, approvals)

    logger.info("audit action=approve_phase jira_id=%s phase=%s actor=%s result=%s",
                jira_id, phase, reviewer, approvals[approval_key]["status"])

    # Slack notification
    _slack_pipeline_event(jira_id, f"{phase.replace('_', ' ').title()} {action}ed",
                          f"Reviewer: {reviewer}" + (f" — {comment}" if comment else ""))

    return {"status": "ok", "phase": phase, "approval": approvals[approval_key]}


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
            # Explicit refresh is the cache-bypass path — push the fresh value
            # into the list-endpoint TTL cache so the two never disagree.
            _pr_state_cache[pr_info["url"]] = (new_state, time.time())
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

    actor = _resolve_actor(request, x_api_key)
    logger.info("audit action=%s_pr jira_id=%s phase=- actor=%s result=%s", action, jira_id, actor, new_state)
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
_JIRA_ERROR_TTL = 30  # negative cache — a down Jira must not be re-hit serially every poll
_JIRA_CACHE_MAX = 200  # max entries before eviction


def _jira_cache_put(jira_id: str, result: dict, now: float) -> None:
    """Insert with bounded-size eviction (oldest first)."""
    if len(_jira_cache) >= _JIRA_CACHE_MAX:
        oldest = sorted(_jira_cache, key=lambda k: _jira_cache[k][1])
        for k in oldest[:len(_jira_cache) - _JIRA_CACHE_MAX + 1]:
            del _jira_cache[k]
    _jira_cache[jira_id] = (result, now)


def _jira_configured() -> bool:
    return bool(_JIRA_URL and _JIRA_USERNAME and _JIRA_API_TOKEN)


def _jira_fetch(jira_id: str) -> dict:
    """Fetch ticket data from Jira REST API with caching."""
    now = time.time()
    cached = _jira_cache.get(jira_id)
    if cached:
        # Errors are cached too (PERF-05), just with a short TTL so recovery is quick.
        ttl = _JIRA_ERROR_TTL if "error" in cached[0] else _JIRA_CACHE_TTL
        if (now - cached[1]) < ttl:
            return cached[0]

    # Build Basic auth header
    creds = base64.b64encode(f"{_JIRA_USERNAME}:{_JIRA_API_TOKEN}".encode()).decode()
    fields = "summary,status,assignee,priority,issuetype,labels,components,created,updated,resolution"
    url = f"{_JIRA_URL.rstrip('/')}/rest/api/2/issue/{jira_id}?fields={fields}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {creds}",
        "Accept": "application/json",
    })

    # ponytail: verified by default (Basic-auth creds go over this connection);
    # QF_JIRA_INSECURE_TLS is the escape hatch for an internal Jira with a
    # self-signed cert — never disable verification unconditionally.
    ctx = ssl.create_default_context()
    if os.environ.get("QF_JIRA_INSECURE_TLS", "").lower() in ("1", "true", "yes"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            err = {"error": f"Ticket {jira_id} not found", "status_code": 404}
        else:
            err = {"error": f"Jira API error: {e.code}", "status_code": e.code}
        _jira_cache_put(jira_id, err, now)
        return err
    except Exception as e:
        err = {"error": f"Failed to connect to Jira: {e}"}
        _jira_cache_put(jira_id, err, now)
        return err

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

    _jira_cache_put(jira_id, result, now)
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

# Map phases to the output directories/files they produce (legacy-shaped
# patterns: "{sub}/{id}/...") — _phase_output_targets() also derives the
# canonical "{id}/{sub}/..." counterpart so reset clears both layouts.
_PHASE_OUTPUTS: dict[str, list[str]] = {
    "stp": ["stp/{id}/{id}_test_plan.md", "reviews/{id}/{id}_stp_review.md"],
    "std": ["std/{id}/", "reviews/{id}/{id}_std_review.md"],
    "codegen": ["go-tests/{id}/", "python-tests/{id}/"],
}


def _phase_output_targets(jira_id: str, pattern: str) -> list[Path]:
    """Canonical + legacy candidate paths for a _PHASE_OUTPUTS pattern."""
    legacy_rel = pattern.format(id=jira_id)
    legacy = OUTPUTS / legacy_rel
    parts = legacy_rel.split("/", 2)  # "{sub}/{id}/{rest}" — rest may be "" (dir patterns end in "/")
    if len(parts) < 2:
        return [legacy]
    sub, rest = parts[0], (parts[2] if len(parts) > 2 else "")
    canonical = OUTPUTS / jira_id / sub / rest if rest else OUTPUTS / jira_id / sub
    return [canonical, legacy]


_PREVIOUS_ROTATIONS_KEPT = 3


def _archive_to_previous(target: Path, ts: str) -> None:
    """Archive `target` into a timestamped .previous-{ts}/ dir before reset_pipeline
    deletes it, then prune to the 3 most recent rotations per parent dir.

    Replaces archiving straight into a single `.previous/` dir, which a second
    reset of the same phase silently destroyed (shutil.rmtree of the existing
    archive right before writing the new one) — so only the latest reset's
    "before" snapshot ever survived. See _latest_previous() for the reader side.
    """
    prev_dir = target.parent / f".previous-{ts}"
    prev_dir.mkdir(parents=True, exist_ok=True)
    target.rename(prev_dir / target.name)
    rotations = sorted(target.parent.glob(".previous-*"), reverse=True)
    for old in rotations[_PREVIOUS_ROTATIONS_KEPT:]:
        shutil.rmtree(old, ignore_errors=True)


def _latest_previous(target: Path) -> Path | None:
    """Most recently archived copy of `target`, across the legacy single
    `.previous/` dir (still written by the outputs-upload endpoint) and the
    rotated `.previous-{ts}/` dirs reset_pipeline now writes. None if neither
    has an archived copy. Shared by artifact_diff."""
    candidates = [p for p in (
        target.parent / ".previous" / target.name,
        *(d / target.name for d in target.parent.glob(".previous-*")),
    ) if p.exists()]
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


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
    reset_ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    for phase in phases_to_clear:
        for pattern in _PHASE_OUTPUTS.get(phase, []):
            for target in _phase_output_targets(jira_id, pattern):
                if target.exists():
                    _archive_to_previous(target, reset_ts)
                    cleared.append(str(target.relative_to(OUTPUTS)))

        # Clear approvals for this phase
        approvals = _read_approvals(jira_id)
        if phase in approvals:
            del approvals[phase]
            _write_approvals(jira_id, approvals)

    # Clear PR info if resetting from stp or earlier (full re-run)
    if start_idx <= 1:
        pr_file = _state_dir(jira_id) / "pr_info.yaml"
        if pr_file.exists():
            pr_file.unlink()
            cleared.append(f"state/{jira_id}/pr_info.yaml")

    actor = _resolve_actor(request, x_api_key)
    logger.info("audit action=reset_phase jira_id=%s phase=%s actor=%s phases_cleared=%s",
                jira_id, from_phase, actor, phases_to_clear)

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
    # Canonical JIRA-first layout — this ticket's artifacts may live here instead.
    canonical_dir = OUTPUTS / jira_id
    if canonical_dir.is_dir():
        shutil.rmtree(canonical_dir)
        deleted_dirs.append(jira_id)

    if not deleted_dirs:
        raise HTTPException(404, f"No outputs found for {jira_id}")

    actor = _resolve_actor(request, x_api_key)
    logger.info("audit action=delete_pipeline jira_id=%s phase=- actor=%s deleted=%s", jira_id, actor, deleted_dirs)
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

    if artifact_type not in _ARTIFACT_KINDS:
        raise HTTPException(400, f"Diff not supported for artifact type: {artifact_type}")

    current_file = _artifact_path(jira_id, artifact_type)
    prev_file = _latest_previous(current_file)

    if not current_file.exists():
        raise HTTPException(404, "Current artifact not found")
    if not prev_file:
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

    state_file = _state_dir(jira_id) / "pipeline_state.yaml"
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
# Traceability — requirements -> STP scenarios -> STD scenarios -> tests
# ---------------------------------------------------------------------------

# STP Section III "Requirements Mapping"/"Test Scenarios": a group bullet
# "- **[JIRA-KEY]** — <free text or comma-separated requirement refs>" —
# used both for the Requirements Mapping definitions and, in Test Scenarios,
# as the line directly above a TS-NN heading that carries that heading's
# requirement refs.
_STP_REQ_GROUP_RE = re.compile(r"^\s*-\s*\*\*\[([A-Za-z][A-Za-z0-9]*-\d+)\]\*\*\s*[—-]\s*(.+)$")
# Requirements Mapping definition bullet: "- **REQ-01:** description" or
# "- **REQ-{JIRA}-01:** description".
_STP_REQ_DEF_RE = re.compile(r"^\s*-\s*\*\*(REQ-[A-Za-z0-9-]+):\*\*\s*(.+)$")
# Test Scenarios heading: "  - **TS-01: Some title** [e2e, P1]".
_STP_TS_HEADING_RE = re.compile(r"^\s*-\s*\*\*TS-(\d+):\s*(.*?)\*\*\s*(?:\[([^\]]*)\])?\s*$")
# Requirement tokens inside a group bullet's free text: fine-grained
# REQ-{JIRA}-NN / legacy REQ-NN, or a bare Jira key.
_REQ_TOKEN_RE = re.compile(r"REQ-[A-Za-z0-9-]+|[A-Z][A-Z0-9]*-\d+")
_BARE_REQ_NN_RE = re.compile(r"^REQ-(\d+)$")


def _normalize_req_id(token: str, jira_id: str) -> str:
    """Legacy ticket-less 'REQ-01' -> 'REQ-{JIRA_ID}-01' for display. Already
    fully-qualified REQ-{JIRA}-NN ids and bare Jira keys pass through unchanged."""
    m = _BARE_REQ_NN_RE.match(token)
    return f"REQ-{jira_id}-{m.group(1)}" if m else token


def _parse_stp_requirements(text: str, jira_id: str) -> tuple[list[str], dict[str, dict]]:
    """Parse STP Section III into (req_defs, ts_map).

    req_defs: requirement ids declared in the Requirements Mapping subsection,
    in document order (deduplicated).
    ts_map: {"TS-01": {"requirements": [...], "title": str, "labels": [...]}}
    from the Test Scenarios subsection — each TS-NN heading's requirement refs
    come from the group bullet directly above it.

    Never raises — a document that doesn't match this shape just yields
    ([], {}), so a partial/legacy/malformed STP degrades gracefully instead
    of 500ing the endpoint.
    """
    req_defs: list[str] = []
    ts_map: dict[str, dict] = {}
    try:
        pending_reqs: list[str] = []
        for line in text.splitlines():
            m_group = _STP_REQ_GROUP_RE.match(line)
            if m_group:
                tokens = _REQ_TOKEN_RE.findall(m_group.group(2))
                pending_reqs = [_normalize_req_id(t, jira_id) for t in tokens]
                continue
            m_def = _STP_REQ_DEF_RE.match(line)
            if m_def:
                req_defs.append(_normalize_req_id(m_def.group(1), jira_id))
                continue
            m_ts = _STP_TS_HEADING_RE.match(line)
            if m_ts:
                labels = [s.strip() for s in (m_ts.group(3) or "").split(",") if s.strip()]
                ts_map[f"TS-{m_ts.group(1)}"] = {
                    "requirements": pending_reqs,
                    "title": m_ts.group(2).strip(),
                    "labels": labels,
                }
    except Exception:
        return [], {}

    seen: set[str] = set()
    ordered: list[str] = []
    for r in req_defs:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return ordered, ts_map


def _parse_std_scenarios(std_data: dict) -> list[dict]:
    """STD YAML `scenarios` -> a flat list of the fields traceability needs.
    Tolerant of missing/malformed fields — a broken scenario entry is skipped,
    not fatal to the rest of the document."""
    raw = std_data.get("scenarios") if isinstance(std_data, dict) else None
    out: list[dict] = []
    for sc in raw if isinstance(raw, list) else []:
        if not isinstance(sc, dict):
            continue
        objective = sc.get("test_objective") or {}
        title = (objective.get("title") if isinstance(objective, dict) else None) or sc.get("test_id") or ""
        req_ids = sc.get("requirement_ids")
        targets = sc.get("coverage_targets")
        out.append({
            "std_test_id": sc.get("test_id"),
            "title": title,
            "stp_scenario_id": sc.get("stp_scenario_id") or None,
            "requirement_ids": req_ids if isinstance(req_ids, list) and req_ids else None,
            "requirement_id": sc.get("requirement_id"),
            # Absent coverage_status means NEW — the backward-compatible default
            # documented in CLAUDE.md, applied here so consumers don't each guess.
            "coverage_status": sc.get("coverage_status") or "NEW",
            "priority": sc.get("priority"),
            "test_type": sc.get("test_type"),
            "coverage_targets": targets if isinstance(targets, list) and targets else None,
        })
    return out


# Python: @pytest.mark.qf_test_id("TS-...") decorator — a runtime-visible marker.
_PY_QF_MARK_RE = re.compile(r'@pytest\.mark\.qf_test_id\(\s*["\']([^"\']+)["\']\s*\)')
_PY_DEF_RE = re.compile(r"^(\s*)def\s+(test_\w+)\s*\(")
# Docstring/comment fallback tag, shared by Python docstrings and Go It()/comments:
# "[TS-...]" or "[test_id:TS-...]".
_BRACKET_TAG_RE = re.compile(r"\[(?:test_id:)?(TS-[A-Za-z0-9-]+)\]")
_GO_FUNC_RE = re.compile(r"func\s+(Test\w+)\s*\(")


def _scan_python_test_file(text: str, filename: str, result: dict[str, list[dict]]) -> None:
    """Map std_test_id -> [{function, file, marker}] for one Python test file.
    marker='id' when a @pytest.mark.qf_test_id(...) decorator sits directly
    above the def; else marker='docstring' when the function's own docstring
    carries a "[TS-...]" tag. A test with neither is simply not indexed."""
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        m = _PY_DEF_RE.match(lines[i])
        if not m:
            i += 1
            continue
        func = m.group(2)

        marker_id = None
        j = i - 1
        while j >= 0 and lines[j].strip().startswith("@"):
            dm = _PY_QF_MARK_RE.search(lines[j])
            if dm:
                marker_id = dm.group(1)
                break
            j -= 1
        if marker_id:
            result.setdefault(marker_id, []).append({"function": func, "file": filename, "marker": "id"})
            i += 1
            continue

        k = i + 1
        while k < n and not lines[k].strip():
            k += 1
        if k < n and ('"""' in lines[k] or "'''" in lines[k]):
            quote = '"""' if '"""' in lines[k] else "'''"
            doc_lines = [lines[k]]
            if lines[k].count(quote) < 2:
                m2 = k + 1
                while m2 < n and quote not in lines[m2]:
                    doc_lines.append(lines[m2])
                    m2 += 1
                if m2 < n:
                    doc_lines.append(lines[m2])
            tag = _BRACKET_TAG_RE.search("\n".join(doc_lines))
            if tag:
                result.setdefault(tag.group(1), []).append({"function": func, "file": filename, "marker": "docstring"})
        i += 1


def _scan_go_test_file(text: str, filename: str, result: dict[str, list[dict]]) -> None:
    """Map std_test_id -> [{function, file, marker}] for one Go test file, via
    the "[test_id:TS-...]" tag Go stubs embed in It()/PendingIt() descriptions
    or doc-comments near the func. Always marker='docstring' — Go has no
    runtime-visible marker equivalent to a pytest mark."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _GO_FUNC_RE.search(line)
        if not m:
            continue
        window = "\n".join(lines[i:i + 40])
        tag = _BRACKET_TAG_RE.search(window)
        if tag:
            result.setdefault(tag.group(1), []).append({"function": m.group(1), "file": filename, "marker": "docstring"})


def _match_tests_to_scenarios(jira_id: str) -> dict[str, list[dict]]:
    """std_test_id -> [{function, file, marker}], scanning every generated
    Python/Go test file for this ticket. Degrades to {} on any read failure —
    a scenario just gets tests: [] rather than a 500."""
    result: dict[str, list[dict]] = {}
    for lang, scanner in (("python", _scan_python_test_file), ("go", _scan_go_test_file)):
        for f in _find_test_files(jira_id, lang):
            try:
                scanner(f.read_text(errors="replace"), f.name, result)
            except Exception:
                continue
    return result


@app.get("/api/pipelines/{jira_id}/ci-runs")
def pipeline_ci_runs(jira_id: str):
    """Recorded CI test runs for one ticket (outputs/{id}/ci/test_runs.yaml,
    written by scripts/qf_record_ci.py). Newest last, capped at 50 by the
    writer. {"runs": []} when nothing is recorded yet — never 404s, so the
    dashboard can show the wire-up snippet instead."""
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")
    data = _read_yaml(OUTPUTS / jira_id / "ci" / "test_runs.yaml")
    runs = data.get("runs") if isinstance(data, dict) else None
    return {"runs": runs if isinstance(runs, list) else []}


@app.get("/api/pipelines/{jira_id}/traceability")
def pipeline_traceability(jira_id: str):
    """Requirements -> STP scenarios -> STD scenarios -> generated test
    functions, for the traceability chain the dashboard renders.

    Works on both new-format artifacts (STD scenarios carry stp_scenario_id +
    requirement_ids; tests carry @pytest.mark.qf_test_id) and legacy ones
    (STD scenarios are matched to their STP TS-NN scenario by position, and
    tests are matched by a "[TS-...]" docstring tag). Built from whatever
    artifacts exist for the ticket — never 500s on a partial pipeline.
    """
    if not re.match(r"^[A-Z]+-\d+$", jira_id):
        raise HTTPException(400, f"Invalid Jira ID format: {jira_id}")

    req_defs: list[str] = []
    ts_map: dict[str, dict] = {}
    stp_path = _artifact_path(jira_id, "stp")
    if stp_path.exists():
        try:
            req_defs, ts_map = _parse_stp_requirements(stp_path.read_text(errors="replace"), jira_id)
        except Exception:
            logger.exception("traceability: STP parse failed for %s", jira_id)
    ts_order = sorted(ts_map.keys(), key=lambda t: int(t.split("-")[1])) if ts_map else []

    std_scenarios: list[dict] = []
    std_path = _artifact_path(jira_id, "std")
    if std_path.exists():
        try:
            std_scenarios = _parse_std_scenarios(_read_yaml(std_path))
        except Exception:
            logger.exception("traceability: STD parse failed for %s", jira_id)

    try:
        tests_by_std_id = _match_tests_to_scenarios(jira_id)
    except Exception:
        logger.exception("traceability: test scan failed for %s", jira_id)
        tests_by_std_id = {}

    grouped: dict[str, list[dict]] = {rid: [] for rid in req_defs}
    unique_scenarios: dict[str, dict] = {}  # dedup key -> scenario dict, for summary stats
    orphaned: list[dict] = []  # scenarios that resolved to no requirement at all

    for idx, sc in enumerate(std_scenarios):
        explicit_stp_id = sc["stp_scenario_id"]
        # A scenario carrying an explicit stp_scenario_id + requirement id is an
        # authored link, not a positional guess ("inferred"). Accept the singular
        # requirement_id (some STDs emit it instead of the plural list) so that
        # drift alone doesn't downgrade a real id-link.
        explicit_req_ids = sc["requirement_ids"] or (
            [sc["requirement_id"]] if sc.get("requirement_id") else []
        )
        link = "id" if (explicit_stp_id and explicit_req_ids) else "inferred"

        stp_id = explicit_stp_id
        if not stp_id and idx < len(ts_order):
            stp_id = ts_order[idx]

        req_ids = explicit_req_ids
        if not req_ids and stp_id:
            req_ids = ts_map.get(stp_id, {}).get("requirements")
        if not req_ids:
            bare = sc.get("requirement_id")
            req_ids = [bare] if bare else []

        std_test_id = sc["std_test_id"]
        scenario_out = {
            "stp_id": stp_id,
            "std_test_id": std_test_id,
            "title": sc["title"],
            "link": link,
            "tests": tests_by_std_id.get(std_test_id, []) if std_test_id else [],
            "coverage_status": sc["coverage_status"],
            "priority": sc["priority"],
            "test_type": sc["test_type"],
            "coverage_targets": sc["coverage_targets"],
        }
        unique_scenarios[std_test_id or f"__idx{idx}"] = scenario_out

        # A scenario that resolves to no requirement is orphaned: it used to be
        # dropped silently here, which made an unlinked scenario look identical
        # to one that was never written.
        if not req_ids:
            orphaned.append(scenario_out)
        for rid in req_ids:
            grouped.setdefault(rid, []).append(scenario_out)

    requirements = [{"id": rid, "scenarios": grouped[rid]} for rid in req_defs]
    requirements += [{"id": rid, "scenarios": scs} for rid, scs in grouped.items() if rid not in req_defs]

    coverage_status_counts: dict[str, int] = {}
    for s in unique_scenarios.values():
        status = s["coverage_status"]
        coverage_status_counts[status] = coverage_status_counts.get(status, 0) + 1

    summary = {
        "requirements_total": len(requirements),
        "scenarios_total": len(unique_scenarios),
        "scenarios_with_tests": sum(1 for s in unique_scenarios.values() if s["tests"]),
        "requirements_with_tests": sum(1 for r in requirements if any(s["tests"] for s in r["scenarios"])),
        "scenarios_orphaned": len(orphaned),
        "coverage_status": coverage_status_counts,
    }

    return {"jira_id": jira_id, "requirements": requirements,
            "orphaned_scenarios": orphaned, "summary": summary}


# ---------------------------------------------------------------------------
# API: Agentic operations
# ---------------------------------------------------------------------------

# The autonomy ladder the review architecture is aimed at. Each level is a
# claim about what the agent is allowed to DO, not how good it is.
_AUTONOMY_LADDER = [
    {"id": "L0", "name": "Observe",
     "detail": "Agent runs and records. Nothing it produces reaches a human by default."},
    {"id": "L1", "name": "Suggest",
     "detail": "Agent posts findings where a human has to go looking for them."},
    {"id": "L2", "name": "Review",
     "detail": "Agent comments on PRs unprompted. Humans still approve every gate."},
    {"id": "L3", "name": "Gate",
     "detail": "Agent's verdict blocks a merge. Humans intervene by exception."},
]

_TIER_SCRIPT = ROOT / ".github" / "review" / "tier.sh"
_REVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "ai-review.yml"
_EVAL_CONFIG = ROOT / "eval" / "eval.yaml"


def _read_risk_policy() -> dict:
    """The review tiering policy, read from tier.sh rather than duplicated here.

    tier.sh is the only definition of these thresholds; restating them in Python
    would let the two drift silently. Parse failure degrades to
    available: false instead of reporting invented numbers."""
    policy: dict = {"available": False, "source": ".github/review/tier.sh"}
    try:
        text = _TIER_SCRIPT.read_text(errors="replace")
    except OSError:
        policy["unavailable_reason"] = "tier.sh not found in this checkout"
        return policy
    dirs = re.search(r"FULL_TIER_DIR_RE='\^\(([^)]+)\)/'", text)
    lines = re.search(r"^LINE_THRESHOLD=(\d+)", text, re.M)
    doc_lines = re.search(r"^DOC_SKIP_LINE_THRESHOLD=(\d+)", text, re.M)
    if not (dirs and lines and doc_lines):
        policy["unavailable_reason"] = "tier.sh thresholds could not be parsed"
        return policy
    policy.update({
        "available": True,
        "full_tier_dirs": dirs.group(1).split("|"),
        "line_threshold": int(lines.group(1)),
        "doc_skip_line_threshold": int(doc_lines.group(1)),
        "tiers": [
            {"id": "skip", "detail": "Doc-only diff under the size cap. No model call."},
            {"id": "lite", "detail": "Single-pass review."},
            {"id": "full", "detail": "Two-pass find-then-verify review."},
        ],
        # tier.sh classifies inside a CI run and prints one word. Nothing
        # persists that choice, so there is no distribution to chart yet.
        "distribution": None,
        "distribution_reason": "tier.sh classifies per CI run; no run history is persisted",
    })
    return policy


def _read_eval_suite() -> dict:
    """Inventory of the adversarial eval suite. Case count and thresholds are
    real; scores stay unavailable until something persists a run's results."""
    suite: dict = {"available": False, "source": "eval/eval.yaml"}
    cases_dir = ROOT / "eval" / "dataset" / "cases"
    if cases_dir.is_dir():
        suite["cases"] = sorted(p.name for p in cases_dir.iterdir() if p.is_dir())
        suite["case_count"] = len(suite["cases"])
    try:
        cfg = _read_yaml(_EVAL_CONFIG)
    except Exception:
        cfg = {}
    thresholds = cfg.get("thresholds") if isinstance(cfg, dict) else None
    if isinstance(thresholds, dict):
        suite["thresholds"] = thresholds
        suite["available"] = True
    # No eval runner writes results anywhere this server can read.
    suite["latest_score"] = None
    suite["score_reason"] = "eval-smoke runs in CI; no scored run is persisted for the dashboard to read"
    return suite


@app.get("/api/agentic")
def agentic_status():
    """What the pipeline is actually allowed to do on its own, and the evidence
    for moving that line.

    Everything here is derived from config and recorded approvals. Sections with
    no emitter report available: false and say why, rather than shipping a
    plausible-looking number — an autonomy dashboard that guesses is worse than
    one that admits the gap."""
    gates = list(_DEFAULT_GATES)

    # Autonomy level is a claim about behaviour, so derive it from behaviour:
    # the review workflow posts comments (L2) but no config here gates a merge.
    review_posts = _REVIEW_WORKFLOW.exists()
    level = "L2" if review_posts else "L1"

    human_approved = auto_approved = human_rejected = 0
    recent: list[dict] = []
    for jid in _scan_jira_ids():
        for gate, entry in (_read_approvals(jid) or {}).items():
            if not isinstance(entry, dict):
                continue
            reviewer = entry.get("reviewer") or ""
            status = entry.get("status")
            is_auto = reviewer == "dashboard (auto)"
            if status == "rejected":
                human_rejected += 1
            elif is_auto:
                auto_approved += 1
            elif status == "approved":
                human_approved += 1
            recent.append({
                "jira_id": jid, "gate": gate, "status": status,
                "reviewer": reviewer, "comment": entry.get("comment") or "",
                "timestamp": entry.get("timestamp"), "auto": is_auto,
            })
    recent.sort(key=lambda r: r["timestamp"] or "", reverse=True)

    decided = human_approved + auto_approved + human_rejected
    return {
        "autonomy": {
            "level": level,
            "ladder": _AUTONOMY_LADDER,
            "gates": gates,
            "blocking_merges": False,
            "basis": ("AI review posts on pull requests but no configured gate blocks a merge; "
                      f"{len(gates)} approval gate(s) still require a decision"),
        },
        "review_activity": {
            "human_approved": human_approved,
            "auto_approved": auto_approved,
            "human_rejected": human_rejected,
            "decided": decided,
            # The share of gate decisions a human actually made. This is the
            # honest read on how supervised the pipeline currently is.
            "human_share_pct": round(100 * (human_approved + human_rejected) / decided) if decided else None,
            "recent": recent[:20],
        },
        "risk_policy": _read_risk_policy(),
        "evals": _read_eval_suite(),
        "findings": {
            "available": False,
            "reason": ("review findings are written as prose in the review markdown, "
                       "not as structured severity counts the dashboard can aggregate"),
        },
    }


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
    jira_url = f"{_jira_base_url(project_id)}/browse/{jira_id}"
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


def _product_coverage_dir(project_id: str) -> Path:
    """Storage dir for a project's product-coverage data.

    Exists so project_id is sanitized in one place: the five call sites that
    built this path inline all sanitized the *component* segment next to it and
    left project_id raw.
    """
    return COVERAGE_DIR / "_product" / _safe_path_segment(project_id)


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
    # Sanitize org/repo to prevent path traversal. The previous inline
    # re.sub let a bare '..' segment through unchanged.
    return COVERAGE_DIR / _safe_path_segment(org) / _safe_path_segment(repo)


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


_CODECOV_API_TOKEN = os.environ.get("CODECOV_API_TOKEN", "")
_codecov_cache: dict[str, tuple[float, dict | None]] = {}
_CODECOV_CACHE_TTL = 300  # seconds — coverage on Codecov changes at most per-CI-run


def _normalize_codecov(data: dict) -> dict | None:
    """Map a Codecov API v2 repo payload to our normalized coverage summary."""
    totals = data.get("totals") or {}
    cov = totals.get("coverage")
    if cov is None:
        return None
    return {
        "totals": {
            "coverage": round(float(cov), 2),
            "files": int(totals.get("files") or 0),
            "lines": int(totals.get("lines") or 0),
            "hits": int(totals.get("hits") or 0),
            "misses": int(totals.get("misses") or 0),
        },
        "commit": None,          # repo-detail endpoint doesn't carry a SHA
        "branch": data.get("branch"),
        "timestamp": data.get("updatestamp"),
        "_source": "codecov",
    }


def _fetch_codecov_coverage(service: str, org: str, repo: str) -> dict | None:
    """Fetch latest coverage from Codecov for repos onboarded there (cached, best-effort).

    Public repos work token-free (rate-limited); private repos need CODECOV_API_TOKEN.
    Returns None when the repo isn't on Codecov or the API is unreachable.
    """
    key = f"{service}/{org}/{repo}"
    cached = _codecov_cache.get(key)
    if cached and (time.time() - cached[0]) < _CODECOV_CACHE_TTL:
        return cached[1]

    import urllib.request
    svc = {"github": "github", "gitlab": "gitlab", "bitbucket": "bitbucket"}.get(service, "github")
    url = f"https://api.codecov.io/api/v2/{svc}/{org}/repos/{repo}/"
    headers = {"Accept": "application/json"}
    if _CODECOV_API_TOKEN:
        headers["Authorization"] = f"Bearer {_CODECOV_API_TOKEN}"
    result: dict | None = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = _normalize_codecov(json.loads(resp.read().decode()))
    except Exception as e:
        logger.info("Codecov fetch failed for %s: %s", key, e)
    _codecov_cache[key] = (time.time(), result)
    return result


# SonarCloud is where teams onboarded to CoverPort land their processed
# coverage: the coverport coverage-processor pipeline uploads via sonar-scanner
# (coverage-processor/tekton/tasks/coverage-task.yaml). We read it back with the
# same shape as the Codecov fallback so onboarded teams need no extra step.
_SONAR_HOST = os.environ.get("SONAR_HOST_URL", "https://sonarcloud.io").rstrip("/")
_SONAR_TOKEN = os.environ.get("SONAR_TOKEN", "") or os.environ.get("SONARCLOUD_TOKEN", "")
_sonar_cache: dict[str, tuple[float, dict | None]] = {}
_SONAR_CACHE_TTL = 300  # seconds — matches _CODECOV_CACHE_TTL rationale


def _resolve_sonar_project_key(org: str, repo: str) -> str:
    """Sonar projectKey for a repo: per-repo override in coverage.yaml, else org_repo.

    Teams set sonar.projectKey in their sonar-project.properties (see the
    coverport coverage-task); the conventional value is "{org}_{repo}". Allow
    a `sonar_project_key` override in the coverage repos config for the rest.
    """
    for r in _get_coverage_repos_config():
        if r.get("org") == org and r.get("repo") == repo and r.get("sonar_project_key"):
            return str(r["sonar_project_key"])
    return f"{org}_{repo}"


def _normalize_sonar(data: dict) -> dict | None:
    """Map a SonarCloud/SonarQube measures/component payload to our summary."""
    measures = {m["metric"]: m.get("value") for m in data.get("component", {}).get("measures", [])}
    cov = measures.get("coverage")
    if cov is None:
        return None
    to_cover = int(float(measures.get("lines_to_cover") or 0))
    uncovered = int(float(measures.get("uncovered_lines") or 0))
    return {
        "totals": {
            "coverage": round(float(cov), 2),
            "files": 0,  # not in the component summary; tree endpoint would need component_tree
            "lines": to_cover,
            "hits": max(to_cover - uncovered, 0),
            "misses": uncovered,
        },
        "commit": None,
        "branch": None,
        "timestamp": None,
        "_source": "sonarcloud",
    }


def _fetch_sonarcloud_coverage(service: str, org: str, repo: str) -> dict | None:
    """Fetch latest coverage from SonarCloud for CoverPort-onboarded repos (cached, best-effort).

    Public projects work token-free; private ones need SONAR_TOKEN. Returns None
    when the project isn't on Sonar or the API is unreachable.
    """
    project_key = _resolve_sonar_project_key(org, repo)
    cached = _sonar_cache.get(project_key)
    if cached and (time.time() - cached[0]) < _SONAR_CACHE_TTL:
        return cached[1]

    import urllib.request
    import urllib.parse
    metrics = "coverage,lines_to_cover,uncovered_lines,ncloc"
    url = (f"{_SONAR_HOST}/api/measures/component"
           f"?component={urllib.parse.quote(project_key)}&metricKeys={metrics}")
    headers = {"Accept": "application/json"}
    if _SONAR_TOKEN:
        headers["Authorization"] = f"Bearer {_SONAR_TOKEN}"
    result: dict | None = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = _normalize_sonar(json.loads(resp.read().decode()))
    except Exception as e:
        logger.info("SonarCloud fetch failed for %s: %s", project_key, e)
    _sonar_cache[project_key] = (time.time(), result)
    return result


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
                raw_path = _product_coverage_dir(project_id) / safe_comp / "raw_response.json"
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
    out_dir = _product_coverage_dir(project_id) / safe_comp
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
        raw_path = _product_coverage_dir(project_id) / safe_comp / "raw_response.json"
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
    prod_dir = _product_coverage_dir(project_id)
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
    comp_dir = _product_coverage_dir(project_id) / safe_comp
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
    return _TEST_COVERAGE_DIR / _safe_path_segment(project_id)


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
    # commit_sha reaches here from a GitHub merge-base response rather than
    # straight off a request, but it still lands in a path — sanitize before
    # joining rather than trusting the upstream's shape.
    exact = by_commit_dir / f"{_safe_path_segment(commit_sha)}.yaml"
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
        # `commit` lands in a path. The upload side already requires a strict
        # SHA, so anything else can only be a typo or a traversal attempt —
        # reject rather than sanitize, so the two ends agree on what a commit is.
        if not _COMMIT_SHA_RE.match(commit):
            raise HTTPException(400, "Invalid commit SHA")
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
        # Same trust boundary as /files above — and this one streams the file
        # body back, so an unvalidated segment here is an arbitrary-file read.
        if not _COMMIT_SHA_RE.match(commit):
            raise HTTPException(400, "Invalid commit SHA")
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
    sonar = _fetch_sonarcloud_coverage(service, org, repo)
    if sonar:
        return sonar
    codecov = _fetch_codecov_coverage(service, org, repo)
    if codecov:
        return codecov
    raise HTTPException(404, f"No coverage data for {org}/{repo}. Upload via POST /api/coverage/upload, or onboard the repo to CoverPort (SonarCloud) or Codecov")


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


@app.get("/vendor/{path:path}")
def serve_vendor(path: str):
    """Serve vendored frontend assets (Tailwind CSS, fonts) baked into the image."""
    base = (ROOT / "ui" / "vendor").resolve()
    target = (base / path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(404, "Not found")
    if not target.is_file():
        raise HTTPException(404, "Not found")
    ctype = {".css": "text/css", ".woff2": "font/woff2", ".woff": "font/woff",
             ".js": "text/javascript", ".svg": "image/svg+xml"}.get(target.suffix, "application/octet-stream")
    return FileResponse(str(target), media_type=ctype)


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
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8420")), help="Port (default: 8420, env PORT)")
    parser.add_argument("--host", default=os.environ.get("QF_HOST", "0.0.0.0"), help="Host (default: 0.0.0.0, env QF_HOST)")
    # ponytail: --no-browser is now a no-op (container runtime has no browser to open); kept so existing launch commands don't break
    parser.add_argument("--no-browser", action="store_true", help="No-op (kept for compatibility)")
    args = parser.parse_args()

    uvicorn.run(
        app, host=args.host, port=args.port, log_level="info",
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("QF_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
