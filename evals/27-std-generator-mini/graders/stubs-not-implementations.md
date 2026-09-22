---
type: llm
focus: last_message
---
Phase 1 stubs must describe each test in a Preconditions / Steps / Expected docstring and
carry no working test body: no assertions, no API calls, no implementation.

PASS if the answer reports writing stubs for all three scenarios with PSE docstrings and
disabled collection (e.g. __test__ = False or an equivalent pending marker).

FAIL if it reports writing runnable tests with assertions, or covers fewer than three
scenarios.
