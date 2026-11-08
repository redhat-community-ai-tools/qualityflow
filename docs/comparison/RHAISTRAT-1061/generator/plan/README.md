# OGXServer Runtime Config

Declarative runtime configuration for OGXServer CRD (`ogx.io/v1beta1`), replacing manual ConfigMap
creation. Target: RHOAI 3.5 GA.

## Links

- **Strategy**: [RHAISTRAT-1061](https://redhat.atlassian.net/browse/RHAISTRAT-1061)
- **QE Validation Epic**: [RHAIENG-2700](https://redhat.atlassian.net/browse/RHAIENG-2700)
- **OCI Label Script**:
  [generate-config-labels.sh](https://github.com/ogx-ai/ogx/blob/main/scripts/generate-config-labels.sh)

## Artifacts

- [TestPlan.md](TestPlan.md) — Full test plan (v1.3.0)
- [TestPlanReview.md](TestPlanReview.md) — Review scores (8/10 Ready)
- [TestPlanGaps.md](TestPlanGaps.md) — 12 remaining gaps
- [test_cases/INDEX.md](test_cases/INDEX.md) — Test case index

## Test Cases

**32 test cases** across 14 categories — P0: 25, P1: 7

| Category | Count | Focus |
| --- | --- | --- |
| TC-SCHEMA | 4 | CRD field validation, CEL rules |
| TC-WEBHOOK | 1 | Admission webhook MinItems/MaxItems |
| TC-MERGE | 3 | Config merge logic, disabledAPIs |
| TC-RENDER | 2 | Immutable ConfigMap creation |
| TC-ROLLOUT | 1 | Rolling update on config change |
| TC-OCI | 3 | OCI label loading, fallback |
| TC-OVERRIDE | 1 | spec.overrideConfig precedence |
| TC-ADOPT | 3 | Legacy LLSD resource adoption |
| TC-UPGRADE | 3 | LlamaStackDistribution to OGXServer migration |
| TC-PROVIDER | 2 | VLLM, Bedrock provider expansion |
| TC-STORAGE | 1 | Postgres storage backend |
| TC-NEG | 3 | Validation gap tests (RHAIENG-5697) |
| TC-NETPOL | 1 | NetworkPolicy per-CR toggle |
| TC-E2E | 4 | End-to-end user journeys |

## Automated Tests

Automated tests will be implemented in:

- [opendatahub-tests](https://github.com/opendatahub-io/opendatahub-tests) — via RHAIENG-3597
- [openshift-python-wrapper](https://github.com/RedHatQE/openshift-python-wrapper) — v1beta1 CRD
  support via [PR #2647](https://github.com/RedHatQE/openshift-python-wrapper/pull/2647)
