# Deploying QualityFlow Dashboard

Helm chart: [`helm/qualityflow-dashboard`](helm/qualityflow-dashboard/). Targets OpenShift
(`restricted-v2` SCC) but also works on plain Kubernetes via `ingress.enabled=true`.

## Quick start

```bash
helm install qf ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$(openssl rand -hex 24)" \
  --set image.repository=quay.io/your-org/qualityflow-dashboard \
  --set image.tag=v0.1.0
```

`auth.apiKey` is required (unless you pass `auth.existingSecret` pointing at a Secret you
already created with a `QUALITYFLOW_API_KEY` key) — the chart's `secret.yaml` template
fails the render otherwise. `image.repository`/`image.tag` also need overriding; the
defaults are placeholders, no public image is published yet.

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

Set `QF_PEERS` (or `QF_PEERS_FILE`, mounted separately — not wired into this chart) to
turn one dashboard into a rollup that polls a list of peer dashboards, rather than running
its own pipelines. This chart deploys a single **team instance**; wiring up a manager
rollup on top is a values/env addition left to the operator (add the var via
`--set-string` against `extraEnv`-style overrides, or a values.yaml fork) since peer URLs
are deployment-specific.

## Environment variables

Source of truth: the module docstring at the top of `../ui.py`, plus grep of
`os.environ.get(...)` call sites in that file. Vars marked "not read by ui.py today" are
part of the platform contract this chart assumes (host/port/data-dir binding via the
Containerfile's entrypoint) but aren't yet consumed by `ui.py` itself as of this commit —
kept in the table anyway since the chart still sets them and a future `ui.py` change may
start reading them.

| Variable | Purpose | Default | Required |
|---|---|---|---|
| `QUALITYFLOW_API_KEY` | Machine auth (CI upload, peer rollup) and write-path fallback when OIDC is off | — | **Yes** |
| `QF_DEV` | Dev-mode toggle (relaxed checks, verbose logging) | unset | No |
| `QF_HOST` | Bind address. *Not read by `ui.py` today* (it uses `--host`, default `127.0.0.1`) — chart sets `0.0.0.0` for the container contract | `0.0.0.0` (chart) | No |
| `PORT` | Listen port. *Not read by `ui.py` today* (it uses `--port`, default `8420`) — chart sets it to `service.port` | `8420` | No |
| `QF_OUTPUTS_DIR` | Writable outputs directory. *Not read by `ui.py` today* (it hardcodes `<repo>/outputs`) — chart points it at the outputs PVC mount | `/data/outputs` | No |
| `QF_CONFIG_DIR` | Writable config directory. *Not read by `ui.py` today* (it hardcodes `<repo>/config`) — chart points it at the config PVC mount | `/data/config` | No |
| `QF_CLUSTER_LABEL` | Free-text label identifying this cluster/instance in the UI | `local` | No |
| `QF_PEERS` / `QF_PEERS_FILE` | Comma-separated peer dashboard URLs (or a file of them) — presence makes this a manager rollup | unset | No |
| `QF_RUNNER` | `cli` switches the pipeline runner to shell out to the `claude` CLI instead of the SDK | unset | No |
| `QF_RUNNER_MODEL` / `QF_RUNNER_MODELS` | Default model / dropdown choices for the runner | inherit session | No |
| `QF_RUNNER_TIMEOUT` | Runner execution timeout | — | No |
| `QF_JIRA_INSECURE_TLS` | Skip TLS verification for Jira calls. *Not found in `ui.py`* — `ui.py`'s HTTP helper always verifies TLS (no `-k`/`--insecure` path); kept here in case a future build adds it | unset | No |
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
| `SONAR_HOST_URL` | SonarQube/SonarCloud base URL | `https://sonarcloud.io` | No |
| `CODECOV_API_TOKEN` | Codecov API auth | unset | No |
| `SLACK_WEBHOOK_URL` | Slack notifications | unset (no-op if unset) | No |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | unset (same-origin only) | No |
| `GITHUB_TOKEN` / `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub API auth (PRs, issues) | unset | No |
| `GITLAB_PERSONAL_ACCESS_TOKEN` | GitLab API auth | unset | No |
| `JIRA_URL` / `JIRA_API_TOKEN` | Jira base URL and API token (`JIRA_USERNAME` also read) | unset | No |

The chart splits these across a ConfigMap (non-secret) and a Secret (`QUALITYFLOW_API_KEY`,
`SESSION_SECRET`, and any of the tokens above you set under `values.yaml`'s `tokens.*`) —
see `templates/configmap.yaml` and `templates/secret.yaml`. Set `auth.existingSecret` to
bring your own Secret instead of letting the chart create one.
