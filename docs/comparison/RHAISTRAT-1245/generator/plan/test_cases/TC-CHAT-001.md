---
test_case_id: TC-CHAT-001
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_chat_completions.py
automation_function: TestGeminiChatCompletions::test_non_streaming_chat_completion
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-CHAT-001: Non-streaming chat completions with Gemini

**Objective**: Verify that non-streaming chat completion requests
through the `remote::gemini` provider return valid responses.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to `/v1/chat/completions` with
   `stream: false` (or omitted) and a simple user message
2. Inspect the response body for valid chat completion structure

**Expected Results**:

- Response status is HTTP 200
- Response body contains `choices` array with at least one entry
- Each choice contains a `message` object with `role: assistant`
  and non-empty `content`
- Response contains a valid `id` field

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "messages": [
    {"role": "user", "content": "What is the capital of France?"}
  ],
  "temperature": 0.7
}
```

**Notes**: To be filled later in the process.
