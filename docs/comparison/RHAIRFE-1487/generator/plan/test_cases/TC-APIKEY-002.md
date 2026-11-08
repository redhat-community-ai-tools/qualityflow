---
test_case_id: TC-APIKEY-002
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-APIKEY-002: POST /internal/v1/api-keys/validate — returns ValidationResult with tenant, userID, modelRef

**Objective**: Verify that validating a valid API key returns
a `ValidationResult` containing the correct `tenant`,
`userID`, and `modelRef` fields.

**Preconditions**:

- A valid API key for `tenant-a` has been created (see TC-APIKEY-001)
- maas-api internal endpoint is accessible

**Test Steps**:

1. Send `POST /internal/v1/api-keys/validate` with the tenant-a API key
2. Parse the response body
3. Verify `tenant`, `userID`, and `modelRef` fields are present and correct

**Test Data**:

```bash
curl -X POST https://<maas-api>/internal/v1/api-keys/validate \
  -H "Content-Type: application/json" \
  -d '{"apiKey": "<tenant-a-api-key>"}'
```

**Expected Response**:

```json
{
  "tenant": "tenant-a",
  "userID": "user@example.com",
  "modelRef": "granite-7b"
}
```

**Expected Results**:

- Response HTTP status is `200 OK`
- Response body contains `"tenant": "tenant-a"`
- Response body contains a non-empty `userID` field
- Response body contains a non-empty `modelRef` field

**Notes**: To be filled later in the process.
