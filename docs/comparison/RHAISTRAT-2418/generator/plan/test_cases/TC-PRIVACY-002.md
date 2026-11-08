---
test_case_id: TC-PRIVACY-002
source_key: RHAISTRAT-2418
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-PRIVACY-002: Verify dashboard does not expose user-identifying data

**Objective**: Confirm that the Perses dashboard variable filter
and panel queries do not expose user-identifying information.

**Preconditions**:

- Dashboard deployed (TC-DASH-001 passed)
- Auth traffic generated using synthetic test identities only
  (e.g., test-only API keys or throwaway OIDC tokens from a
  test IdP). Do not use production or real user credentials.
  Verify no real credentials appear in test logs, traces,
  audit records, or test artifacts.

**Test Steps**:

1. Query the `authconfig` variable values (the only user-facing
   filter):

   ```bash
   curl -s "https://<prometheus-route>/api/v1/label/\
     authconfig/values" | jq '.data'
   ```

2. Verify all values are SHA-256 hashes (64-char hex strings),
   not user names, email addresses, or other PII.
3. Review all 8 dashboard panel PromQL queries (from Section 4.1)
   and verify none reference user-identifying labels.
4. Verify dashboard panel series names use `{{authconfig}}` and
   `{{status}}` template variables — not user-identifying fields.

**Expected Results**:

- Dashboard variable filter shows only SHA-256 hashes as
  selectable values
- No user names, email addresses, or organization identifiers
  appear in filter options
- Panel series names display hash values and gRPC status codes
  only
- No panel query references `enduser.id`, `user`, `cost_center`,
  `organization_id`, or `subscription`

**Notes**: To be filled later in the process.
