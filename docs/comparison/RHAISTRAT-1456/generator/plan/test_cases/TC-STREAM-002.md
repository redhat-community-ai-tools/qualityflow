---
test_case_id: TC-STREAM-002
source_key: RHAISTRAT-1456
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-STREAM-002: Multi-tool streaming interleave

**Objective**: Verify that when the model returns multiple tool calls in
a single response, each tool call receives a unique index in the SSE
delta stream and arguments are streamed independently per index.

**Preconditions**:

- OGX distribution running on port 8321
- vLLM serving a target OSS model with `--tool-call-parser` enabled
- Tools array includes at least `grep_search` and `read_file`
  definitions

**Test Steps**:

1. Send a POST request to `http://<llamastack>:8321/v1/chat/completions`
   with `stream: true` and a prompt that requires two sequential tool
   calls (e.g., "Find all TODO comments in main.py and then show me the
   file contents")
2. Include `grep_search` and `read_file` tool definitions in the
   `tools` array
3. Consume the SSE event stream and collect all delta chunks containing
   `tool_calls`
4. Verify that `tool_calls` array entries use distinct `index` values
   (0 and 1)
5. Verify each index has a unique `function.name`
6. Verify `function.arguments` for each index are streamed
   incrementally across multiple chunks

**Expected Results**:

- Delta chunks contain `tool_calls` entries with `index: 0` and
  `index: 1`
- Index 0 has one `function.name` (e.g., `grep_search`), index 1 has
  a different `function.name` (e.g., `read_file`)
- Arguments for each index accumulate across chunks independently
- No index collision — each tool call ID (`call_*`) is unique
- Stream terminates with `data: [DONE]`

**Test Data**:

```bash
curl -N -X POST http://llamastack:8321/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-3.5",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Find all TODO comments in main.py and show me the file"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "grep_search",
          "description": "Search for a pattern in files",
          "parameters": {
            "type": "object",
            "properties": {
              "pattern": {"type": "string"},
              "path": {"type": "string"}
            },
            "required": ["pattern"]
          }
        }
      },
      {
        "type": "function",
        "function": {
          "name": "read_file",
          "description": "Read the contents of a file",
          "parameters": {
            "type": "object",
            "properties": {
              "path": {"type": "string", "description": "File path to read"}
            },
            "required": ["path"]
          }
        }
      }
    ]
  }'
```

**Notes**: To be filled later in the process.
