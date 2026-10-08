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

# LSP (lsp_analysis, on by default). Claude Code's LSP tool needs two things:
# a code-intelligence plugin (gopls-lsp / pyright-lsp from the official
# marketplace, enabled in /app/.claude/settings.json by deploy.py below) and
# the language server binary on PATH. Without them every run silently fell
# back to grep. pyright-langserver ships in the pyright npm package. gopls
# loads packages through `go list`, so it needs the Go toolchain at runtime
# too — that is most of the growth: ~+300 MB (Go ~230 MB, gopls ~35 MB,
# pyright ~35 MB, plugin seed <10 MB).
ARG PYRIGHT_VERSION=1.1.414
RUN npm install -g "pyright@${PYRIGHT_VERSION}"
# GOPROXY/GOTOOLCHAIN set explicitly: RHEL's go.env may default to direct
# fetches, and auto lets a gopls newer than dnf's Go still build. GOPATH and
# GOCACHE are build-only scratch, removed in the same layer.
ARG GOPLS_VERSION=v0.20.0
RUN dnf install -y golang && dnf clean all && \
    GOPROXY=https://proxy.golang.org,direct GOTOOLCHAIN=auto \
    GOBIN=/usr/local/bin GOPATH=/tmp/gopath GOCACHE=/tmp/gocache \
      go install "golang.org/x/tools/gopls@${GOPLS_VERSION}" && \
    rm -rf /tmp/gopath /tmp/gocache
# More languages, the ones Red Hat teams most often test (official Claude Code
# plugins below; the same servers back the bridge). Go and Python are always
# in; LSP_EXTRA_LANGUAGES picks the rest, so a team builds only what its repos
# use. Measured installed size: typescript ~26 MB, java ~263 MB (JDK 21 +
# jdtls), c ~231 MB (clangd + LLVM), rust ~332 MB (toolchain + std source +
# rust-analyzer). Ruby/PHP/C#/Kotlin/Swift/Lua have plugins too; add them here
# when a team needs one.
ARG LSP_EXTRA_LANGUAGES="typescript java c rust"
ARG TYPESCRIPT_LANGUAGE_SERVER_VERSION=6.0.1
ARG TYPESCRIPT_VERSION=5.9.3
RUN case " ${LSP_EXTRA_LANGUAGES} " in *" typescript "*) \
      npm install -g "typescript-language-server@${TYPESCRIPT_LANGUAGE_SERVER_VERSION}" \
        "typescript@${TYPESCRIPT_VERSION}" ;; esac
# rust-src: rust-analyzer needs the standard library's source to resolve std types.
RUN pkgs=""; \
    case " ${LSP_EXTRA_LANGUAGES} " in *" c "*) pkgs="$pkgs clang-tools-extra" ;; esac; \
    case " ${LSP_EXTRA_LANGUAGES} " in *" java "*) pkgs="$pkgs java-21-openjdk-headless" ;; esac; \
    case " ${LSP_EXTRA_LANGUAGES} " in *" rust "*) pkgs="$pkgs cargo rust-src" ;; esac; \
    if [ -n "$pkgs" ]; then dnf install -y $pkgs && dnf clean all; fi
# 1.50.0, not newer: 1.55+ answers initialize with an LSP 3.18 capability
# (textDocumentContent) that mcp-language-server v0.1.1 cannot parse, so Codex
# runs got no Java LSP (verified in this image). Bump both together.
ARG JDTLS_VERSION=1.50.0
ARG JDTLS_BUILD=202509041425
ARG JDTLS_SHA256=3292c5c33888f95ab0ff718e777ee94ff5496b8635a23a8844b876ee090ebdea
# config_*: Eclipse writes its configuration area there; group 0 + g+w lets
# OpenShift's arbitrary UID (always in group 0) write it.
RUN case " ${LSP_EXTRA_LANGUAGES} " in *" java "*) ;; *) exit 0 ;; esac; \
    curl -fsSL -o /tmp/jdtls.tar.gz \
      "https://download.eclipse.org/jdtls/milestones/${JDTLS_VERSION}/jdt-language-server-${JDTLS_VERSION}-${JDTLS_BUILD}.tar.gz" && \
    echo "${JDTLS_SHA256}  /tmp/jdtls.tar.gz" | sha256sum -c - && \
    mkdir -p /opt/jdtls && tar --no-same-owner -xzf /tmp/jdtls.tar.gz -C /opt/jdtls && rm /tmp/jdtls.tar.gz && \
    chmod -R a+rX /opt/jdtls && chgrp -R 0 /opt/jdtls/config_* && chmod -R g+w /opt/jdtls/config_* && \
    ln -s /opt/jdtls/bin/jdtls /usr/local/bin/jdtls
