# Test Plan

## **Agent catalog - backend work - Quality Engineering Plan**

### **Metadata & Tracking**

- **Enhancement(s):** [RHAISTRAT-1740](https://redhat.atlassian.net/browse/RHAISTRAT-1740)
- **Feature Tracking:** [RHAISTRAT-1740](https://redhat.atlassian.net/browse/RHAISTRAT-1740)
- **Epic Tracking:** [RHOAIENG-70680](https://redhat.atlassian.net/browse/RHOAIENG-70680)
- **Feature Maturity:**
  - DP: 3.5 [confirm]
  - TP: N/A
  - GA: N/A
- **QE Owner(s):** [Name]
- **Owning SIG:** AI Hub
- **Participating SIGs:** None identified beyond AI Hub

**Document Conventions (if applicable):**

- **Starter kit:** A curated example agent with documentation, model requirements, and configuration requirements.
- **Agent template artifact:** The published starter-kit definition available for inspection without executing the agent.
- **Dev Preview:** Early feature availability with the product constraints listed in Section I.2.
- **Catalog source:** An administrator-configured origin from which agent entries are published.

### **Feature Overview**

AI engineers can discover curated agent starter kits, inspect their documentation, and compare their configuration requirements through the catalog API. This gives users one place to evaluate available agents before building an application. Administrators configure the sources from which agents are published, and the operator deploys the default source configuration. This plan covers the browse-only Dev Preview backend; it does not cover agent execution or the separate UI.

---

### **I. Motivation and Requirements Review (QE Review Guidelines)**

This section documents the mandatory QE review process. The goal is to understand the feature's value,
technology, and testability before formal test planning.

#### **1. Requirement & User Story Review Checklist**

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:*
    - Reviewed the backend Epic and its 11 children for discovery, metadata publication, source administration, artifact access, documentation, and source reload behavior.
    - Compared the parent feature with the narrower backend scope; UI and deployment goals belong to the broader feature.

- [x] **Understand Value and Customer Use Cases**
  - *Describe the feature's value to customers:*
    - Users can evaluate starter kits and their requirements without collecting metadata from multiple repositories.
  - *List the customer use cases identified:*
    - As an AI engineer, I want to find starter kits matching my framework and inspect their requirements.
    - As an administrator, I want to publish curated sources for my organization.
    - As an AI engineer, I want to inspect a starter kit's template without executing it.

- [x] **Testability**
  - *Note any requirements that are unclear or untestable:*
    - The parent and child issues describe different detail and source routes; the released API contract must resolve this before execution.
    - Remote documentation failure semantics are not fully specified. Entry criteria require agreement before negative-case execution.

- [x] **Acceptance Criteria**
  - *List the acceptance criteria:*
    - Configured sources publish starter-kit metadata and documentation.
    - Users can list, search, filter, page, and inspect agent entries.
    - Users can discover agent-specific sources and available filters.
    - Users can inspect image and template artifacts without executing them.
    - Source updates remove obsolete templates.
    - Installation publishes curated starter kits and supports administrator-configured sources.
    - Documentation explains the API, source configuration, and Dev Preview limits.
  - *Note any gaps or missing criteria:*
    - No numeric latency, throughput, scale, or remote-fetch recovery targets are supplied.
    - Parent route examples conflict with later child requirements; use the signed-off released contract.

- [x] **Non-Functional Requirements (NFRs)**
  - *List applicable NFRs and their targets:*
    - Configuration and template integrity are required across source updates and supported upgrades.
    - No new authorization boundary or telemetry contract is specified for this backend Epic.
  - *Note any NFRs not covered and why:*
    - Performance and scale acceptance measurements need agreed targets; see Out of Scope.
    - UI accessibility and deployment telemetry belong to separate delivery scope.

#### **2. Known Limitations**

The limitations are documented to ensure alignment between development, QA, and product teams.
The following are confirmed product constraints accepted before testing begins.

- **Browse-only Dev Preview excludes agent deployment and execution**
  - *Sign-off:* [Name/Date]

- **Agent versioning and lifecycle management are unavailable**
  - *Sign-off:* [Name/Date]

- **End-user agent registration is unavailable; sources are administrator-configured**
  - *Sign-off:* [Name/Date]

#### **3. Technology and Design Review**

- [ ] **Developer Handoff/QE Kickoff**
  - *Key takeaways and concerns:*
    - QE kickoff belongs in the design phase, before implementation; no meeting date is supplied.
    - Resolve detail-route differences and remote-fetch failure contracts with development before execution.

- [x] **Technology Challenges**
  - *List identified challenges:*
    - Metadata collection, catalog service, and operator integration span three repositories.
    - Source reload must preserve agent identity while replacing or removing template artifacts.
    - README content is fetched from remote repositories and must remain readable outside those repositories.
  - *Impact on testing approach:*
    - Trace shared integration boundaries and validate the current agent implementation before producing concrete test data.
    - Do not treat model or MCP catalog tests as proof of agent behavior.

- [x] **API Extensions**
  - *List new or modified APIs:*
    - Agent discovery supports filtering, search, ordering, pagination, and detailed configuration information.
    - Artifact discovery separates image references from downloadable templates.
    - Shared source discovery gains agent-specific selection.
  - *Testing impact:*
    - Compare responses against the approved release contract and verify both populated and empty collections.

- [x] **Test Environment Needs**
  - *See environment requirements in Section II.3 and testing tools in Section II.3.1*

- [x] **Topology Considerations**
  - *Describe topology requirements:*
    - Use the configured multi-node OpenShift topology with at least three workers for installation and upgrade checks.
  - *Impact on test design:*
    - Single API assertions use the installed catalog; full publication and upgrade checks cover cross-component workflows.

### **II. Software Test Plan (STP)**

This STP serves as the **overall roadmap for testing**, detailing the scope, approach, resources, and schedule.

#### **1. Scope of Testing**

Validate browse-only agent discovery, metadata and documentation publication, artifact access, source updates, installation, and supported configuration preservation for the Dev Preview backend. Validate administrator-configured sources without creating end-user registration workflows.

**Testing Goals**

- **[P0]** As an AI engineer, verify curated agents can be discovered and inspected.
- **[P0]** As an administrator, verify shipped starter kits are available after installation.
- **[P1]** As an AI engineer, verify missing entries and invalid discovery requests have defined outcomes.
- **[P1]** As an administrator, verify source updates preserve metadata integrity and remove obsolete templates.
- **[P1]** As an administrator, verify documentation retrieval failures have a defined outcome and configuration survives supported upgrades.
- **[P1]** As an administrator, verify custom agent catalog sources can be generated from repositories.
- **[P1]** As an AI engineer, verify Dev Preview documentation accurately describes catalog capabilities and limits.
- **[P2]** As an AI engineer, verify documentation links and preview guidance remain usable.

**Out of Scope (Testing Scope Exclusions)**

The following items are explicitly Out of Scope for this test cycle and represent intentional exclusions.
No verification activities will be performed for these items, and any related issues found will not be classified as defects for this release.

- **Frontend and BFF interactions, including catalog telemetry**
  - *Rationale:* The backend Epic explicitly delegates these to separate UI work; parent deployment and interaction goals are not backend acceptance criteria.
  - *PM/Lead Agreement:* [Name/Date]

- **Agent deployment and execution**
  - *Rationale:* Dev Preview is browse-only; execution belongs to a later release.
  - *PM/Lead Agreement:* [Name/Date]

- **Agent versioning and lifecycle management**
  - *Rationale:* The Epic explicitly excludes these capabilities.
  - *PM/Lead Agreement:* [Name/Date]

- **End-user agent registration**
  - *Rationale:* Sources are administrator-configured in Dev Preview.
  - *PM/Lead Agreement:* [Name/Date]

- **Quantitative performance and scale certification**
  - *Rationale:* No targets are supplied. Add a dedicated acceptance cycle when product and engineering publish thresholds.
  - *PM/Lead Agreement:* [Name/Date]

**Test Limitations**

- **Remote repository availability affects documentation generation**
  - *Rationale:* README retrieval depends on GitHub availability and rate limits.
  - *Sign-off:* [Name/Date]

- **API error contracts require release confirmation**
  - *Rationale:* Invalid discovery and unavailable documentation behavior are not fully specified in the source issues.
  - *Sign-off:* [Name/Date]

#### **2. Test Strategy**

**Functional**

- [x] **Functional Testing** — Validates that the feature works according to specified requirements and user stories
  - *Details:* Agent discovery, details, filters, metadata, artifact inspection, and published documentation; Section III lists feature-specific outcomes.

- [x] **Automation Testing** — Confirms test automation plan is in place for CI and regression coverage (all tests are expected to be automated)
  - *Details:* Automate API checks and publication workflows using the existing repository conventions; documentation reference accuracy is checked against the release contract.

- [x] **Regression Testing** — Verifies that new changes do not break existing functionality
  - *Details:* Preserve existing model and MCP source listing, label validation, configuration parsing, and plugin startup. Existing-test duplicate search ran in both pinned checkouts and found no agent-specific assertions before this feature.

- [ ] **Self-Validation Testing** — Should any of the new tests be included in the self-validation test package?
  - *Details:* N/A — no new packaged self-diagnostic capability is specified.

**Non-Functional**

- [ ] **Performance Testing** — Validates feature performance meets requirements (latency, throughput, resource usage)
  - *Details:* N/A for this cycle — no measurable latency or throughput target is supplied; see Out of Scope.

- [ ] **Scale Testing** — Validates feature behavior under increased load and at production-like scale (e.g., large number of resources, nodes, or concurrent operations)
  - *Details:* N/A for this cycle — no published maximum or scale acceptance target is supplied; ordinary pagination remains functional coverage.

- [ ] **Security Testing** — Verifies security requirements, RBAC, authentication, authorization, and vulnerability scanning
  - *Details:* N/A as a separate strategy — no new RBAC or authentication boundary is specified. Existing platform access controls remain prerequisites.

- [ ] **Usability Testing** — Validates user experience and accessibility requirements
  - *Details:* N/A — frontend/BFF validation belongs to the separate AI Hub UI delivery; this plan validates backend metadata and documentation only.

- [ ] **Monitoring** — Does the feature require metrics and/or alerts?
  - *Details:* N/A — no new metrics or alerting acceptance contract is specified in this backend Epic; parent interaction telemetry belongs to the UI/deployment scope.

**Integration & Compatibility**

- [ ] **Compatibility Testing** — Ensures feature works across supported platforms, versions, and configurations
  - *Details:* N/A as a separate cross-version matrix — no agent client or cross-platform matrix is specified. Preserve existing model/MCP behavior under Regression Testing.

- [x] **Upgrade Testing** — Validates upgrade paths from previous versions, data migration, and configuration preservation
  - *Details:* Administrator source configuration and persisted template artifacts require preservation across a supported product upgrade.

- [x] **Dependencies** — Blocked by deliverables from other components/products. Identify what we need from other teams before we can test.
  - *Details:* AI Hub metadata collection delivery (RHOAIENG-70682, RHOAIENG-76086) must publish the agent data image, and operator delivery (RHOAIENG-70685) must expose its sources for backend end-to-end testing.

- [x] **Cross Integrations** — Does the feature affect other features or require testing by other teams? Identify the impact we cause.
  - *Details:* Validate curated metadata through installed catalog APIs and verify source updates change published artifacts. No runtime agent execution is included.

**Infrastructure**

- [ ] **Cloud Testing** — Does the feature require multi-cloud platform testing? Consider cloud-specific features.
  - *Details:* N/A — no provider-specific backend behavior is specified; use the configured OpenShift environment.

#### **3. Test Environment**

- **Cluster Topology:** Multi-node OpenShift with at least three worker nodes, per project configuration; needed for operator installation and upgrade coverage.

- **Platform & Product Version(s):** Product release: 3.5 GA RHOAI RELEASE, copied from Jira. Feature maturity remains Dev Preview per Epic description; confirm release-owner interpretation before testing. OpenShift version: release-supported version to be confirmed.

- **CPU Virtualization:** N/A — agent execution is not exercised; virtualization is not required by discovery.

- **Compute Resources:** Release-supported catalog and metadata-processing resources; record actual sizing before publication and upgrade tests.

- **Special Hardware:** No specialized accelerator required for browsing starter kits.

- **Storage:** Catalog database and persisted administrator source configuration; template update tests require retained state.

- **Network:** Repository access for metadata and README retrieval, image registry access for the metadata image, and access to the installed catalog API.

- **Required Operators:** Release-supported model registry operator with agent source support; delivery tracked by RHOAIENG-70685.

- **Platform:** OpenShift; no new provider-specific integration is identified.

- **Special Configurations:** Dev Preview enabled according to the approved release installation instructions; curated and administrator-managed sources, empty sources, multiple frameworks, images, and templates available as controlled test data.

#### **3.1. Testing Tools & Frameworks**

- **Test Framework:** Standard tooling — no additional tools required

- **CI/CD:** Standard tooling — no additional tools required

- **Other Tools:** No additional tools identified

#### **4. Entry Criteria**

The following conditions must be met before testing can begin:

- [ ] Requirements and design documents are **approved and merged**
- [ ] Test environment can be **set up and configured** (see Section II.3 - Test Environment)
- [ ] Development confirms released API paths and error contracts against the implementation.
- [ ] Release owner confirms Dev Preview maturity within 3.5 GA RHOAI RELEASE.
- [ ] Current agent implementation, metadata image, and operator source wiring are available for verification.
- [ ] Development agrees behavior for invalid discovery requests, unavailable README locations, rate limits, and invalid sources.
- [ ] A supported source-to-target upgrade path is identified with retained source and template data.
- [ ] QE owner and sign-off stakeholders are confirmed.

#### **5. Risks**

**Timeline/Schedule**

- **Mitigation:** No risk identified — No testing deadline or outstanding schedule dependency is specified by the closed Epic.

**Test Coverage**

- **Risk:** Custom catalog-source generation and release documentation have no checked-in automated coverage.
  - **Mitigation:** Add focused tests for repository scanning, generated schema compatibility, and documentation accuracy before release.
  - *Areas with reduced coverage:* Custom source generation and Dev Preview documentation
  - *Sign-off:* [Name/Date]

**Test Environment**

- **Risk:** Metadata image, operator source wiring, and catalog service versions may not be compatible.
  - **Mitigation:** Verify the released component set together before starting installation and upgrade validation.
  - *Missing resources or infrastructure:* Compatible metadata image, operator, and catalog service
  - *Sign-off:* [Name/Date]

**Untestable Aspects**

- **Risk:** Unspecified API error and remote documentation failure contracts may produce incorrect expected results.
  - **Mitigation:** Agree these contracts with development before execution; align negative scenarios to the approved contract.
  - *Alternative validation approach:* Negative response expectations; confirm before test execution
  - *Sign-off:* [Name/Date]

**Resource Constraints**

- **Mitigation:** No risk identified — No team capacity gap is recorded; confirm allocation at entry.

**Dependencies**

- **Risk:** Metadata collection, operator, and catalog service deliveries may land at different times.
  - **Mitigation:** Track component readiness through RHOAIENG-70682, RHOAIENG-70685, and RHOAIENG-76086 before end-to-end execution.
  - *Dependent teams or components:* AI Hub metadata collection, model registry operator, and catalog service
  - *Sign-off:* [Name/Date]

---

### **III. Test Scenarios & Traceability**

This section links requirements to test coverage, enabling reviewers to verify all requirements are tested.

#### **1. Requirements-to-Tests Mapping**

- **[RHOAIENG-70682]** — As an AI engineer, I want curated starter kits converted into complete catalog entries
  - *Test Scenario:* **TS-01**: [functional] [EXISTING_COVERAGE] Verify generated metadata completeness — covered by existing test `test_default_agents_have_required_fields`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (validates required fields and non-empty values)
    - *Downstream required:* no
    - *Covered by:* `test_default_agents_have_required_fields`
  - *Test Scenario:* **TS-02**: [integration] [EXISTING_COVERAGE] Verify repository documentation populates agent details — covered by existing test `test_agents_with_repository_url_have_readme`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates non-empty README for agents with repository URLs)
    - *Downstream required:* no
    - *Covered by:* `test_agents_with_repository_url_have_readme`
  - *Test Scenario:* **TS-03**: [integration] Verify offline generation produces a complete catalog without remote fetches
    - *Priority:* P2

- **[RHOAIENG-70683]** — As an AI engineer, I want to discover agents through a stable API
  - *Test Scenario:* **TS-04**: [functional] [EXISTING_COVERAGE] Verify agents are listed from configured sources — covered by existing test `test_agents_list_returns_non_empty_catalog`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (validates configured and LangGraph starter-kit agents)
    - *Downstream required:* no
    - *Covered by:* `test_agents_list_returns_non_empty_catalog`
  - *Test Scenario:* **TS-05**: [functional] [EXISTING_COVERAGE] Verify search and filters return matching agents — covered by existing test `test_filter_returns_matching_agents`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (covers equality, LIKE, ILIKE, IN, AND, OR, and nested expressions)
    - *Downstream required:* no
    - *Covered by:* `test_filter_returns_matching_agents`
  - *Test Scenario:* **TS-06**: [functional] [EXISTING_COVERAGE] Verify details expose documentation and configuration requirements — covered by existing test `test_get_agent_by_id`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (compares detail and list representations)
    - *Downstream required:* no
    - *Covered by:* `test_get_agent_by_id`
  - *Test Scenario:* **TS-07**: [functional] [EXISTING_COVERAGE] Verify filter options reflect available agent metadata — covered by existing test `test_filter_options_returns_expected_fields`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates expected filter fields)
    - *Downstream required:* no
    - *Covered by:* `test_filter_options_returns_expected_fields`
  - *Test Scenario:* **TS-08**: [integration] [EXISTING_COVERAGE] Verify empty agent sources allow successful catalog startup — covered by existing catalog startup tests
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates startup with empty model, MCP, agent, and skill sources)
    - *Downstream required:* no
    - *Covered by:* `catalog startup tests`

