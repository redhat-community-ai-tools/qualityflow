# QualityFlow dashboard — OpenShift-friendly image (UBI9, arbitrary non-root UID).
#
# NOTE: on-cluster coverage-collection Jobs (Go/pip toolchains) are a SEPARATE
# image — out of scope here. This image only runs `ui.py` (the dashboard).
# Pinned by digest, not by a floating tag: a rebuild on an unrelated trigger
# (e.g. re-running publish-image.yml) must not silently pick up a new base
# OS/Python layer. The tag is kept alongside the digest for readability only
# — the digest is what resolves. Refresh both together, deliberately:
#   podman pull registry.access.redhat.com/ubi9/python-311:latest
#   podman inspect --format '{{index .RepoDigests 0}}' \
#     registry.access.redhat.com/ubi9/python-311:latest
FROM registry.access.redhat.com/ubi9/python-311:9.8-1779945715@sha256:a0bdb55576fc5b8d6704279307817828ef027e1065533ceba133fe9516003a6c

WORKDIR /app

# git is needed by gitpython, the git-sync loop, and coverage tooling. nodejs
# is only for the `claude`, `codex` and supporting CLI tools the in-cluster
# runner shells out to (QF_RUNNER=cli) — npm's global install needs it.
# curl/tar (for the Cursor
# CLI below) already ship in the base image (curl-minimal, tar) — installing
# the full `curl` package conflicts with curl-minimal, so don't add it.
# The ubi9/python image runs as UID 1001 by default; switch to root just for
# the package install, then drop back to a non-root user below.
USER 0
RUN dnf install -y git nodejs && dnf clean all

# mcp-atlassian is launched by Claude, Cursor, and Codex through uvx. Pin uv
# so the MCP launcher is present and image rebuilds do not silently change it.
ARG UV_VERSION=0.12.13
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

# The pinned version here is the one this image has actually been built and
# tested against — bump deliberately, not on every rebuild.
ARG CLAUDE_CODE_VERSION=2.1.270
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"

# Codex CLI, pinned so an image rebuild cannot silently change the agent
# runtime. The explicit platform package avoids npm optional-dependency
# resolution issues on Linux builders while retaining arm64 support.
ARG CODEX_CLI_VERSION=0.143.0
RUN case "$(uname -m)" in \
      x86_64|amd64) CODEX_PLATFORM=linux-x64 ;; \
      aarch64|arm64) CODEX_PLATFORM=linux-arm64 ;; \
      *) echo "unsupported arch for codex: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    npm install -g "@openai/codex@${CODEX_CLI_VERSION}" \
      "@openai/codex-${CODEX_PLATFORM}@npm:@openai/codex@${CODEX_CLI_VERSION}-${CODEX_PLATFORM}"

# Cursor CLI (`agent`, dual-runtime companion to `claude` above). The
# installer at cursor.com/install writes to $HOME/.local/{bin,share}, which
# is fine for a real user but a trap under OpenShift: the runtime UID is
# arbitrary and unrelated to the UID that built this image, so a HOME-relative
# install is invisible to it. We skip the installer script and pull the same
# versioned tarball it would (its own DOWNLOAD_URL, https://downloads.cursor.com
# /lab/<version>/<os>/<arch>/agent-cli-package.tar.gz) straight into a fixed,
# root-owned path on PATH — same reasoning as npm's global install above,
# which already lands claude on PATH for any UID without extra chgrp.
# ponytail: cursor.com/install has no version-pin knob — the script text
# itself is server-rendered per request with "today's latest" version baked
# into its own download URL, so `curl .../install | bash` is unpinnable by
# construction. Downloading the versioned tarball directly (below) *is* the
# pin — mirrors the Claude CLI's pinned npm version above. Ceiling: if Cursor
# ever prunes old versions from downloads.cursor.com, this URL 404s and
# CURSOR_AGENT_VERSION must be bumped by hand; there is no floating fallback.
ARG CURSOR_AGENT_VERSION=2026.09.02-c22c1a3
RUN case "$(uname -m)" in \
      x86_64|amd64) CURSOR_ARCH=x64 ;; \
      aarch64|arm64) CURSOR_ARCH=arm64 ;; \
      *) echo "unsupported arch for cursor-agent: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    mkdir -p "/usr/local/share/cursor-agent/versions/${CURSOR_AGENT_VERSION}" && \
    curl -fsSL "https://downloads.cursor.com/lab/${CURSOR_AGENT_VERSION}/linux/${CURSOR_ARCH}/agent-cli-package.tar.gz" \
      | tar --strip-components=1 -xzf - -C "/usr/local/share/cursor-agent/versions/${CURSOR_AGENT_VERSION}" && \
    ln -s "/usr/local/share/cursor-agent/versions/${CURSOR_AGENT_VERSION}/cursor-agent" /usr/local/bin/agent && \
    ln -s "/usr/local/share/cursor-agent/versions/${CURSOR_AGENT_VERSION}/cursor-agent" /usr/local/bin/cursor-agent

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baked-in code + default config + resources. Every top-level module ui.py
# imports must be listed here — qf_metrics.py was missing for months and
# /api/metrics/engineering 500'd in-cluster while passing every local test.
COPY ui.py qf_metrics.py review_cycle.py pipeline_runner.py deploy.py .
COPY ui/ ui/
COPY agents/ agents/
COPY skills/ skills/
COPY commands/ commands/
COPY config/ config/
COPY .claude-plugin/ .claude-plugin/
COPY .codex/ .codex/

