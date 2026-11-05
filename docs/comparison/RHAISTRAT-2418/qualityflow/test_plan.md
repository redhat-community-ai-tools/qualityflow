# Test Plan

## **Per-policy auth decision metrics from Authorino in RHOAI monitoring stack - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAIRFE-2820](https://redhat.atlassian.net/browse/RHAIRFE-2820) (source RFE; reduced scope requires agreement)
- **Feature Tracking:** [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418)
- **Epic Tracking:** [RHAISTRAT-2418](https://redhat.atlassian.net/browse/RHAISTRAT-2418) (input Feature; child epics own delivery)
- **Feature Maturity:**
  - DP: N/A
  - TP: N/A
  - GA: 3.6 GA RHOAI RELEASE [confirm]
- **QE Owner(s):** [Name]
- **Owning SIG:** Model and Agent Observability (aicp-team-compass)
- **Participating SIGs:** MaaS, Platform, Documentation

**Document Conventions (if applicable):**

- **Auth decision:** An allow or deny result when an inference request is authenticated.
- **Per-policy visibility:** Aggregate decisions for an authorization policy, without identifying individual users.
- **Opaque policy identifier:** A hashed policy identifier requiring a separate name mapping.

### **Feature Overview**

Operators can inspect aggregate authentication decisions by policy in the RHOAI monitoring experience. This helps them identify policies generating denials and compare decision trends and latency. The plan targets the current GA fix version, subject to release and scope confirmation. Individual-user attribution remains outside this delivery scope, and the warning alert is conditional on PM agreement.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the main feature’s proposed criteria and seven child epics against the cloned source RFE.
    - Separated recording rules, dashboard delivery and documentation from deferred lifecycle and telemetry work.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:* 
    - Policy-level trends help operators investigate authentication failures without exposing individual identities.
  - *List the customer use cases identified:*
    - As an operator, I want to identify policies generating denied inference requests.
    - As an operator, I want to distinguish an idle system from broken monitoring.
    - As an operator, I want a catalog explaining metrics and operational actions.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - Recording rules and dashboard behavior are testable once the intended build and datasource are available.
    - Numerical performance and policy-count limits are unspecified; quantitative acceptance awaits PM and Platform targets.
    - Main-feature scope supersedes older child text asserting that telemetry migration blocks this work.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Traffic produces nonempty auth decision metrics with policy, namespace and status dimensions.
    - Dashboard views show policy allow/deny counts, deny trends and latency using the recording-rule data.
    - When PM approves alert scope, denials exceeding 10% for 10 minutes produce a warning.
    - Deterministic recording-rule and alert examples produce the expected values; Jira reports nine existing tests, which this run could not verify.
    - The catalog includes metric names, types, value domains, source, endpoint, interval and two operator questions with example queries.
    - Cold-start and stopped-traffic panels show zero or no data without NaN or rendering errors.
    - Monitoring recovers after Authorino readiness without false rollout warnings.
    - Counter resets during replacement do not create negative spikes or incorrect trends.
    - Auth decision series exclude user-identifying dimensions beyond standard target metadata.
  - *Note any gaps or missing criteria:* 
    - Criteria remain proposed. PM must resolve reduced scope, alert inclusion and Loki feasibility before execution approval.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Privacy: no individual user, organization, cost-center or subscription identifiers in auth decision series.
    - Portability: both ODH and RHOAI Authorino namespaces.
    - Availability: scrape recovery and stable dashboard presentation during restarts.
    - Compatibility: additive rules preserve existing observability and configured dashboards across the approved upgrade path.
  - *Note any NFRs not covered and why:*
    - Performance overhead and maximum policy cardinality have no numeric targets; see scope exclusions and Untestable Aspects risk.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Policy identifiers are opaque hashes**
  - Human-readable mapping is not part of the described reduced delivery. Confirm whether this remains acceptable for the current GA target before execution.
  - *Sign-off:* [Name/Date]

- **Metrics are absent before first authentication traffic**
  - Lazy initialization is expected; dashboards must still handle no data gracefully.
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [x] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:* 
    - Schedule the design-phase QE kickoff before further dashboard work; no meeting completion is asserted.
    - Agree datasource alignment, current release scope, alert approval and cross-repo deployment ownership.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - ServiceMonitor targets /server-metrics at a 30s interval in the checked-out source.
    - Existing resources use monitoring.coreos.com/v1; Perses may query a separate monitoring stack. Datasource alignment is an entry gate.
    - Jira reports new rate, deny-ratio and P95 rules, but the local snapshot lacks these additions and the standalone rule tests.
    - AuthConfig identifiers are hashes. Multi-replica aggregation must preserve policy and namespace isolation.
    - Zero-denial and zero-total traffic differ: a fallback for absent denials does not alone prove that 0/0 NaN is handled.
    - Existing LokiDatasource manifests invalidate the older claim that Loki support does not exist; drill-down still needs a separate feasibility decision.
  - *Impact on testing approach:* 
    - Use source-confirmed constants only. Reconcile the intended PR head before producing executable rule tests or choosing dashboard deployment paths.

- [x] **API Extensions**
  - *List new or modified APIs:* 
    - New monitoring views expose policy decision trends; authentication APIs and policy schemas remain unchanged.
  - *Testing impact:* 
    - Check that traffic, monitoring queries and displayed values agree, including missing-data and restart cases.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:* 
    - Multi-node OpenShift with at least three workers per project configuration; deployed MaaS and/or LLMInferenceService models.
    - Include supported single- and multiple-Authorino-replica configurations and both product namespace variants.
  - *Impact on test design:* 
    - Parameterize equivalent deployment variants; verify policy isolation and aggregate values across replicas.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate per-policy authentication decision visibility for the current GA target after release confirmation. Cover metric availability, decision rates, deny ratios, latency, dashboard behavior, privacy, portability, restart recovery, upgrade preservation and catalog completeness. Warning-alert validation is a conditional workstream requiring PM approval before execution.

**Testing Goals**

- **[P0]** As an operator, verify policy decision totals and trends reflect traffic accurately.
- **[P0]** As an operator, verify idle and interrupted traffic never displays misleading data.
- **[P0]** As an operator, verify authentication monitoring excludes individual identities.
- **[P1]** As an operator, verify monitoring remains accurate through restarts and upgrades.
- **[P1]** As an operator, verify approved warnings distinguish sustained denials from transient activity.
- **[P1]** As an operator, verify catalog guidance supports interpreting auth decision data.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Operator lifecycle migration and telemetry consumer migration**
  - *Rationale:* Main-feature scope defers RHAI-491 and decouples RHAI-492. Reopen lifecycle work only if datasource alignment requires it.
  - *PM/Lead Agreement:* [Name/Date]

- **Individual-user denial drill-down**
  - *Rationale:* Requires an explicit feasibility and scope decision. Existing Loki support is confirmed; its absence is not a valid exclusion rationale.
  - *PM/Lead Agreement:* [Name/Date]

- **Other component metrics and cross-layer governance**
  - *Rationale:* Limitador, Envoy and broad capacity governance belong to sibling initiatives.
  - *PM/Lead Agreement:* [Name/Date]

- **Anomaly-based warnings**
  - *Rationale:* RHAI-497 describes a separate, undesigned extension beyond the main feature’s conditional static warning.
  - *PM/Lead Agreement:* [Name/Date]

- **Quantitative overhead and maximum-cardinality certification**
  - *Rationale:* No approved resource-overhead or maximum-policy targets exist. Resume in a follow-up once PM and Platform supply measurable limits; see Untestable Aspects risk.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Implementation and execution evidence unavailable in this run**
  - GitHub access failed and the local source snapshot lacks the new rules and their claimed tests. The dashboard/operator repositories and a live target cluster are unavailable for verification.
  - Obtain the intended build, artifacts and test access at entry; no scenario is claimed executed or already covered.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Validate policy decision rates, ratios, latency and absence-of-data behavior; require observed values to match controlled traffic.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Use the detected Python pytest integration conventions for cluster checks and deterministic promtool fixtures for rule arithmetic. This run plans tests; it does not execute cluster validation.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve existing metadata-evaluator alerts and scrape behavior, existing model metrics and authentication isolation. Existing-test duplicate search ran in both clean default-branch snapshots; no assertions for this feature were found. Jira’s nine reported rule tests are unverified and must be reconciled before code generation.

- [x] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* Include a feature-specific smoke check for metric availability and target recovery after readiness; it diagnoses missing monitoring data rather than changing product health behavior.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* Not selected: P95 is a reported statistic, not a performance SLA. Quantitative overhead acceptance awaits an approved target; see Out of Scope.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* Not selected for capacity certification: maximum policy cardinality is unspecified. Multi-replica arithmetic is covered by integration checks; no numeric maximum is invented.

- [x] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* Validate the feature-specific privacy boundary: auth decision metrics must exclude individual user and tenant identifiers. Authentication logic and generic RBAC certification remain unchanged.

- [x] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* Dashboard views must distinguish no traffic, stopped traffic and missing data without invalid values or rendering errors.

- [x] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* Verify auth decision metrics and dashboard agreement; execute conditional sustained-denial warning checks only after PM approval.

**Integration & Compatibility**

- [x] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* Parameterize ODH and RHOAI namespace variants and confirm additive monitoring behavior. Verify supported Perses API versions once the delivery implementation is available.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Stored monitoring rules and dashboard configuration must survive the approved predecessor-to-target product upgrade. Confirm the supported predecessor at entry.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* Platform team must deliver or confirm dashboard deployment and datasource alignment before dashboard execution (RHAI-494). Documentation team must deliver the catalog entry and format agreement (RHAI-495 / RHAIRFE-2227). Lifecycle migration is required only if alignment cannot be achieved otherwise.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* MaaS and Platform jointly validate the request-to-metrics-to-dashboard path and namespace portability; Documentation validates catalog accuracy against the delivered build.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* Not selected: this feature changes no cloud-provider-specific capability; the configured OpenShift platform is sufficient for this cycle.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift, at least three worker nodes per project configuration; include multiple Authorino replicas for aggregation checks.

- **Platform & Product Version(s):** OpenShift version: [confirm supported platform version]. Product: 3.6 GA RHOAI RELEASE [confirm]. Use the release owner’s approved predecessor for upgrade validation.

- **CPU Virtualization:** N/A — authentication monitoring requires no CPU virtualization features.

- **Compute Resources:** Capacity for inference traffic, Authorino replicas, Prometheus and Perses; size with Platform before execution, with no invented capacity threshold.

- **Special Hardware:** N/A — a supported lightweight inference deployment can generate auth traffic; no feature-specific accelerator is required.

- **Storage:** Monitoring persistence sufficient for comparison across restart and upgrade windows; use the platform-supported configuration.

- **Network:** Connectivity from monitoring to Authorino server metrics and from Perses to the rule-evaluating Prometheus instance.

- **Required Operators:** Supported RHOAI/ODH deployment with Authorino/Kuadrant, Prometheus monitoring CRDs and Perses; confirm versions against the intended build.

- **Platform:** OpenShift with user-workload monitoring; verify which monitoring instance evaluates and serves the feature’s rules.

- **Special Configurations:** Controlled allowed/denied traffic for MaaS and LLMInferenceService as deployed; both namespace variants; independent policy identifiers; traffic interruption and rollout windows.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional framework required.

- **CI/CD:** Standard tooling — no additional CI system required.

- **Other Tools:** promtool for deterministic recording-rule and alert fixtures; prerequisite rule files must first be obtained from the intended implementation.

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] PM/Engineering validate the proposed criteria, reduced per-policy scope and conditional alert approval.
- [ ] Release owner reconciles 3.6 GA RHOAI RELEASE with older 3.6 EA1 RHOAI RELEASE target and EA2 narrative, including hash-mapping expectations for GA.
- [ ] Obtain the intended implementation commit and confirm rule files, new alert, dashboard deployment repository and existing tests.
- [ ] Platform confirms the dashboard datasource can query outputs of the Prometheus instance evaluating the new rules.
- [ ] Agree catalog schema and location with Documentation; reassess Loki drill-down separately.
- [ ] Confirm the supported predecessor and target builds for upgrade checks.
- [ ] Test access, controlled traffic and rollback arrangements are available.

