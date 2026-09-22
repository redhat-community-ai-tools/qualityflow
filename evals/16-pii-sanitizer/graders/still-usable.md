---
type: llm
focus: last_message
---
The extract had to be de-identified: customer name (Globex Industries), vendor (Acme
Storage), internal hostnames, a private IP, an email address, a phone number, and a test
credential.

PASS if all of those are replaced with generic placeholders (e.g. <customer>, example.com,
RFC 5737 addresses like 192.0.2.x, worker-node-1) AND the test steps still read as the same
test: a disk is attached, the guest sees it, the nightly backup still completes.

FAIL if any real identifier survives, if the credential is kept, or if the scenario steps
are dropped or turned into something else.