ARG RUST_ANALYZER_VERSION=2026-10-05
ARG RUST_ANALYZER_SHA256_X86_64=28070188df63b6f217768040781decc8db43bc9d29b126847acb365575b09bc9
ARG RUST_ANALYZER_SHA256_AARCH64=3974c863acbbd96ef2cc02a7aaa79123935b05f27ffe4fd393fc229522f75cb9
RUN case " ${LSP_EXTRA_LANGUAGES} " in *" rust "*) ;; *) exit 0 ;; esac; \
    case "$(uname -m)" in \
      x86_64|amd64) RA_ARCH=x86_64; RA_SHA256="${RUST_ANALYZER_SHA256_X86_64}" ;; \
      aarch64|arm64) RA_ARCH=aarch64; RA_SHA256="${RUST_ANALYZER_SHA256_AARCH64}" ;; \
      *) echo "unsupported arch for rust-analyzer: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/ra.gz \
      "https://github.com/rust-lang/rust-analyzer/releases/download/${RUST_ANALYZER_VERSION}/rust-analyzer-${RA_ARCH}-unknown-linux-gnu.gz" && \
    echo "${RA_SHA256}  /tmp/ra.gz" | sha256sum -c - && \
    gunzip -c /tmp/ra.gz > /usr/local/bin/rust-analyzer && rm /tmp/ra.gz && \
    chmod 0755 /usr/local/bin/rust-analyzer && rust-analyzer --version
# Codex has no LSP tool: mcp-language-server puts the servers above behind MCP
# tools (definition, references, hover, diagnostics). pipeline_runner starts
# one per checked-out repo for Codex STP and codegen runs.
# Built from the tag with deploy/mcp-language-server.patch, which fixes two
# hangs seen on cnv2 (2026-10-08): the bridge opened every workspace file, so
# pyright type-checked all of openshift-virtualization-tests before answering
# anything (3 of 4 calls never returned) and gopls held ~1 GB more on kubevirt;
# and when its language server died (an OOM kill) it kept the MCP call open
# until the client's timeout, 5 minutes per call. Pre-opening is now opt-in
# (MCP_LSP_PRELOAD=1, which pipeline_runner sets for typescript-language-server
# only) and the bridge exits with its server.
ARG MCP_LANGUAGE_SERVER_VERSION=v0.1.1
COPY deploy/mcp-language-server.patch /tmp/mls.patch
RUN git clone -q --depth 1 --branch "${MCP_LANGUAGE_SERVER_VERSION}" \
      https://github.com/isaacphi/mcp-language-server /tmp/mls && \
    git -C /tmp/mls apply /tmp/mls.patch && \
    cd /tmp/mls && GOPROXY=https://proxy.golang.org,direct GOTOOLCHAIN=auto \
      GOPATH=/tmp/gopath GOCACHE=/tmp/gocache \
      go build -o /usr/local/bin/mcp-language-server . && \
    cd / && rm -rf /tmp/mls /tmp/mls.patch /tmp/gopath /tmp/gocache
