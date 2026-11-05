# Remote Gemini Provider

Enable native `remote::gemini` provider support in the RHOAI OGX
distribution for proper Gemini model integration.

## Links

- **Strategy**: [RHAISTRAT-1245](https://redhat.atlassian.net/browse/RHAISTRAT-1245)
- **Test Plan**: [TestPlan.md](TestPlan.md)

## Overview

This test plan covers validation of the `remote::gemini` inference provider
included in the RHOAI OGX (formerly Llama Stack) distribution image. The
provider enables native Gemini model support with proper authentication,
embedding handling, tool calling compatibility, and per-request API key override.

## Test Cases

- **Index**: [test_cases/INDEX.md](test_cases/INDEX.md)
- **Total**: 24 test cases (16 P0, 6 P1, 2 P2)
- **Categories**: PROV, CHAT, EMB, TOOL, AUTH, MCP, DEP, REG, SEC, E2E
