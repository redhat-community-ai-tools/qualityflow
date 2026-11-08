---
feature: ogx/codex_sdk
source_key: RHAISTRAT-1456
review_date: '2026-06-12'
verdict: Ready
total_score: 9
revision_cycle: 1
max_cycles: 2
---
# Test Plan Review — OGX Codex SDK

## Score Table

| Criterion | Score | Evidence | Rationale |
| ----------- | ------- | ---------- | ----------- |
| Specificity | 2 | P0 names SSE streaming with Codex CLI, session persistence across 5+ turns, TTFT <200ms on A100-80/H100. Risks name Compaction API PR #5327 merge timeline, vLLM tool-call parser mode incompatibility per model, Codex CLI version drift. Section 8 risk "upstream Compaction API (PR #5327) and Memories API not merged before RHOAI 3.5 code freeze" is unique to this feature. | Swap test: pasting "vLLM tool-call parser incompatibility with specific model outputs" into a database migration test plan makes no sense. All priority definitions reference feature-specific failure modes (SSE stream parsing, session_id collision, tool-call JSON schema violations), not generic language. |
| Grounding | 2 | All ports (8000 vLLM, 8321 OGX, 5432 PostgreSQL), model names (Qwen 3.5, Mistral Small 4, Llama 3.3 70B, Nemotron 3 Super, GPT-oss), parser modes (hermes, mistral, llama3_json, pythonic), six Codex tools, acceptance criteria (5+ chained tool calls, session_id, TTFT <200ms), architecture (vLLM continuous batching, OGX FastAPI/Uvicorn proxy, kube-rbac-proxy/ext_authz) — all traceable to strategy text. | OGX version "v0.5.0+rhai0" is a minor extrapolation (ODH fork naming convention) but not fabricated. No invented API signatures, no assumed versions without basis. Unknowns (exact Codex CLI version, PostgreSQL schema DDL) are left as requirements in test data section, not guessed at. 0 fabrications identified. |
| Scope Fidelity | 2 | Strategy deliverables mapped: SSE streaming fidelity → Obj 1, stateful session management → Obj 2, tool-call interoperability → Obj 3, session recovery → Obj 4, TTFT performance → Obj 5, E2E validation → Obj 6, compaction → Obj 7. Out-of-scope list matches strategy verbatim (custom CLI mods, fine-tuning, multi-user isolation at app layer, proprietary SDKs, permission model enforcement). | No orphans in either direction. Every strategy deliverable has a corresponding test objective. No test objectives reference scope not in the strategy. Out-of-scope item "Multi-model routing based on task type (P2, not MVP)" correctly defers to P2 per strategy. |
| Actionability | 1 | Concrete: RHOAI 3.5, PostgreSQL 5432/TCP, A100-80GB/H100 GPUs, specific tools (curl/httpie, psql, oc, JSON Schema validators), six Codex tools with parameter schemas, ClusterIP service ports. Test users have defined roles (service accounts, data scientist, authenticated users). | A platform engineer would ask: "Which exact OCP version?", "Which Codex CLI version to pin?", "What's the LlamaStackDistribution CR YAML?", "What PostgreSQL session store schema (DDL)?" — approximately 4 questions. Not at the 5+ threshold for a zero, but gaps remain. No sample YAML, no sample JSON test data, no DDL provided. |
| Consistency | 2 | Cross-checks: (1) All 9 Section 4 entries are within Section 1.2 scope. (2) Test levels in 2.1 (API Integration, Data Validation, Functional, Performance, Integration) match interface types in Section 4 (REST endpoints, SQL store, CLI flag, K8s CRD, config file). (3) Priority assignments match 2.3 definitions — P0 items are streaming/session/model/TTFT, P1 items are tools/recovery/compaction/parser. (4) Section 10.2 lists all 9 endpoints from Section 4. (5) NFR categories properly addressed — Disconnected marked N/A with justification (no external dependencies), Upgrade/Performance/RBAC substantive. (6) Section 6 has placeholder text — pre-create-cases state, acceptable. | No contradictions found. No orphan endpoints. No mismatched priorities. Section 7.1 N/A justification is correct — feature operates within cluster on internal services only. |

**Total: 9/10 — Verdict: Ready**

## Key Observations

- Strong grounding: the test plan closely follows the strategy text
  without fabricating technical details. Ports, model names, tools,
  parser modes, and acceptance criteria are all traceable.
- Scope fidelity is excellent with no orphan deliverables or scope
  creep. The P2 deferral for multi-model routing is explicitly noted.
- Actionability is the single weakness: while the plan names RHOAI 3.5
  and GPU types, it lacks pinned versions for OCP and Codex CLI, and
  provides no sample CR YAML or PostgreSQL DDL. These are reasonable
  gaps for a Draft-stage plan sourced from a strategy.
- The 20 gaps documented in TestPlanGaps.md correctly identify these
  missing details and name the document types that would resolve them.
- Pre-create-cases state: Sections 5, 6, 10.1 are empty placeholders,
  which is expected and does not affect the rubric score.

## Recommendations

1. **Pin Codex CLI version** — add a specific version or commit SHA to
   Section 3.1 once validation testing begins
2. **Add sample CR YAML** — include a minimal LlamaStackDistribution CR
   example in Section 9.2 or as an appendix
3. **Add PostgreSQL schema** — include DDL for session store tables once
   Memories API design lands
4. **Specify OCP version** — pin to a specific 4.x release once RHOAI
   3.5 target platform is confirmed

These are improvements for the next revision, not blockers for the Ready verdict.

---

**End of Review**