#### **5. Risks**

**Timeline/Schedule**

- **Risk:** Cross-repository review may delay dashboard completion
  - **Mitigation:** Prioritize core metrics while MaaS and Platform agree the delivery repository and review schedule.
  - *Estimated impact on schedule:* Not quantified; schedule at the design kickoff.
  - *Sign-off:* [Name/Date]

**Test Coverage**

- **Risk:** Reported rule-test coverage may differ from the delivered build
  - **Mitigation:** Obtain the exact implementation and compare existing assertions before adding tests; rerun deterministic cases.
  - *Areas with reduced coverage:* Rule arithmetic and new alert evidence until implementation reconciliation.
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Separate Prometheus instances may make dashboard values invisible
  - **Mitigation:** Platform verifies datasource alignment first; reconfigure or explicitly reopen lifecycle migration if necessary.
  - *Missing resources or infrastructure:* Datasource-to-rule-evaluator alignment evidence.
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Unspecified performance and policy-count acceptance limits prevent capacity certification
  - **Mitigation:** PM and Platform define numeric targets before a follow-up capacity cycle; see scope exclusions.
  - *Alternative validation approach:* Validate functional arithmetic and replica aggregation now; make no performance or scale certification claim.
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Risk:** Platform and Documentation review capacity may not match MaaS delivery timing
  - **Mitigation:** Reserve named team review slots and settle catalog format at kickoff.
  - *Current capacity gaps:* Cross-team availability unconfirmed; no staffing estimate supplied.
  - *Sign-off:* [Name/Date]