- **[RHOAIENG-70684]** — As an AI engineer, I want sample and production catalog data loaded consistently
  - *Test Scenario:* **TS-09**: [integration] [EXISTING_COVERAGE] Verify catalog service loads agents from YAML sources — covered by existing test `test_yaml_agents_match_api_response`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (compares YAML and API field values)
    - *Downstream required:* no
    - *Covered by:* `test_yaml_agents_match_api_response`
  - *Test Scenario:* **TS-10**: [functional] [EXISTING_COVERAGE] Verify source selection returns only matching agents — covered by existing test `test_filter_valid_source_label`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (compares returned names with expected source membership)
    - *Downstream required:* no
    - *Covered by:* `test_filter_valid_source_label`
  - *Test Scenario:* **TS-11**: [e2e] Verify installed catalog exposes sample agents
    - *Priority:* P0

- **[RHOAIENG-70685]** — As an administrator, I want the operator to deploy and configure agent catalog sources
  - *Test Scenario:* **TS-12**: [integration] [EXISTING_COVERAGE] Verify operator creates agent source configuration — covered by existing test `test_agent_catalog_configmap_exists`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (validates ConfigMap existence and empty user source list)
    - *Downstream required:* no
    - *Covered by:* `test_agent_catalog_configmap_exists`
  - *Test Scenario:* **TS-13**: [integration] [EXISTING_COVERAGE] Verify deployment mounts and receives agent source path — covered by existing tests `test_catalog_deployment_has_agent_sources_volume_mount` and `test_catalog_deployment_has_agent_catalogs_path_arg`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in tests — full (validate volume mount and startup argument)
    - *Downstream required:* no
    - *Covered by:* `test_catalog_deployment_has_agent_sources_volume_mount`
  - *Test Scenario:* **TS-14**: [e2e] [EXISTING_COVERAGE] Verify default source is available after installation — covered by existing test `test_default_agent_source_available`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (validates default source availability)
    - *Downstream required:* no
    - *Covered by:* `test_default_agent_source_available`

