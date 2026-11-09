# Test Plan

## **Per-policy auth decision metrics from Authorino in RHOAI monitoring stack - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-2820](https://redhat.atlassian.net/browse/RHAIRFE-2820)
- **Feature Tracking:** [RHAIRFE-2820](https://redhat.atlassian.net/browse/RHAIRFE-2820)
- **Epic Tracking:** [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418)
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: 3.7 EA RHOAI RELEASE
- **QE Owner(s):** [Name]
- **Owning SIG:** Model and Agent Observability
- **Participating SIGs:** Documentation, Model and Agent Observability

**Document Conventions (if applicable):**

- **Authorino:** The authorization service that evaluates requests against configured policies.
- **AuthConfig:** An Authorino authorization policy.
- **RHOAI:** Red Hat OpenShift AI.
- **Perses:** The dashboard service used by the RHOAI monitoring stack.

### **Feature Overview**

Operators can view authorization decisions for each policy in the RHOAI monitoring stack. The feature collects Authorino decision counters and latency data, records policy-level rates and deny ratios, and displays those results in a Perses dashboard. It also raises a warning when a policy denies more than 10% of requests for ten minutes. Per-user and per-tenant attribution are not provided by this release; the available policy identifier is opaque and must be documented for operators.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value, technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Collect per-policy authorization decision counters from Authorino.
    - Expose policy-level decision rates, deny ratios, and latency through Prometheus recording rules.
    - Display authorization decisions in a RHOAI Perses dashboard.
    - Warn operators when a policy exceeds a sustained deny-rate threshold.
    - Document the metrics, labels, endpoint, and useful operator queries.
    - Do not expose user-identifying information in the Prometheus metrics.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* Operators can identify which authorization policy is allowing or denying requests without examining service logs, and they receive a warning when denial behavior changes.
  - *List the customer use cases identified:*
    - As an operator, I want to see allow and deny counts for each authorization policy.
    - As an operator, I want to know when one policy denies an unusual share of requests.
    - As an administrator, I want authorization metrics that do not expose user identity.
    - As an operator, I want documentation that explains the available metrics and queries.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The proposed acceptance criteria are testable, but PM and Engineering validation is still pending.
    - No performance target or authorization-policy cardinality bound is specified.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - RHOAI Prometheus contains non-empty per-policy authorization decision counters after authorization traffic.
    - The Perses dashboard shows policy-level allow and deny counts and deny rate.
    - The deny-rate alert fires when denials exceed 10% for ten minutes, subject to PM sign-off.
    - All new recording-rule and alert unit tests pass.
    - The metrics catalog documents each metric, type, labels, source, endpoint, scrape interval, and at least two operator questions with query examples.
    - The dashboard shows zero or no data gracefully when there is no authorization traffic.
    - The metric target returns to healthy after Authorino restarts without a spurious alert.
    - Counter resets do not produce negative spikes or incorrect dashboard values.
    - Authorization metrics contain no user-identifying labels.
    - Every dashboard datasource resolves to a datasource that evaluates the recording rules.
  - *Note any gaps or missing criteria:* The source ticket marks the acceptance criteria as proposed and still requiring PM and Engineering validation.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Privacy: no user-identifying metric labels.
    - Availability: metric collection recovers after Authorino restarts.
    - Data integrity: counter resets are handled without incorrect dashboard values.
    - Usability: the dashboard handles no-data conditions without errors.
    - Monitoring: the deny-rate alert is available with warning severity.
  - *Note any NFRs not covered and why:* Performance and scale targets are not specified in the source ticket.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams. The following are confirmed product constraints accepted before testing begins.

- **Authorization policy identifiers are opaque**
  - The current policy label does not provide a human-readable tenant or user identity, so operators see an opaque policy identifier rather than a named tenant.
  - *Sign-off:* [Name/Date]

- **Per-user and per-tenant attribution is deferred**
  - The current Prometheus metrics do not contain user identity, and per-user drill-down requires the deferred logs integration.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* A QE kickoff record is not present in the Jira source. Schedule or complete the design walkthrough before final STP sign-off; implementation PR #1363 is already open.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Authorization metrics appear only after the first authorization traffic.
    - Recording rules must support both RHOAI and ODH Authorino namespaces.
    - Multiple Authorino replicas require aggregation across targets.
    - Deny-ratio queries must handle a zero-denominator condition without displaying errors.
    - Dashboard panels must use a datasource that can evaluate the new recording rules.
  - *Impact on testing approach:* Tests must generate authorization traffic, verify the dashboard through its declared datasource, and include cold-start, restart, and counter-reset cases.

- [x] **API Extensions**
  - *List new or modified APIs:* No product API is extended. The feature adds monitoring resources and a dashboard.
  - *Testing impact:* Verification focuses on collected metrics, recorded values, alert behavior, and dashboard rendering rather than API compatibility.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* A RHOAI deployment with an available model or inference service, Authorino, the platform monitoring stack, and Perses is required. Authorino may run in either supported namespace.
  - *Impact on test design:* Scenarios must use the deployed dashboard datasource and verify that namespace filtering and target aggregation work in the selected topology.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

This plan covers per-policy authorization decision collection, recording rules, deny-rate alerting, dashboard rendering and datasource resolution, operator documentation, privacy of metric labels, and deployment through the MaaS lifecycle controller. Testing targets the 3.7 EA RHOAI release. Upstream Authorino changes, per-user attribution, operator lifecycle migration, and sibling rate-limit metrics are excluded.

**Testing Goals**

- **[P0]** As an operator, verify per-policy authorization decisions are collected without user identity.
- **[P0]** As an operator, verify the dashboard and alert expose policy-level denial behavior.
- **[P1]** As an operator, verify dashboard data remains usable during cold start, restart, and counter reset.
- **[P1]** As an administrator, verify the authorization dashboard is installed by default and documented.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions. No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Upstream Authorino and Kuadrant changes**
  - *Rationale:* The required metrics are already exposed by Authorino; no upstream change is needed.
  - *PM/Lead Agreement:* [Name/Date]

- **Per-user metrics and logs drill-down**
  - *Rationale:* The current Prometheus label set has no user identity, and the logs integration is deferred.
  - *PM/Lead Agreement:* [Name/Date]

- **Operator lifecycle migration and TelemetryPolicy scoping**
  - *Rationale:* Both are tracked as separate initiatives.
  - *PM/Lead Agreement:* [Name/Date]

- **Rate-limit and per-tenant request metrics**
  - *Rationale:* These belong to sibling request RHAIRFE-2782.
  - *PM/Lead Agreement:* [Name/Date]

- **Cross-layer capacity governance dashboards**
  - *Rationale:* The current feature provides authorization decision visibility, not capacity governance.
  - *PM/Lead Agreement:* [Name/Date]

- **Authorization logic and policy schema changes**
  - *Rationale:* The feature observes existing authorization decisions and does not change authorization behavior.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **No performance or cardinality target is specified**
  - *Sign-off:* [Name/Date]

- **Proposed acceptance criteria and reduced EA scope require PM and Engineering sign-off**
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Verify metric presence, dashboard values, documentation, privacy, deployment, and recovery.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate rule unit tests and cluster dashboard, alert, datasource, and label checks.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Verify existing usage dashboards, observability setup, metadata evaluator alert, and Authorino authentication alert behavior remain intact.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Not applicable; no self-validation package requirement is identified for this feature.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Not applicable; no scrape-load or resource-consumption target is specified.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Not applicable; no authorization-policy cardinality bound is specified.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Verify authorization metrics contain no user-identifying labels.

- [x] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Verify the operator dashboard renders useful data and handles no-data conditions without errors.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Verify the policy-level deny-rate alert and dashboard monitoring data.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Verify recording rules support both supported Authorino namespaces and the cluster Prometheus datasource.

- [ ] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Not applicable; the feature adds monitoring resources and does not require migration of persistent product state.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* Platform monitoring and Perses integration must be available, and cross-repo review coordination is required for dashboard deployment.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Verify interaction with Authorino, platform monitoring, Thanos Querier, Perses, and the MaaS lifecycle controller.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not applicable; the behavior is not cloud-specific.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift cluster.

- **Platform & Product Version(s):** OpenShift platform supported by RHOAI 3.7 EA RHOAI RELEASE.

- **CPU Virtualization:** Standard cluster CPU virtualization; no special CPU capability is required.

- **Compute Resources:** Standard RHOAI worker capacity sufficient for one model or inference service and the monitoring stack.

- **Special Hardware:** N/A.

- **Storage:** Standard cluster storage; no dedicated authorization-metric storage is required.

- **Network:** Standard in-cluster networking between the model gateway, Authorino, Prometheus, and Perses.

- **Required Operators:** Authorino, RHOAI monitoring components, Perses or the dashboard operator that provides Perses custom resources.

- **Platform:** OpenShift with user-workload monitoring and the cluster Prometheus datasource available.

- **Special Configurations:** Authorino deployed in a supported namespace, authorization traffic generated against a deployed model or inference service, and the dashboard configured to use a datasource that evaluates the recording rules.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** N/A — standard framework only.

- **CI/CD:** N/A — existing pipelines only.

- **Other Tools:** promtool for recording-rule and alert unit tests.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] The authorization dashboard and recording-rule implementation are available in the test build
- [ ] A model or inference service is available to generate authorization traffic
- [ ] PM and Engineering approve the proposed acceptance criteria and reduced EA scope

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** The open implementation PR and cross-repo dashboard review may not align with the 3.7 EA test window.
  - **Mitigation:** Prioritize P0 scenarios and coordinate early with the platform and MaaS teams.
  - *Estimated impact on schedule:* Up to one sprint.
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Performance and policy-cardinality targets are unspecified, so resource impact cannot be validated against a requirement.
  - **Mitigation:** Record observed scrape load and cardinality during integration testing and request targets before GA.
  - *Areas with reduced coverage:* Prometheus resource consumption and policy-count scaling.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** The test cluster may not provide the same cluster Prometheus datasource and rule federation path as the target RHOAI deployment.
  - **Mitigation:** Verify every dashboard datasource in the deployed environment and reject direct Prometheus checks as the sole evidence.
  - *Missing resources or infrastructure:* A RHOAI deployment with live authorization traffic and a correctly federating cluster datasource.
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** The deny-rate threshold and traffic floor remain pending PM approval.
  - **Mitigation:** Test the documented 10% and ten-minute behavior while recording the pending product decision.
  - *Alternative validation approach:* Compare alert behavior against the proposed threshold and retain the decision as an entry criterion.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** QE may not have capacity to run repeated dashboard, restart, and traffic-generation scenarios before the EA milestone.
  - **Mitigation:** Automate the P0 checks first and reuse one traffic-generation setup for restart and counter-reset scenarios.
  - *Current capacity gaps:* Cluster execution time and multi-replica topology availability.
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Platform monitoring or dashboard changes may be required outside the MaaS repository.
  - **Mitigation:** Engage the platform team early and track any required dashboard deployment coordination.
  - *Dependent teams or components:* Platform monitoring, Perses integration, and MaaS lifecycle controller owners.
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[REQ-RHAISTRAT-2418-01]** — As an operator, I want per-policy authorization decisions collected without exposing user identity.
  - *Test Scenario:* **TS-01**: [functional] Verify per-policy authorization metrics are collected
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [functional] Verify authorization metrics omit user identity
    - *Priority:* P0