**Dependencies**

- **Risk:** Source RFE, child epics and current release metadata describe inconsistent scope
  - **Mitigation:** PM resolves the main feature’s proposed criteria and release target before test execution; retain conditional alert gating.
  - *Dependent teams or components:* PM, MaaS, Platform and Documentation; RHAI-494 and RHAI-495 deliverables.
  - *Sign-off:* [Name/Date]



---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHAISTRAT-2418]** — As an operator, I want to inspect auth decisions for traffic-bearing policies
  - *Test Scenario:* **TS-01**: [e2e] Verify policy auth decisions reflect inference traffic
    - *Priority:* P0
  - *Test Scenario:* **TS-02**: [integration] Verify auth metrics recover after source unavailability
    - *Priority:* P1

- **[RHAI-493]** — As an operator, I want accurate policy decision rates and latency
  - *Test Scenario:* **TS-03**: [unit] Verify decision rates distinguish allowed and denied traffic
    - *Priority:* P0
  - *Test Scenario:* **TS-04**: [unit] Verify deny ratios distinguish each policy
    - *Priority:* P0
  - *Test Scenario:* **TS-05**: [unit] Verify policy latency percentiles reflect observed durations
    - *Priority:* P0
  - *Test Scenario:* **TS-06**: [unit] Verify zero denials produce zero deny ratios
    - *Priority:* P2