- **[RHOAIENG-75429]** — As an AI engineer, I want to inspect available agent artifacts
  - *Test Scenario:* **TS-15**: [functional] [EXISTING_COVERAGE] Verify artifact listings distinguish images and deployment templates — covered by existing test `test_agent_artifact_types`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (separates inline image and persisted template artifact behavior)
    - *Downstream required:* no
    - *Covered by:* `test_agent_artifact_types`
  - *Test Scenario:* **TS-16**: [functional] [EXISTING_COVERAGE] Verify artifact filtering and pagination return the selected subset — covered by existing tests `test_list_artifacts` and `test_artifacts_pagination`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in tests — full (validate type filtering and continuation)
    - *Downstream required:* no
    - *Covered by:* `test_list_artifacts`
  - *Test Scenario:* **TS-17**: [functional] [EXISTING_COVERAGE] Verify template artifacts expose names and content — covered by existing test `test_template_artifacts_have_content_and_names`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates names and non-empty content)
    - *Downstream required:* no
    - *Covered by:* `test_template_artifacts_have_content_and_names`
  - *Test Scenario:* **TS-18**: [functional] [EXISTING_COVERAGE] Verify unknown agents return not-found for artifact requests — covered by existing test `TestGetAgentArtifacts_AgentNotFound`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates not-found mapping)
    - *Downstream required:* no
    - *Covered by:* `TestGetAgentArtifacts_AgentNotFound`

