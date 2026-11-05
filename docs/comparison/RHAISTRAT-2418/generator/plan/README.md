# Authorino Auth Decision Metrics

Per-policy auth decision metrics from Authorino in the RHOAI monitoring stack.

## Links

- **Strategy**: [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418)
- **Source RFE**: [RHAIRFE-2820](https://redhat.atlassian.net/browse/RHAIRFE-2820)
- **Recording Rules PR**: [models-as-a-service #1363](https://github.com/opendatahub-io/models-as-a-service/pull/1363)

## Artifacts

- [TestPlan.md](TestPlan.md) — Test plan document (score: 10/10)
- [TestPlanReview.md](TestPlanReview.md) — Quality rubric review
- [TestPlanGaps.md](TestPlanGaps.md) — Identified gaps requiring additional documentation
- [test_cases/INDEX.md](test_cases/INDEX.md) — Test case index (27 TCs — 15 P0, 10 P1, 2 P2)

## Test Implementation

Automated tests will be implemented in:

- `deployment/base/observability/` (promtool unit tests for recording rules and alerts)
- opendatahub-tests repository (integration tests for metrics pipeline and dashboard verification)
