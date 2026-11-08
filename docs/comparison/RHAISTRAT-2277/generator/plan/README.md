# OGX to Praxis Migration

Test planning for the migration of the Responses, Conversations, and RAG APIs from OGX to Praxis as
the single customer-facing entrypoint in RHOAI 3.6, with OGX retained as an internal state backend.

## Source Documents

- Strategy: [RHAISTRAT-2277](https://redhat.atlassian.net/browse/RHAISTRAT-2277)
- Source RFE: [RHAIRFE-2711](https://redhat.atlassian.net/browse/RHAIRFE-2711)
- ADR: not yet created

## Artifacts

- [TestPlan.md](TestPlan.md) — the test plan
- [TestPlanGaps.md](TestPlanGaps.md) — open questions blocking full test specification
- [TestPlanReview.md](TestPlanReview.md) — quality rubric scores and verdict
- [test_cases/INDEX.md](test_cases/INDEX.md) — 10 test cases (9 P0, 1 P1) across E2E, negative, and
  upgrade categories

## Test Implementation

Automated tests are expected to land in the OGX component repositories and the downstream RHOAI
end-to-end suite. Placement per test case is decided by `/test-plan-case-implement`, which reads
Section 4 of the test plan and the test level assigned to each case.
