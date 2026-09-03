# Pilot deploy runbook — first real-cluster install

The one gate left before broad rollout: stand the dashboard up on a real OpenShift
cluster once and drive it end to end. This is that script. ~30 minutes.

Config template: [`pilot-values.example.yaml`](pilot-values.example.yaml) — fill every
`<...>` first. Secrets stay off disk (passed with `--set`).

## Preflight — collect these before you start

| Need | How to get it |
|---|---|
| A namespace you can install into | `oc new-project qf-pilot` (or an existing one) |
| RWO StorageClass name | `oc get storageclass` → pick one, put it in the values file |
| Cluster apps domain | `oc get ingresses.config/cluster -o jsonpath='{.spec.domain}'` → sets the Route host |
| GHCR read token | GitHub → Settings → Developer settings → PAT (classic) with `read:packages` |
| Jira URL + API token, GitHub token | your team's existing creds |
| OIDC client (confidential) + secret | your IdP; realm/issuer URL; register the redirect URI in step 5 |

Pin `route.host` in the values file to `qf-pilot.apps.<cluster-domain>` so you know the
OIDC redirect URI up front — set `oidc.redirectUri` to `https://<that-host>/auth/callback`.

## 1. Image pull secret (the image is private)

```bash
oc project qf-pilot
kubectl create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<read:packages token>
```

## 2. Dry-run against the cluster (renders + validates, installs nothing)

```bash
helm install qf ./deploy/helm/qualityflow-dashboard \
  -f ./deploy/pilot-values.example.yaml \
  --set auth.apiKey="$(openssl rand -hex 24)" \
  --set oidc.clientSecret='<oidc-client-secret>' \
  --set tokens.jira.apiToken='<jira-token>' \
  --set tokens.github='<github-token>' \
  --dry-run --debug | less
```

Read the rendered manifests. Expect 10: ServiceAccount, Secret, ConfigMap, two PVCs,
Role, RoleBinding, Service, Deployment, Route. Confirm the Route host, the
`imagePullSecrets: - name: ghcr-pull`, the PVC `storageClassName`, and the OIDC
`/auth/callback` redirect all look right. (This exact set renders clean offline already;
`--dry-run` adds the cluster's own admission validation.)

## 3. Install for real

Same command, **drop** `--dry-run --debug`. Save the generated `auth.apiKey` — it's the
machine credential (and the shared key for any future manager rollup).

```bash
oc rollout status deploy/qf-qualityflow-dashboard   # waits for Ready
oc get pods -l app.kubernetes.io/name=qualityflow-dashboard
```

`ImagePullBackOff` here = the pull secret is missing/wrong, not an app fault (step 1).

## 4. Get the URL and open it

```bash
oc get route qf-qualityflow-dashboard -o jsonpath='https://{.spec.host}{"\n"}'
```

You should see the dashboard shell (not a spinner). It populates once the git-sync pulls
your `git.repoUrl` config (a few minutes).

## 5. Finish SSO

Register `https://<route-host>/auth/callback` as the redirect URI on your IdP client (it
matches `oidc.redirectUri` from the values file). Sign in — you should land back
authenticated; writes are now gated by login, reads stay open (`publicRead: true`).

## 6. Smoke test (drive it end to end)

- [ ] Pod `Ready`; `oc logs` shows JSON logs and `QualityFlow Dashboard ready`.
- [ ] Route renders; your projects appear after git-sync.
- [ ] Log in via SSO; approve/reset something → audit log shows your real user, not `dashboard-user`.
- [ ] `oc exec deploy/qf-qualityflow-dashboard -- curl -s localhost:8420/metrics | head` → `qf_*` gauges.
- [ ] `oc delete pod -l app.kubernetes.io/name=qualityflow-dashboard` → it restarts, no runs stuck `in_progress` (startup reconciliation).

## Rollback

Rolling back means going to the **previous release revision**, not uninstalling:

```bash
helm history qf                    # find the last good REVISION
helm rollback qf <revision>        # re-applies that revision's manifests
oc rollout status deploy/qf-qualityflow-dashboard
```

Tearing the install down entirely:

```bash
helm uninstall qf                  # keeps both PVCs — they carry helm.sh/resource-policy: keep
oc get pvc -l app.kubernetes.io/instance=qf
```

The PVCs are kept on purpose: `qf-qualityflow-dashboard-outputs` holds the team's
approvals, audit log and coverage history, which no re-run regenerates. A fresh
`helm install qf` in the same namespace re-binds to them, so an uninstall/reinstall
keeps the data. Delete them only when you actually want a clean slate:

```bash
oc delete pvc qf-qualityflow-dashboard-outputs qf-qualityflow-dashboard-config
```

Something misbehaving rather than broken? [deploy/README.md#troubleshooting](README.md#troubleshooting)
has the detect → diagnose → fix entries (full PVC, stale git sync, OIDC login loop, key
rotation, OOMKilled, backup/restore).

## What the pilot is really proving

The wrinkles a source/container/browser gate can't: Route TLS + the real cluster domain,
the OIDC round-trip against a live IdP, the RWO PVC binding on the cluster's StorageClass,
and the arbitrary-UID `restricted-v2` SCC accepting the image. Green here = ready to
onboard more teams with [ONBOARDING.md](ONBOARDING.md).
