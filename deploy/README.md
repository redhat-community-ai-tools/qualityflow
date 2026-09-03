# Deploying QualityFlow Dashboard

Helm chart: [`helm/qualityflow-dashboard`](helm/qualityflow-dashboard/). Targets OpenShift
(`restricted-v2` SCC) but also works on plain Kubernetes via `ingress.enabled=true`.

**Onboarding a team?** Start with [ONBOARDING.md](ONBOARDING.md) — the 15-minute
install-and-wire-your-data checklist. This page is the full reference (every option, the
env-var table, SSO, manager rollup).

## Quick start

```bash
helm install qf ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$(openssl rand -hex 24)" \
  --set image.tag=0.2.1
```

`auth.apiKey` is optional — set it to gate writes (approve/reject, run, push-PR, delete)
behind a shared key. Left blank, the chart deploys with `QF_DEV=1` instead (unauthenticated
writes), which is a reasonable call when the cluster's network access is already restricted
to the team. `auth.existingSecret` brings your own Secret with a `QUALITYFLOW_API_KEY` key
instead of either.

The image defaults to `ghcr.io/redhat-community-ai-tools/qualityflow-dashboard`, published
by [`.github/workflows/publish-image.yml`](../.github/workflows/publish-image.yml) on every
`vX.Y.Z` tag. `image.tag` defaults to the chart's `appVersion`, so a plain install is
already pinned to a released image — set it only to test an unreleased build. Note the
published image tags are unprefixed (`0.2.0`), even though the git tag that builds them
is `v0.2.0`.

### Pulling the image (it's private)

Org policy disables public GHCR packages, so the published image is **private** — the
cluster needs pull credentials. Create a GHCR read token (a classic PAT with the
`read:packages` scope) and wire it one of two ways:

```bash
# 1. Bring your own pull secret (recommended — the token never enters the Helm release):
kubectl create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io --docker-username=<user> --docker-password=<token>
helm install qf ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$(openssl rand -hex 24)" --set image.tag=0.2.1 \
  --set 'image.pullSecrets[0].name=ghcr-pull'

# 2. Or let the chart create the dockerconfigjson secret from the token:
helm install qf ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$(openssl rand -hex 24)" --set image.tag=0.2.1 \
  --set image.pullSecret.create=true \
  --set image.pullSecret.username=<user> --set image.pullSecret.token=<token>
```

If you mirror the image into your own internal registry, override `image.repository`
(and point the pull secret at that registry instead).

On OpenShift a Route is created by default. Get the URL:

```bash
oc get route qf-qualityflow-dashboard -o jsonpath='{.spec.host}{"\n"}'
```

Set `route.host` to pin a hostname instead of the cluster-assigned one, or
`--set route.enabled=false --set ingress.enabled=true --set ingress.host=...` on
non-OpenShift clusters.

## Single-replica / in-memory state

Task state, rate limiting, and background-job bookkeeping all live in the dashboard
process's memory — there is no shared store. The chart hardcodes `replicas: 1` in
`templates/deployment.yaml` and ships no HPA. Do not scale this Deployment out; a second
pod would run its own disconnected view of the world and split task state between the two.
If you need HA, that's an application-level change first (state needs to move out of
process), not a chart change.

## Manager rollup vs. team instance

By default this chart deploys a single **team instance** that runs its own pipelines. To
stand up a **manager rollup** that instead polls other teams' dashboards and merges their
views, set the `peers` list in values:

```bash
helm install qf-manager ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$SHARED_KEY" \
  --set image.tag=0.2.1 \
  --set 'peers[0].label=cnv' --set 'peers[0].url=https://cnv-qf.apps.cluster-a.example.com' \
  --set 'peers[1].label=mtv' --set 'peers[1].url=https://mtv-qf.apps.cluster-b.example.com'
```

The chart renders that into `QF_PEERS` on the ConfigMap. Peers are polled with the manager's
own `QUALITYFLOW_API_KEY` as the bearer token, so every peer team instance must share that
key (give them the same `auth.apiKey`, or an `auth.existingSecret` holding it). A manager
with `peers` set stops running its own pipelines — deploy it as a separate release from the
team instances.

