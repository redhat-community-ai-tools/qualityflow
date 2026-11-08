---
test_case_id: TC-TOOL-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_tool_calling.py
automation_function: TestGeminiToolCalling::test_tool_calling
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-TOOL-001: Tool calling via /v1/chat/completions with Gemini

**Objective**: Verify that tool calling via `/v1/chat/completions`
succeeds and returns valid `tool_calls` output when using the
`remote::gemini` provider.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to `/v1/chat/completions` with a
   `tools` array containing a function definition and a user
   message that should trigger tool invocation
2. Inspect the response for `tool_calls` in the assistant message

**Expected Results**:

- Response status is HTTP 200
- Response `choices[0].message` contains a `tool_calls` array
- Each tool call has `type: function`, a valid `id`, and a
  `function` object with `name` matching the defined tool and
  parseable JSON `arguments`
- `finish_reason` is `tool_calls`

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "messages": [
    {"role": "user", "content": "What is the weather in Paris?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    }
  ]
}
```

**Notes**: To be filled later in the process.