- **[RHOAIENG-76086]** — As an AI engineer, I want starter-kit presentation and templates preserved
  - *Test Scenario:* **TS-19**: [integration] [EXISTING_COVERAGE] Verify published agents preserve source labels and logos — covered by existing test `test_agent_labels_match_yaml`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates label propagation)
    - *Downstream required:* no
    - *Covered by:* `test_agent_labels_match_yaml`
  - *Test Scenario:* **TS-20**: [integration] [EXISTING_COVERAGE] Verify shipped catalog includes agent template data — covered by existing test `test_agents_have_template_artifacts`
    - *Priority:* P0
    - *Upstream coverage:* local checked-in test — full (validates template artifact presence)
    - *Downstream required:* no
    - *Covered by:* `test_agents_have_template_artifacts`
  - *Test Scenario:* **TS-21**: [integration] [EXISTING_COVERAGE] Verify logo data remains valid for display — covered by existing test `test_agent_template_logo_is_valid_svg_data_uri`
    - *Priority:* P2
    - *Upstream coverage:* local checked-in test — full (validates SVG data URI format)
    - *Downstream required:* no
    - *Covered by:* `test_agent_template_logo_is_valid_svg_data_uri`

- **[RHOAIENG-76111]** — As an administrator, I want source updates to remove obsolete agent templates
  - *Test Scenario:* **TS-22**: [integration] [EXISTING_COVERAGE] Verify changed templates replace previously published templates — covered by existing test `TestAgentLoaderTemplateSaveFlow_ReloadReplacesTemplates`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (verifies upsert and stale-template deletion)
    - *Downstream required:* no
    - *Covered by:* `TestAgentLoaderTemplateSaveFlow_ReloadReplacesTemplates`
  - *Test Scenario:* **TS-23**: [integration] [EXISTING_COVERAGE] Verify removing all templates leaves no obsolete artifacts — covered by existing test `TestAgentLoaderTemplateSaveFlow_ReloadWithNoTemplatesRemovesAll`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (verifies orphan cleanup for zero-template reloads)
    - *Downstream required:* no
    - *Covered by:* `TestAgentLoaderTemplateSaveFlow_ReloadWithNoTemplatesRemovesAll`

