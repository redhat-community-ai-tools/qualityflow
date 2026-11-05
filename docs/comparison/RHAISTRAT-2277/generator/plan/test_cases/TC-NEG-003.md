---
test_case_id: TC-NEG-003
source_key: RHAISTRAT-2277
objectives: [8, 10]
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-08-11"
---
# TC-NEG-003: Tenant isolation holds across the Praxis-to-OGX delegation boundary

**Objective**: Verify that a request carrying tenant A credentials cannot read or modify tenant B
resources through the delegation path, and that the internal hop does not bypass OGX's own
authentication.

**Preconditions**:

- RHOAI 3.6 cluster with Praxis delegating to OGX
- Two tenants, A and B, with distinct credentials and separate resources
- Tenant B owns at least one file, one vector store, and one conversation, with their IDs recorded
- Tenant A owns equivalent resources, so a positive control is available

**Test Steps**:

1. As tenant A, call `GET /v1/files/{tenant_A_file_id}` to establish the positive control.
2. As tenant A, call `GET /v1/files/{tenant_B_file_id}`.
3. As tenant A, call `GET /v1/vector_stores/{tenant_B_vs_id}`.
4. As tenant A, send `POST /v1/responses` with a `file_search` tool referencing tenant B's vector
   store ID — this exercises isolation specifically through the delegation path rather than at the
   public boundary alone.
5. As tenant A, attempt to retrieve tenant B's conversation by ID.
6. Inspect OGX pod logs for the delegated calls and confirm each carried tenant context rather than
   a shared or elevated identity.

**Expected Results**:

- Step 1 returns HTTP 200, confirming tenant A's own access works and the test is not passing
  because all requests fail
- Steps 2, 3, and 5 return HTTP 404 or 403, and never HTTP 200
- Step 4 does not return content derived from tenant B's documents: the response contains no
  citation whose `file_id` belongs to tenant B
- No error body discloses tenant B resource metadata such as filenames, sizes, or creation times
- OGX logs show the delegated requests carrying tenant-scoped identity, not an unscoped internal
  identity that would bypass OGX's own ACL enforcement

**Notes**: To be filled later in the process.