- **[RHAI-494]** — As an operator, I want dashboard views of policy authentication trends
  - *Test Scenario:* **TS-07**: [e2e] Verify dashboard displays policy decision totals and trends
    - *Priority:* P0
  - *Test Scenario:* **TS-08**: [e2e] Verify dashboard displays policy authentication latency
    - *Priority:* P1
  - *Test Scenario:* **TS-09**: [e2e] Verify dashboard handles unavailable monitoring data gracefully
    - *Priority:* P1

- **[RHAISTRAT-2418]** — As an operator, I want idle monitoring views without invalid values
  - *Test Scenario:* **TS-10**: [e2e] Verify cold-start dashboard handles absent authentication traffic
    - *Priority:* P1
  - *Test Scenario:* **TS-11**: [e2e] Verify stopped traffic displays no invalid deny ratios
    - *Priority:* P2

- **[RHAISTRAT-2418]** — As an operator, I want accurate monitoring during authentication restarts
  - *Test Scenario:* **TS-12**: [e2e] Verify dashboard trends avoid negative spikes during restarts
    - *Priority:* P1
  - *Test Scenario:* **TS-13**: [e2e] Verify monitoring configuration survives the supported product upgrade
    - *Priority:* P1

- **[RHAI-496]** — As an operator, I want warnings for sustained policy denials when PM approves alert scope
  - *Test Scenario:* **TS-14**: [unit] Verify approved warning follows sustained excessive policy denials
    - *Priority:* P1
  - *Test Scenario:* **TS-15**: [unit] Verify approved warning respects denial threshold boundaries
    - *Priority:* P1
  - *Test Scenario:* **TS-16**: [unit] Verify transient denial bursts produce no warning
    - *Priority:* P2
  - *Test Scenario:* **TS-17**: [unit] Verify negligible traffic produces no denial warning
    - *Priority:* P1
  - *Test Scenario:* **TS-18**: [e2e] Verify no spurious denial warnings throughout authentication rollouts
    - *Priority:* P1

  - *Test Scenario:* **TS-19**: [e2e] Verify approved warning fires for sustained policy denials
    - *Priority:* P1

