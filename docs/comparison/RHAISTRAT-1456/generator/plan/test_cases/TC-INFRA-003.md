---
test_case_id: TC-INFRA-003
source_key: RHAISTRAT-1456
priority: P2
status: Draft
automation_status: Not Started
last_updated: "2026-06-12"
---
# TC-INFRA-003: NetworkPolicy for pod-to-pod communication

**Objective**: Validate that NetworkPolicies correctly allow required
communication paths between OGX, vLLM, and PostgreSQL pods
while blocking unauthorized access from other pods.

**Preconditions**:

- OGX deployed on port 8321
- vLLM serving on port 8000
- PostgreSQL on port 5432
- NetworkPolicies applied for all three services
- A test pod deployed in the same namespace for negative testing
- Test inputs are parameterized and validated before execution:
  `NAMESPACE` matches `^[a-z0-9-]+$`, `TIMEOUT_SECONDS` matches
  `^[0-9]+$`, and resource names for OGX, vLLM, PostgreSQL, and the
  test pod resolve in the target namespace

**Test Steps**:

1. Validate the discovered resource names and confirm the
   NetworkPolicies restrict ingress to vLLM (port 8000) and
   PostgreSQL (port 5432) to only allow traffic from OGX pods.
2. From the OGX pod, verify vLLM DNS resolution and HTTP 200 health:

   ```bash
   oc exec -n "${NAMESPACE}" deploy/"${OGX_DEPLOYMENT}" -- \
     getent hosts "${VLLM_SERVICE}"
   oc exec -n "${NAMESPACE}" deploy/"${OGX_DEPLOYMENT}" -- \
     curl -fsS -o /dev/null -w "%{http_code}" \
     "http://${VLLM_SERVICE}:8000/health" | grep -qx 200
   ```

3. From the OGX pod, verify PostgreSQL DNS resolution and readiness:

   ```bash
   oc exec -n "${NAMESPACE}" deploy/"${OGX_DEPLOYMENT}" -- \
     getent hosts "${POSTGRES_SERVICE}"
   oc exec -n "${NAMESPACE}" deploy/"${OGX_DEPLOYMENT}" -- \
     pg_isready -h "${POSTGRES_SERVICE}" -p 5432
   ```

4. From a test pod (not OGX), attempt to reach vLLM directly within
   the configured timeout window after confirming DNS resolution:

   ```bash
   oc exec -n "${NAMESPACE}" deploy/"${TEST_DEPLOYMENT}" -- \
     getent hosts "${VLLM_SERVICE}"
   oc exec -n "${NAMESPACE}" deploy/"${TEST_DEPLOYMENT}" -- \
     curl -fsS --connect-timeout "${TIMEOUT_SECONDS}" \
     "http://${VLLM_SERVICE}:8000/health"
   ```

5. From the test pod, attempt to reach PostgreSQL directly:

   ```bash
   oc exec -n "${NAMESPACE}" deploy/"${TEST_DEPLOYMENT}" -- \
     getent hosts "${POSTGRES_SERVICE}"
   oc exec -n "${NAMESPACE}" deploy/"${TEST_DEPLOYMENT}" -- \
     pg_isready -h "${POSTGRES_SERVICE}" -p 5432 \
     -t "${TIMEOUT_SECONDS}"
   ```

**Expected Results**:

- OGX → vLLM (port 8000): connection succeeds, HTTP 200
- OGX → PostgreSQL (port 5432): connection succeeds,
  `pg_isready` exits 0 and reports accepting connections
- test-pod → vLLM (port 8000): connection refused or timeout
  within the configured timeout window; DNS resolution succeeds first,
  and the captured curl exit code distinguishes refused (7), timeout
  (28), and name resolution failure (6)
- test-pod → PostgreSQL (port 5432): connection refused or
  timeout within the configured timeout window; `pg_isready` output and
  exit code distinguish rejecting connections (1), no response (2), and
  unknown state (3)

**Notes**: To be filled later in the process.
