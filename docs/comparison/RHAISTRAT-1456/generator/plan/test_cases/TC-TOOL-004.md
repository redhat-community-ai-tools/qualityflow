---
test_case_id: TC-TOOL-004
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-TOOL-004: Tool-call parser mode compatibility per model

**Objective**: Validate that vLLM `--tool-call-parser` modes produce
correctly formatted tool calls for each target OSS model.

**Preconditions**:

- vLLM serving on port 8000 with configurable `--tool-call-parser`
- At least three target models available: Qwen 3.5, Mistral Small 4,
  Llama 3.3 70B
- OGX on port 8321 proxying to vLLM

**Test Steps**:

1. Deploy Qwen 3.5 on vLLM with `--tool-call-parser hermes`
2. POST to `/v1/chat/completions` via OGX with the `bash`
   tool definition and prompt "List files in the current directory"
3. Validate the returned tool_call has `function.name = "bash"` and
   valid JSON in `function.arguments` with `"command"` field
4. Redeploy with Mistral Small 4 and `--tool-call-parser mistral`
5. Repeat the same request and validation
6. Redeploy with Llama 3.3 70B and `--tool-call-parser llama3_json`
7. Repeat the same request and validation
8. For each model, also test with `--tool-call-parser pythonic` to
   verify fallback behavior

**Expected Results**:

- Each model + parser combination produces well-formed tool_calls
- `function.name` matches the requested tool exactly
- `function.arguments` is valid JSON with required fields present
- At least one parser mode per model produces correct results
- Incompatible parser modes produce a clear error or fallback, not
  silently malformed output

**Test Data**:

```bash
# Parser mode matrix (expected valid combinations — TBD per
# TestPlanGaps.md, test with all and document which pass)
# Qwen 3.5:       hermes, pythonic
# Mistral Small 4: mistral, pythonic
# Llama 3.3 70B:  llama3_json, pythonic
```

**Notes**: To be filled later in the process.
