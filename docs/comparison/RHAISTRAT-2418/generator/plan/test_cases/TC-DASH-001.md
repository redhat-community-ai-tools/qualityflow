---
test_case_id: TC-DASH-001
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-DASH-001: Verify Perses dashboard CR deploys and is accessible

**Objective**: Confirm that the `dashboard-4-maas-auth-decisions-admin`
PersesDashboard CR deploys successfully and the dashboard is accessible
via the Perses API.

**Preconditions**:

- Perses CRDs (`perses.dev/v1alpha1`) installed
- opendatahub-operator deployed with monitoring service controller
- Dashboard kustomize overlay applied

**Test Steps**:

1. Verify the PersesDashboard CR exists:

   ```bash
   kubectl get persesdashboard \
     dashboard-4-maas-auth-decisions-admin -n opendatahub
   ```

2. Verify the CR is in a ready/synced state (no error conditions).
3. Query the Perses API to confirm the dashboard is accessible:

   ```bash
   curl -s "https://<perses-route>/api/v1/dashboards/\
     dashboard-4-maas-auth-decisions-admin" | jq '.spec.display'
   ```

4. Verify the dashboard display name is "Auth decisions".

**Expected Results**:

- `persesdashboard/dashboard-4-maas-auth-decisions-admin` exists
  in `opendatahub` namespace
- CR has no error conditions in its status
- Perses API returns HTTP 200 for the dashboard
- Dashboard display name is "Auth decisions"
- Dashboard contains panels: `totalDecisionRate`,
  `overallDenyRate`, `p95Latency`, `activePolicies`,
  `decisionsByStatus`, `decisionsByPolicy`, `denyRatioByPolicy`,
  `latencyByPolicy`

**Notes**: To be filled later in the process.
