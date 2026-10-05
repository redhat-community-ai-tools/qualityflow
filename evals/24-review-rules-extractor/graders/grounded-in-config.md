---
type: llm
focus: last_message
---
The rules must come from this repository's config for the cnv project (config/projects/cnv:
project.yaml, components.yaml, repositories.yaml, environment.yaml, pii_exceptions.yaml).

PASS if the answer cites project configuration it actually read — naming cnv config files
and values found in them (components, repositories, scope boundaries, PII exceptions) — and
presents rules for reviewing the STP.

FAIL if it gives only generic QE review advice with no reference to this project's
configuration, or if it cites config files or values that do not exist.
