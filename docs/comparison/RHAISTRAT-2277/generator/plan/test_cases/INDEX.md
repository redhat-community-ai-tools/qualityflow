# Test Case Index — OGX to Praxis Migration

Parent test plan: [TestPlan.md](../TestPlan.md)

## Quick Stats

| Metric | Count |
|--------|-------|
| Total test cases | 10 |
| P0 (Critical) | 9 |
| P1 (High) | 1 |
| P2 (Medium) | 0 |

## End-to-End (TC-E2E)

| Test Case ID | Title | Priority |
|--------------|-------|----------|
| [TC-E2E-001](TC-E2E-001.md) | Greenfield 3.6 serves /v1/responses from Praxis with no competing implementation | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Greenfield 3.6 routes /v1/embeddings through Praxis to the configured backend | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Pre-existing file and vector store IDs resolve identically through Praxis after upgrade | P0 |
| [TC-E2E-004](TC-E2E-004.md) | Write path routes each resource to exactly one backend with no dual-write | P0 |
| [TC-E2E-005](TC-E2E-005.md) | RAG file_search through Praxis returns citations from pre-upgrade OGX data | P0 |
| [TC-E2E-006](TC-E2E-006.md) | Rollback reverts external routing to OGX within five minutes with state intact | P1 |

## Negative and Error Paths (TC-NEG)

| Test Case ID | Title | Priority |
|--------------|-------|----------|
| [TC-NEG-001](TC-NEG-001.md) | OGX port 8321 is unreachable from outside the cluster and unauthenticated calls are rejected | P0 |
| [TC-NEG-002](TC-NEG-002.md) | Praxis returns an OpenAI-compatible error when OGX is unreachable | P0 |
| [TC-NEG-003](TC-NEG-003.md) | Tenant isolation holds across the Praxis-to-OGX delegation boundary | P0 |

## Upgrade Testing (TC-UPG)

| Test Case ID | Title | Priority |
|--------------|-------|----------|
| [TC-UPG-001](TC-UPG-001.md) | The 3.5-to-3.6 routing switchover preserves state and opens no traffic black hole | P0 |

## Upgrade Phase Coverage

| Test Case | Phase | Rationale |
|-----------|-------|-----------|
| TC-E2E-003 | both | Establishes the pre-upgrade baseline and re-verifies the same IDs after upgrade |
| TC-E2E-004 | post | Write ownership is only defined once Praxis fronts OGX |
| TC-E2E-005 | post | RAG through Praxis exists only after the switchover |
| TC-E2E-006 | post | Rollback is only meaningful once routing points at Praxis |
| TC-UPG-001 | both | Probes continuously across the version boundary |

Test cases without a phase — TC-E2E-001, TC-E2E-002, TC-NEG-001, TC-NEG-002, TC-NEG-003 — verify
behaviour that is identical regardless of how the cluster reached 3.6.