- **[RHAISTRAT-2418]** — As an operator, I want authentication monitoring without exposing individual identities
  - *Test Scenario:* **TS-20**: [integration] Verify authentication monitoring excludes individual identity data
    - *Priority:* P0

- **[RHAI-493]** — As an operator, I want consistent monitoring across supported deployment layouts
  - *Test Scenario:* **TS-21**: [e2e] Verify auth monitoring across supported product namespace variants
    - *Priority:* P1
  - *Test Scenario:* **TS-22**: [integration] Verify policy totals aggregate across authentication replicas
    - *Priority:* P1

- **[RHAI-495]** — As an operator, I want complete and actionable authentication metrics documentation
  - *Test Scenario:* **TS-23**: [functional] Verify metrics catalog contains complete authentication metric definitions
    - *Priority:* P1
  - *Test Scenario:* **TS-24**: [integration] Verify catalog examples answer operator authentication questions
    - *Priority:* P1


#### **2. Source Constants**

> Extracted from source code — use verbatim in test data. Do not paraphrase or infer.

| Constant | Value | Source File | Line |
|:---|:---|:---|:---|
| SCRAPE_PATH | `/server-metrics` | deployment/base/observability/authorino-server-metrics-servicemonitor.yaml | 29 |
| SCRAPE_INTERVAL | `30s` | deployment/base/observability/authorino-server-metrics-servicemonitor.yaml | 30 |
| SCRAPE_TIMEOUT | `10s` | deployment/base/observability/authorino-server-metrics-servicemonitor.yaml | 31 |
| MONITORING_API | `monitoring.coreos.com/v1` | deployment/base/observability/authorino-server-metrics-servicemonitor.yaml | 15 |
| AUTH_COUNTER | `auth_server_authconfig_response_status` | docs/content/observability/metrics-and-dashboards.md | 65 |
| AUTH_LATENCY | `auth_server_authconfig_duration_seconds` | docs/content/observability/metrics-and-dashboards.md | 64 |
| PERSES_DATASOURCE | `data-science-prometheus-datasource` | deployment/components/observability/observability/dashboards/usage-dashboard.yaml | 89 |
| EXISTING_LOKI_KIND | `LokiDatasource` | deployment/components/observability/usage-logs/usage-logs-dashboard.yaml | 37 |
| AUTH_DECISION_RATE_RULE | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| AUTH_DENY_RATIO_RULE | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| AUTH_LATENCY_P95_RULE | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| NEW_DENY_ALERT | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| NEW_DENY_THRESHOLD | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| NEW_DENY_DURATION | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |
| NEW_MINIMUM_TRAFFIC | [NOT FOUND] | Intended implementation unavailable; no local source hit | — |

New rule and alert identifiers and thresholds in Jira are planned acceptance targets, not extracted source constants. Obtain the intended implementation before converting them into executable test data. PR-derived FILE_PATH rows are omitted because no PR file list or diff was retrievable.

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
