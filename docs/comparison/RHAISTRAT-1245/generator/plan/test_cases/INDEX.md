# Test Case Index — Remote Gemini Provider

**Parent Test Plan**: [TestPlan.md](../TestPlan.md)

## Quick Stats

- **Total Test Cases**: 24
- **P0 (Critical)**: 16
- **P1 (High)**: 6
- **P2 (Medium)**: 2

---

## Provider Availability (TC-PROV)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-PROV-001](TC-PROV-001.md) | Verify remote::gemini provider listed in /v1/providers | P0 |
| [TC-PROV-002](TC-PROV-002.md) | Verify provider configuration without network.headers workaround | P0 |
| [TC-PROV-003](TC-PROV-003.md) | Verify conditional provider activation with GEMINI_API_KEY | P0 |

## Chat Completions (TC-CHAT)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-CHAT-001](TC-CHAT-001.md) | Non-streaming chat completions with Gemini | P0 |
| [TC-CHAT-002](TC-CHAT-002.md) | Streaming chat completions with Gemini | P0 |
| [TC-CHAT-003](TC-CHAT-003.md) | Temperature parameter controls response variability | P0 |

## Embeddings API (TC-EMB)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-EMB-001](TC-EMB-001.md) | Successful embedding generation via remote::gemini | P0 |
| [TC-EMB-002](TC-EMB-002.md) | Embeddings handle missing usage statistics gracefully | P0 |

## Tool Calling (TC-TOOL)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-TOOL-001](TC-TOOL-001.md) | Tool calling via /v1/chat/completions with Gemini | P0 |
| [TC-TOOL-002](TC-TOOL-002.md) | Tool calling with unsupported JSON schema fields | P2 |

## Per-Request Authentication (TC-AUTH)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-AUTH-001](TC-AUTH-001.md) | Per-request API key override via x-ogx-provider-data | P1 |
| [TC-AUTH-002](TC-AUTH-002.md) | Invalid per-request API key returns error | P1 |

## MCP Server Integration (TC-MCP)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-MCP-001](TC-MCP-001.md) | MCP server connectivity with Gemini models | P1 |

## Deployment (TC-DEP)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-DEP-001](TC-DEP-001.md) | build.yaml includes remote::gemini provider | P0 |
| [TC-DEP-002](TC-DEP-002.md) | config.yaml conditional activation pattern | P0 |
| [TC-DEP-003](TC-DEP-003.md) | OGX K8s Operator ConfigMap injection for GEMINI_API_KEY | P0 |

## Regression (TC-REG)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-REG-001](TC-REG-001.md) | Existing remote::openai configurations unaffected | P0 |
| [TC-REG-002](TC-REG-002.md) | Other providers unaffected by remote::gemini addition | P1 |

## Security (TC-SEC)

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-SEC-001](TC-SEC-001.md) | Gemini API key not exposed in pod specs or logs | P1 |
| [TC-SEC-002](TC-SEC-002.md) | TLS 1.2+ enforced for Gemini API egress | P2 |

## End-to-End Scenarios (TC-E2E)

| Test Case | Title | Priority |
| ----------- | ------- | ---------- |
| [TC-E2E-001](TC-E2E-001.md) | Deploy OGX with Gemini and run chat completion | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Full tool calling workflow with Gemini | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Embedding generation end-to-end with Gemini | P0 |
| [TC-E2E-004](TC-E2E-004.md) | Multi-tenant per-request API key override | P1 |

## Upgrade Testing

All test cases are tagged with `upgrade_phase` in their
frontmatter to support upgrade/migration testing:

- **`post`**: New `remote::gemini` functionality (22 TCs) —
  only valid after upgrade to RHOAI 3.5 EA2+
- **`both`**: Regression tests (2 TCs: TC-REG-001, TC-REG-002) —
  should pass on both pre-upgrade and post-upgrade distributions
