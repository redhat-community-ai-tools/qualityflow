---
test_case_id: TC-MCP-001
source_key: RHAISTRAT-1245
priority: P1
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_mcp.py
automation_function: TestGeminiMCP::test_mcp_server_connectivity_with_gemini
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-MCP-001: MCP server connectivity with Gemini models

**Objective**: Verify that MCP servers function correctly when
connected to Gemini models through the `remote::gemini` provider.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured
- MCP server configured and accessible (TBD — specific harness
  to be selected by QE team)

**Test Steps**:

1. Configure an MCP server that exposes callable tools
2. Connect the MCP server to the OGX distribution using a
   Gemini model via `remote::gemini` provider
3. Send a user message that should trigger MCP tool invocation
4. Verify the model invokes the MCP tool and returns results

**Expected Results**:

- The MCP server connects successfully to the OGX distribution
- The Gemini model receives tool definitions from the MCP server
- Tool invocation through MCP completes without errors
- The model returns a response that incorporates the MCP tool
  output

**Notes**: To be filled later in the process.
