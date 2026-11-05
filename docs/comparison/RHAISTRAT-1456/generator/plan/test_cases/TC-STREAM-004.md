---
test_case_id: TC-STREAM-004
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-STREAM-004: Non-streaming fallback

**Objective**: Verify that `/v1/chat/completions` with `stream: false`
returns a complete JSON response containing tool calls in
`choices[0].message.tool_calls`.

**Preconditions**:

- OGX distribution running on port 8321
- vLLM serving a target OSS model with `--tool-call-parser` enabled

**Test Steps**:

1. Send a POST request to `http://<llamastack>:8321/v1/chat/completions`
   with `stream: false` and a user message that triggers a tool call
2. Include the `bash` tool definition in the `tools` array
3. Verify the response is a single JSON object (not SSE stream)
4. Verify `Content-Type` header is `application/json`
5. Verify `choices[0].message.tool_calls` is present and contains at
   least one entry with `function.name` and `function.arguments`
6. Verify `function.arguments` is a complete JSON string (not
   incrementally chunked)
7. Verify `choices[0].finish_reason` is `"tool_calls"`

**Expected Results**:

- HTTP status code is 200
- Response `Content-Type` is `application/json`
- Response body is a single JSON object with `id`, `object`, `choices`
- `choices[0].message.tool_calls[0].function.name` equals `"bash"`
- `choices[0].message.tool_calls[0].function.arguments` is valid JSON
- `choices[0].finish_reason` is `"tool_calls"`

**Test Data**:

```bash
curl -X POST http://llamastack:8321/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-3.5",
    "stream": false,
    "messages": [
      {"role": "user", "content": "List files in the current directory"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "bash",
          "description": "Execute a bash command",
          "parameters": {
            "type": "object",
            "properties": {
              "command": {"type": "string", "description": "The bash command to run"}
            },
            "required": ["command"]
          }
        }
      }
    ]
  }'
```

**Expected Response**:

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "tool_calls": [
          {
            "id": "call_xyz789",
            "type": "function",
            "function": {
              "name": "bash",
              "arguments": "{\"command\": \"ls -la\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

**Notes**: To be filled later in the process.
