---
test_case_id: TC-TOOL-002
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-TOOL-002: Tool-call chaining across turns

**Objective**: Validate that the model chains tool calls sequentially
where each call depends on the output of the prior call.

**Preconditions**:

- OGX running on port 8321 with session_id enabled
- A sample repository with Python files available on the test cluster
- All six Codex CLI tool definitions registered

**Test Steps**:

1. Start a new session with a unique session_id
2. Send the prompt: "Find all Python files in the project, read the
   first one, then add a module-level docstring to it"
3. Observe the first tool call — expect `glob_search` with pattern
   `"*.py"` or similar
4. Return the glob_search result (list of .py files) as tool output
5. Observe the second tool call — expect `read_file` with the path
   of the first file from the glob results
6. Return the file contents as tool output
7. Observe the third tool call — expect `edit_file` with the same
   path, inserting a docstring at the top of the file
8. Verify the edit_file arguments reference content from the
   read_file output (e.g., module name or existing imports)

**Expected Results**:

- 3 or more tool calls are produced in sequence
- Each subsequent tool call references information from the prior
  tool's output (file path from glob, content from read)
- The final `edit_file` call produces a valid edit that adds a
  docstring without corrupting existing code
- Session state retains context across all turns

**Notes**: To be filled later in the process.
