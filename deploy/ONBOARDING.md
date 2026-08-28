# Onboarding a team onto the QualityFlow dashboard

The goal: a team goes from nothing to a running dashboard showing **their own**
pipelines, tickets, and coverage. Budget ~15 minutes. Everything here is
`helm` + a few tokens — no build step.

Reference: the chart lives in [`helm/qualityflow-dashboard`](helm/qualityflow-dashboard/);
full option list and env-var table are in [README.md](README.md).

## 0. Prerequisites

- Cluster access (`oc`/`kubectl`) and Helm 3, in a namespace you can install into.
- A **GHCR read token** — the image is private (org policy), so you need one to pull it.
  Create a classic PAT with the `read:packages` scope.
- Your data tokens (any you want the dashboard to read): a **Jira** URL + API token,
  a **GitHub** token (PRs/issues), optionally GitLab / Sonar / Codecov.

## 1. Create the image pull secret

```bash
kubectl create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<your-github-user> \
  --docker-password=<read:packages token>
```

(Or skip this and let the chart make it — `--set image.pullSecret.create=true …`. See README.)

## 2. Install

```bash
helm install qf ./deploy/helm/qualityflow-dashboard \
  --set auth.apiKey="$(openssl rand -hex 24)" \
  --set image.tag=0.2.0 \
  --set 'image.pullSecrets[0].name=ghcr-pull' \
  --set clusterLabel="my-team"
```

`auth.apiKey` is the machine credential (CI upload, peer rollup, and the write-path
fallback before SSO is on) — keep it; you'll reuse it in step 5's manager rollup if you
ever set one up.

## 3. Get the URL

```bash
# OpenShift (Route is on by default):
oc get route qf-qualityflow-dashboard -o jsonpath='{.spec.host}{"\n"}'
# Plain Kubernetes: install with --set route.enabled=false --set ingress.enabled=true \
#   --set ingress.host=qf.example.com  and use that host.
```

Open it — you should get the dashboard shell (not a loading spinner). It'll be empty
until step 4.

## 4. Wire your team's data

Without this the dashboard has nothing to show. Set the tokens (they land in the chart's
Secret) and point it at your pipeline config:

```bash
helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values \
  --set tokens.jira.url=https://your-jira.example.com \
  --set tokens.jira.username=<jira-user> \
  --set tokens.jira.apiToken=<jira-token> \
  --set tokens.github=<github-token> \
  --set git.repoUrl=https://github.com/your-org/your-qf-config \
  --set git.branch=main
```

`git.repoUrl` is how the dashboard tracks **your** projects instead of the bundled demo —
it syncs pipeline config from that repo every few minutes. Omit it only if you baked config
into your own image.

## 5. Turn on SSO (recommended for day-to-day team use)

Out of the box, writes are gated by the shared `auth.apiKey`. For a team, wire OIDC to your
IdP so people log in as themselves and actions are attributed to the real user. A worked
example is in [`helm/qualityflow-dashboard/values-oidc-example.yaml`](helm/qualityflow-dashboard/values-oidc-example.yaml):

```bash
helm upgrade qf ./deploy/helm/qualityflow-dashboard --reuse-values \
  -f ./deploy/helm/qualityflow-dashboard/values-oidc-example.yaml
```

Register this **redirect URI** with your IdP client: `https://<your-route-host>/auth/callback`.
With `oidc.publicRead: true` (in the example) anyone in the org can view; only writes require
login. The chart auto-generates `SESSION_SECRET` if you leave it blank.

## 6. (Optional) Cross-team manager rollup

If you want one dashboard that aggregates several teams, deploy a **separate** release with a
`peers` list — see the "Manager rollup vs. team instance" section in [README.md](README.md).
Give every peer team instance the same `auth.apiKey` so the manager can poll them.

## Verify

- `oc get pods` → the pod is `Running` and `Ready` (readiness probe hits `/readyz`).
- The Route URL renders the dashboard; your projects appear once step 4's git sync runs.
- Prometheus: `GET /metrics` returns `qf_*` gauges (unauthenticated, in-cluster only).

## Gotchas (all in AGENTS.md / README, surfaced here)

- **Private image** — a missing/wrong pull secret shows as `ImagePullBackOff`, not an app error.
- **Behind the Route**, widen `network.forwardedAllowIps` (e.g. to `*`) or the write-rate-limiter
  buckets every request together — the Service is ClusterIP-only by default, so `*` is safe.
- **Single replica by design** — state is in-process; do not scale the Deployment out.
- **Notifications no-op without keys** — Slack/Resend/Twilio silently do nothing if unset (dev-safe).
