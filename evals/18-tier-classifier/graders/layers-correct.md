---
type: llm
focus: last_message
---
Correct classification: (1) is a unit test — one function, no cluster. (2) and (4) are
functional/integration tests of the feature through its API. (3) is an end-to-end test
spanning several services.

PASS if (1) is classified as unit, (3) as end-to-end (or the project's widest tier), and
(2) and (4) as the same, narrower functional/integration layer, each with a short reason.

FAIL if (1) is classified as end-to-end, if (3) is classified as unit, or if items are
classified with no reasoning at all.