- **[RHOAIENG-76762]** — As an administrator, I want documentation found at supported repository locations
  - *Test Scenario:* **TS-24**: [integration] Verify documentation loads from explicit and default locations
    - *Priority:* P1
  - *Test Scenario:* **TS-25**: [integration] Verify unavailable README overrides return defined errors
    - *Priority:* P2

- **[RHOAIENG-76987]** — As an AI engineer, I want readable documentation outside its repository
  - *Test Scenario:* **TS-26**: [functional] [EXISTING_COVERAGE] Verify relative documentation links resolve to repository content — covered by existing test `test_agent_readmes_have_no_relative_references`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (rejects relative markdown links, markdown images, and HTML images)
    - *Downstream required:* no
    - *Covered by:* `test_agent_readmes_have_no_relative_references`
  - *Test Scenario:* **TS-27**: [functional] Verify absolute documentation links remain unchanged
    - *Priority:* P2

- **[RHOAIENG-76364]** — As an administrator, I want to generate a custom agent catalog source from a repository
  - *Test Scenario:* **TS-28**: [integration] Verify repository scanning discovers convention-based agents
    - *Priority:* P1
  - *Test Scenario:* **TS-29**: [integration] Verify heuristic discovery finds non-standard agent definitions
    - *Priority:* P1
  - *Test Scenario:* **TS-30**: [integration] Verify generated catalog and deployment artifacts match the runtime schema
    - *Priority:* P0
  - *Test Scenario:* **TS-31**: [e2e] Verify a generated custom source loads into the catalog service
    - *Priority:* P1