- **[REQ-RHAISTRAT-2418-02]** — As an operator, I want the dashboard to show reliable policy-level authorization activity.
  - *Test Scenario:* **TS-03**: [e2e] Verify dashboard shows policy decisions and deny rate
    - *Priority:* P0
  - *Test Scenario:* **TS-04**: [integration] Verify dashboard datasource resolves recording rules
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [functional] Verify dashboard handles no authorization traffic
    - *Priority:* P1
  - *Test Scenario:* **TS-06**: [functional] Verify dashboard handles authorization counter resets
    - *Priority:* P1

- **[REQ-RHAISTRAT-2418-03]** — As an operator, I want policy denial anomalies to raise a reliable warning.
  - *Test Scenario:* **TS-07**: [functional] Verify deny-rate alert fires with warning severity
    - *Priority:* P0
  - *Test Scenario:* **TS-08**: [functional] Verify alert stays silent below deny threshold
    - *Priority:* P1
  - *Test Scenario:* **TS-09**: [functional] Verify alert stays silent before ten minutes
    - *Priority:* P1
  - *Test Scenario:* **TS-10**: [functional] Verify deny-rate alert respects traffic floor
    - *Priority:* P1
  - *Test Scenario:* **TS-11**: [unit] Verify authorization alert rules pass CI unit tests
    - *Priority:* P0

- **[REQ-RHAISTRAT-2418-04]** — As an administrator, I want the dashboard deployed by default, recoverable, and documented for operators.
  - *Test Scenario:* **TS-12**: [functional] Verify dashboard deploys without usage-dashboard gate
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [integration] Verify target recovers without spurious alert
    - *Priority:* P1
  - *Test Scenario:* **TS-14**: [functional] Verify catalog documents metrics, labels, endpoint, queries
    - *Priority:* P1

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name / @github-handle]
  - Product Manager: [Name / @github-handle]
