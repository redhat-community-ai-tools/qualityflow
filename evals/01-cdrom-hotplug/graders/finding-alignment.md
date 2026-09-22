---
type: llm
focus: last_message
weight: 1
---
You are grading a QE review of a well-formed, template-conformant Software Test
Plan for a GA storage feature (CD-ROM hotplug). The STP is strong overall, but it
contains two Rule A (Abstraction Level) violations that the reviewer's rules
classify as CRITICAL: the Testing Goal "Verify declarative hotplug volumes
correctly reconcile VM spec changes to running VMIs" uses the implementation verb
"reconcile", and scenario REQ-EPHEMERAL-01 says "the VM controller removes it",
naming an internal component. A March 2026 run missed both and approved the STP;
catching them is the point of this case.

The review PASSES only if ALL of these hold:

1. **Catches the Rule A leak.** It flags at least one of the two items above
   (the "reconcile" Testing Goal or the "VM controller" scenario) as a critical /
   blocking finding, and the verdict is NEEDS_REVISION.
2. **No invented criticals.** Every other critical finding must be grounded in
   the STP text. At most two criticals in total; a third blocking finding beyond
   the Rule A leaks is over-flagging and fails.
3. **Counts agree.** The prose verdict, the Summary table finding counts, and the
   final machine-readable YAML block (`verdict` / `critical_count` / ...) are
   mutually consistent.

A finding you cannot ground in the STP text is a hallucination and fails the
review. Do not penalise the review for the number of major or minor findings.

Return whether the review passes and a short rationale naming which Rule A item
was caught and flagging any ungrounded finding.
