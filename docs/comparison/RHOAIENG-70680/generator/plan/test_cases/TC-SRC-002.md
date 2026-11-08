---
test_case_id: TC-SRC-002
source_key: RHOAIENG-70680
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-07-07"
---
# TC-SRC-002: Custom agent source added via ConfigMap patch loads agents

**Objective**: Verify that patching the `model-catalog-sources` ConfigMap
with a new agent catalog source causes the agents from that source to
appear in the catalog API.

**Preconditions**:

- `model-catalog-sources` ConfigMap exists in the RHOAI namespace

**Test Steps**:

1. Prepare a custom agent catalog YAML file with 7 agents across
   different frameworks
2. Patch the `model-catalog-sources` ConfigMap to add the custom agent
   catalog source
3. Wait for the catalog service to reload sources
4. Send GET request to `/api/agent_catalog/v1alpha1/agents` with
   `sourceLabel=custom-agents`
5. Verify the custom agents appear in the response

**Expected Results**:

- Response status is HTTP 200
- Response contains agents from the custom source
- Agent names, frameworks, and metadata match the custom catalog YAML
- The custom source appears in
  `/api/model_catalog/v1alpha1/sources?assetType=agents`

**Test Data**:

```yaml
agent_catalogs:
  - name: custom-agents
    label: custom-agents
    enabled: true
    url: /opt/app-root/src/catalogs/custom-agents-catalog.yaml
```

**Notes**: To be filled later in the process.
