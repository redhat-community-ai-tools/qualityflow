---
test_case_id: TC-TOOL-003
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-TOOL-003: Invalid tool schema rejection

**Objective**: Verify that Codex CLI gracefully handles tool_calls
with invalid or missing required parameters in function.arguments.

**Test Steps**:

1. POST to `/v1/chat/completions` with all six tool definitions and
   a deliberately ambiguous prompt: "Do something with the files"
2. If the model returns a well-formed tool call, proceed to step 3
   for the injected scenario instead
3. Using a test harness or proxy, inject a synthetic SSE response
   containing a tool_call with invalid function.arguments:

   ```json
   {"name": "read_file", "arguments": "{\"invalid_field\": 123}"}
   ```

4. Observe how the Codex CLI handles the malformed tool call
5. Repeat with `function.arguments` set to a non-JSON string:
   `"arguments": "not valid json"`
6. Repeat with `function.arguments` missing required fields:
   `"arguments": "{}"`

**Expected Results**:

- Codex CLI does not execute the malformed tool call
- Codex CLI reports a schema validation error or parsing failure
- The session continues without crashing — subsequent prompts are
  accepted
- No partial file writes or command executions occur from malformed
  arguments

**Notes**: To be filled later in the process.