- **[RHOAIENG-70686]** — As an AI engineer, I want accurate instructions for the Dev Preview catalog
  - *Test Scenario:* **TS-32**: [functional] Verify documentation describes discovery and administrator source configuration
    - *Priority:* P1
  - *Test Scenario:* **TS-33**: [functional] Verify API reference and preview limitations match released behavior
    - *Priority:* P2

- **[RHOAIENG-70685]** — As an administrator, I want agent source configuration preserved across supported upgrades
  - *Test Scenario:* **TS-34**: [e2e] Verify source configuration survives a supported product upgrade
    - *Priority:* P1

- **[RHOAIENG-70683]** — As an AI engineer, I want invalid discovery requests rejected predictably
  - *Test Scenario:* **TS-35**: [functional] [EXISTING_COVERAGE] Verify invalid discovery requests return defined errors — covered by existing test `test_invalid_request_returns_error`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates invalid request error handling)
    - *Downstream required:* no
    - *Covered by:* `test_invalid_request_returns_error`
  - *Test Scenario:* **TS-36**: [functional] [EXISTING_COVERAGE] Verify nonexistent source labels return empty results — covered by existing test `test_filter_nonexistent_label_returns_empty`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates empty result for unknown labels)
    - *Downstream required:* no
    - *Covered by:* `test_filter_nonexistent_label_returns_empty`

