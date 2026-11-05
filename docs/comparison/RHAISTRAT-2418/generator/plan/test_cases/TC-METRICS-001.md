---
test_case_id: TC-METRICS-001
source_key: RHAISTRAT-2418
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
---
# TC-METRICS-001: Verify auth decision counter metric with correct labels

**Objective**: Confirm that `auth_server_authconfig_response_status`
counter is exposed on `/server-metrics` with the expected label schema
`{authconfig, namespace, status}` after generating auth traffic.

**Preconditions**:

- RHOAI 3.6-ea1 installed on OpenShift 4.16+ cluster
- Authorino running in `kuadrant-system` or `rh-connectivity-link`
- At least one LLMInferenceService or MaaS model deployed
- ServiceMonitor `authorino-server-metrics-servicemonitor` applied

**Test Steps**:

1. Generate auth traffic by calling Authorino gRPC Check:

   ```bash
   grpcurl -plaintext -d '{"attributes": {"request": {"http": \
     {"method": "GET", "path": "/test"}}}}' \
     <authorino-service>:50051 \
     envoy.service.auth.v3.Authorization/Check
   ```

   Repeat 10 times to ensure metrics are initialized.
2. Query the `/server-metrics` endpoint directly:

   ```bash
   kubectl exec -n <authorino-namespace> <authorino-pod> -- \
     curl -s http://localhost:8080/server-metrics
   ```

3. Search the output for `auth_server_authconfig_response_status`.
4. Verify the metric has labels `authconfig`, `namespace`, and
   `status`.
5. Verify `status` label values are gRPC code names (e.g., `OK`,
   `UNAUTHENTICATED`, `PERMISSION_DENIED`, `NOT_FOUND`).

**Expected Results**:

- `auth_server_authconfig_response_status` appears in the
  `/server-metrics` output
- Each metric line contains `authconfig="<sha256-hash>"`,
  `namespace="<authorino-namespace>"`, and `status="<gRPC-code>"`
- Counter values are non-zero after generating traffic
- No unexpected labels (e.g., `enduser.id`, `user`) are present

**Notes**: To be filled later in the process.
