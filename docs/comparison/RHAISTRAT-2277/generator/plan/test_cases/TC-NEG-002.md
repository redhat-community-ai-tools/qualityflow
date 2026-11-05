---
test_case_id: TC-NEG-002
source_key: RHAISTRAT-2277
objectives: [6, 12]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-NEG-002: Praxis returns an OpenAI-compatible error when OGX is unreachable

**Objective**: Verify that when Praxis cannot reach OGX for a state-dependent operation, it returns
a structured OpenAI-compatible error rather than hanging or surfacing a platform-internal error.

**Preconditions**:

- RHOAI 3.6 cluster with Praxis delegating state operations to OGX
- Ability to make OGX unreachable — scaling the OGX deployment to zero replicas, or applying a
  NetworkPolicy that blocks Praxis-to-OGX traffic
- A known-good file ID and vector store ID that resolve successfully while OGX is up
- A client timeout set well above the expected response time, so a hang is observable as a hang
  rather than as a client-side timeout

**Test Steps**:

1. While OGX is healthy, call `GET /v1/files/{known_id}` and record the successful baseline response
   and its latency.
2. Make OGX unreachable and wait until its endpoints are removed from the Service.
3. Call `GET /v1/files/{known_id}` again, recording the full response and the elapsed time.
4. Call `POST /v1/responses` with a `file_search` tool referencing the known vector store, which
   requires delegation, and record the response.
5. Validate both error bodies against the OpenAI error schema, checking for `type`, `message`, and
   `code`.
6. Restore OGX and confirm the original request succeeds again.

**Expected Results**:

- Both requests made while OGX is unreachable return HTTP 503
- Each error body contains an `error` object with non-empty `type`, `message`, and `code` fields
- Neither response hangs: each returns within the client timeout, and elapsed time is bounded rather
  than open-ended
- No response body contains a raw stack trace, a Go or Python exception string, an internal pod
  name, or a cluster-internal hostname
- After OGX is restored, `GET /v1/files/{known_id}` returns HTTP 200 with the same body as the
  step 1 baseline

**Expected Response**:

```json
{
  "error": {
    "type": "service_unavailable",
    "message": "The upstream service is temporarily unavailable. Please retry.",
    "code": "backend_unavailable",
    "param": null
  }
}
```

**Notes**: To be filled later in the process.
