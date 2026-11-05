# Test Case Index — OGX Codex SDK

**Parent Test Plan**: [TestPlan.md](../TestPlan.md)

## Quick Stats

| Metric | Count |
| -------- | ------- |
| Total Test Cases | 27 |
| P0 (Critical) | 8 |
| P1 (High) | 15 |
| P2 (Medium) | 4 |

---

## SSE Streaming (TC-STREAM)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-STREAM-001](TC-STREAM-001.md) | SSE streaming delta format compliance | P0 |
| [TC-STREAM-002](TC-STREAM-002.md) | Multi-tool streaming interleave | P0 |
| [TC-STREAM-003](TC-STREAM-003.md) | Malformed SSE stream handling | P1 |
| [TC-STREAM-004](TC-STREAM-004.md) | Non-streaming fallback | P1 |

## Session Management (TC-SESS)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-SESS-001](TC-SESS-001.md) | Session persistence across 5+ chained tool calls | P0 |
| [TC-SESS-002](TC-SESS-002.md) | Session recovery after network disconnect | P0 |
| [TC-SESS-003](TC-SESS-003.md) | Session ID collision prevention | P1 |
| [TC-SESS-004](TC-SESS-004.md) | Invalid session_id handling | P1 |

## Tool-Call Interoperability (TC-TOOL)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-TOOL-001](TC-TOOL-001.md) | All six Codex tools produce valid JSON arguments | P0 |
| [TC-TOOL-002](TC-TOOL-002.md) | Tool-call chaining across turns | P1 |
| [TC-TOOL-003](TC-TOOL-003.md) | Invalid tool schema rejection | P1 |
| [TC-TOOL-004](TC-TOOL-004.md) | Tool-call parser mode compatibility per model | P1 |

## Conversation Compaction (TC-COMPACT)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-COMPACT-001](TC-COMPACT-001.md) | Compaction triggers at context window limit | P1 |
| [TC-COMPACT-002](TC-COMPACT-002.md) | Post-compaction context accuracy | P1 |
| [TC-COMPACT-003](TC-COMPACT-003.md) | Compaction with concurrent sessions | P2 |

## Performance (TC-PERF)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-PERF-001](TC-PERF-001.md) | TTFT under 200ms at p95 | P0 |
| [TC-PERF-002](TC-PERF-002.md) | OGX proxy overhead | P1 |
| [TC-PERF-003](TC-PERF-003.md) | Concurrent session performance | P2 |

## End-to-End Scenarios (TC-E2E)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-E2E-001](TC-E2E-001.md) | Multi-step coding task — fix failing test | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Session recovery during coding task | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Multi-tool file exploration workflow | P0 |
| [TC-E2E-004](TC-E2E-004.md) | Concurrent Codex CLI sessions | P1 |

## Regression (TC-REGR)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-REGR-001](TC-REGR-001.md) | Non-Codex client compatibility | P1 |
| [TC-REGR-002](TC-REGR-002.md) | HPA and PDB functionality preserved | P1 |

## Infrastructure (TC-INFRA)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-INFRA-001](TC-INFRA-001.md) | LlamaStackDistribution CR deployment with PostgreSQL | P1 |
| [TC-INFRA-002](TC-INFRA-002.md) | config.yaml Memories and Compaction provider registration | P1 |
| [TC-INFRA-003](TC-INFRA-003.md) | NetworkPolicy for pod-to-pod communication | P2 |
