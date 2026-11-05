---
test_case_id: TC-QUAL-001
source_key: RHAISTRAT-2493
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-QUAL-001: Blind listening evaluation for timbre drift (MANUAL)

**Objective**: Evaluate whether audio quality (timbre) drifts over a long vLLM-Omni
session from a human listener perspective — requires >= 4/5 listeners to not report
drift (strategy threshold: <= 1/5 report drift).

**Preconditions**:

- A 10-minute dialogue audio recording has been captured in two segments:
  - Segment A: first 2 minutes of the session
  - Segment B: final 2 minutes of the session
- At least 5 human evaluators are available for blind listening
- Evaluators are not told which segment is early vs. late in the session
- Audio playback equipment is available

**Test Steps**:

1. Play Segment A (first-2-minute clip) to each evaluator without labeling it as
   "early" or "late".
2. Play Segment B (final-2-minute clip) to each evaluator without labeling.
3. Ask each evaluator: "Did the voice quality change notably between the two
   audio segments?"
4. Record each evaluator's response (yes/no drift reported).
5. Count how many of the 5 evaluators report noticeable timbre drift.
6. Assert drift_count <= 1 (at most 1 of 5 evaluators reports drift).

**Expected Results**:

- At most 1 of 5 evaluators reports noticeable timbre drift between the
  early-session and late-session audio segments
- The strategy threshold (>= 4/5 listeners do not report drift) is satisfied

**Notes**: To be filled later in the process. MANUAL test — cannot be automated.
Must be scheduled as a human evaluation session before TP release. Coordinate with
the voice quality team to source evaluators and schedule the session.
