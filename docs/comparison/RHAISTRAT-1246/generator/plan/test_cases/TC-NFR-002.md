---
test_case_id: TC-NFR-002
source_key: RHAISTRAT-1246
objectives: [6]
priority: P1
status: Draft
automation_status: Not Started
last_updated: "2026-08-14"
upgrade_phase: both
---

# TC-NFR-002: TLS 1.2+ enforced for egress to Anthropic API

**Objective**: Verify that TLS 1.2 or higher is enforced for all
egress traffic from the OGX distribution to Anthropic API endpoints.

**Preconditions**:

- RHOAI 3.5 cluster with `remote::anthropic` provider activated
- Network tools available for TLS inspection

**Test Steps**:

1. Send a successful inference request to confirm connectivity
2. Inspect the TLS connection to the Anthropic API endpoint using
   `openssl s_client` or equivalent from the cluster network:

   ```bash
   openssl s_client -connect <anthropic-api-host>:443 \
     -tls1_2 < /dev/null 2>&1 | grep "Protocol"
   ```

3. Verify the connection uses TLS 1.2 or TLS 1.3
4. Verify the OGX distribution does not downgrade to TLS 1.1 or
   lower for Anthropic API calls

**Expected Results**:

- TLS connection to Anthropic API uses protocol version 1.2 or 1.3
- No TLS 1.0 or 1.1 connections are established

**Notes**: To be filled later in the process.
