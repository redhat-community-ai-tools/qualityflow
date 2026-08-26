# QualityFlow Threat Model

A checked-in threat model for QualityFlow — codifying security expectations
as a quality gate that agents and reviewers can eval against.

## System Overview

QualityFlow is two things:

1. A markdown/YAML framework of agents, skills, and slash commands deployed
   into Claude Code or Cursor AI (`deploy.py` copies these to `~/.claude/` or
   `~/.cursor/`). It generates test planning documents (STPs, STDs) and test
   code from Jira tickets or GitHub issues, run inside the AI assistant's
   session.
2. **A deployed FastAPI server** (`ui.py`, ~8k lines) — the QualityFlow
   Dashboard — that runs those same pipelines on a schedule/on-demand for a
   team, holds pipeline state, and serves a web UI. It's shipped as a
   container + Helm chart (`deploy/helm/qualityflow-dashboard/`) for
   OpenShift/Kubernetes. **This section of the codebase used to say
   QualityFlow "has no runtime server component in production" — that has
   not been true since the dashboard shipped, and treating it as a static
   framework understates its attack surface.** The rest of this document
   covers the dashboard; the framework-only threats from the original
   version (MCP server trust, prompt injection via ticket content, PII in
   generated docs, deploy.py integrity, config validation) still apply and
   are folded in below rather than dropped.

Deployment model: single Kubernetes/OpenShift pod (`replicaCount: 1`,
hardcoded, no HPA — see `deploy/README.md`), FastAPI/uvicorn process, task
state and rate-limit counters **in-process memory** (no external store),
two RWO PVCs (`/data/outputs`, `/data/config`).

## Assets

| Asset | Where | Why it matters |
|---|---|---|
| `outputs` PVC (`/data/outputs`) | RWO PersistentVolume | Generated STPs/STDs/tests, per-ticket pipeline state (`state/*.yaml`), task history. Loss = lost work product; tampering = poisoned test artifacts fed back into a repo. |
| `config` PVC (`/data/config`) | RWO PersistentVolume | Project routing config, PII rules, tier/pattern files. Tampering changes pipeline behavior for every ticket processed afterward. |
| `QUALITYFLOW_API_KEY` | K8s Secret, env | Machine auth for writes (CI upload, peer rollup, and the general write-path fallback whenever OIDC is off). Anyone with this key can drive the pipeline and read/write everything the API can touch. |
| OIDC session (`SESSION_SECRET`) | K8s Secret, signed cookie | Human login when SSO is enabled. A leaked `SESSION_SECRET` lets an attacker forge sessions for arbitrary users/groups. |
| Upstream tokens (GitHub/GitLab/Jira/Sonar/Codecov) | K8s Secret, env | `GITHUB_TOKEN`/`GITHUB_PERSONAL_ACCESS_TOKEN`, `GITLAB_PERSONAL_ACCESS_TOKEN`, `JIRA_API_TOKEN`, `SONAR_TOKEN`, `CODECOV_API_TOKEN`. Each is API auth to a real external system on the team's behalf; leakage is equivalent to leaking that system's credential directly. |
| Service Account + `Role` (RBAC) | in-cluster | The pod's SA can `create/get/list/delete` `batch/Jobs` and read `pods`/`pods/log`/`pods/proxy` in its namespace (`templates/role.yaml`) — used to launch on-cluster coverage-collection Jobs. Anything that can act as this SA can spin up arbitrary Jobs in the namespace, bounded by whatever ServiceAccount those Jobs themselves run as. |
| `claude`/Anthropic credentials (`ANTHROPIC_API_KEY` or Vertex project) | env | The dashboard's own LLM calls (estimation, chat, the CLI runner). Leakage = spend/abuse on the team's account. |

## Trust Boundaries & AuthN/AuthZ

Enforced by `AuthMiddleware` in `ui.py` plus per-route dependencies
(`_require_api_key` / `_check_api_key_or_origin`):

