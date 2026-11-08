# Test Case Index — MaaS Multi-Tenancy

**Total Test Cases**: 21 | **P0**: 12 | **P1**: 8 | **P2**: 0 (1 deferred) | **E2E**: 2

Parent Test Plan: [TestPlan.md](../TestPlan.md)

---

## TC-PROV — Tenant Provisioning & CR Lifecycle

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-PROV-001](TC-PROV-001.md) | Create Tenant CR — namespace provisioned with correct label | P0 |
| [TC-PROV-002](TC-PROV-002.md) | Create Tenant CR — MaaSSubscription reconciled in tenant namespace | P0 |
| [TC-PROV-003](TC-PROV-003.md) | Create Tenant CR — MaaSAuthPolicy reconciled in tenant namespace | P0 |
| [TC-PROV-004](TC-PROV-004.md) | Update Tenant CR — configuration changes are reconciled | P1 |

## TC-CTRL — Controller Reconciliation

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-CTRL-001](TC-CTRL-001.md) | maas-controller discovers namespace with maas.opendatahub.io/tenant label | P0 |
| [TC-CTRL-002](TC-CTRL-002.md) | maas-controller ignores namespace without tenant label | P1 |
| [TC-CTRL-003](TC-CTRL-003.md) | Multiple tenant namespaces — all reconciled simultaneously | P1 |

## TC-POLICY — AuthPolicy Propagation

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-POLICY-001](TC-POLICY-001.md) | MaaSAuthPolicy created — Kuadrant AuthPolicy generated on shared Gateway | P1 |
| [TC-POLICY-002](TC-POLICY-002.md) | MaaSAuthPolicy updated — Kuadrant AuthPolicy updated | P1 |
| [TC-POLICY-003](TC-POLICY-003.md) | MaaSAuthPolicy deleted — Kuadrant AuthPolicy removed | P1 |

## TC-APIKEY — API Key Management

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-APIKEY-001](TC-APIKEY-001.md) | POST /v1/api-keys — create API key with tenant persisted in DB | P0 |
| [TC-APIKEY-002](TC-APIKEY-002.md) | POST /internal/v1/api-keys/validate — returns ValidationResult with tenant, userID, modelRef | P0 |
| [TC-APIKEY-003](TC-APIKEY-003.md) | POST /internal/v1/api-keys/validate — cross-tenant key returns 401 | P0 |
| [TC-APIKEY-004](TC-APIKEY-004.md) | GET /v1/api-keys — list returns only keys scoped to the requesting tenant | P1 |

## TC-CONTRACT — Internal/Gateway Contract

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-CONTRACT-001](TC-CONTRACT-001.md) | POST /internal/v1/subscriptions/select — returns correct subscription for tenant | P1 |
| [TC-CONTRACT-002](TC-CONTRACT-002.md) | POST /internal/v1/subscriptions/select — wrong tenant returns 403 | P1 |

## TC-WEBHOOK — Admission Webhook

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-WEBHOOK-001](TC-WEBHOOK-001.md) | Webhook rejects MaaSSubscription CREATE in unlabeled namespace | P1 |
| [TC-WEBHOOK-002](TC-WEBHOOK-002.md) | Webhook rejects MaaSAuthPolicy CREATE in unlabeled namespace | P1 |
| [TC-WEBHOOK-003](TC-WEBHOOK-003.md) | Webhook admits MaaSSubscription CREATE in correctly labeled namespace | P1 |

## TC-ISO — Tenant Isolation (Negative Testing)

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-ISO-001](TC-ISO-001.md) | Tenant A cannot access Tenant B's models or subscriptions | P0 |
| [TC-ISO-002](TC-ISO-002.md) | Tenant A API key cannot authenticate on Tenant B's resources | P0 |
| [TC-ISO-003](TC-ISO-003.md) | Tenant A cannot enumerate Tenant B's API keys | P0 |
| [TC-ISO-004](TC-ISO-004.md) | Subscription changes in Tenant A are invisible to Tenant B | P0 |

## TC-CLEANUP — Tenant Deletion & Resource Cleanup

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-CLEANUP-001](TC-CLEANUP-001.md) | Delete Tenant CR — all tenant-owned resources removed | P0 |
| [TC-CLEANUP-002](TC-CLEANUP-002.md) | Delete Tenant CR — other tenants are unaffected | P0 |

## TC-E2E — End-to-End Scenarios

| Test Case ID | Title | Priority |
| --- | --- | --- |
| [TC-E2E-001](TC-E2E-001.md) | Full tenant lifecycle — provision, use API key, delete | P0 |
| [TC-E2E-002](TC-E2E-002.md) | Multi-tenant isolation — two tenants cannot cross-access each other's resources | P0 |
