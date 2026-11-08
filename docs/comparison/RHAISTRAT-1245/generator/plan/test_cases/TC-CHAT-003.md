---
test_case_id: TC-CHAT-003
source_key: RHAISTRAT-1245
priority: P0
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_chat_completions.py
automation_function: TestGeminiChatCompletions::test_temperature_controls_variability
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-CHAT-003: Temperature parameter controls response variability

**Objective**: Verify that the `temperature` parameter in Gemini
chat completions affects response variability as expected.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST to `/v1/chat/completions` with `temperature: 0`
   and a deterministic prompt (e.g., "Reply with exactly one
   word: yes or no")
2. Send the same request three times and record responses
3. Send a POST to `/v1/chat/completions` with `temperature: 1.0`
   and the same prompt
4. Send the same high-temperature request three times and
   record responses

**Expected Results**:

- All requests return HTTP 200
- With `temperature: 0`, the three responses are identical or
  nearly identical
- With `temperature: 1.0`, responses may vary between runs
- Both temperature values produce valid chat completion
  response structures

**Notes**: To be filled later in the process.