## SSO / OIDC login

By default writes are gated by `QUALITYFLOW_API_KEY` and reads are anonymous. To have people
log in as themselves (and attribute approvals/deletes to the real user), enable OIDC against
your IdP. A worked, commented example is
[`helm/qualityflow-dashboard/values-oidc-example.yaml`](helm/qualityflow-dashboard/values-oidc-example.yaml):

```bash
helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values \
  -f ./deploy/helm/qualityflow-dashboard/values-oidc-example.yaml
```

Register `https://<your-route-host>/auth/callback` as the client's redirect URI. The discovery
URL is derived from `oidc.issuer` (`<issuer>/.well-known/openid-configuration`), or set
`oidc.discoveryUrl` directly. `oidc.publicRead: true` keeps reads open and gates only writes.
`SESSION_SECRET` is auto-generated into the Secret if you leave `oidc.sessionSecret` blank.
Restrict who may sign in with `oidc.allowedDomains` / `oidc.allowedGroups`. All OIDC env vars
are in the table below.

## Observability

- `GET /metrics` (hand-rolled Prometheus text format) is served **unauthenticated**,
  same posture as `/healthz`/`/readyz` — it's exempt from the API-key/OIDC gate so
  a scraper doesn't need a credential. It's only reachable within the cluster via
  the ClusterIP Service by default; don't expose it externally without a
  NetworkPolicy or equivalent if that's a concern in your cluster.
- Structured JSON logs (`QF_LOG_FORMAT=json`) are the default so log shipping
  (Loki/ELK/etc.) doesn't need a custom parser; set `logging.level`/`logging.format`
  in `values.yaml` to change either.
