---
feature: ogx/codex_sdk
source_key: RHAISTRAT-1456
source_type: strat
status: Reviewed
author: OGX Core
components:
- Documentation
- OGX Core
additional_docs: []
last_updated: '2026-06-12'
version: 1.0.0
reviewers: []
---
# OGX Codex SDK Test Plan

**OGX Core – OpenAI Codex CLI Compatibility Testing**

**Strategy**: [RHAISTRAT-1456](https://redhat.atlassian.net/browse/RHAISTRAT-1456)

---

## 1. Executive Summary

### 1.1 Purpose

This test plan validates OGX's ability to serve as a drop-in
OpenAI-compatible backend for the OpenAI Codex CLI, enabling enterprise
customers to run agentic coding workflows against self-hosted OSS models
on Red Hat OpenShift AI (RHOAI). The feature bridges the gap between
customer adoption of the Codex CLI for agentic coding and the need to
run those workflows on open-source models without vendor lock-in to
Anthropic or OpenAI hosted APIs.

Testing focuses on three core capability areas: SSE streaming fidelity
for tool-call deltas, server-side stateful session management via the
Memories and Compaction APIs, and tool-call interoperability for the
six Codex CLI tools. Validation ensures at least one target OSS model
can complete an end-to-end multi-step coding task through the
OGX proxy.

### 1.2 Scope

#### In Scope (OGX Core Responsibilities)

- SSE streaming from OGX's `/v1/chat/completions` endpoint
  compatible with OpenAI format and Codex CLI parsing expectations
- Server-side stateful session management via `session_id` that
  persists conversation context across multi-turn tool-calling
  sequences
- Integration of Compaction API and Memories API for conversation
  history compression and session state persistence
- Tool-call interoperability for Codex CLI's six core tools: `bash`,
  `read_file`, `write_file`, `edit_file`, `grep_search`, `glob_search`
- Session recovery after network disconnect using `session_id`
- PostgreSQL-backed session state storage leveraging OGX's
  existing persistent storage backend
- Validation of at least one target OSS model for end-to-end Codex
  CLI task completion
- TTFT performance validation (target: <200ms p95)
- Compatibility with upstream open-source Codex CLI as-is

#### Out of Scope (Other Teams)

- Custom Codex CLI modifications or forks
- Model fine-tuning for tool-calling capabilities
- Multi-user session isolation at the OGX application layer
  (handled by RHOAI platform ingress)
- Integration with proprietary coding agent SDKs (Claude Code, Cursor)
- Codex CLI permission model enforcement within OGX
  (client-side responsibility)
- Multi-model routing based on task type (P2, not MVP)

### 1.3 Test Objectives

1. Verify that OGX's `/v1/chat/completions` endpoint emits SSE
   streams with OpenAI-format `delta` objects containing incremental
   `tool_calls` arrays that Codex CLI can parse without error
2. Confirm that server-side session state persists conversation context
   across 5+ chained tool calls without requiring the Codex CLI to
   resend full conversation history
3. Validate tool-call interoperability: all six Codex CLI tools
   (`bash`, `read_file`, `write_file`, `edit_file`, `grep_search`,
   `glob_search`) return JSON arguments matching their parameter
   schemas without schema violations
4. Test session recovery: verify that sessions resume with full
   conversation context intact after network interruption using
   `session_id`
5. Measure streaming TTFT performance and confirm p95 TTFT is under
   200ms on validated hardware configurations
6. Validate end-to-end Codex CLI workflow: confirm at least one target
   OSS model successfully completes a multi-step coding task (read
   failing test, navigate repo, write patch, verify test passes)
7. Verify that Compaction API correctly compresses long conversation
   histories when context window approaches model limits

---

## 2. Test Strategy

### 2.1 Test Levels

- **API Integration Testing** — validate OGX's
  `/v1/chat/completions` endpoint compatibility with OpenAI format,
  SSE streaming behavior, tool-call delta formatting, and session
  management API calls
- **Data Validation Testing** — verify PostgreSQL session state
  persistence, conversation turn storage, compaction policy execution,
  and session recovery from stored state
- **Functional Testing** — validate tool-call interoperability for
  all six Codex tools, multi-turn conversation context retention,
  session ID mapping, and end-to-end Codex CLI task completion
- **Performance Testing** — measure streaming TTFT, latency per HTTP
  hop, concurrent session handling, and PostgreSQL query performance
  under load
- **Integration Testing** — verify OGX-to-vLLM communication,
  tool-call parser compatibility across target models, operator-
  provisioned infrastructure, and Codex CLI connectivity

### 2.2 Test Types

- **Positive Testing** — valid Codex CLI sessions with 5+ tool calls,
  successful session recovery, correct tool-call JSON parsing, and
  end-to-end task completion (read test, navigate, write patch, verify)
- **Negative Testing** — invalid tool schemas, malformed SSE streams,
  session ID mismatches, context window overflow without compaction,
  network interruptions mid-stream, unsupported tool-call parser modes
- **Boundary Testing** — maximum conversation length (token limits),
  concurrent session limits, PostgreSQL storage capacity, tool-call
  chain depth, and TTFT at p95/p99 latencies
- **Regression Testing** — ensure existing `/v1/chat/completions`
  behavior for non-Codex clients remains intact, no breaking changes
  to OGX API surface, preserved HPA/PDB functionality

### 2.3 Test Priorities

- **P0 (Critical)** — SSE streaming compatibility with Codex CLI,
  server-side session persistence across 5+ turns, at least one OSS
  model passing end-to-end validation, TTFT under 200ms on target
  hardware
- **P1 (High)** — all six Codex tools producing valid JSON schemas,
  session recovery after network disconnect, compaction of long
  conversations, tool-call parser compatibility per model
- **P2 (Medium)** — multi-model routing based on task type,
  documentation coverage, operator CR validation for PostgreSQL
  config, performance characterization across hardware tiers

---

## 3. Test Environment

### 3.1 Test Cluster Configuration

- OpenShift cluster with RHOAI 3.5 deployed
- OGX distribution version: v0.5.0+rhai0 (ODH fork)
- vLLM serving runtime with `--tool-call-parser` enabled (supporting
  `hermes`, `mistral`, `llama3_json`, `pythonic` formats)
- PostgreSQL 5432/TCP for session state persistence
- GPU hardware: A100-80GB or H100 for TTFT validation
- Network: ClusterIP services on port 8321 (OGX), port 8000
  (vLLM), port 5432 (PostgreSQL)

### 3.2 Test Data Requirements

- **Codex CLI tool definitions (JSON Schema)**: `bash`, `read_file`,
  `write_file`, `edit_file`, `grep_search`, `glob_search` with
  parameter schemas
- **Sample code repositories**: repos with failing tests for multi-step
  coding task validation (Codex CLI navigates, patches, verifies)
- **Session state test data**: conversation turns with 5+ chained tool
  calls for session persistence validation
- **SSE streaming validation data**: OpenAI-format delta objects with
  incremental `tool_calls` arrays
- **Model artifacts**: at least one of Qwen 3.5, Mistral Small 4,
  Llama 3.3 70B, Nemotron 3 Super, GPT-oss
- **PostgreSQL schema**: session store tables for conversation state
  (`session_id`, turns)

### 3.3 Test Users

- **Service accounts** with RBAC permissions to create
  LlamaStackDistribution CRs and InferenceService/LLMInferenceService
  CRs
- **Data scientist users** with project namespace access for deploying
  OGX instances
- **Authenticated users** for session isolation validation (multiple
  concurrent Codex CLI sessions)
- **Network disconnect scenario users** for session recovery testing

---

## 4. API Endpoints Under Test

| Endpoint | Method | Purpose | Priority |
| ---------- | -------- | --------- | ---------- |
| `/v1/chat/completions` (OGX) | POST | OpenAI-compatible chat completions endpoint on port 8321; handles SSE streaming and tool-call responses | P0 |
| Memories API | POST/GET | Server-side session state persistence; stores conversation turns per `session_id` | P0 |
| PostgreSQL session store | SQL | Persistent storage for session state (conversation turns, session metadata); port 5432/TCP | P0 |
| Session ID parameter | Parameter | Client-provided or server-generated identifier for session tracking and recovery | P0 |
| `/v1/chat/completions` (vLLM) | POST | Underlying inference endpoint on port 8000; OGX proxies to this | P0 |
| Compaction API (PR #5327) | POST | Compresses long conversation histories when approaching context window limits | P1 |
| vLLM `--tool-call-parser` | CLI Flag | Tool-call parsing modes: `hermes`, `mistral`, `llama3_json`, `pythonic` | P1 |
| LlamaStackDistribution CR | K8s CRD | Custom resource managed by llama-stack-k8s-operator; provisions OGX instances | P1 |
| `config.yaml` (OGX) | Config | Distribution config; must register Memories and Compaction providers | P1 |

---

## 5. Test Cases

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

| Category | Test Cases | Priority Distribution |
| ---------- | ------------ | ---------------------- |
| SSE Streaming (TC-STREAM) | 4 | 2 P0, 2 P1 |
| Session Management (TC-SESS) | 4 | 2 P0, 2 P1 |
| Tool-Call Interoperability (TC-TOOL) | 4 | 1 P0, 3 P1 |
| Conversation Compaction (TC-COMPACT) | 3 | 2 P1, 1 P2 |
| Performance (TC-PERF) | 3 | 1 P0, 1 P1, 1 P2 |
| End-to-End (TC-E2E) | 4 | 3 P0, 1 P1 |
| Regression (TC-REGR) | 2 | 2 P1 |
| Infrastructure (TC-INFRA) | 3 | 2 P1, 1 P2 |
| **Total** | **27** | **9 P0, 15 P1, 3 P2** |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

- `TC-STREAM` — SSE streaming fidelity and OpenAI format compliance
- `TC-SESS` — session management, persistence, and recovery
- `TC-TOOL` — tool-call interoperability for six Codex CLI tools
- `TC-COMPACT` — conversation history compaction
- `TC-PERF` — TTFT and latency performance validation
- `TC-E2E` — end-to-end Codex CLI workflow scenarios
- `TC-REGR` — regression tests for non-Codex client compatibility
- `TC-INFRA` — operator CR, PostgreSQL, and infrastructure validation

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Each scenario maps to one or more TC-E2E-*.md test cases
generated by `/test-plan-create-cases`.

> **Requirement**: At least one E2E scenario MUST be generated for
> each P0 endpoint in Section 4.
> E2E scenarios will be filled by `/test-plan-create-cases`.

### 6.1 Scenario Summary

| ID | Scenario | Endpoints Covered | Priority |
| ---- | ---------- | ------------------- | ---------- |
| TC-E2E-001 | Multi-step coding task — fix failing test | /v1/chat/completions (OGX), /v1/chat/completions (vLLM), Memories API, PostgreSQL session store, Session ID parameter | P0 |
| TC-E2E-002 | Session recovery during coding task | /v1/chat/completions (OGX), Memories API, PostgreSQL session store, Session ID parameter | P0 |
| TC-E2E-003 | Multi-tool file exploration workflow | /v1/chat/completions (OGX), /v1/chat/completions (vLLM), Session ID parameter | P0 |
| TC-E2E-004 | Concurrent Codex CLI sessions | /v1/chat/completions (OGX), PostgreSQL session store, Session ID parameter | P1 |

### 6.2 E2E Coverage Matrix

| Endpoint (from Section 4) | E2E Scenarios |
| ---------------------------- | --------------- |
| `/v1/chat/completions` (OGX) | TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-004 |
| Memories API | TC-E2E-001, TC-E2E-002 |
| PostgreSQL session store | TC-E2E-001, TC-E2E-002, TC-E2E-004 |
| Session ID parameter | TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-004 |
| `/v1/chat/completions` (vLLM) | TC-E2E-001, TC-E2E-003 |
| Compaction API (PR #5327) | — |
| vLLM `--tool-call-parser` | — |
| LlamaStackDistribution CR | — |
| `config.yaml` (OGX) | — |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification.

### 7.1 Disconnected/Air-Gapped

**Not Applicable** — this feature depends on real-time model serving
via vLLM over HTTP (port 8000) and OGX distribution service
(port 8321) within the cluster. No external registry dependencies,
image pulls at runtime, or catalog sources are required. PostgreSQL
(port 5432) is internal. Codex CLI is an external client connecting
via base URL, not a component requiring air-gapped installation.

### 7.2 Upgrade/Migration

- **Session state schema migration** — PostgreSQL stores conversation
  turns as rows; schema changes (e.g., adding compaction metadata,
  session ID scoping) must support zero-downtime migration and
  backwards-compatible queries
- **API version compatibility** — Memories API and Compaction API are
  additive; verify existing `/v1/chat/completions` clients are
  unaffected during rollout
- **Operator upgrade path** — validate that LlamaStackDistribution CR
  updates (new config.yaml keys for Memories/Compaction providers) do
  not break existing LLSD instances
- **Downstream patch handling** — if Compaction API/Memories API are
  cherry-picked into RHOAI fork, test upgrade path when upstream
  merges occur (patch removal, reconciliation)
- **Rollback scenarios** — session state written by new version must
  be readable by previous version (or graceful degradation)

### 7.3 Performance/Scalability

- **Streaming TTFT latency** — p95 TTFT must be under 200ms on
  validated hardware (A100-80/H100); measure OGX proxy
  overhead (target <5ms per hop)
- **Concurrent session handling** — validate PostgreSQL performance
  with hundreds of concurrent sessions, each ~50 turns; measure
  query latency for session retrieval and compaction trigger overhead
- **Large dataset behavior** — test conversation compaction near
  model context window limits and verify compaction policy activates
  correctly
- **Multi-turn latency** — measure end-to-end latency for 5+ chained
  tool calls; ensure session state retrieval does not introduce
  >10ms overhead per turn
- **vLLM continuous batching impact** — characterize TTFT degradation
  as concurrent Codex sessions increase (interaction with vLLM batch
  scheduler)

### 7.4 RBAC/Authorization

- **Session isolation per user** — session IDs must be scoped to
  authenticated user identity (enforced at platform ingress via
  kube-rbac-proxy or Gateway API ext_authz); test cross-user session
  access attempts fail
- **OGX service account permissions** — validate operator-
  provisioned ServiceAccount has minimal required permissions for
  PostgreSQL access, HPA control, PVC management
- **Multi-tenant namespace isolation** — verify LlamaStackDistribution
  CR in user's data science project namespace cannot access sessions
  from other namespaces
- **Tool execution permissions** — Codex CLI executes tools client-
  side; OGX only routes tool definitions. Verify OGX
  does not log sensitive tool outputs (e.g., file contents from
  `read_file`)
- **Session-store principal binding** — verify the backend binds each
  `session_id` to the authenticated principal and rejects replayed or
  guessed session IDs owned by another user, including service account
  flows and LlamaStackDistribution-managed deployments
- **Sensitive tool log redaction** — verify request, response, and
  audit logs redact tool names and argument values for all Codex CLI
  tools, not only `read_file`, before data reaches platform log
  aggregation

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
| ------ | -------- | ------------- | ------------ |
| Upstream Compaction API (PR #5327) and Memories API not merged before RHOAI 3.5 code freeze | High | Medium | Cherry-pick upstream PRs into RHOAI fork; carry as downstream patches until next upstream sync; validate patch compatibility weekly |
| No target OSS model reliably produces valid tool calls for all six Codex tools | High | Medium | Validate tool-calling quality early against all five candidate models; document partial support and recommend specific models for specific tool subsets |
| Codex CLI updates its API expectations after initial validation | Medium | Low | Pin Codex CLI version for validation; monitor upstream releases; re-validate on minor/major releases; establish regression test suite |
| 200ms TTFT target not achievable on customer hardware configurations | Medium | Medium | Specify supported hardware configurations; document TTFT expectations per hardware tier; flag model and hardware dependency |
| PostgreSQL session store becomes bottleneck at scale (>500 concurrent sessions) | Medium | Low | Load test with 1000 concurrent sessions; implement connection pooling; add read replicas if needed; validate compaction reduces storage growth |
| vLLM tool-call parser incompatibility with specific model outputs | Medium | Medium | Validate each target model against all four vLLM parser modes; document required parser mode per model; create model-specific validation matrix |
| SSE streaming fidelity fixes introduce breaking changes for existing non-Codex clients | Medium | Low | Regression test existing clients; implement feature flag for Codex-specific SSE formatting if necessary; validate backwards compatibility in CI |
| Session recovery fails due to session ID collision or stale state | Low | Low | Implement session ID namespacing (user identity + timestamp + UUID); add session expiration policy (24h TTL); test recovery with expired sessions |

---

## 9. Test Environment Requirements

### 9.1 Infrastructure

- LlamaStackDistribution CR deployed via llama-stack-k8s-operator in
  data science project namespace
- vLLM InferenceService or LLMInferenceService serving target OSS model
- PostgreSQL instance for KV stores, SQL stores, agent state, and
  session persistence
- Gateway API HTTPRoute or ClusterIP service for Codex CLI endpoint
  access
- HPA (Horizontal Pod Autoscaler) for OGX instances
- PodDisruptionBudget for availability during rolling updates
- NetworkPolicies for pod-to-pod communication (OGX, vLLM,
  PostgreSQL)
- PVCs for persistent storage

### 9.2 Configuration

- `OPENAI_BASE_URL`: environment variable pointing to OGX
  service endpoint (port 8321)
- `config.yaml`: OGX distribution config with Memories API
  and Compaction API providers registered
- vLLM `--tool-call-parser` flag set to appropriate mode per model
- `session_id` parameter for server-side session management
- LlamaStackDistribution CR YAML with PostgreSQL connection config
- kube-rbac-proxy or Gateway API ext_authz for authentication at
  platform ingress layer

### 9.3 Test Tools

- **OpenAI Codex CLI** (upstream open-source, Apache 2.0, pinned
  version)
- **curl/httpie** for SSE streaming validation and endpoint testing
- **psql** for PostgreSQL session state inspection
- **kubectl/oc** for CR creation, service inspection, log viewing
- **Network disruption tools** for session recovery testing (iptables,
  tc, or pod kill)
- **TTFT measurement tools** for streaming latency validation
- **JSON Schema validators** for tool-call parameter validation
- **Log aggregation tools** for FastAPI/Uvicorn and vLLM logs

---

## 10. Appendix

### 10.1 Test Case Summary

| Category | Total | P0 | P1 | P2 |
| ---------- | ------- | ---- | ---- | ----- |
| SSE Streaming (TC-STREAM) | 4 | 2 | 2 | 0 |
| Session Management (TC-SESS) | 4 | 2 | 2 | 0 |
| Tool-Call Interoperability (TC-TOOL) | 4 | 1 | 3 | 0 |
| Conversation Compaction (TC-COMPACT) | 3 | 0 | 2 | 1 |
| Performance (TC-PERF) | 3 | 1 | 1 | 1 |
| End-to-End (TC-E2E) | 4 | 3 | 1 | 0 |
| Regression (TC-REGR) | 2 | 0 | 2 | 0 |
| Infrastructure (TC-INFRA) | 3 | 0 | 2 | 1 |
| **Total** | **27** | **9** | **15** | **3** |

### 10.2 Endpoint Coverage

| Endpoint | Test Cases | Coverage |
| ---------- | ------------ | ---------- |
| `/v1/chat/completions` (OGX) | TC-STREAM-001, TC-STREAM-002, TC-STREAM-003, TC-STREAM-004, TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-004, TC-REGR-001 | |
| Memories API | TC-SESS-001, TC-SESS-002, TC-SESS-003, TC-SESS-004, TC-E2E-001, TC-E2E-002 | |
| PostgreSQL session store | TC-SESS-001, TC-SESS-002, TC-SESS-003, TC-PERF-003, TC-E2E-001, TC-E2E-002, TC-E2E-004 | |
| Session ID parameter | TC-SESS-001, TC-SESS-002, TC-SESS-003, TC-SESS-004, TC-E2E-001, TC-E2E-002, TC-E2E-003, TC-E2E-004 | |
| `/v1/chat/completions` (vLLM) | TC-PERF-001, TC-PERF-002, TC-E2E-001, TC-E2E-003 | |
| Compaction API (PR #5327) | TC-COMPACT-001, TC-COMPACT-002, TC-COMPACT-003 | |
| vLLM `--tool-call-parser` | TC-TOOL-004 | |
| LlamaStackDistribution CR | TC-INFRA-001, TC-REGR-002 | |
| `config.yaml` (OGX) | TC-INFRA-002 | |

### 10.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-06-11 | Initial test plan |

---

**End of Test Plan**