# QF_RUNNER=cli shells out to `claude -p /<command>` and Cursor's
# `agent -p /<command>`; Codex reads the same raw command/agent/skill contract
# through its project-scoped `.codex/config.toml`. Claude/Cursor only recognize
# their slash commands once deployed into .claude/ / .cursor/ — COPYing the raw
# agents/commands/skills/ dirs above is not enough on its own (same reason
# ONBOARDING.md tells a laptop install to run this, not just clone the repo).
# --target both deploys both trees from the one existing copier (deploy.py) —
# no second copier needed.
RUN python3 deploy.py --target both --scope project --project-path /app

# Project-scoped MCP config (unlike the user-scope ~/.claude/.mcp.json the
# README documents for a laptop install, this sits beside .claude/ so it
# works under OpenShift's arbitrary, home-less runtime UID). ${VAR}
# placeholders resolve from the `claude` subprocess's own env — pipeline_runner
# overlays each run's caller-supplied Jira/GitHub identity there (see
# pipeline_runner._env_for). On a shared (API key or SSO) server the pod's own
# JIRA_*/GITHUB_PERSONAL_ACCESS_TOKEN are stripped from every dashboard run —
# never a fallback.
RUN printf '%s\n' \
    '{' \
    '  "mcpServers": {' \
    '    "mcp-atlassian": {' \
    '      "command": "uvx",' \
    '      "args": ["mcp-atlassian"],' \
    '      "env": {' \
    '        "JIRA_URL": "${JIRA_URL}",' \
    '        "JIRA_USERNAME": "${JIRA_USERNAME}",' \
    '        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"' \
    '      }' \
    '    },' \
    '    "github": {' \
    '      "command": "npx",' \
    '      "args": ["-y", "@modelcontextprotocol/server-github"],' \
    '      "env": {' \
    '        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"' \
    '      }' \
    '    }' \
    '  }' \
    '}' > /app/.mcp.json

# Same file, same ${VAR} placeholders, for the Cursor CLI (fact C-4: measured
# in audit-runs/RUN-2026-09-08-dual-runtime/A-02 — Cursor's `agent` expands
# ${VAR} inside an mcp.json env block from the process environment, same as
# Claude Code, so no format translation is needed here). A straight copy
# instead of a second printf keeps the two files provably identical.
RUN mkdir -p /app/.cursor && cp /app/.mcp.json /app/.cursor/mcp.json

RUN mkdir -p /app/outputs /data/config

# Bake the build commit so qf_build_info{commit=...} is meaningful in-cluster
# (there is no .git in the image, so ui.py's git lookup falls back to this).
ARG QF_COMMIT=unknown
ENV QF_COMMIT=${QF_COMMIT}

# Arbitrary-UID support: OpenShift's restricted-v2 SCC runs the container as a
# random, unpredictable UID that is always a member of group 0 (root group).
# The image can't know that UID in advance, so instead of owning files by UID
# we make them group-writable by group 0 and rely on every possible runtime
# UID sharing that group.
RUN chgrp -R 0 /app /data && chmod -R g=u /app /data

# Non-root default for `podman run`/local use; OpenShift overrides this with
# its assigned random UID (still in group 0, so the chmod above still applies).
USER 1001

ENV PORT=8420 \
    QF_HOST=0.0.0.0 \
    QF_OUTPUTS_DIR=/app/outputs \
    QF_CONFIG_DIR=/data/config \
    PYTHONUNBUFFERED=1

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8420\")}/healthz', timeout=3)" || exit 1

CMD ["python", "ui.py"]
