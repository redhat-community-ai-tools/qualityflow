---
test_case_id: TC-PRIVACY-001
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-PRIVACY-001: Verify no user-identifying labels in metrics

**Objective**: Confirm that auth decision metrics do not contain
any user-identifying information in their Prometheus label schema.

**Preconditions**:

- Auth traffic generated with real user credentials

**Test Steps**:

1. Query `auth_server_authconfig_response_status` and list all
   label names:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/query?query=\
     auth_server_authconfig_response_status" | \
     jq '[.data.result[0].metric | keys[]] | sort'
   ```

2. Verify the label set contains ONLY: `__name__`, `authconfig`,
   `namespace`, `status`, and standard Prometheus target labels
   (`instance`, `job`, etc.).
3. Verify NONE of the following labels are present:
   `enduser.id`, `user`, `cost_center`, `organization_id`,
   `subscription`.
4. Repeat for `auth_server_authconfig_duration_seconds`.

**Expected Results**:

- Label set is limited to `{authconfig, namespace, status}` plus
  standard Prometheus scrape labels
- No `enduser.id`, `user`, `cost_center`, `organization_id`, or
  `subscription` labels present
- No other labels containing personally identifiable information

**Notes**: To be filled later in the process.