# Dashboard runs get a fresh, empty CLAUDE_CONFIG_DIR (pipeline_runner), so
# the LSP plugins are installed once here, at user scope, into a template the
# runner copies into each run's config dir. Verified with --debug-file in this
# image: plugins enabled only in /app/.claude/settings.json are skipped as
# "repo-authored", and a CLAUDE_CODE_PLUGIN_SEED_DIR seed registers after the
# LSP manager has already started with 0 servers.
# ponytail: the marketplace is not pinned to a commit (its LSP entries are a
# command name + an extension map). Pin with `...official#<tag>` if it drifts.
RUN export CLAUDE_CONFIG_DIR=/opt/claude-config CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1 && \
    claude plugin marketplace add anthropics/claude-plugins-official && \
    claude plugin install gopls-lsp@claude-plugins-official && \
    claude plugin install pyright-lsp@claude-plugins-official && \
    for lang in ${LSP_EXTRA_LANGUAGES}; do \
      case "$lang" in typescript) p=typescript-lsp ;; java) p=jdtls-lsp ;; \
        c) p=clangd-lsp ;; rust) p=rust-analyzer-lsp ;; \
        *) echo "unknown LSP_EXTRA_LANGUAGES entry: $lang" >&2; exit 1 ;; esac; \
      claude plugin install "$p@claude-plugins-official" || exit 1; \
    done && \
    rm -rf /opt/claude-config/plugins/marketplaces/*/.git /opt/claude-config/backups && \
    chmod -R a+rX /opt/claude-config
# QF_REPOS_DIR: ui.py shallow-clones every configured team repo here and sets
# its <NAME>_REPO_PATH, so dashboard runs have checkouts to analyze.
ENV QF_CLAUDE_CONFIG_TEMPLATE=/opt/claude-config \
    QF_REPOS_DIR=/tmp/qualityflow-team-repos \
    ENABLE_LSP_TOOL=1

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

# --- RTK (github.com/rtk-ai/rtk): compresses shell-command output for the agents
# a pipeline run starts, so tool output costs fewer input tokens. Self-contained
# block: the pinned release binary, then its Claude hook and Codex instruction.
# Bump RTK_VERSION and both digests together (`gh release view vX -R rtk-ai/rtk
# --json assets`); the build fails on a digest mismatch, never installs unverified.
ARG RTK_VERSION=0.42.4
ARG RTK_SHA256_X86_64=34975116da11e09e502501daf758143e0b22ed3a42a10eb67fb693a6270d9e36
# x86_64 only: the release's arm64 build is glibc-linked and needs GLIBC_2.39,
# newer than UBI9's 2.34 (seen in a local arm64 build); there is no static
# arm64 build. An arm64 image (a laptop build) ships without rtk, and the two
# steps below then add neither the hook nor the instruction.
RUN case "$(uname -m)" in \
      x86_64|amd64) RTK_TARGET=x86_64-unknown-linux-musl; RTK_SHA256="${RTK_SHA256_X86_64}" ;; \
      *) echo "rtk: no build for $(uname -m) that runs on UBI9; skipped" >&2; exit 0 ;; \
    esac; \
    mkdir /tmp/rtk && \
    curl -fsSL -o /tmp/rtk/rtk.tar.gz \
      "https://github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}/rtk-${RTK_TARGET}.tar.gz" && \
    echo "${RTK_SHA256}  /tmp/rtk/rtk.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/rtk/rtk.tar.gz -C /tmp/rtk && \
    install -m 0755 /tmp/rtk/rtk /usr/local/bin/rtk && \
    rm -rf /tmp/rtk && \
    rtk --version | grep -qx "rtk ${RTK_VERSION}"
# Claude: pipeline_runner gives each Claude run a fresh, empty CLAUDE_CONFIG_DIR,
# so user-level hooks never apply; project settings in /app/.claude do. Same
# PreToolUse entry `rtk init -g` writes. Merged into any settings.json already
# there, so another step writing that file keeps its keys.
RUN if command -v rtk >/dev/null; then python3 -c 'import json, pathlib; p = pathlib.Path("/app/.claude/settings.json"); s = json.loads(p.read_text()) if p.exists() else {}; s.setdefault("hooks", {}).setdefault("PreToolUse", []).append({"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}); p.write_text(json.dumps(s, indent=2) + "\n")'; fi
# Codex: rtk has no Codex hook (`rtk init --codex` only writes instructions),
# so this is an INSTRUCTION, not enforced: Codex reads AGENTS.md from its
# working directory (/app, pipeline_runner's cwd). Image-only, so laptop runs,
# where rtk may be absent, never see it. Cursor's `agent` reads it too.
RUN command -v rtk >/dev/null || exit 0; printf '%s\n' \
    '# Shell commands' \
    '' \
    'Prefix shell commands with `rtk` (installed on PATH), e.g. `rtk git status`,' \
    '`rtk ls`, `rtk pytest -q`: it compresses their output. Commands rtk' \
    'does not know pass through unchanged; `rtk proxy <cmd>` gives raw output.' \
    > /app/AGENTS.md
# --- end RTK

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
