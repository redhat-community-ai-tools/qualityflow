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

# git is needed by gitpython, the git-sync loop, and coverage tooling.
# The ubi9/python image runs as UID 1001 by default; switch to root just for
# the package install, then drop back to a non-root user below.
USER 0
RUN dnf install -y git && dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baked-in code + default config + resources.
COPY ui.py .
COPY ui/ ui/
COPY agents/ agents/
COPY skills/ skills/
COPY commands/ commands/
COPY config/ config/

RUN mkdir -p /data/outputs /data/config

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
    QF_OUTPUTS_DIR=/data/outputs \
    QF_CONFIG_DIR=/data/config \
    PYTHONUNBUFFERED=1

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8420\")}/healthz', timeout=3)" || exit 1

CMD ["python", "ui.py"]
