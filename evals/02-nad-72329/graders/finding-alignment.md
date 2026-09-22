---
type: llm
focus: last_message
weight: 1
---
You are grading a QE review of a Software Test Plan that is technically strong —
27 well-written test cases, good domain knowledge — but structurally
non-conformant: it was written to its author's own 11-section layout instead of
the mandated four-section CNV template, and it omits Section I (Motivation &
Requirements Review) and Section IV (Sign-off) entirely. The reference run
blocked it (`NEEDS_REVISION`, 3 critical). The failure mode this case exists to
catch is a reviewer that gets charmed by the well-written test cases into
approving a document that cannot be submitted.

The review PASSES only if BOTH of these hold:

1. **The structural non-conformance is called out at CRITICAL / blocking
   severity.** The review must identify — as a critical, verdict-blocking issue —
   at least one of: the missing Section I, the missing Section IV, or the use of
   a non-standard section structure instead of the mandated four-section (I, II,
   III, IV) layout. Naming the structural block at only major/minor severity, or
   missing it entirely, is a fail — that is the charmed-into-approving failure.
2. **Counts agree.** The prose verdict, the Summary table finding counts, and the
   final machine-readable YAML block are mutually consistent.

The major-level findings (CNV version 4.18 vs fix_version 4.22, no QE kickoff, no
Tier 1/Tier 2 classification, guest-continuity coverage gap beyond MAC, prohibited
Glossary/References sections) are ADVISORY — note which appear, but do not require
them and do not fail the review for missing some. A finding you cannot ground in
the STP text is a hallucination and fails the review.

Return whether the review passes and a short rationale naming which structural
critical(s) were found and, advisorily, roughly how many of the major findings
appeared.
