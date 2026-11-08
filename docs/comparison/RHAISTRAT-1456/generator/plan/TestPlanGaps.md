---
feature: ogx/codex_sdk
source_key: RHAISTRAT-1456
status: Open
gap_count: 20
last_updated: '2026-06-11'
---
# Gaps — OGX Codex SDK

## Scope & Endpoints

- **Missing ADR** — would be resolved by: ADR specifying detailed API
  contract for Memories API, Compaction API, session ID handling,
  PostgreSQL schema design, and SSE streaming format requirements
- **Codex CLI source code review pending** — would be resolved by:
  design doc analyzing Codex CLI's exact streaming expectations,
  session_id parameter handling, and tool definition schemas from
  source code
- **vLLM parser validation matrix undefined** — would be resolved by:
  design doc or validation plan specifying test matrix (6 tools x
  5 models x streaming/non-streaming modes) with expected parser
  modes per model
- **Hardware target for TTFT requirement unspecified** — would be
  resolved by: feature refinement or acceptance criteria update
  specifying validated GPU types (A100-80, H100) and deployment
  configurations
- **Upstream dependency timelines unknown** — would be resolved by:
  dependency tracking document or design doc with Compaction API
  (PR #5327) and Memories API merge timeline estimates and fallback
  plan details

## Test Strategy & Risks

- **Hardware configuration specification** — strategy mentions
  A100-80/H100 as target hardware for 200ms TTFT but does not
  specify cluster node configuration, GPU count, or memory
  requirements — would be resolved by: ADR (hardware sizing and
  resource allocation)
- **Session ID generation and scoping mechanism** — open question:
  does the Codex CLI support configurable session_id, or does it
  generate IDs internally? — would be resolved by: feature
  refinement (Codex CLI source code review) or API spec (session
  management API contract)
- **Compaction policy parameters** — no sizing guidance for
  compaction trigger thresholds, summary length, or PostgreSQL
  storage limits — would be resolved by: design doc (compaction
  algorithm and storage sizing)
- **Tool-call parser mode per model** — no model-specific parser
  mapping provided — would be resolved by: feature refinement
  (model validation matrix)
- **Codex CLI version compatibility range** — risk mitigation
  mentions pinning version but does not specify which versions are
  validated — would be resolved by: feature refinement (supported
  version matrix)
- **Multi-user session isolation implementation** — NFR mentions
  platform ingress handles authentication but does not specify how
  session IDs are scoped to authenticated identity at OGX
  layer — would be resolved by: ADR (session isolation architecture)

## Environment & Infrastructure

- **Target OSS model selection and validation matrix** — would be
  resolved by: ADR documenting which specific model(s) passed
  validation across all six Codex CLI tools
- **Upstream Compaction API (PR #5327) merge timeline** — would be
  resolved by: design doc or ADR describing fallback plan if upstream
  not merged before code freeze
- **Upstream Memories API specification** — would be resolved by:
  design doc detailing session store schema, compaction policy
  parameters, and PostgreSQL sizing
- **Codex CLI session_id semantics (client vs server generated)** —
  would be resolved by: design doc after Codex CLI source review
- **SSE streaming fidelity fix implementation details** — would be
  resolved by: design doc describing delta object format, incremental
  tool_calls chunking, and compatibility testing approach
- **Session isolation implementation** — would be resolved by: design
  doc or security ADR
- **PostgreSQL capacity planning** — would be resolved by: design doc
  with storage calculations and retention policies
- **vLLM tool-call parser mode selection per model** — would be
  resolved by: ADR documenting parser mode compatibility matrix
- **Authentication enforcement at platform ingress** — would be
  resolved by: ADR or deployment guide
