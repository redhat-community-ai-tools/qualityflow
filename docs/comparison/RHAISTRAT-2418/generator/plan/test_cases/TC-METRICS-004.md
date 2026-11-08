---
test_case_id: TC-METRICS-004
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-METRICS-004: Verify authconfig label values are SHA-256 hashes

**Objective**: Confirm that the `authconfig` label in auth decision
metrics contains SHA-256 hash values that correspond to actual
AuthConfig resource names.

**Preconditions**:

- Auth traffic previously generated (TC-METRICS-001 preconditions met)

**Test Steps**:

1. List AuthConfig resources in the Authorino namespace:

   ```bash
   kubectl get authconfig -n <authorino-namespace> \
     -o jsonpath='{.items[*].metadata.name}'
   ```

2. Query Prometheus for distinct `authconfig` label values:

   ```bash
   curl -s "https://<prometheus-route>/api/v1/label/authconfig/values" \
     | jq '.data[]'
   ```

3. Compare the AuthConfig resource names from step 1 with the
   `authconfig` label values from step 2.
4. Verify each `authconfig` value is a 64-character hexadecimal
   string (SHA-256 format).

**Expected Results**:

- Each `authconfig` label value is a 64-character lowercase
  hexadecimal string matching the regex `^[a-f0-9]{64}$`
- The set of `authconfig` values from Prometheus matches the
  set of AuthConfig resource names from step 1
- No plain-text policy names appear as `authconfig` label values

**Notes**: To be filled later in the process.