- **Anonymous reads by default.** With OIDC off (the default — `oidc.enabled:
  false`), all GETs are open; writes require `QUALITYFLOW_API_KEY`. With OIDC
  on, every request needs a session *unless* `OIDC_PUBLIC_READ=true`, which
  reopens GET/HEAD to anonymous callers and keeps the login requirement only
  for writes — the same "public dashboard, gated writes" shape as the no-OIDC
  default, now with human identity for the write side.
- **Writes need either an API key or an authenticated session.**
  `_require_api_key`/`_check_api_key_or_origin` do a constant-time
  (`hmac.compare_digest`) comparison against `QUALITYFLOW_API_KEY`; when OIDC
  is enabled, `AuthMiddleware` additionally accepts a logged-in session
  (`_session_user`) in place of the key for browser traffic.
- **Machine bypass:** `_machine_authorized()` accepts the shared
  `QUALITYFLOW_API_KEY` via `X-API-Key` or `Authorization: Bearer` on *any*
  path when OIDC is enabled — this is intentional (CI upload, peer-rollup
  polling) but means the API key is a full authentication bypass, not scoped
  to specific endpoints. Treat it with the same care as a root credential.
- **Startup fails closed on missing auth.** If `QUALITYFLOW_API_KEY` is unset
  and `QF_DEV` is not truthy, the process refuses to start (`SystemExit(1)`)
  rather than silently serving unauthenticated writes. `QF_DEV=1` is the
  documented escape hatch for local dev only — it must never be set in a
  deployed values file; the chart doesn't expose it as a value on purpose.
- **`/metrics`, `/healthz`, `/readyz` are intentionally unauthenticated**
  (`_AUTH_EXEMPT_PREFIXES` covers `/healthz`/`/readyz`; `/metrics` is a
  similarly-exempt Phase 2 addition) so kubelet probes and a Prometheus
  scraper don't need a credential. `/metrics` is a hand-rolled Prometheus
  text-format endpoint with no aggregation controls of its own — it's scoped
  by network reachability (ClusterIP Service, no external route to it) rather
  than by auth. Don't put it behind a public Route/Ingress.
- **CORS** is same-origin unless `CORS_ORIGINS` is set — leave it empty
  unless a specific external origin needs cross-origin access.
- **Framework-level boundary (non-server mode):** MCP servers run as local
  child processes with network access to configured APIs; only
  published/audited packages, pinned versions, no project-repo-embedded MCP
  config. Jira/GitHub issue content is untrusted input — agents treat it as
  data, not instructions, and the pipeline's phase structure can't be altered
  by ticket text.

## Notable Hardening Already Done (Phase 0/1/2)

- **Referer-bypass removed.** An earlier auth path trusted the `Referer`
  header as a same-origin signal for write requests; `Referer` is
  attacker-controlled (a browser will send whatever the page sets, and many
  clients let it be forged outright), so this was a spoofable auth bypass.
  `_check_api_key_or_origin` now ignores `request` entirely and requires the
  API key — the parameter stayed in the signature only to avoid touching
  every call site.
- **Artifact markdown is sanitized before client-side render.** STP/STD
  content is derived from Jira ticket text (attacker-influenceable) and
  rendered client-side via `innerHTML`; `bleach` with an explicit
  tag/attribute allowlist (`_MD_ALLOWED_TAGS`/`_MD_ALLOWED_ATTRS`) sits at
  that boundary.
- **Jira TLS verification is on by default.** `QF_JIRA_INSECURE_TLS` is an
  explicit opt-out for internal self-signed Jira instances rather than the
  default posture.