- To let a Prometheus Operator scrape `/metrics` automatically, set
  `--set monitoring.enabled=true` (optionally `monitoring.interval` and
  `monitoring.labels` to match your Prometheus CR's `serviceMonitorSelector`).
  This renders a `ServiceMonitor` (`templates/servicemonitor.yaml`); it requires
  the Prometheus Operator CRDs, which is why it's off by default — leaving it
  disabled keeps the chart installable on clusters that don't have them.
- Alerting rules ship with the chart but are gated *separately*, so switching on
  scraping doesn't also start paging someone: `--set monitoring.enabled=true
  --set monitoring.rules.enabled=true` renders a `PrometheusRule`
  (`templates/prometheusrule.yaml`) with five alerts — pod not ready, >3 phase
  failures in 15m, git sync stale >15m, a data volume over 90% full, and a 5xx
  rate over 5%. `monitoring.rules.labels` matches your Prometheus CR's
  `ruleSelector`. Each alert maps to an entry in [Troubleshooting](#troubleshooting).
- `QF_FORWARDED_ALLOW_IPS` (`network.forwardedAllowIps`) controls which hop the
  app trusts for `X-Forwarded-For` when it identifies a caller for the
  write-endpoint rate limiter. **The chart's default is `*`** — trust exactly the
  one hop that connected, which behind this chart's own topology (ClusterIP
  Service, pod not otherwise reachable) is the Route/Ingress router, so the
  address it appends is the real client. The old `127.0.0.1` default trusted
  nothing, so every user keyed on the router pod and one person's clicking
  rate-limited the whole team out. Narrow it to the ingress controller's pod or
  service CIDR (e.g. `10.128.0.0/14`) whenever something else can reach the pod
  directly — `hostNetwork`, a NodePort Service, or a mesh sidecar — because then
  a client can append its own last hop. (`127.0.0.1` remains `ui.py`'s built-in
  default for a bare, non-chart run.)

## Troubleshooting

Detect → diagnose → fix. The signals below are the ones the chart's
[alerting rules](#observability) fire on, so an alert lands you in the matching entry.

### PVC full / ENOSPC

- **Detect** — `qf_disk_free_bytes / qf_disk_total_bytes` under 0.1
  (`QualityFlowDiskNearlyFull`); `/readyz` starts returning 503 because its write
  probe fails; uploads return `507`.
- **Diagnose** — `oc exec deploy/qf-qualityflow-dashboard -- df -h /data/outputs /data/config`.
  It is almost always the outputs volume: every re-run of a phase snapshots the
  previous artifacts under `outputs/<TICKET>/.previous`.
- **Fix** — prune the snapshots, then resize if it refills:
  ```bash
  oc exec deploy/qf-qualityflow-dashboard -- sh -c 'rm -rf /data/outputs/*/.previous'
  oc patch pvc qf-qualityflow-dashboard-outputs \
    -p '{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'   # needs an expandable StorageClass
  ```
  `persistence.outputs.size` in values keeps the new size across upgrades.

### Git sync stale or failing

- **Detect** — `qf_git_sync_last_success_timestamp` more than 900s behind `time()`
  (`QualityFlowGitSyncStale`); `GET /api/status` shows an old `last_sync`; the pod
  logs carry `Git sync failed`.
- **Diagnose** — the log line names the git error. Auth failure = `git.token` is
  missing, expired, or lacks read access to `git.repoUrl`. A timeout with no
  further detail = the remote is unreachable from the pod (egress policy, proxy)
  and `GIT_SYNC_TIMEOUT` (default 120s) killed it.
- **Fix** — rotate/set the token and force a sync:
  ```bash
  helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values --set git.token=<pat>
  curl -sf -X POST -H "X-API-Key: $QUALITYFLOW_API_KEY" https://<route-host>/api/sync
  ```
  Never put the credential in `git.repoUrl` — that value lands in the ConfigMap and
  is served by the anonymous `/api/status`. `git.token` goes to the Secret and is
  injected into the clone URL at runtime.

### OIDC redirect mismatch / login loop

- **Detect** — the IdP returns a 4xx on `/auth/callback` (`redirect_uri_mismatch`,
  `invalid_client`), or login "succeeds" and bounces straight back to the login
  page because no session cookie was stored.
- **Diagnose** — compare the three: `oidc.redirectUri` in values, the redirect URI
  registered on the IdP client, and the actual Route host
  (`oc get route qf-qualityflow-dashboard -o jsonpath='{.spec.host}'`).
- **Fix** — `OIDC_REDIRECT_URI` must equal `https://<route-host>/auth/callback`
  **exactly**: same scheme, same host, no trailing slash. If the browser reaches the
  dashboard over plain `http` (port-forward, no TLS on the Route), the always-`Secure`
  session cookie is dropped and login loops — that is what `QF_INSECURE_COOKIES=1` is
  for, and it is for local development only, never a cluster the team uses.

### API key rotation

1. Generate the new key and roll it into the release:
   ```bash
   NEW=$(openssl rand -hex 24)
   helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values --set auth.apiKey="$NEW"
   ```
   With `auth.existingSecret`, update `QUALITYFLOW_API_KEY` in that Secret and restart
   the Deployment instead (`oc rollout restart deploy/qf-qualityflow-dashboard`).
2. Update the `QUALITYFLOW_API_KEY` CI secret in **every onboarded repo** — the coverage
   upload job authenticates with it and starts failing 401 the moment the key changes.
3. If this instance is a manager rollup (`QF_PEERS` set), the same key is the bearer
   token it polls peers with: rotate every peer team instance to the new key in the
   same window, or the rollup goes blank.

### Pod OOMKilled

- **Detect** — `QualityFlowPodNotReady`, restart count climbing, and
  `oc describe pod -l app.kubernetes.io/name=qualityflow-dashboard` showing
  `Last State: Terminated, Reason: OOMKilled`.
- **Diagnose** — the list/metrics routes hold a working set proportional to the number
  of tickets on the outputs PVC. The 1Gi default limit is sized against the ~1,000-ticket
  bar; count yours with `oc exec deploy/qf-qualityflow-dashboard -- sh -c 'ls /data/outputs | wc -l'`.
- **Fix** — raise the limit and let it restart:
  ```bash
  helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values \
    --set resources.limits.memory=2Gi
  ```
  Do **not** add replicas instead — task state is per-process (see
  [Single-replica](#single-replica--in-memory-state)).

### Backup and restore

What is on each volume, and what a backup is actually protecting:

| PVC | Holds | Regenerable? |
|---|---|---|
| `...-outputs` | STP/STD/test artifacts per ticket | Yes — re-run the pipeline |
| `...-outputs` | approvals, audit log, coverage history, usage log | **No** |
| `...-config` | pipeline config synced from `git.repoUrl` | Yes — from git |
| `...-config` | local edits made in the UI | **No** |

Back up (either one):

```bash
# CSI snapshot, if your StorageClass supports it — atomic, stays in-cluster
oc create -f - <<'EOF'
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata: {name: qf-outputs-backup}
spec: {source: {persistentVolumeClaimName: qf-qualityflow-dashboard-outputs}}
EOF

# or copy both mounts out to a workstation
oc rsync deploy/qf-qualityflow-dashboard:/data/outputs ./qf-backup/outputs
oc rsync deploy/qf-qualityflow-dashboard:/data/config  ./qf-backup/config
```

Restore:

- **Same namespace, data still there.** Both PVCs carry `helm.sh/resource-policy: keep`,
  so `helm uninstall` leaves them; a fresh `helm install qf ...` with the same release
  name re-binds to the existing PVCs and the data comes back with it. Nothing to restore.
- **Data lost, or a new cluster.** Install first so the PVCs and pod exist, then push the
  copy back in and restart:
  ```bash
  helm install qf ./deploy/helm/qualityflow-dashboard -f values.yaml
  oc rsync ./qf-backup/outputs/ deploy/qf-qualityflow-dashboard:/data/outputs
  oc rsync ./qf-backup/config/  deploy/qf-qualityflow-dashboard:/data/config
  oc rollout restart deploy/qf-qualityflow-dashboard
  ```
  From a VolumeSnapshot instead: create the PVCs from the snapshot (`spec.dataSource`)
  under the names `<release>-qualityflow-dashboard-outputs` / `-config` *before*
  `helm install`. Helm only adopts a pre-existing object that already carries its
  ownership metadata, so stamp it on first, or the install fails on "invalid ownership":
  ```bash
  for p in outputs config; do
    oc label   pvc qf-qualityflow-dashboard-$p app.kubernetes.io/managed-by=Helm
    oc annotate pvc qf-qualityflow-dashboard-$p \
      meta.helm.sh/release-name=qf meta.helm.sh/release-namespace="$(oc project -q)"
  done
  ```
  PVCs left behind by `helm uninstall` already have all of that — this is only for
  volumes you created yourself.

Rolling back a bad upgrade is `helm rollback` — see [PILOT.md](PILOT.md#rollback).

## Environment variables

Source of truth: the module docstring at the top of `../ui.py` and its
`os.environ.get(...)` call sites. Every variable below is read by `ui.py` — the
host/port/data-dir env binding and the Jira-TLS toggle landed in the Phase 1
container-readiness change; CLI flags (`--host`/`--port`) still override the env.

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `QUALITYFLOW_API_KEY` | Machine auth (CI upload, peer rollup) and write-path gate when OIDC is off | — | No — but one of this or `QF_DEV=1` must be set, or `ui.py` refuses to start |
| `QF_DEV` | Unauthenticated-writes mode — the only thing this toggles is bypassing the `QUALITYFLOW_API_KEY` requirement above | unset | No |
| `QF_HOST` | Bind address (env; `--host` overrides) | `0.0.0.0` | No |
| `PORT` | Listen port (env; `--port` overrides) | `8420` | No |
| `QF_OUTPUTS_DIR` | Writable outputs directory (points at the outputs PVC mount) | `/data/outputs` | No |
| `QF_CONFIG_DIR` | Writable config directory (points at the config PVC mount) | `/data/config` | No |
| `QF_CLUSTER_LABEL` | Free-text label identifying this cluster/instance in the UI | `local` | No |
| `QUALITYFLOW_BASE_URL` | This dashboard's own external URL (chart: `dashboardUrl`). **Must be set for coverage onboarding**: the workflow it commits to your repos POSTs `QUALITYFLOW_API_KEY` to this URL, so it is never taken from the request's `Host` header or body — `/api/coverage/onboard` and `/api/coverage/bulk-onboard` return `503` while it is unset | unset | Only for coverage onboarding |
| `QF_LOG_FORMAT` | Structured logging output format: `json` or `text` | `json` | No |
| `QF_LOG_LEVEL` | Log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) | `INFO` | No |
| `QF_FORWARDED_ALLOW_IPS` | Upstream hop(s) trusted for `X-Forwarded-For` when computing client IP (rate limiter). Narrow it if anything can reach the pod directly — see [Observability](#observability) | `*` from the chart (`network.forwardedAllowIps`); `127.0.0.1` in a bare `ui.py` run | No |
| `QF_PEERS` / `QF_PEERS_FILE` | Comma-separated peer dashboard URLs (or a file of them) — presence makes this a manager rollup | unset | No |
| `QF_RUNNER` | `cli` switches the pipeline runner to shell out to the `claude` CLI instead of the SDK | unset | No |
| `QF_RUNNER_MODEL` / `QF_RUNNER_MODELS` | Default model / dropdown choices for the runner | inherit session | No |
| `QF_RUNNER_TIMEOUT` | Runner execution timeout | — | No |
| `QF_JIRA_INSECURE_TLS` | Skip TLS verification for internal self-signed Jira (default: verify) | unset | No |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | IdP client credentials | unset (OIDC off) | No |
| `OIDC_DISCOVERY_URL` | `.well-known/openid-configuration` URL | unset | No |
| `OIDC_ISSUER` | Alternative to discovery URL; discovery URL is derived from it | unset | No |
| `OIDC_REDIRECT_URI` | Override behind a TLS-terminating proxy | derived | No |
| `OIDC_ALLOWED_DOMAINS` / `OIDC_ALLOWED_GROUPS` | CSV allowlists (email domain / IdP group claim) | unset (allow all) | No |
| `OIDC_PUBLIC_READ` | Allow anonymous GETs, require login only for writes | `false` | No |
| `SESSION_SECRET` | Cookie-signing secret — **required whenever OIDC is enabled**; chart auto-generates one if `oidc.sessionSecret` is left blank | — | Conditional |
| `GIT_REPO_URL` / `GIT_BRANCH` | Pull pipeline config from git instead of the bundled default | unset / `main` | No |
| `GIT_SYNC_INTERVAL` | Seconds between background git syncs | `300` | No |
| `ANTHROPIC_VERTEX_PROJECT_ID` / `CLOUD_ML_REGION` | Use Vertex AI as the Claude backend | unset / `us-east5` | No |
| `ANTHROPIC_API_KEY` | Use the direct Anthropic API instead of Vertex | unset | No |
| `CLAUDE_MODEL` | Model id for the dashboard's own Claude client | `claude-sonnet-4@20250514` | No |
| `SONAR_TOKEN` | SonarQube/SonarCloud auth | unset | No |
| `SONARCLOUD_TOKEN` | Alias for `SONAR_TOKEN`, read only if that is unset. The chart only ever sets `SONAR_TOKEN` (from `tokens.sonar.token`) — this name exists for hand-rolled deployments | unset | No |
| `SONAR_HOST_URL` | SonarQube/SonarCloud base URL | `https://sonarcloud.io` | No |
| `CODECOV_API_TOKEN` | Codecov API auth | unset | No |
| `SLACK_WEBHOOK_URL` | Slack notifications | unset (no-op if unset) | No |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | unset (same-origin only) | No |
| `GITHUB_TOKEN` / `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub API auth (PRs, issues) | unset | No |
| `GITLAB_PERSONAL_ACCESS_TOKEN` | GitLab API auth | unset | No |
| `QUALITYFLOW_GIT_TOKEN` | Single-token fallback for both forges, read only when the forge-specific name above is unset. The chart sets the specific names (from `tokens.github` / `tokens.gitlab`) — this name exists for hand-rolled deployments | unset | No |
| `JIRA_URL` / `JIRA_API_TOKEN` | Jira base URL and API token (`JIRA_USERNAME` also read) | unset | No |

The chart splits these across a ConfigMap (non-secret) and a Secret (`QUALITYFLOW_API_KEY`,
`SESSION_SECRET`, and any of the tokens above you set under `values.yaml`'s `tokens.*`) —
see `templates/configmap.yaml` and `templates/secret.yaml`. Set `auth.existingSecret` to
bring your own Secret instead of letting the chart create one.

Variables with no dedicated `values.yaml` key of their own — `QF_JIRA_INSECURE_TLS`,
`QF_RUNNER_TIMEOUT`, `GIT_SYNC_INTERVAL`, `SLACK_WEBHOOK_URL` — go through the chart's
`extraEnv` map, which is rendered into the same ConfigMap:

```yaml
extraEnv:
  QF_RUNNER_TIMEOUT: "900"
  GIT_SYNC_INTERVAL: "60"
```

`extraEnv` is rendered *before* the chart-managed keys, so anything that does have its own
key (`logging.level`, `cors.origins`, ...) must be set there — a duplicate in `extraEnv` is
overridden. It lands in a ConfigMap in plaintext; route real secrets through
`auth.existingSecret` instead.

## Cutting a release

**Bump `Chart.yaml` before you tag.** `values.yaml` leaves `image.tag` empty and
`deployment.yaml` falls back to `.Chart.AppVersion`, so `appVersion` is what a default
install actually pulls. Tagging without bumping it leaves the chart installing the
*previous* image while the git tag claims otherwise — and nothing fails, so the only
symptom is a cluster quietly running old code.

1. **Bump `deploy/helm/qualityflow-dashboard/Chart.yaml`** — both `version` (the chart)
   and `appVersion` (the image, and the `app.kubernetes.io/version` pod label). Use the
   unprefixed number: `0.3.0`, not `v0.3.0`.
2. **Merge that to `main`**, so the tag lands on a commit whose chart is self-consistent.
3. **Tag and push** — this is what triggers the build:
   ```bash
   git tag -a v0.3.0 -m "v0.3.0 — <one line>"
   git push origin v0.3.0
   ```
4. **Watch [`publish-image.yml`](../.github/workflows/publish-image.yml)** and confirm it
   pushed. Nothing else builds the `Containerfile` — it is *not* exercised by PR CI, so a
   broken dependency or COPY path first surfaces here. If it fails, delete the tag
   (`git push --delete origin v0.3.0`), fix, and re-tag.
5. **Verify the tags that actually reached the registry**, rather than trusting the green
   check:
   ```bash
   gh run view <run-id> --log | grep -oE 'qualityflow-dashboard:[A-Za-z0-9._-]+' | sort -u
   ```
   Expect exactly four: `X.Y.Z`, `X.Y`, `latest`, and `sha-<short>`. All unprefixed — a
   `v` in front of the number means something upstream changed and the chart's default
   will no longer resolve.
6. **Write the release notes** (`gh release create v0.3.0 --verify-tag --notes-file …`).
   Lead with breaking changes and what to do about them — an operator reads this while
   deciding whether an upgrade is safe, not afterwards.

### Version choice

Pre-1.0, bump the **minor** for anything breaking, not just for features: a changed API
verb or response shape, a values key that now fails the render, or an endpoint that starts
rejecting input it used to accept. `v0.2.0` carried four such changes.

### Checking what a release will pull

```bash
helm template t deploy/helm/qualityflow-dashboard --set auth.apiKey=x | grep 'image:'
```

Run it before tagging. If that prints the previous version, step 1 hasn't been done.
