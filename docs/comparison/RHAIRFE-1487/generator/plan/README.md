# MaaS Multi-Tenancy Test Plan

Multi-tenancy support for MaaS enabling platform admins to
provision isolated tenants, with automated policy
propagation and API key scoping.

## Documentation

### Main Documents

- [TestPlan.md](TestPlan.md) — Complete test strategy, approach, and execution plan
- [TestPlanGaps.md](TestPlanGaps.md) — Open gaps and blocked items (9 open)
- [TestPlanReview.md](TestPlanReview.md) — Quality review rubric assessment (9/10 — Ready)

### Test Cases

- [test_cases/INDEX.md](test_cases/INDEX.md) — Index of all 27 test cases organized by category

## Related Links

- **Jira RFE**: [RHAIRFE-1487](https://redhat.atlassian.net/browse/RHAIRFE-1487)
- **Strategy**: [RHAISTRAT-1741](https://redhat.atlassian.net/browse/RHAISTRAT-1741)
- **Epic**: [RHOAIENG-62570](https://redhat.atlassian.net/browse/RHOAIENG-62570)
- **Architecture (v2)**: [Working Design Doc](https://docs.google.com/document/d/1Ie0hZFwPlQmVHzZLDtyHxviDXtvwY9wNPjnd1Tw8Gy8/edit?tab=t.0#heading=h.fi2ik433erf1)

## Directory Structure

```text
MaaSMultiTenancy/
├── README.md          # This file
├── TestPlan.md        # Main test plan document
└── test_cases/        # Individual test case files (to be added)
    └── INDEX.md       # Test case index
```

## Quick Start

1. Review the test strategy: Read `TestPlan.md` sections 1–5
2. Browse test cases: Check `test_cases/INDEX.md` for organized listing
