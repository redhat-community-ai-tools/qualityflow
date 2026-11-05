---
test_case_id: TC-TOOL-002
source_key: RHAISTRAT-1245
priority: P2
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_tool_calling.py
automation_function: TestGeminiToolCalling::test_tool_calling_with_unsupported_schema_fields
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-TOOL-002: Tool calling with unsupported JSON schema fields

**Objective**: Verify that the `remote::gemini` provider correctly
handles tool definitions containing JSON schema fields that Gemini
does not support, filtering them before sending to the Gemini API.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider active
- Valid `GEMINI_API_KEY` configured

**Test Steps**:

1. Send a POST request to `/v1/chat/completions` with a tool
   definition that includes JSON schema fields unsupported by
   Gemini: `additionalProperties`, `$schema`,
   `exclusiveMaximum`, `exclusiveMinimum`, `maxItems`,
   `minItems`, `propertyNames`, `const`, `default`
2. Inspect the response for successful tool invocation or
   valid chat completion

**Expected Results**:

- Response status is HTTP 200 (not HTTP 400 with
  "Invalid JSON payload")
- The `remote::gemini` provider filters out unsupported schema
  fields before forwarding to the Gemini API
- The request does not fail with Gemini API schema validation
  errors
- Tool calling succeeds if the model determines the tool
  should be called

**Test Data**:

```json
{
  "model": "<GEMINI-MODEL-ID>",
  "messages": [
    {"role": "user", "content": "Look up item 42"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "lookup_item",
        "description": "Look up an item by ID",
        "parameters": {
          "type": "object",
          "$schema": "http://json-schema.org/draft-07/schema#",
          "properties": {
            "item_id": {
              "type": "integer",
              "exclusiveMinimum": 0,
              "exclusiveMaximum": 10000,
              "default": 1
            },
            "tags": {
              "type": "array",
              "minItems": 1,
              "maxItems": 10
            }
          },
          "required": ["item_id"],
          "additionalProperties": false
        }
      }
    }
  ]
}
```

**Notes**: To be filled later in the process.