- **Container runs as an arbitrary, non-root UID.** No `runAsUser`/`fsGroup`
  is templated — OpenShift's `restricted-v2` SCC assigns one from the
  namespace's UID range; `runAsNonRoot: true`, `allowPrivilegeEscalation:
  false`, `capabilities: drop: ["ALL"]`, `seccompProfile: RuntimeDefault` are
  set explicitly (`templates/deployment.yaml`).
- **Per-IP rate limiting on write endpoints** (`_check_rate_limit`): sliding
  60s window, 30 requests/window, in-memory (bounded to 1000 tracked IPs with
  periodic eviction). As of Phase 2 the IP it keys on is proxy-aware
  (`QF_FORWARDED_ALLOW_IPS`) instead of always trusting `request.client.host`
  directly — see the Observability section of `deploy/README.md` for the
  trust-boundary tradeoff in setting it.
- **Graceful shutdown + startup reconciliation.** On SIGTERM the app drains
  in-flight requests before exiting (`terminationGracePeriodSeconds: 30` in
  the chart gives this room to run); on startup, any pipeline state file left
  `in_progress` (a thread that died with the previous process) is swept to
  `failed` rather than left stuck forever (`_fail_stuck_phases`).
- **Structured JSON logging** (`QF_LOG_FORMAT`/`QF_LOG_LEVEL`, Phase 2) —
  machine-parseable audit trail for log aggregation, including auth
  decisions and pipeline lifecycle events.
- **Data dirs are env-overridable**, separating the read-only image layer
  from writable PVC mounts (`QF_OUTPUTS_DIR`/`QF_CONFIG_DIR`), and the RBAC
  `Role` is scoped to exactly the verbs the coverage-Job launcher needs
  (`create/get/list/delete` on `batch/jobs`, read-only on pods/logs) rather
  than a broad `edit`/`admin` binding.

## Residual Risks / Assumptions (be honest)

| Risk | Severity | Status |
|---|---|---|
| **Single replica is an availability property, not a security control.** Task state and rate-limit counters live in process memory; there is no HPA and the chart hardcodes `replicas: 1`. A pod restart drops in-flight rate-limit history (self-healing, low risk) and briefly interrupts service (no failover). Do not read "single replica" as a mitigation for anything in this table — it isn't one. | Low (availability) | Accepted; scaling out requires moving state out of process first, not a chart change. |
| **The pipeline runner executes the `claude` CLI with `--dangerously-skip-permissions`** (`pipeline_runner.py`, gated behind `QF_RUNNER=cli`, off by default). This skips the CLI's own permission prompts because the dashboard runs headless and can't answer them. It assumes a single-tenant-per-team host: anyone who can trigger a pipeline run effectively gets unprompted tool access on that host for the duration of the run. | **High** if `QF_RUNNER=cli` is enabled on a shared/multi-tenant host | Accepted for single-tenant deployments; documented upgrade path is a `settings.json` permission allowlist shipped with the image so the flag can be dropped. Do not enable `QF_RUNNER` on a host shared across teams without that allowlist first. |
| **The coverage collector clones and builds arbitrary registered repos inside the dashboard pod** — `git.Repo.clone_from`/`git clone` followed by `pip install -e .` (Python) or `go build` (Go) run in-process to compute coverage. Registering a repo requires write auth (API key or session), but a compromised or malicious *registered* repo gets arbitrary code execution as the dashboard's ServiceAccount — including its RBAC (`Role` on `batch/jobs`, `pods`, `pods/log`) and reachability to every Secret-backed env var in the pod. | **High** for the blast radius if it's ever hit, gated by write-auth to reach it | Accepted for now; recommended follow-up is running the clone/build/coverage step in a separate, more tightly-scoped job image (the existing `batch/Jobs` RBAC already exists for on-cluster coverage runs — extending that pattern to *this* step, rather than running it in the long-lived dashboard process, is the natural next step) or a sandboxed runner. |
| **Secrets are delivered as plain env vars from a K8s Secret**, not a vault (Vault/External Secrets/sealed-secrets). Anyone who can `kubectl get secret`/`exec` into the pod in this namespace reads them in plaintext; there's no rotation hook, no audit trail beyond the cluster's own Secret-access logging. | Medium | Accepted as the baseline for this chart; `auth.existingSecret` lets an operator substitute a Secret populated by an external-secrets controller without changing this trust model, but the chart itself doesn't do that integration. |
| **`/metrics` has no per-endpoint auth**, matching `/healthz`/`/readyz`. Anyone who can reach the Service (in-cluster, or externally if a Route/Ingress is pointed at it against the README's guidance) can scrape internal counters (pipeline counts, phase timings, etc. — no secrets are exported, but it is a full inventory of dashboard activity). | Low | Accepted; scoped by not exposing the Service externally, not by auth. |
| **`QUALITYFLOW_API_KEY` is a single shared secret with no scoping** — it authenticates CI, peer dashboards, and any human using it as a bypass, all as the same identity, with no per-caller audit trail beyond IP/timestamp in logs. | Medium | Accepted; OIDC (when enabled) gives per-human identity for interactive use, but machine callers still share one key. Rotate it like any other bearer credential; there's no built-in rotation support. |
| **Job creation via the SA's `Role` is a privilege a compromised dashboard process could abuse** beyond its intended coverage-collection use — e.g. to run an arbitrary image as a `batch/Job` in the namespace. Bounded by whatever the namespace's Jobs are themselves allowed to do (their own ServiceAccount, typically `default`), and by the fact that reaching this requires either code execution in the dashboard pod or write-authenticated access to the coverage-collection endpoint. | Medium | Accepted; this is the intended feature (on-cluster coverage runs), the residual risk is scope creep if that RBAC is ever widened without re-reviewing this row. |
| AI model hallucinating test scenarios not grounded in requirements | Medium | Mitigated by review skills (`stp-reviewer`, `std-reviewer`) with structured verdicts; pinned by `eval/` exemplar cases (see below). |
| Stale PII rules missing new data patterns | Low | Periodic review of `pii_rules` in `_defaults.yaml`. |

## Using This Threat Model as an Eval Gate

Concrete checks, automatable via `agent-eval-harness` or CI:

1. **Credential leak check** — grep `outputs/` artifacts and dashboard logs
   for token patterns (`ghp_`, `glpat-`, API key formats). Zero matches = pass.
2. **Auth fail-closed check** — start `ui.py` with `QUALITYFLOW_API_KEY`
   unset and `QF_DEV` unset; expect `SystemExit(1)`, not a running server.
3. **Machine-bypass scope check** — with OIDC enabled, confirm
   `_machine_authorized` only ever succeeds with the correct key
   (`hmac.compare_digest`, not `==`) and that no other header/param accepts
   it.
4. **Referer-bypass regression check** — a request with a spoofed
   `Referer`/`Origin` and no valid API key/session must still 401/403 on
   write endpoints.
5. **`/metrics`, `/healthz`, `/readyz` reachability check** — confirm these
   respond without credentials, and confirm no other path is in
   `_AUTH_EXEMPT_PREFIXES` without a documented reason here.
6. **MCP allowlist check** — validate `mcp.json` against known-good packages.
7. **Prompt injection resistance** — adversarial ticket → normal STP
   structure, adversarial text quoted/sanitized, never executed.
8. **PII sanitization check** — known PII input → sanitized output;
   `pii_exceptions.yaml` entries are the only permitted exceptions.
9. **Generated code safety** — static analysis of test outputs; no new
   findings beyond what pattern files permit.
10. **Deployment integrity** — `deploy.py --dry-run --validate` exits 0;
    `lint-specs` CI job passes.
11. **Config rejection** — `validate.py` rejects a config with invalid
    `feature_toggles` or missing required fields.
12. **Chart hygiene** — `helm lint deploy/helm/qualityflow-dashboard` and
    `helm template` render cleanly; `strategy.type: Recreate` is present on
    the Deployment (regression guard against a future RollingUpdate default
    silently reappearing).

`eval/` already runs the pattern behind check 7/9's "mitigated by review
skills" claims. It holds three exemplar cases for the `stp-reviewer` skill —
two captured from real pipeline runs, one a documented degradation of a real
STP — that pin the reviewer's verdict and critical-finding count before and
after a model change. See `eval/README.md` for the runbook. The remaining
checks above are still manual.
