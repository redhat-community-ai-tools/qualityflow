---
type: llm
focus: last_message
---
Correct routing: #12345 (internal-mechanism wording) and #12346 (broken markdown table) and
#12348 (trailing whitespace) are mechanical and can be fixed automatically. #12347 asks an
open product question and needs a human.

PASS if #12347 is routed to a human (needs-human / ask the reviewer), and the other three
are routed to automatic fixing (a "propose fix" or equivalent middle category counts as
automatic).

FAIL if #12347 is treated as auto-fixable, or if a mechanical comment is sent to a human.
