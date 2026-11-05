---
test_case_id: TC-NEG-001
source_key: RHAISTRAT-2277
objectives: [1, 10]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-NEG-001: OGX port 8321 is unreachable from outside the cluster and unauthenticated calls are rejected

**Objective**: Verify that the OGX delegation port is not reachable from outside the cluster and
that Praxis rejects unauthenticated requests at the public boundary.

**Preconditions**:

- RHOAI 3.6 cluster with Praxis public and OGX internal-only
- A NetworkPolicy restricting OGX to accept traffic only from Praxis
- A scan host outside the cluster network, with no in-cluster credentials
- A pod inside the cluster from which in-cluster reachability can be contrasted

**Test Steps**:

1. From the external scan host, attempt a TCP connection to port 8321 on every externally resolvable
   address associated with the cluster, including the Gateway hostname and any exposed node
   addresses.
2. From the external scan host, attempt an HTTP request to `:8321/v1/responses`.
3. From a pod inside the cluster that is not Praxis, attempt to reach OGX on port 8321.
4. From the Praxis pod, attempt to reach OGX on port 8321 — this is the permitted path and confirms
   the policy is restrictive rather than simply blocking everything.
5. Send `POST /v1/responses` to the public Gateway with no `Authorization` header.
6. Send `POST /v1/responses` to the public Gateway with a malformed bearer token.

**Expected Results**:

- Every external connection attempt to port 8321 is refused, filtered, or times out — no TCP
  handshake completes
- The external HTTP request to port 8321 does not return any OGX API response
- The non-Praxis in-cluster pod is denied by NetworkPolicy
- The Praxis pod reaches OGX on port 8321 successfully, proving the policy permits the intended path
- The unauthenticated request returns HTTP 401, and the response body does not leak internal
  hostnames, pod names, or stack traces
- The malformed-token request returns HTTP 401

**Validation**:

- `oc get networkpolicy -n <ogx-namespace> -o yaml` shows an ingress rule whose peer selector
  matches only the Praxis workload

**Notes**: To be filled later in the process.
