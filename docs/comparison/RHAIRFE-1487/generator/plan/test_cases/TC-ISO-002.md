---
test_case_id: TC-ISO-002
source_key: RHAIRFE-1487
priority: P0
status: Draft
automation_status: Not Started
last_updated: "2026-05-18"
---
# TC-ISO-002: Tenant A API key cannot authenticate on Tenant B's resources

**Objective**: Verify that an API key issued for tenant-a
cannot be used to authenticate and access tenant-b's
resources.

**Preconditions**:

- API key `key-a` created for `tenant-a`
- Tenant `tenant-b` is provisioned and has a model endpoint

**Test Steps**:

1. Use `key-a` to send an inference request to tenant-b's model endpoint
2. Check the HTTP response status

**Test Data**:

```bash
curl -X POST https://<gateway>/tenant-b/v1/chat/completions \
  -H "Authorization: Bearer <key-a>" \
  -H "Content-Type: application/json" \
  -d '{"model": "granite-7b", "messages": [{"role": "user", "content": "hello"}]}'
```

**Expected Results**:

- Response HTTP status is `401 Unauthorized`
- Response body does not contain any model output
- No tenant-b resources are modified or accessed

**Notes**: To be filled later in the process.
