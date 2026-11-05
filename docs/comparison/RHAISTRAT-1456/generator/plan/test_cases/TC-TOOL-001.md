---
test_case_id: TC-TOOL-001
source_key: RHAISTRAT-1456
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-TOOL-001: All six Codex tools produce valid JSON arguments

**Objective**: Validate that each of the 6 Codex CLI tools returns
tool_calls with function.arguments conforming to the tool's parameter
schema.

**Preconditions**:

- OGX running on port 8321 with a target OSS model
- vLLM serving on port 8000 with appropriate `--tool-call-parser`
- All six Codex CLI tool definitions registered in the request

**Test Steps**:

1. POST to `/v1/chat/completions` with `stream=true`, all six tool
   definitions, and the prompt "List all files in /tmp"
2. Validate the response contains a tool_call with
   `function.name = "bash"` and `function.arguments` containing a
   `"command"` field
3. Repeat with prompt "Read the contents of main.py" — expect
   `function.name = "read_file"` with `"path"` field
4. Repeat with prompt "Write 'hello world' to test.txt" — expect
   `function.name = "write_file"` with `"path"` and `"content"` fields
5. Repeat with prompt "Change line 5 of app.py to return 42" — expect
   `function.name = "edit_file"` with `"path"` and edit-related fields
6. Repeat with prompt "Search for TODO comments in the project" —
   expect `function.name = "grep_search"` with `"pattern"` field
7. Repeat with prompt "Find all .yaml files in the repo" — expect
   `function.name = "glob_search"` with `"pattern"` field
8. For each response, parse `function.arguments` as JSON and validate
   against the corresponding tool's parameter schema

**Expected Results**:

- All 6 tool calls have `function.name` matching the intended tool
- `function.arguments` is valid JSON (not a string, not truncated)
- Each tool's required parameters are present (e.g., `bash` has
  `command`, `read_file` has `path`)
- No extraneous parameters outside the tool schema are present

**Test Data**:

```json
{
  "model": "<target_oss_model>",
  "stream": true,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "bash",
        "description": "Execute a bash command",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {"type": "string", "description": "The command to run"}
          },
          "required": ["command"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {"type": "string", "description": "File path to read"}
          },
          "required": ["path"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "write_file",
        "description": "Write content to a file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}
          },
          "required": ["path", "content"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "edit_file",
        "description": "Edit a file",
        "parameters": {
          "type": "object",
          "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"}
          },
          "required": ["path", "old_string", "new_string"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "grep_search",
        "description": "Search for a pattern",
        "parameters": {
          "type": "object",
          "properties": {
            "pattern": {"type": "string"}
          },
          "required": ["pattern"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "glob_search",
        "description": "Find files matching a glob pattern",
        "parameters": {
          "type": "object",
          "properties": {
            "pattern": {"type": "string"}
          },
          "required": ["pattern"]
        }
      }
    }
  ],
  "messages": [
    {"role": "user", "content": "<prompt_per_tool>"}
  ]
}
```

**Notes**: To be filled later in the process.
