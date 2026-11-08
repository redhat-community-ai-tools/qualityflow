---
test_case_id: TC-STREAM-001
source_key: RHAISTRAT-1456
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-STREAM-001: SSE streaming delta format compliance

**Objective**: Verify that OGX's `/v1/chat/completions` endpoint
emits SSE events with OpenAI-format delta objects containing incremental
`tool_calls` arrays that the Codex CLI can parse.

**Preconditions**:

- OGX distribution running on port 8321
- vLLM serving a target OSS model on port 8000 with
  `--tool-call-parser` enabled
- Network connectivity between test client and OGX endpoint

**Test Steps**:

1. Send a POST request to `http://<llamastack>:8321/v1/chat/completions`
   with `stream: true`, a user message requesting a file operation, and
   a `tools` array containing the `bash` tool definition
2. Consume the SSE event stream and collect all chunks
3. Verify each chunk begins with `data:` prefix followed by a
   parseable payload
4. Verify at least one chunk contains an observable tool-call delta
   with function name and arguments content
5. Verify function argument text is delivered incrementally across
   multiple chunks
6. Verify the final event in the stream is `data: [DONE]`

**Expected Results**:

- Every SSE chunk starts with `data:` prefix
- JSON in each chunk parses without error
- Delta payloads are compatible with Codex CLI parsing expectations
- Function argument text grows across consecutive chunks
- Stream terminates with `data: [DONE]`

**Test Data**:

```bash
curl -N -X POST http://llamastack:8321/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-3.5",
    "stream": true,
    "messages": [
      {"role": "user", "content": "List the files in the current directory"}
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

```text
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_xyz","type":"function","function":{"name":"bash","arguments":""}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"comma"}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"nd\": \"ls"}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments": " -la\"}"}}]},"finish_reason":"tool_calls"}]}

data: [DONE]
```

**Notes**: To be filled later in the process.