- **[RHOAIENG-75429]** — As an AI engineer, I want invalid artifact requests rejected predictably
  - *Test Scenario:* **TS-37**: [functional] [EXISTING_COVERAGE] Verify invalid artifact types return errors — covered by existing test `test_artifacts_invalid_artifact_type`
    - *Priority:* P1
    - *Upstream coverage:* local checked-in test — full (validates invalid artifact type rejection)
    - *Downstream required:* no
    - *Covered by:* `test_artifacts_invalid_artifact_type`
  - *Test Scenario:* **TS-38**: [functional] [EXISTING_COVERAGE] Verify agents without artifacts return empty collections — covered by existing test `TestGetAgentArtifacts_EmptyResultReturnsEmptySliceNotNil`
    - *Priority:* P2
    - *Upstream coverage:* local checked-in test — full (validates empty, non-nil artifact collections)
    - *Downstream required:* no
    - *Covered by:* `TestGetAgentArtifacts_EmptyResultReturnsEmptySliceNotNil`

- **[RHOAIENG-76364]** — As an administrator, I want invalid custom sources rejected predictably
  - *Test Scenario:* **TS-39**: [integration] Verify malformed custom source YAML is rejected
    - *Priority:* P1
  - *Test Scenario:* **TS-40**: [integration] Verify custom sources missing required fields are rejected
    - *Priority:* P1
  - *Test Scenario:* **TS-41**: [integration] Verify unsupported repository paths return diagnosable errors
    - *Priority:* P2

---

### **IV. Sign-off and Approval**

This Software Test Plan requires approval from the following stakeholders:

- **Reviewers:**
  - QE: [Name / @github-handle]
  - Development: [Name]
- **Approvers:**
  - QE Lead: [Name / @github-handle]
  - Dev Lead: [Name]
  - Product Manager: [Name / @github-handle]
