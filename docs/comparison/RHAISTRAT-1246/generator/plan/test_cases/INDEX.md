# Test Cases Index — Remote Anthropic Provider

**Source**: [TestPlan.md](../TestPlan.md)
**Strategy**: [RHAISTRAT-1246](https://redhat.atlassian.net/browse/RHAISTRAT-1246)

## Quick Stats

- **Total Test Cases**: 16
- **P0 (Critical)**: 6
- **P1 (High)**: 10
- **P2 (Medium)**: 0

## E2E Test Cases

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-E2E-001](TC-E2E-001.md) | Basic inference with native Anthropic provider | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Streaming chat completion with temperature parameters | P0 |
| [TC-E2E-003](TC-E2E-003.md) | Per-request API key override via provider data header | P1 |
| [TC-E2E-004](TC-E2E-004.md) | Anthropic model listing via /v1/models | P1 |
| [TC-E2E-005](TC-E2E-005.md) | Provider listing includes remote::anthropic | P1 |
| [TC-E2E-006](TC-E2E-006.md) | Tool calling via chat completions API | P0 |
| [TC-E2E-007](TC-E2E-007.md) | Tool calling via responses API | P0 |
| [TC-E2E-008](TC-E2E-008.md) | MCP server integration with Anthropic models | P1 |
| [TC-E2E-009](TC-E2E-009.md) | Provider activation via ANTHROPIC_API_KEY env var | P0 |

## Negative Test Cases

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-NEG-001](TC-NEG-001.md) | Invalid Anthropic API key returns authentication error | P0 |
| [TC-NEG-002](TC-NEG-002.md) | Invalid per-request API key override | P1 |
| [TC-NEG-003](TC-NEG-003.md) | Missing ANTHROPIC_API_KEY prevents provider activation | P1 |

## NFR Test Cases

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-NFR-001](TC-NFR-001.md) | API keys not leaked in logs or error responses | P1 |
| [TC-NFR-002](TC-NFR-002.md) | TLS 1.2+ enforced for egress to Anthropic API | P1 |

## Upgrade Test Cases

| Test Case | Title | Priority |
|-----------|-------|----------|
| [TC-UPG-001](TC-UPG-001.md) | Existing remote::openai workaround survives upgrade | P1 |
| [TC-UPG-002](TC-UPG-002.md) | Migration from remote::openai workaround to native provider | P1 |
