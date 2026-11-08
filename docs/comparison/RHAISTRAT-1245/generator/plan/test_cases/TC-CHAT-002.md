---
test_case_id: TC-CHAT-002
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_chat_completions.py
automation_function: TestGeminiChatCompletions::test_streaming_chat_completion
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-CHAT-002: Streaming chat completions with Gemini

**Objective**: Verify that streaming chat completion requests
through the `remote::gemini` provider deliver chunked responses
correctly.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to `/v1/chat/completions` with
   `stream: true`
2. Read the server-sent events (SSE) stream
3. Verify each chunk follows the expected format
4. Verify the stream terminates with a `[DONE]` marker

**Expected Results**:

- Response status is HTTP 200 with `Content-Type` media type
  `text/event-stream` (charset parameter is acceptable)
- Multiple SSE chunks are received, each prefixed with `data:`
- Each chunk contains a `choices` array with delta content
- The final chunk contains `finish_reason: stop`
- The stream ends with `data: [DONE]`
- Concatenating all delta content produces coherent text

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "messages": [
    {"role": "user", "content": "Explain quantum computing."}
  ],
  "stream": true,
  "temperature": 0.5
}
```

**Notes**: To be filled later in the process.
