---
test_case_id: TC-SEC-002
source_key: RHAISTRAT-1245
priority: P2
status: Draft
automation_status: Complete
automation_file: tests/ogx/gemini/test_security.py
automation_function: TestGeminiSecurity::test_tls_enforced_for_gemini_egress
last_updated: "2026-06-05"
upgrade_phase: post
---
# TC-SEC-002: TLS 1.2+ enforced for Gemini API egress

**Objective**: Verify that outbound connections from the OGX
distribution to the Gemini API enforce TLS 1.2 or higher.

**Preconditions**:

- OGX distribution deployed with `remote::gemini` provider
  active
- Valid `GEMINI_API_KEY` configured
- Network inspection tooling available (e.g., `tcpdump`,
  pod-level packet capture, or proxy logs)

**Test Steps**:

1. Send a chat completion request through the `remote::gemini`
   provider
2. Capture the outbound TLS handshake from the OGX pod to
   the Gemini API endpoint
3. Inspect the negotiated TLS version

**Expected Results**:

- The TLS handshake negotiates TLS 1.2 or TLS 1.3
- No connections use TLS 1.1 or lower
- The connection to the Gemini API endpoint uses a valid
  certificate chain

**Notes**: To be filled later in the process.
