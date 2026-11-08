---
test_case_id: TC-REGR-001
source_key: RHAISTRAT-1456
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-REGR-001: Non-Codex client compatibility

**Objective**: Verify that existing /v1/chat/completions clients using
the standard OpenAI Python SDK continue to work correctly after
Codex-specific SSE streaming changes are applied to OGX.

**Preconditions**:

- OGX deployed on port 8321 with Codex-specific SSE changes
  applied
- OpenAI Python SDK installed (e.g., `openai>=1.0`)
- No session_id or Codex-specific parameters in requests

**Test Steps**:

1. Send a non-streaming chat completion request via the OpenAI Python
   SDK with a simple user message (no tools, no session_id):

   ```python
   client = OpenAI(base_url="http://llamastack:8321/v1")
   response = client.chat.completions.create(
       model="<target_model>",
       messages=[{"role": "user", "content": "What is 2+2?"}],
       stream=False
   )
   ```

2. Verify the response is a valid `ChatCompletion` object with
   `choices[0].message.content` populated and no Codex-specific
   fields (e.g., no `session_id` in response).
3. Send a streaming chat completion request via the OpenAI Python
   SDK (no tools, no session_id):

   ```python
   stream = client.chat.completions.create(
       model="<target_model>",
       messages=[{"role": "user", "content": "Count from 1 to 5."}],
       stream=True
   )
   for chunk in stream:
       # collect chunks
   ```

4. Verify each streaming chunk is a valid `ChatCompletionChunk`
   object with `choices[0].delta` populated and no unexpected
   Codex-specific fields.
5. Verify the assembled response from streaming matches the expected
   output format.

**Expected Results**:

- Non-streaming response returns HTTP 200 with Content-Type
  `application/json`
- Response body matches standard OpenAI `ChatCompletion` schema
  (id, object, created, model, choices, usage)
- No `session_id`, `compaction`, or other Codex-specific fields
  appear in the response
- Streaming response returns SSE events matching standard OpenAI
  `ChatCompletionChunk` schema
- Final streaming event is `data: [DONE]`
- No breaking changes to existing API surface

**Test Data**:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://llamastack:8321/v1",
    api_key="not-needed"
)

# Non-streaming
response = client.chat.completions.create(
    model="meta-llama/Llama-3.3-70B-Instruct",
    messages=[{"role": "user", "content": "What is 2+2?"}],
    stream=False
)

# Streaming
stream = client.chat.completions.create(
    model="meta-llama/Llama-3.3-70B-Instruct",
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
    stream=True
)
```

**Notes**: To be filled later in the process.
